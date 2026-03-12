#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

"""Moonstone Headless Server — standalone PKM system, no external dependencies.

Usage:
    moonstone /path/to/notebook [--port 8090] [--token SECRET]
    moonstone                    # tray-only mode, notebook from saved settings

Provides a full REST API (pages CRUD, search, tags,
links, attachments, SSE) as a standalone system.

Dependencies: watchdog, pystray, Pillow (+ tkinter from stdlib).
"""

import sys
import os
import argparse
import logging
import threading
import signal

# ============================================================
# NavigationHistory — tracks page navigation in headless mode
# ============================================================


class NavigationHistory:
    """Track page navigation history for headless mode.

    Provides get_history() and get_recent() iterators compatible
    with the api.py get_history() expectations.
    """

    def __init__(self, max_size=200):
        self._max_size = max_size
        self._history = []  # chronological list of _HistoryRecord
        self._recent_map = {}  # name → _HistoryRecord (latest visit)
        self._lock = threading.Lock()

    def add(self, page_name):
        """Record a page visit."""
        import time

        record = _HistoryRecord(page_name, time.time())
        with self._lock:
            self._history.append(record)
            if len(self._history) > self._max_size:
                self._history = self._history[-self._max_size :]
            self._recent_map[page_name] = record

    def get_history(self):
        """Chronological history (newest first)."""
        with self._lock:
            return reversed(list(self._history))

    def get_recent(self):
        """Unique pages, most recently visited first."""
        with self._lock:
            items = sorted(
                self._recent_map.values(), key=lambda r: r.timestamp, reverse=True
            )
            return iter(items)


class _HistoryRecord:
    """Single history entry, duck-typed for api.py."""

    __slots__ = ("name", "basename", "timestamp")

    def __init__(self, name, timestamp):
        self.name = name
        self.basename = name.rsplit(":", 1)[-1] if ":" in name else name
        self.timestamp = timestamp


# ============================================================
# FileWatcher — watchdog-based, instant FS event detection
# ============================================================

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class _NotebookEventHandler(FileSystemEventHandler):
    """Watchdog handler that converts FS events to Moonstone callbacks.

    Uses native OS mechanisms (inotify on Linux, FSEvents on macOS,
    ReadDirectoryChangesW on Windows) — instant, zero CPU idle.

    @param notebook_path: root directory of the notebook
    @param callback: fn(event_type, page_name, file_path)
    @param extensions: tuple of watched file extensions
    """

    def __init__(self, notebook_path, callback, extensions=(".txt", ".md", ".wiki")):
        super().__init__()
        self._path = notebook_path
        self._callback = callback
        self._extensions = extensions
        self._logger = logging.getLogger("moonstone.watcher")

    def _is_page_file(self, path):
        return any(path.endswith(ext) for ext in self._extensions)

    def _path_to_page(self, file_path):
        """Convert /path/to/notebook/Projects/Moonstone.txt → Projects:Moonstone"""
        rel = os.path.relpath(file_path, self._path)
        for ext in self._extensions:
            if rel.endswith(ext):
                rel = rel[: -len(ext)]
                break
        page_name = rel.replace(os.sep, ":")
        page_name = page_name.replace("_", " ")
        return page_name

    def _fire(self, event_type, file_path):
        if not self._is_page_file(file_path):
            return
        # Skip hidden dirs
        rel = os.path.relpath(file_path, self._path)
        if any(part.startswith(".") for part in rel.split(os.sep)):
            return
        page_name = self._path_to_page(file_path)
        try:
            self._callback(event_type, page_name, file_path)
        except Exception:
            self._logger.debug("FileWatcher callback error", exc_info=True)

    def on_created(self, event):
        if not event.is_directory:
            self._fire("created", event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._fire("modified", event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self._fire("deleted", event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._fire("deleted", event.src_path)
            self._fire("created", event.dest_path)


class FileWatcher:
    """Watchdog-based file watcher — instant, cross-platform, zero CPU idle.

    Uses native OS mechanisms: inotify (Linux), FSEvents (macOS),
    ReadDirectoryChangesW (Windows).

    @param notebook_path: root directory of the notebook
    @param callback: fn(event_type, page_name, file_path)
    @param extensions: tuple of watched file extensions
    """

    def __init__(self, notebook_path, callback, extensions=(".txt", ".md", ".wiki")):
        self._path = notebook_path
        self._callback = callback
        self._extensions = extensions
        self._logger = logging.getLogger("moonstone.watcher")
        self._observer = Observer()
        self._handler = _NotebookEventHandler(
            notebook_path,
            callback,
            extensions,
        )

    def start(self):
        self._observer.schedule(
            self._handler,
            self._path,
            recursive=True,
        )
        self._observer.daemon = True
        self._observer.start()
        self._logger.info("FileWatcher started (watchdog/inotify, instant)")

    def stop(self):
        self._observer.stop()
        self._observer.join(timeout=2)


class TrackingArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that tracks which arguments were explicitly provided."""
    def parse_args(self, args=None, namespace=None):
        parsed = super().parse_args(args, namespace)
        # Find all explicitly provided options
        provided_args = sys.argv[1:] if args is None else args
        explicit = set()
        
        # Simple heuristic to find provided options
        for action in self._actions:
            # Check if any of the option strings for this action are in provided args
            if any(opt in provided_args for opt in action.option_strings):
                explicit.add(action.dest)
                
        # Handle positional arguments (if any positional arg provided, we assume notebook)
        positionals = [arg for arg in provided_args if not arg.startswith('-')]
        if positionals:
            explicit.add('notebook')
            
        parsed._explicit = explicit
        return parsed

def parse_args():
    parser = TrackingArgumentParser(
        description="Moonstone — standalone REST API server for personal knowledge management",
    )
    parser.add_argument(
        "notebook",
        nargs="?",
        default=None,
        help="Path to the notebook directory (optional if saved in settings)",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=8090,
        help="HTTP port (default: 8090)",
    )
    parser.add_argument(
        "--token",
        "-t",
        default="",
        help="Auth token (empty = no auth)",
    )
    parser.add_argument(
        "--applets-dir",
        "-a",
        default=None,
        help="Path to webapps directory",
    )
    parser.add_argument(
        "--services-dir",
        "-s",
        default=None,
        help="Path to background services directory",
    )
    parser.add_argument(
        "--ws-port",
        type=int,
        default=None,
        help="WebSocket port (default: HTTP port + 1, 0 = disable)",
    )
    parser.add_argument(
        "--host",
        default="localhost",
        help="Host to bind to (default: localhost)",
    )
    parser.add_argument(
        "--verbose",
        "-V",
        action="store_true",
        help="Verbose logging",
    )
    parser.add_argument(
        "--debug",
        "-D",
        action="store_true",
        help="Debug logging",
    )
    parser.add_argument(
        "--profile",
        choices=["auto", "moonstone", "obsidian", "logseq", "zim"],
        default="auto",
        help="Vault profile (default: auto-detect). Controls file format, tag/link syntax, etc.",
    )
    parser.add_argument(
        "--install-shortcut",
        action="store_true",
        help="Create OS-native desktop shortcut (menu entry) and exit",
    )
    parser.add_argument(
        "--uninstall-shortcut",
        action="store_true",
        help="Remove OS-native desktop shortcut and exit",
    )
    parser.add_argument(
        "--no-tray",
        action="store_true",
        help="Disable system tray icon (console-only mode)",
    )
    return parser.parse_args()


class AppContext:
    """Application context — holds state for the Moonstone server."""

    # Dedup window: ignore FileWatcher events for pages saved via API
    # within this many seconds.
    _DEDUP_WINDOW = 4.0

    def __init__(self, applets_dir, port=8090, auth_token="", services_dir=None):
        self._current_page_name = None
        self._event_manager = None
        self._pageview_ext = None
        self._history = None
        self._applets_dir = applets_dir
        self._services_dir = services_dir
        self.preferences = {
            "port": port,
            "auth_token": auth_token,
        }
        self.notebook = None
        self._server_ref = None
        self._standby_callback = None
        self._yielding = False
        self._recent_api_saves = {}  # page_name → timestamp

    @property
    def applets_dir(self):
        return self._applets_dir

    @property
    def services_dir(self):
        return self._services_dir

    @property
    def server_running(self):
        return True

    def set_current_page(self, page_name):
        old = self._current_page_name
        self._current_page_name = page_name
        if self._event_manager and old != page_name:
            self._event_manager.emit("page-changed", {"page": page_name})

    def notify_page_saved(self, page_name):
        import time

        self._recent_api_saves[page_name] = time.time()
        if self._event_manager:
            self._event_manager.emit("page-saved", {"page": page_name, "source": "api"})

    def request_navigate(self, page_name):
        """Navigate to a page — in headless mode, sets current page + SSE event."""
        self.set_current_page(page_name)
        if self._history:
            self._history.add(page_name)
        logging.getLogger("moonstone").debug("Navigate (headless focus): %s", page_name)

    def get_base_url(self):
        return "http://localhost:%d" % self.preferences["port"]

    def request_yield(self):
        if self._yielding:
            return
        self._yielding = True
        print("\n  🔵 Yield requested — entering standby mode...")

        def _do_yield():
            import time

            srv = self._server_ref
            if srv:
                srv.shutdown()
                srv.server_close()
                time.sleep(0.3)
            self._yielding = False
            if self._standby_callback:
                self._standby_callback()

        threading.Thread(target=_do_yield, daemon=True, name="YieldHandler").start()

    _ws_port = None

    def get_ws_url(self):
        if self._ws_port:
            return "ws://localhost:%d" % self._ws_port
        return None

    @property
    def readonly(self):
        return False


def connect_notebook_signals(notebook, event_manager):
    """Subscribe to notebook signals and relay them as SSE events."""
    logger = logging.getLogger("moonstone")

    def on_stored_page(nb, page):
        page_name = page.name if hasattr(page, "name") else str(page)
        event_manager.emit("page-saved", {"page": page_name, "source": "notebook"})

    def on_moved_page(nb, oldpath, newpath):
        old_name = oldpath.name if hasattr(oldpath, "name") else str(oldpath)
        new_name = newpath.name if hasattr(newpath, "name") else str(newpath)
        event_manager.emit(
            "page-moved",
            {
                "old": old_name,
                "new": new_name,
                "source": "notebook",
            },
        )

    def on_deleted_page(nb, path):
        page_name = path.name if hasattr(path, "name") else str(path)
        event_manager.emit("page-deleted", {"page": page_name, "source": "notebook"})

    try:
        notebook.connect("stored-page", on_stored_page)
        notebook.connect("moved-page", on_moved_page)
        notebook.connect("deleted-page", on_deleted_page)
        logger.info("Connected notebook signals → SSE events")
    except Exception:
        logger.warning("Could not connect notebook signals", exc_info=True)


# ============================================================
# MoonstoneServer — encapsulates notebook + HTTP/WS lifecycle
# ============================================================


class MoonstoneServer:
    """Manages the full server lifecycle: notebook, HTTP, WS, file watcher.

    Can be stopped and re-created with different settings to support
    tray-based restart.
    """

    def __init__(self, settings):
        self._settings = settings
        self._logger = logging.getLogger("moonstone")
        self._server = None
        self._ws_server = None
        self._file_watcher = None
        self._app = None
        self._notebook = None
        self._event_manager = None
        self._history = None
        self._n_pages = 0
        self._profile_label = "?"
        self._actual_port = settings.get("port", 8090)
        self._running = False

    @property
    def is_running(self):
        return self._running

    def get_info(self):
        """Return status dict for the tray menu."""
        if self._running:
            return {
                "status": "http://%s:%d"
                % (
                    self._settings.get("host", "localhost"),
                    self._actual_port,
                ),
                "url": "http://%s:%d"
                % (
                    self._settings.get("host", "localhost"),
                    self._actual_port,
                ),
                "n_pages": self._n_pages,
                "profile": self._profile_label,
            }
        return {
            "status": "not running",
            "n_pages": "?",
            "profile": self._settings.get("profile", "auto"),
        }

    def start(self):
        """Start the server. Returns True on success, False on failure."""
        from moonstone.notebook import resolve_notebook, build_notebook
        from moonstone.webbridge.events import EventManager
        from moonstone.webbridge.server import create_server

        notebook_path = self._settings.get("notebook", "")
        if not notebook_path or not os.path.isdir(notebook_path):
            self._logger.error("Notebook directory not found: %s", notebook_path)
            print(
                "ERROR: Notebook directory not found: %s" % notebook_path,
                file=sys.stderr,
            )
            return False

        self._logger.info("Opening notebook: %s", notebook_path)
        notebookinfo = resolve_notebook(notebook_path)
        if not notebookinfo:
            self._logger.error("Could not resolve notebook: %s", notebook_path)
            return False

        # Resolve vault profile
        profile = None
        profile_name = self._settings.get("profile", "auto")
        if profile_name != "auto":
            from moonstone.profiles import get_profile

            profile = get_profile(profile_name)
            self._logger.info("Profile override: %s", profile.display_name)

        notebook, _ = build_notebook(notebookinfo, profile=profile)
        self._notebook = notebook

        # Update index
        self._logger.info("Checking notebook index...")
        if not notebook.index.is_uptodate:
            self._logger.info("Updating index (this may take a moment)...")
            notebook.index.check_and_update()
        self._n_pages = notebook.pages.n_all_pages()
        self._logger.info("Index up to date (%d pages)", self._n_pages)

        self._profile_label = notebook.profile.display_name if notebook.profile else "?"

        # Applets directory
        applets_dir = self._settings.get("applets_dir")
        if not applets_dir:
            xdg_data = os.environ.get(
                "XDG_DATA_HOME",
                os.path.join(os.path.expanduser("~"), ".local", "share"),
            )
            applets_dir = os.path.join(xdg_data, "moonstone", "webapps")
        os.makedirs(applets_dir, exist_ok=True)

        # App context + event manager
        port = self._settings.get("port", 8090)
        auth_token = self._settings.get("token", "") or None
        host = self._settings.get("host", "localhost")

        # Services directory (independent of applets_dir)
        services_dir = self._settings.get("services_dir")
        if not services_dir:
            xdg_data = os.environ.get(
                "XDG_DATA_HOME",
                os.path.join(os.path.expanduser("~"), ".local", "share"),
            )
            services_dir = os.path.join(xdg_data, "moonstone", "services")
        os.makedirs(services_dir, exist_ok=True)

        app = AppContext(
            applets_dir=applets_dir,
            port=port,
            auth_token=auth_token or "",
            services_dir=services_dir,
        )
        self._app = app

        event_manager = EventManager()
        app._event_manager = event_manager
        self._event_manager = event_manager

        connect_notebook_signals(notebook, event_manager)

        # Navigation history
        history = NavigationHistory()
        app._history = history
        self._history = history

        home_page = notebook.config.get("Notebook", "home", "Home")
        app.set_current_page(home_page)
        history.add(home_page)

        # File watcher
        from moonstone.notebook.page import Path

        def _on_file_change(event_type, page_name, file_path):
            import time as _time

            last_api_save = app._recent_api_saves.get(page_name, 0)
            if _time.time() - last_api_save < app._DEDUP_WINDOW:
                return
            notebook._page_cache.pop(page_name, None)
            try:
                if event_type in ("created", "modified"):
                    path = Path(page_name)
                    page = notebook.get_page(path)
                    tree = page.get_parsetree()
                    notebook.index.update_page(page, tree)
                elif event_type == "deleted":
                    notebook.index.remove_page(Path(page_name))
            except Exception:
                self._logger.debug(
                    "Index update on file change failed for %s",
                    page_name,
                    exc_info=True,
                )

            if event_type == "deleted":
                event_manager.emit(
                    "page-deleted",
                    {
                        "page": page_name,
                        "source": "filesystem",
                    },
                )
            else:
                event_manager.emit(
                    "page-saved",
                    {
                        "page": page_name,
                        "source": "filesystem",
                    },
                )

        self._file_watcher = FileWatcher(notebook_path, _on_file_change)
        self._file_watcher.start()

        # Create HTTP server (with port fallback)
        server = None
        for try_port in [port] + list(range(port + 1, port + 20)):
            try:
                server = create_server(
                    notebook=notebook,
                    app=app,
                    port=try_port,
                    auth_token=auth_token,
                    event_manager=event_manager,
                    bind_address=host,
                )
                self._actual_port = try_port
                break
            except OSError:
                continue

        if not server:
            self._logger.error("No free port found in range %d-%d", port, port + 19)
            return False

        self._server = server
        app.preferences["port"] = self._actual_port
        app._server_ref = server

        # Start HTTP server thread
        server_thread = threading.Thread(
            target=server.serve_forever,
            daemon=True,
            name="MoonstoneHTTPServer",
        )
        server_thread.start()

        # Start WebSocket server
        ws_port_setting = self._settings.get("ws_port")
        if ws_port_setting != 0:
            ws_port = ws_port_setting if ws_port_setting else self._actual_port + 1
            try:
                from moonstone.webbridge.websocket import create_ws_server

                api = None
                wsgi_app = server.get_app()
                if hasattr(wsgi_app, "api"):
                    api = wsgi_app.api

                ws_server, ws_manager = create_ws_server(
                    port=ws_port,
                    bind_address=host,
                    auth_token=auth_token,
                    api=api,
                )
                self._ws_server = ws_server
                app._ws_port = ws_port
                event_manager.set_ws_manager(ws_manager)

                ws_thread = threading.Thread(
                    target=ws_server.serve_forever,
                    daemon=True,
                    name="MoonstoneWS",
                )
                ws_thread.start()
                self._logger.info("WebSocket server started on %s:%d", host, ws_port)
            except OSError as e:
                self._logger.warning(
                    "Failed to start WebSocket server on port %d: %s", ws_port, e
                )
            except Exception:
                self._logger.exception("Unexpected error starting WebSocket server")

        self._running = True

        # Print banner
        alt_note = " (alt)" if self._actual_port != port else ""
        print()
        print("  🌉 Moonstone Server")
        print("  ────────────────────────────────")
        print("  Notebook:  %s" % notebook_path)
        print("  Profile:   %s" % self._profile_label)
        print("  Pages:     %d" % self._n_pages)
        print("  Server:    http://%s:%d%s" % (host, self._actual_port, alt_note))
        print("  API:       http://%s:%d/api/" % (host, self._actual_port))
        if app._ws_port:
            print("  WebSocket: ws://%s:%d" % (host, app._ws_port))
        if auth_token:
            print("  Auth:      token required")
        else:
            print("  Auth:      none (open access)")
        print("  ────────────────────────────────")
        print()

        return True

    def stop(self):
        """Stop all server components."""
        self._running = False
        if self._file_watcher:
            try:
                self._file_watcher.stop()
            except Exception:
                pass
            self._file_watcher = None

        if self._ws_server:
            try:
                self._ws_server.shutdown()
                self._ws_server.server_close()
            except Exception:
                pass
            self._ws_server = None

        if self._server:
            try:
                # Stop background services gracefully
                wsgi_app = getattr(self._server, "application", None)
                if wsgi_app and getattr(wsgi_app, "service_manager", None):
                    self._logger.info("Stopping background services...")
                    wsgi_app.service_manager.stop_all()

                self._server.shutdown()
                self._server.server_close()
            except Exception:
                pass
            self._server = None

        self._logger.info("Server stopped")


def main():
    args = parse_args()

    # ---- Desktop shortcut commands (exit immediately) ----
    if args.install_shortcut:
        from moonstone.desktop import install_shortcut

        install_shortcut()
        sys.exit(0)
    if args.uninstall_shortcut:
        from moonstone.desktop import uninstall_shortcut

        uninstall_shortcut()
        sys.exit(0)

    # ---- Load persistent settings and merge with CLI args ----
    from moonstone import settings as msettings

    saved = msettings.load()
    settings = msettings.merge_cli_args(args, saved)

    # Setup logging
    if settings.get("debug"):
        level = logging.DEBUG
    elif settings.get("verbose"):
        level = logging.INFO
    else:
        level = logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("moonstone")

    use_tray = not args.no_tray

    # ---- Check if we have a notebook to work with ----
    notebook_path = settings.get("notebook", "")

    if not notebook_path and not use_tray:
        # No notebook and no tray — nothing useful to do
        print(
            "ERROR: No notebook specified. Provide a path or run without --no-tray.",
            file=sys.stderr,
        )
        print("Usage: moonstone /path/to/notebook", file=sys.stderr)
        sys.exit(1)

    # If no notebook but tray is enabled, we'll start the tray
    # and let the user pick a notebook from there.

    # ---- Save current settings ----
    msettings.save(settings)

    # ---- Create server manager ----
    # Use a list so nested functions can replace the server object
    _server_box = [MoonstoneServer(settings)]

    # ---- Server info callback for tray ----
    def get_server_info():
        return _server_box[0].get_info()

    # ---- Restart callback for tray ----
    _restart_lock = threading.Lock()

    def on_restart():
        with _restart_lock:
            logger.info("Restarting server...")
            _server_box[0].stop()
            import time

            time.sleep(0.3)
            # Re-read settings (they may have been changed by tray)
            new_server = MoonstoneServer(settings)
            ok = new_server.start()
            if ok:
                _server_box[0] = new_server
                logger.info("Server restarted successfully")
            else:
                logger.error("Server restart failed")
            # Update tray menu
            if tray:
                tray.update_menu()

    # ---- Quit callback ----
    def on_quit():
        logger.info("Shutting down...")
        _server_box[0].stop()
        # Force exit since pystray may have already stopped
        os._exit(0)

    # ---- Start server if we have a notebook ----
    tray = None

    if notebook_path and os.path.isdir(notebook_path):
        ok = _server_box[0].start()
        if not ok and not use_tray:
            sys.exit(1)
    else:
        if use_tray:
            print("  🌉 Moonstone — no notebook selected yet.")
            print("  Use the tray icon to select a notebook directory.")
            print()
        # Server not started; tray will handle it

    # ---- Start tray or fallback to main loop ----
    if use_tray:
        try:
            from moonstone.tray import MoonstoneTray

            tray = MoonstoneTray(
                settings=settings,
                on_restart=on_restart,
                on_quit=on_quit,
                server_info=get_server_info,
                save_settings=msettings.save,
            )

            print("  System tray icon active. Right-click to configure.")
            print("  Press Ctrl+C to stop.")
            print()

            # Handle Ctrl+C cleanly for pystray
            def _sigint_handler(signum, frame):
                logger.info("Ctrl+C received, shutting down...")
                tray.stop()
                _server_box[0].stop()
                os._exit(0)

            signal.signal(signal.SIGINT, _sigint_handler)
            signal.signal(signal.SIGTERM, _sigint_handler)

            # pystray.run() blocks the main thread
            tray.run()

        except ImportError as e:
            logger.warning(
                "pystray not available (%s), falling back to console mode", e
            )
            use_tray = False
        except KeyboardInterrupt:
            _server_box[0].stop()
        except Exception as e:
            logger.warning("Tray failed (%s), falling back to console mode", e)
            use_tray = False

    if not use_tray:
        # Console-only mode: use MainLoop
        from moonstone.mainloop import MainLoop

        print("  Press Ctrl+C to stop")
        print()
        main_loop = MainLoop()
        try:
            main_loop.run()
        except KeyboardInterrupt:
            pass
        finally:
            _server_box[0].stop()


if __name__ == "__main__":
    main()
