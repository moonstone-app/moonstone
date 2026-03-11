# -*- coding: UTF-8 -*-

"""Applet installer for WebBridge.

Provides functionality to install, update, and uninstall web applets
from Git repositories. Tracks installation metadata for update checks.
"""

import json
import logging
import os
import shutil
import subprocess
import tempfile
import time

logger = logging.getLogger("moonstone.webbridge")

# Files that are suspicious in a pure web applet
WARN_EXTENSIONS_APPLET = {
    ".py",
    ".sh",
    ".bash",
    ".zsh",
    ".bat",
    ".cmd",
    ".exe",
    ".so",
    ".dll",
    ".dylib",
    ".bin",
    ".com",
    ".php",
    ".rb",
    ".pl",
    ".jar",
    ".class",
}

# Files that are suspicious in a service (binaries only — .py is expected)
WARN_EXTENSIONS_SERVICE = {
    ".exe",
    ".so",
    ".dll",
    ".dylib",
    ".bin",
    ".com",
    ".jar",
    ".class",
}

# Valid manifest types
MANIFEST_TYPE_APPLET = "applet"
MANIFEST_TYPE_SERVICE = "service"
VALID_MANIFEST_TYPES = {MANIFEST_TYPE_APPLET, MANIFEST_TYPE_SERVICE}

# Metadata filename stored inside installed applet dir
INSTALL_META = ".installed.json"


class InstallError(Exception):
    """Raised when applet installation fails."""

    pass


class AppletInstaller:
    """Manages installation, updating, and uninstalling of applets from Git."""

    def __init__(self, applets_dir):
        """Constructor.
        @param applets_dir: path to the user's webapps directory
        """
        self.applets_dir = applets_dir

    # ---- Install ----

    def install_from_git(self, url, branch=None, name_override=None):
        """Install an applet from a Git repository.

        Clones the repository (shallow), validates its structure,
        and copies it into the applets directory.

        @param url: Git repository URL
        @param branch: branch to clone (None = repository default)
        @param name_override: override the applet directory name
        @returns: dict with installation info
        @raises InstallError: on validation or installation failure
        """
        os.makedirs(self.applets_dir, exist_ok=True)

        # Clone into a temporary directory
        tmpdir = tempfile.mkdtemp(prefix="moonstone-applet-")
        clone_dir = os.path.join(tmpdir, "repo")

        try:
            self._git_clone(url, clone_dir, branch)
            applet_root = self._find_applet_root(clone_dir)
            self._validate_applet(applet_root)

            # Determine applet name
            manifest = self._load_manifest(applet_root)
            applet_id = name_override or manifest.get("id") or self._derive_name(url)
            applet_id = self._sanitize_name(applet_id)

            dest = os.path.join(self.applets_dir, applet_id)
            if os.path.exists(dest):
                raise InstallError(
                    'Applet "%s" already exists. Uninstall first or use update.'
                    % applet_id
                )

            # Get commit hash
            commit = self._git_head_commit(clone_dir)

            # Check for suspicious files
            warnings = self._scan_suspicious(applet_root)

            # Copy applet files (exclude .git)
            self._copy_applet(applet_root, dest)

            # Write installation metadata
            meta = {
                "source": "git",
                "repository": url,
                "branch": branch,
                "commit": commit,
                "installed_at": self._now_iso(),
                "updated_at": self._now_iso(),
            }
            self._write_meta(dest, meta)

            # Reload manifest after copy for response
            manifest = self._load_manifest(dest)

            logger.info(
                'Installed applet "%s" from %s (commit %s)', applet_id, url, commit[:8]
            )

            result = {
                "name": applet_id,
                "label": manifest.get("name", applet_id),
                "version": manifest.get("version", "0.0.0"),
                "commit": commit[:12],
                "repository": url,
                "branch": branch,
            }
            if warnings:
                result["warnings"] = warnings
            return result

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # ---- Uninstall ----

    def uninstall(self, name):
        """Remove an installed applet.

        @param name: applet directory name
        @returns: dict with result
        @raises InstallError: if applet not found
        """
        dest = os.path.join(self.applets_dir, name)
        if not os.path.isdir(dest):
            raise InstallError('Applet "%s" not found' % name)

        # Safety: ensure path is inside applets_dir
        real_dest = os.path.realpath(dest)
        real_base = os.path.realpath(self.applets_dir)
        if not real_dest.startswith(real_base + os.sep):
            raise InstallError("Invalid applet path")

        shutil.rmtree(dest)
        logger.info('Uninstalled applet "%s"', name)
        return {"name": name, "uninstalled": True}

    # ---- Check updates ----

    def check_update(self, name):
        """Check if an update is available for a git-installed applet.

        Uses `git ls-remote` to compare remote HEAD with local commit.

        @param name: applet directory name
        @returns: dict with update info or None if not a git applet
        """
        meta = self._read_meta(name)
        if not meta or meta.get("source") != "git":
            return None

        url = meta.get("repository")
        branch = meta.get("branch")  # None = default branch
        local_commit = meta.get("commit", "")

        try:
            remote_commit = self._git_ls_remote(url, branch)
        except Exception as e:
            logger.warning("Failed to check updates for %s: %s", name, e)
            return {
                "name": name,
                "error": str(e),
                "has_update": False,
            }

        has_update = bool(remote_commit and remote_commit != local_commit)
        return {
            "name": name,
            "repository": url,
            "branch": branch,
            "local_commit": local_commit[:12] if local_commit else "",
            "remote_commit": remote_commit[:12] if remote_commit else "",
            "has_update": has_update,
            "installed_at": meta.get("installed_at", ""),
            "updated_at": meta.get("updated_at", ""),
        }

    def check_all_updates(self):
        """Check updates for all git-installed applets.

        @returns: list of update info dicts
        """
        results = []
        if not os.path.isdir(self.applets_dir):
            return results

        for entry in sorted(os.listdir(self.applets_dir)):
            if entry.startswith(".") or entry.startswith("_"):
                continue
            applet_dir = os.path.join(self.applets_dir, entry)
            if not os.path.isdir(applet_dir):
                continue
            meta_path = os.path.join(applet_dir, INSTALL_META)
            if not os.path.isfile(meta_path):
                continue
            info = self.check_update(entry)
            if info is not None:
                results.append(info)

        return results

    # ---- Update ----

    def update(self, name):
        """Update a git-installed applet to the latest version.

        Re-clones the repository and replaces the applet files,
        preserving the installation metadata.

        @param name: applet directory name
        @returns: dict with update result
        @raises InstallError: on failure
        """
        meta = self._read_meta(name)
        if not meta or meta.get("source") != "git":
            raise InstallError('Applet "%s" is not installed from Git' % name)

        url = meta["repository"]
        branch = meta.get("branch")  # None = default branch
        old_commit = meta.get("commit", "")

        dest = os.path.join(self.applets_dir, name)
        if not os.path.isdir(dest):
            raise InstallError('Applet "%s" not found' % name)

        tmpdir = tempfile.mkdtemp(prefix="moonstone-applet-update-")
        clone_dir = os.path.join(tmpdir, "repo")

        try:
            self._git_clone(url, clone_dir, branch)
            applet_root = self._find_applet_root(clone_dir)
            self._validate_applet(applet_root)

            new_commit = self._git_head_commit(clone_dir)

            if new_commit == old_commit:
                return {
                    "name": name,
                    "updated": False,
                    "message": "Already up to date",
                    "commit": old_commit[:12],
                }

            warnings = self._scan_suspicious(applet_root)

            # Backup old meta
            old_installed_at = meta.get("installed_at", self._now_iso())

            # Remove old files, copy new
            # Preserve nothing — clean replacement
            shutil.rmtree(dest)
            self._copy_applet(applet_root, dest)

            # Write updated metadata
            new_meta = {
                "source": "git",
                "repository": url,
                "branch": branch,
                "commit": new_commit,
                "installed_at": old_installed_at,
                "updated_at": self._now_iso(),
            }
            self._write_meta(dest, new_meta)

            manifest = self._load_manifest(dest)
            logger.info(
                'Updated applet "%s" from %s to %s',
                name,
                old_commit[:8],
                new_commit[:8],
            )

            result = {
                "name": name,
                "updated": True,
                "old_commit": old_commit[:12],
                "new_commit": new_commit[:12],
                "version": manifest.get("version", "0.0.0"),
            }
            if warnings:
                result["warnings"] = warnings
            return result

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # ---- Source info ----

    def get_source_info(self, name):
        """Get installation source info for an applet.

        @param name: applet directory name
        @returns: dict with source info or None
        """
        meta = self._read_meta(name)
        if meta and meta.get("source") == "git":
            return {
                "name": name,
                "source": "git",
                "repository": meta.get("repository", ""),
                "branch": meta.get("branch", "main"),
                "commit": meta.get("commit", "")[:12],
                "installed_at": meta.get("installed_at", ""),
                "updated_at": meta.get("updated_at", ""),
            }

        # Check if it's a bundled applet
        applet_dir = os.path.join(self.applets_dir, name)
        if os.path.isdir(applet_dir):
            return {
                "name": name,
                "source": "local",
            }
        return None

    # ---- Git helpers ----

    def _git_clone(self, url, dest, branch=None):
        """Shallow-clone a Git repository.

        @param branch: specific branch, or None for repository default
        """
        try:
            if branch:
                cmd = [
                    "git",
                    "clone",
                    "--depth=1",
                    "--branch",
                    branch,
                    "--single-branch",
                    url,
                    dest,
                ]
            else:
                cmd = ["git", "clone", "--depth=1", url, dest]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                raise InstallError("Git clone failed: %s" % result.stderr.strip())
        except FileNotFoundError:
            raise InstallError(
                "Git is not installed. Please install git to use this feature."
            )
        except subprocess.TimeoutExpired:
            raise InstallError("Git clone timed out (120s)")

    def _git_head_commit(self, repo_dir):
        """Get the HEAD commit hash of a cloned repo."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=repo_dir,
            )
            return result.stdout.strip()
        except Exception:
            return ""

    def _git_ls_remote(self, url, branch=None):
        """Get the latest commit hash from a remote without cloning.

        @param branch: specific branch, or None to check HEAD (default branch)
        """
        try:
            if branch:
                ref = "refs/heads/" + branch
            else:
                ref = "HEAD"
            result = subprocess.run(
                ["git", "ls-remote", url, ref],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise InstallError("git ls-remote failed: %s" % result.stderr.strip())
            line = result.stdout.strip()
            if line:
                return line.split()[0]
            # Fallback: try HEAD if branch ref had no results
            if branch:
                result2 = subprocess.run(
                    ["git", "ls-remote", url, "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                line2 = result2.stdout.strip()
                if line2:
                    return line2.split()[0]
            return ""
        except FileNotFoundError:
            raise InstallError("Git is not installed")
        except subprocess.TimeoutExpired:
            raise InstallError("git ls-remote timed out")

    # ---- Validation helpers ----

    def _find_applet_root(self, clone_dir):
        """Find the applet root within a cloned repository.

        The applet can be either:
        1. At the repository root (index.html in root)
        2. In a single subdirectory

        @returns: path to directory containing index.html
        @raises InstallError: if no valid applet structure found
        """
        # Check root
        if os.path.isfile(os.path.join(clone_dir, "index.html")):
            return clone_dir

        # Check one level of subdirectories
        for entry in os.listdir(clone_dir):
            if entry.startswith("."):
                continue
            subdir = os.path.join(clone_dir, entry)
            if os.path.isdir(subdir) and os.path.isfile(
                os.path.join(subdir, "index.html")
            ):
                return subdir

        raise InstallError(
            "No valid applet found: repository must contain index.html "
            "at root or in a subdirectory"
        )

    def _validate_applet(self, applet_root):
        """Validate applet structure.

        @raises InstallError: if validation fails
        """
        index = os.path.join(applet_root, "index.html")
        if not os.path.isfile(index):
            raise InstallError("Missing index.html")

        manifest = os.path.join(applet_root, "manifest.json")
        if not os.path.isfile(manifest):
            raise InstallError(
                "Missing manifest.json — every applet must have a manifest"
            )

        # Validate manifest is valid JSON
        try:
            with open(manifest, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise InstallError("manifest.json must be a JSON object")
            if "name" not in data:
                raise InstallError('manifest.json must have a "name" field')
        except json.JSONDecodeError as e:
            raise InstallError("Invalid manifest.json: %s" % e)

        # Check for symlinks pointing outside
        for root, dirs, files in os.walk(applet_root):
            for name in files + dirs:
                full = os.path.join(root, name)
                if os.path.islink(full):
                    target = os.path.realpath(full)
                    if not target.startswith(os.path.realpath(applet_root)):
                        raise InstallError(
                            "Symlink points outside applet directory: %s" % name
                        )

    def _scan_suspicious(self, applet_root):
        """Scan for potentially suspicious files.

        @returns: list of warning strings (empty if clean)
        """
        warnings = []
        for root, dirs, files in os.walk(applet_root):
            # Skip .git
            dirs[:] = [d for d in dirs if d != ".git"]
            for fname in files:
                _, ext = os.path.splitext(fname.lower())
                if ext in WARN_EXTENSIONS_APPLET:
                    relpath = os.path.relpath(os.path.join(root, fname), applet_root)
                    warnings.append("Suspicious file: %s" % relpath)
        return warnings

    # ---- File helpers ----

    def _copy_applet(self, src, dest):
        """Copy applet files, excluding .git directory."""
        shutil.copytree(
            src,
            dest,
            ignore=shutil.ignore_patterns(
                ".git", ".gitignore", ".github", INSTALL_META
            ),
        )

    def _load_manifest(self, applet_dir):
        """Load manifest.json from an applet directory."""
        manifest_path = os.path.join(applet_dir, "manifest.json")
        if os.path.isfile(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _write_meta(self, applet_dir, meta):
        """Write installation metadata to .installed.json."""
        meta_path = os.path.join(applet_dir, INSTALL_META)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

    def _read_meta(self, name):
        """Read installation metadata for an applet.

        @returns: dict or None
        """
        meta_path = os.path.join(self.applets_dir, name, INSTALL_META)
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return None

    def _derive_name(self, url):
        """Derive an applet name from a Git URL."""
        # https://github.com/user/moonstone-kanban.git → moonstone-kanban
        clean = url.rstrip("/")
        if clean.endswith(".git"):
            clean = clean[:-4]
        name = clean.split("/")[-1]
        # Remove common prefixes
        for prefix in ("moonstone-applet-", "moonstone-webapp-", "moonstone-"):
            if name.startswith(prefix):
                name = name[len(prefix) :]
                break
        return name or "applet"

    @staticmethod
    def _sanitize_name(name):
        """Sanitize an applet name for use as a directory name."""
        # Replace spaces and special chars with hyphens
        safe = ""
        for c in name.lower():
            if c.isalnum() or c in "-_":
                safe += c
            elif c in " ./\\":
                safe += "-"
        # Collapse multiple hyphens
        while "--" in safe:
            safe = safe.replace("--", "-")
        return safe.strip("-") or "applet"

    @staticmethod
    def _now_iso():
        """Current time as ISO 8601 string."""
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()


class ServiceInstaller(AppletInstaller):
    """Manages installation of background services from Git.

    Extends AppletInstaller with service-specific validation:
    - manifest.json must have "type": "service"
    - Entry point (service.py) must exist instead of index.html
    - .py files are expected, not suspicious
    """

    def install_from_git(self, url, branch=None, name_override=None):
        """Install a service from a Git repository."""
        os.makedirs(self.applets_dir, exist_ok=True)

        tmpdir = tempfile.mkdtemp(prefix="moonstone-service-")
        clone_dir = os.path.join(tmpdir, "repo")

        try:
            self._git_clone(url, clone_dir, branch)
            service_root = self._find_service_root(clone_dir)
            self._validate_service(service_root)

            manifest = self._load_manifest(service_root)
            service_id = name_override or manifest.get("id") or self._derive_name(url)
            service_id = self._sanitize_name(service_id)

            dest = os.path.join(self.applets_dir, service_id)
            if os.path.exists(dest):
                raise InstallError(
                    'Service "%s" already exists. Uninstall first or use update.'
                    % service_id
                )

            commit = self._git_head_commit(clone_dir)
            warnings = self._scan_suspicious_service(service_root)

            # Copy service files (exclude .git, .venv)
            shutil.copytree(
                service_root,
                dest,
                ignore=shutil.ignore_patterns(
                    ".git",
                    ".gitignore",
                    ".github",
                    ".venv",
                    "__pycache__",
                    "*.pyc",
                    INSTALL_META,
                ),
            )

            meta = {
                "source": "git",
                "repository": url,
                "branch": branch,
                "commit": commit,
                "installed_at": self._now_iso(),
                "updated_at": self._now_iso(),
            }
            self._write_meta(dest, meta)

            manifest = self._load_manifest(dest)
            logger.info(
                'Installed service "%s" from %s (commit %s)',
                service_id,
                url,
                commit[:8],
            )

            result = {
                "name": service_id,
                "type": "service",
                "label": manifest.get("name", service_id),
                "version": manifest.get("version", "0.0.0"),
                "commit": commit[:12],
                "repository": url,
                "branch": branch,
            }
            if warnings:
                result["warnings"] = warnings
            return result

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def update(self, name):
        """Update a git-installed service to the latest version."""
        meta = self._read_meta(name)
        if not meta or meta.get("source") != "git":
            raise InstallError('Service "%s" is not installed from Git' % name)

        url = meta["repository"]
        branch = meta.get("branch")
        old_commit = meta.get("commit", "")

        dest = os.path.join(self.applets_dir, name)
        if not os.path.isdir(dest):
            raise InstallError('Service "%s" not found' % name)

        tmpdir = tempfile.mkdtemp(prefix="moonstone-service-update-")
        clone_dir = os.path.join(tmpdir, "repo")

        try:
            self._git_clone(url, clone_dir, branch)
            service_root = self._find_service_root(clone_dir)
            self._validate_service(service_root)

            new_commit = self._git_head_commit(clone_dir)

            if new_commit == old_commit:
                return {
                    "name": name,
                    "updated": False,
                    "message": "Already up to date",
                    "commit": old_commit[:12],
                }

            warnings = self._scan_suspicious_service(service_root)
            old_installed_at = meta.get("installed_at", self._now_iso())

            # Preserve _data and .venv directories
            data_backup = None
            venv_backup = None
            data_dir = os.path.join(dest, "_data")
            venv_dir = os.path.join(dest, ".venv")

            if os.path.isdir(data_dir):
                data_backup = tempfile.mkdtemp(prefix="moonstone-svc-data-")
                shutil.copytree(data_dir, os.path.join(data_backup, "_data"))
            if os.path.isdir(venv_dir):
                venv_backup = venv_dir  # just remember path, don't move

            # Remove old files (except .venv)
            for item in os.listdir(dest):
                item_path = os.path.join(dest, item)
                if item == ".venv":
                    continue
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                else:
                    os.remove(item_path)

            # Copy new files
            for item in os.listdir(service_root):
                if item in (
                    ".git",
                    ".gitignore",
                    ".github",
                    ".venv",
                    "__pycache__",
                    INSTALL_META,
                ):
                    continue
                src_path = os.path.join(service_root, item)
                dst_path = os.path.join(dest, item)
                if os.path.isdir(src_path):
                    shutil.copytree(
                        src_path,
                        dst_path,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                    )
                else:
                    shutil.copy2(src_path, dst_path)

            # Restore _data
            if data_backup:
                backup_data = os.path.join(data_backup, "_data")
                if os.path.isdir(backup_data):
                    if os.path.isdir(data_dir):
                        shutil.rmtree(data_dir)
                    shutil.copytree(backup_data, data_dir)
                shutil.rmtree(data_backup, ignore_errors=True)

            new_meta = {
                "source": "git",
                "repository": url,
                "branch": branch,
                "commit": new_commit,
                "installed_at": old_installed_at,
                "updated_at": self._now_iso(),
            }
            self._write_meta(dest, new_meta)

            # Invalidate venv deps marker so next start re-installs
            marker = os.path.join(dest, ".venv", ".deps_installed")
            if os.path.isfile(marker):
                os.remove(marker)

            manifest = self._load_manifest(dest)
            logger.info(
                'Updated service "%s" from %s to %s',
                name,
                old_commit[:8],
                new_commit[:8],
            )

            result = {
                "name": name,
                "updated": True,
                "old_commit": old_commit[:12],
                "new_commit": new_commit[:12],
                "version": manifest.get("version", "0.0.0"),
            }
            if warnings:
                result["warnings"] = warnings
            return result

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _find_service_root(self, clone_dir):
        """Find the service root within a cloned repository.

        Looks for manifest.json with type=service + entry point file.
        """
        manifest = self._load_manifest(clone_dir)
        if manifest.get("type") == "service":
            entry = manifest.get("entry", "service.py")
            if os.path.isfile(os.path.join(clone_dir, entry)):
                return clone_dir

        # Check subdirectories
        for entry_name in os.listdir(clone_dir):
            if entry_name.startswith("."):
                continue
            subdir = os.path.join(clone_dir, entry_name)
            if not os.path.isdir(subdir):
                continue
            manifest = self._load_manifest(subdir)
            if manifest.get("type") == "service":
                entry = manifest.get("entry", "service.py")
                if os.path.isfile(os.path.join(subdir, entry)):
                    return subdir

        raise InstallError(
            "No valid service found: repository must contain manifest.json "
            'with "type": "service" and an entry point script'
        )

    def _validate_service(self, service_root):
        """Validate service structure."""
        manifest_path = os.path.join(service_root, "manifest.json")
        if not os.path.isfile(manifest_path):
            raise InstallError("Missing manifest.json")

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise InstallError("manifest.json must be a JSON object")
            if "name" not in data:
                raise InstallError('manifest.json must have a "name" field')
            if data.get("type") != "service":
                raise InstallError('manifest.json must have "type": "service"')
        except json.JSONDecodeError as e:
            raise InstallError("Invalid manifest.json: %s" % e)

        entry = data.get("entry", "service.py")
        entry_path = os.path.join(service_root, entry)
        if not os.path.isfile(entry_path):
            raise InstallError("Entry point not found: %s" % entry)

        # Check for symlinks pointing outside
        for root, dirs, files in os.walk(service_root):
            for name in files + dirs:
                full = os.path.join(root, name)
                if os.path.islink(full):
                    target = os.path.realpath(full)
                    if not target.startswith(os.path.realpath(service_root)):
                        raise InstallError(
                            "Symlink points outside service directory: %s" % name
                        )

    def _scan_suspicious_service(self, service_root):
        """Scan for suspicious files in a service (binaries only)."""
        warnings = []
        for root, dirs, files in os.walk(service_root):
            dirs[:] = [d for d in dirs if d not in (".git", ".venv", "__pycache__")]
            for fname in files:
                _, ext = os.path.splitext(fname.lower())
                if ext in WARN_EXTENSIONS_SERVICE:
                    relpath = os.path.relpath(os.path.join(root, fname), service_root)
                    warnings.append("Suspicious file: %s" % relpath)
        return warnings
