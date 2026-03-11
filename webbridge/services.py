# -*- coding: UTF-8 -*-

"""Service manager for WebBridge.

Discovers, launches and manages background Python services that
interact with the Moonstone notebook via the WebBridge REST API.

Each service runs as an isolated subprocess with its own virtualenv.
Communication happens exclusively through HTTP — services are
first-class API clients, just like browser-based applets.
"""

import atexit
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time

logger = logging.getLogger("moonstone.webbridge")

# How long to wait for graceful shutdown before SIGKILL
_SHUTDOWN_TIMEOUT = 8

# Maximum log file size before rotation (512 KB)
_MAX_LOG_SIZE = 512 * 1024

# Health-check interval (seconds)
_HEALTH_CHECK_INTERVAL = 15


class ServiceStatus:
    """Possible service states."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class Service:
    """Represents a discovered background service."""

    def __init__(self, name, path, manifest=None, source_info=None):
        self.name = name
        self.path = path
        self.manifest = manifest or {}
        self.source_info = source_info

        # Runtime state
        self._process = None  # subprocess.Popen
        self._status = ServiceStatus.STOPPED
        self._error_msg = ""
        self._start_time = None
        self._restart_count = 0
        self._log_path = os.path.join(path, "_data", "service.log")

    # ---- Properties from manifest ----

    @property
    def label(self):
        return self.manifest.get("name", self.name)

    @property
    def description(self):
        return self.manifest.get("description", "")

    @property
    def icon(self):
        return self.manifest.get("icon", "⚙️")

    @property
    def version(self):
        return self.manifest.get("version", "0.0.0")

    @property
    def author(self):
        return self.manifest.get("author", "")

    @property
    def entry_point(self):
        return self.manifest.get("entry", "service.py")

    @property
    def python_cmd(self):
        return self.manifest.get("python", "python3")

    @property
    def auto_start(self):
        return self.manifest.get("auto_start", False)

    @property
    def status(self):
        # Reconcile status with actual process state
        if self._process is not None:
            poll = self._process.poll()
            if poll is not None:
                # Process has exited
                if self._status in (ServiceStatus.RUNNING, ServiceStatus.STARTING):
                    self._status = ServiceStatus.ERROR
                    self._error_msg = "Process exited with code %d" % poll
                self._process = None
        return self._status

    @property
    def pid(self):
        if self._process is not None and self._process.poll() is None:
            return self._process.pid
        return None

    @property
    def uptime_seconds(self):
        if self._start_time and self.status == ServiceStatus.RUNNING:
            return int(time.time() - self._start_time)
        return 0

    # ---- Serialization ----

    def to_dict(self):
        d = {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "icon": self.icon,
            "version": self.version,
            "author": self.author,
            "status": self.status,
            "pid": self.pid,
            "uptime": self.uptime_seconds,
            "auto_start": self.auto_start,
            "error": self._error_msg if self._status == ServiceStatus.ERROR else "",
            "restart_count": self._restart_count,
            "has_config": bool(self.manifest.get("preferences")),
            "source": "local",
        }
        if self.source_info and self.source_info.get("source") == "git":
            d["source"] = "git"
            d["repository"] = self.source_info.get("repository", "")
            d["branch"] = self.source_info.get("branch", "")
            d["commit"] = self.source_info.get("commit", "")[:12]
            d["installed_at"] = self.source_info.get("installed_at", "")
            d["updated_at"] = self.source_info.get("updated_at", "")
        return d


class ServiceManager:
    """Discovers, launches and manages background services.

    Services are Python scripts that run as subprocesses and interact
    with the Moonstone notebook exclusively through the WebBridge HTTP API.
    """

    def __init__(
        self,
        services_dir,
        api_url="http://localhost:8090/api",
        auth_token=None,
        ws_url=None,
    ):
        """Constructor.

        @param services_dir: path to directory containing services
        @param api_url: base URL of the WebBridge API
        @param auth_token: auth token for API access
        @param ws_url: WebSocket URL (optional)
        """
        self.services_dir = services_dir
        self.api_url = api_url
        self.auth_token = auth_token
        self.ws_url = ws_url
        self._services = {}
        self._health_thread = None
        self._health_stop = threading.Event()
        self._lock = threading.Lock()
        self._event_manager = None

        os.makedirs(services_dir, exist_ok=True)
        self.refresh()
        self._cleanup_stale_pids()

        # Register atexit handler to kill orphan processes on interpreter exit
        atexit.register(self._atexit_cleanup)

    def set_event_manager(self, em):
        """Set EventManager for emitting service lifecycle events."""
        self._event_manager = em

    def _emit(self, event_type, data):
        """Emit an SSE event if EventManager is available."""
        if self._event_manager:
            self._event_manager.emit("service:" + event_type, data)

    # ---- Discovery ----

    def refresh(self):
        """Re-scan the services directory. Preserves running service state."""
        if not os.path.isdir(self.services_dir):
            return

        from moonstone.webbridge.installer import INSTALL_META

        discovered = set()
        for entry in sorted(os.listdir(self.services_dir)):
            if entry.startswith(".") or entry.startswith("_"):
                continue

            svc_path = os.path.join(self.services_dir, entry)
            if not os.path.isdir(svc_path):
                continue

            manifest_file = os.path.join(svc_path, "manifest.json")
            if not os.path.isfile(manifest_file):
                continue

            # Load manifest
            manifest = None
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Bad manifest for service %s: %s", entry, e)
                continue

            # Must be type=service
            if manifest.get("type") != "service":
                continue

            # Load source info
            source_info = None
            meta_file = os.path.join(svc_path, INSTALL_META)
            if os.path.isfile(meta_file):
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        source_info = json.load(f)
                except (json.JSONDecodeError, OSError):
                    pass

            discovered.add(entry)

            # Preserve existing running service object
            with self._lock:
                if entry in self._services:
                    # Update manifest/source_info but keep process state
                    svc = self._services[entry]
                    svc.manifest = manifest
                    svc.source_info = source_info
                else:
                    svc = Service(entry, svc_path, manifest, source_info)
                    self._services[entry] = svc

            logger.debug("Discovered service: %s (%s)", entry, svc.label)

        # Remove services that no longer exist on disk
        with self._lock:
            for name in list(self._services.keys()):
                if name not in discovered:
                    svc = self._services[name]
                    if svc.status == ServiceStatus.RUNNING:
                        self._stop_process(svc)
                    del self._services[name]

    # ---- Listing ----

    def list_services(self):
        """Return list of services as dicts."""
        with self._lock:
            return [svc.to_dict() for svc in self._services.values()]

    def get_service(self, name):
        """Get a service by name. Returns Service or None."""
        return self._services.get(name)

    # ---- Start / Stop / Restart ----

    def start_service(self, name):
        """Start a service by name.

        Creates venv + installs deps if needed, then launches subprocess.

        @returns: dict with result
        @raises: ServiceError on failure
        """
        with self._lock:
            svc = self._services.get(name)
            if not svc:
                return {"error": "Service not found: %s" % name}

            if svc.status == ServiceStatus.RUNNING:
                return {"ok": True, "status": "already_running", "pid": svc.pid}

        # Ensure deps are installed (outside lock — may take time)
        try:
            self._ensure_venv(svc)
        except Exception as e:
            svc._status = ServiceStatus.ERROR
            svc._error_msg = "Dependency install failed: %s" % str(e)
            return {"error": svc._error_msg}

        # Launch subprocess
        with self._lock:
            try:
                self._launch_process(svc)
                self._set_enabled(svc, True)
                self._emit("starting", {"name": name, "pid": svc.pid})
                return {"ok": True, "name": name, "pid": svc.pid, "status": "starting"}
            except Exception as e:
                svc._status = ServiceStatus.ERROR
                svc._error_msg = str(e)
                return {"error": "Failed to start %s: %s" % (name, e)}

    def stop_service(self, name):
        """Stop a running service.

        Sends SIGTERM, waits for graceful shutdown, then SIGKILL.

        @returns: dict with result
        """
        with self._lock:
            svc = self._services.get(name)
            if not svc:
                return {"error": "Service not found: %s" % name}

            if svc.status != ServiceStatus.RUNNING:
                return {"ok": True, "status": "already_stopped"}

            self._stop_process(svc)
            self._set_enabled(svc, False)
            self._emit("stopped", {"name": name})
            return {"ok": True, "name": name, "status": "stopped"}

    def restart_service(self, name):
        """Restart a service (stop + start)."""
        svc = self._services.get(name)
        if not svc:
            return {"error": "Service not found: %s" % name}

        if svc.status == ServiceStatus.RUNNING:
            self.stop_service(name)

        svc._restart_count += 1
        return self.start_service(name)

    # ---- Logs ----

    def get_logs(self, name, tail=100):
        """Read the last N lines of service log.

        @returns: dict with log lines
        """
        svc = self._services.get(name)
        if not svc:
            return {"error": "Service not found: %s" % name}

        log_path = svc._log_path
        if not os.path.isfile(log_path):
            return {"name": name, "lines": [], "log_file": log_path}

        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
            lines = all_lines[-tail:]
            return {
                "name": name,
                "lines": [l.rstrip("\n") for l in lines],
                "total_lines": len(all_lines),
                "log_file": log_path,
            }
        except OSError as e:
            return {"error": "Failed to read log: %s" % str(e)}

    # ---- Config ----

    def get_config(self, name):
        """Read service configuration from _data/_config.json."""
        svc = self._services.get(name)
        if not svc:
            return None, "Service not found: %s" % name

        config_file = os.path.join(svc.path, "_data", "_config.json")
        config = {}
        if os.path.isfile(config_file):
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

        schema = svc.manifest.get("preferences", [])
        return {
            "name": name,
            "config": config,
            "schema": schema,
        }, None

    def save_config(self, name, config):
        """Save service configuration."""
        svc = self._services.get(name)
        if not svc:
            return None, "Service not found: %s" % name

        data_dir = os.path.join(svc.path, "_data")
        os.makedirs(data_dir, exist_ok=True)
        config_file = os.path.join(data_dir, "_config.json")

        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            return {"ok": True, "name": name}, None
        except Exception as e:
            return None, "Save failed: %s" % str(e)

    # ---- Enabled state (persist across restarts) ----

    def _enabled_path(self, svc):
        """Return path to the .enabled marker file."""
        return os.path.join(svc.path, "_data", ".enabled")

    def _is_enabled(self, svc):
        """Check if the service was previously started by the user."""
        return os.path.isfile(self._enabled_path(svc))

    def _set_enabled(self, svc, enabled):
        """Set or clear the .enabled marker."""
        path = self._enabled_path(svc)
        try:
            if enabled:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w") as f:
                    f.write("")
            else:
                if os.path.isfile(path):
                    os.remove(path)
        except OSError:
            pass

    # ---- Auto-start ----

    def auto_start_services(self):
        """Start services that have auto_start=true in manifest
        OR that were previously running (have .enabled marker).
        """
        for name, svc in list(self._services.items()):
            should_start = svc.auto_start or self._is_enabled(svc)
            if should_start and svc.status != ServiceStatus.RUNNING:
                logger.info("Auto-starting service: %s", name)
                threading.Thread(
                    target=self.start_service,
                    args=(name,),
                    daemon=True,
                    name="SvcAutoStart-%s" % name,
                ).start()

    # ---- Stop all (for shutdown) ----

    def stop_all(self):
        """Stop all running services. Called during server shutdown."""
        self._health_stop.set()
        with self._lock:
            for name, svc in self._services.items():
                if svc.status == ServiceStatus.RUNNING:
                    logger.info("Stopping service: %s", name)
                    self._stop_process(svc)

    # ---- Health monitor ----

    def start_health_monitor(self):
        """Start a background thread that monitors running services."""
        if self._health_thread is not None:
            return

        self._health_stop.clear()
        self._health_thread = threading.Thread(
            target=self._health_loop,
            daemon=True,
            name="ServiceHealthMonitor",
        )
        self._health_thread.start()

    def _health_loop(self):
        """Periodically check if running services are still alive."""
        while not self._health_stop.is_set():
            with self._lock:
                for name, svc in list(self._services.items()):
                    if svc._process is not None:
                        poll = svc._process.poll()
                        if poll is not None:
                            # Process died unexpectedly
                            logger.warning(
                                "Service %s exited unexpectedly (code %d)",
                                name,
                                poll,
                            )
                            svc._status = ServiceStatus.ERROR
                            svc._error_msg = "Exited with code %d" % poll
                            svc._process = None
                            self._emit(
                                "crashed",
                                {
                                    "name": name,
                                    "exit_code": poll,
                                },
                            )

            self._health_stop.wait(timeout=_HEALTH_CHECK_INTERVAL)

        self._health_thread = None

    # ---- Internal: process management ----

    def _launch_process(self, svc):
        """Launch a service as a subprocess. Must be called with lock held."""
        entry = svc.entry_point
        entry_path = os.path.join(svc.path, entry)
        if not os.path.isfile(entry_path):
            raise FileNotFoundError("Entry point not found: %s" % entry)

        # Determine Python executable (venv or system)
        venv_dir = os.path.join(svc.path, ".venv")
        if os.path.isdir(venv_dir):
            python = os.path.join(venv_dir, "bin", "python")
            if not os.path.isfile(python):
                python = sys.executable
        else:
            python = sys.executable

        # Prepare environment
        env = dict(os.environ)
        env.update(
            {
                "MOONSTONE_API_URL": self.api_url,
                "MOONSTONE_SERVICE_NAME": svc.name,
                "MOONSTONE_SERVICE_DATA_DIR": os.path.join(svc.path, "_data"),
                "PYTHONUNBUFFERED": "1",
            }
        )
        if self.auth_token:
            env["MOONSTONE_AUTH_TOKEN"] = self.auth_token
        if self.ws_url:
            env["MOONSTONE_WS_URL"] = self.ws_url

        # Ensure data dir and log file exist
        data_dir = os.path.join(svc.path, "_data")
        os.makedirs(data_dir, exist_ok=True)

        # Rotate log if too large
        self._rotate_log(svc._log_path)

        log_file = open(svc._log_path, "a", encoding="utf-8")

        # Write startup marker
        log_file.write(
            "\n--- Service started at %s ---\n" % time.strftime("%Y-%m-%d %H:%M:%S")
        )
        log_file.flush()

        svc._status = ServiceStatus.STARTING
        svc._error_msg = ""

        try:
            proc = subprocess.Popen(
                [python, entry],
                cwd=svc.path,
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
        except Exception:
            log_file.close()
            raise

        svc._process = proc
        svc._start_time = time.time()

        # Write PID file for stale process cleanup
        self._write_pid_file(svc, proc.pid)

        # Monitor startup (give it a moment, then check if it's still alive)
        def _check_startup():
            time.sleep(1.5)
            poll = proc.poll()
            if poll is not None:
                svc._status = ServiceStatus.ERROR
                svc._error_msg = "Exited during startup (code %d)" % poll
                svc._process = None
                self._remove_pid_file(svc)
                logger.error("Service %s failed to start (exit %d)", svc.name, poll)
                self._emit("crashed", {"name": svc.name, "exit_code": poll})
            else:
                svc._status = ServiceStatus.RUNNING
                logger.info("Service %s running (pid %d)", svc.name, proc.pid)
                self._emit(
                    "started", {"name": svc.name, "pid": proc.pid, "status": "running"}
                )

        threading.Thread(target=_check_startup, daemon=True).start()

        logger.info("Launched service %s (pid %d)", svc.name, proc.pid)

    def _stop_process(self, svc):
        """Stop a service process. Must be called with lock held."""
        proc = svc._process
        if proc is None:
            svc._status = ServiceStatus.STOPPED
            return

        svc._status = ServiceStatus.STOPPING

        # Try graceful shutdown (SIGTERM)
        try:
            proc.terminate()
        except (ProcessLookupError, PermissionError, OSError):
            svc._process = None
            svc._status = ServiceStatus.STOPPED
            self._remove_pid_file(svc)
            return

        # Wait for graceful shutdown
        try:
            proc.wait(timeout=_SHUTDOWN_TIMEOUT)
        except subprocess.TimeoutExpired:
            # Force kill
            logger.warning(
                "Service %s did not stop gracefully, sending SIGKILL", svc.name
            )
            try:
                proc.kill()
                proc.wait(timeout=3)
            except (
                ProcessLookupError,
                PermissionError,
                subprocess.TimeoutExpired,
                OSError,
            ):
                pass

        svc._process = None
        svc._status = ServiceStatus.STOPPED
        svc._start_time = None
        self._remove_pid_file(svc)
        logger.info("Service %s stopped", svc.name)

    # ---- Internal: venv management ----

    def _ensure_venv(self, svc):
        """Create venv and install requirements if needed."""
        venv_dir = os.path.join(svc.path, ".venv")
        requirements = os.path.join(svc.path, "requirements.txt")

        if not os.path.isfile(requirements):
            # No requirements — no venv needed
            return

        # Check if venv already exists and deps are installed
        marker = os.path.join(venv_dir, ".deps_installed")
        req_mtime = os.path.getmtime(requirements)

        if os.path.isdir(venv_dir) and os.path.isfile(marker):
            try:
                marker_mtime = os.path.getmtime(marker)
                if marker_mtime >= req_mtime:
                    return  # Already up to date
            except OSError:
                pass

        logger.info("Setting up venv for service %s...", svc.name)

        # Create venv
        if not os.path.isdir(venv_dir):
            result = subprocess.run(
                [sys.executable, "-m", "venv", venv_dir],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                raise RuntimeError("venv creation failed: %s" % result.stderr.strip())

        # Install requirements
        pip = os.path.join(venv_dir, "bin", "pip")
        if not os.path.isfile(pip):
            pip = os.path.join(venv_dir, "bin", "pip3")

        logger.info("Installing requirements for %s...", svc.name)
        result = subprocess.run(
            [pip, "install", "-r", requirements, "--quiet"],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=svc.path,
        )
        if result.returncode != 0:
            raise RuntimeError("pip install failed: %s" % result.stderr.strip())

        # Write marker
        with open(marker, "w") as f:
            f.write(str(time.time()))

        logger.info("Dependencies installed for %s", svc.name)

    # ---- Internal: log rotation ----

    def _rotate_log(self, log_path):
        """Rotate log file if it exceeds max size."""
        if not os.path.isfile(log_path):
            return
        try:
            size = os.path.getsize(log_path)
            if size > _MAX_LOG_SIZE:
                backup = log_path + ".1"
                if os.path.isfile(backup):
                    os.remove(backup)
                os.rename(log_path, backup)
                logger.debug("Rotated log: %s", log_path)
        except OSError:
            pass

    # ---- Internal: PID file management ----

    def _pid_file_path(self, svc):
        """Return path to the PID file for a service."""
        return os.path.join(svc.path, "_data", "service.pid")

    def _write_pid_file(self, svc, pid):
        """Write process PID to file for stale cleanup."""
        try:
            pid_path = self._pid_file_path(svc)
            os.makedirs(os.path.dirname(pid_path), exist_ok=True)
            with open(pid_path, "w") as f:
                f.write(str(pid))
        except OSError:
            pass

    def _remove_pid_file(self, svc):
        """Remove PID file after process stops."""
        try:
            pid_path = self._pid_file_path(svc)
            if os.path.isfile(pid_path):
                os.remove(pid_path)
        except OSError:
            pass

    def _cleanup_stale_pids(self):
        """Kill orphan service processes from a previous session.

        Reads PID files, checks if the process is still alive,
        and sends SIGTERM + SIGKILL if needed.
        """
        for name, svc in list(self._services.items()):
            pid_path = self._pid_file_path(svc)
            if not os.path.isfile(pid_path):
                continue

            try:
                with open(pid_path, "r") as f:
                    old_pid = int(f.read().strip())
            except (ValueError, OSError):
                self._remove_pid_file(svc)
                continue

            # Check if process is still alive
            try:
                os.kill(old_pid, 0)  # signal 0 = existence check
            except ProcessLookupError:
                # Already dead — clean up PID file
                self._remove_pid_file(svc)
                continue
            except PermissionError:
                # Alive but we can't signal it
                self._remove_pid_file(svc)
                continue

            # Process is alive — it's an orphan from a previous session
            logger.warning("Killing orphan service %s (pid %d)", name, old_pid)
            try:
                os.kill(old_pid, signal.SIGTERM)
                # Wait briefly for graceful exit
                for _ in range(20):
                    time.sleep(0.25)
                    try:
                        os.kill(old_pid, 0)
                    except ProcessLookupError:
                        break
                else:
                    # Still alive — force kill
                    try:
                        os.kill(old_pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            except ProcessLookupError:
                pass  # Already dead
            except PermissionError:
                logger.warning("Cannot kill orphan pid %d (permission denied)", old_pid)

            self._remove_pid_file(svc)

    def _atexit_cleanup(self):
        """Called by atexit: stop all services on interpreter shutdown.

        This is a safety net for cases where teardown() is not called
        (e.g. the process is killed with SIGTERM but atexit still runs).
        """
        for name, svc in list(self._services.items()):
            proc = svc._process
            if proc is not None and proc.poll() is None:
                logger.info("atexit: stopping service %s (pid %d)", name, proc.pid)
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                self._remove_pid_file(svc)

    # ---- Update connection params ----

    def update_connection(self, api_url=None, auth_token=None, ws_url=None):
        """Update the API connection parameters.

        Called when the server port changes.
        """
        if api_url is not None:
            self.api_url = api_url
        if auth_token is not None:
            self.auth_token = auth_token
        if ws_url is not None:
            self.ws_url = ws_url
