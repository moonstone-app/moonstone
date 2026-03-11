# -*- coding: UTF-8 -*-

"""Applet discovery and management for WebBridge.

Discovers and loads web applets from the applets directory.
Each applet is a folder with at minimum an index.html file
and optionally a manifest.json with metadata.
"""

import json
import logging
import os
import sys
import mimetypes

from moonstone.webbridge.installer import INSTALL_META

logger = logging.getLogger("moonstone.webbridge")

# Ensure common web mimetypes are registered
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("text/html", ".html")


class Applet:
    """Represents a discovered web applet."""

    def __init__(self, name, path, manifest=None, source_info=None):
        self.name = name
        self.path = path
        self.manifest = manifest or {}
        self.source_info = source_info

    @property
    def label(self):
        return self.manifest.get("name", self.name)

    @property
    def description(self):
        return self.manifest.get("description", "")

    @property
    def icon(self):
        return self.manifest.get("icon", None)

    @property
    def version(self):
        return self.manifest.get("version", "0.0.0")

    @property
    def author(self):
        return self.manifest.get("author", "")

    def to_dict(self):
        d = {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "icon": self.icon,
            "version": self.version,
            "author": self.author,
            "source": "local",
        }
        if self.source_info and self.source_info.get("source") == "git":
            d["source"] = "git"
            d["repository"] = self.source_info.get("repository", "")
            d["branch"] = self.source_info.get("branch", "main")
            d["commit"] = self.source_info.get("commit", "")[:12]
            d["installed_at"] = self.source_info.get("installed_at", "")
            d["updated_at"] = self.source_info.get("updated_at", "")
        return d


class AppletManager:
    """Discovers and manages web applets."""

    def __init__(self, applets_dir):
        """Constructor.
        @param applets_dir: path to the directory containing applets
        """
        self.applets_dir = applets_dir
        self._applets = {}
        logger.info("AppletManager initialized: %s", applets_dir)
        self.refresh()

    def refresh(self):
        """Re-scan the applets directory for applets."""
        self._applets = {}

        if not os.path.isdir(self.applets_dir):
            logger.debug("Applets directory does not exist: %s", self.applets_dir)
            return

        for entry in sorted(os.listdir(self.applets_dir)):
            if entry.startswith("_") or entry.startswith("."):
                continue

            applet_path = os.path.join(self.applets_dir, entry)
            if not os.path.isdir(applet_path):
                continue

            index_file = os.path.join(applet_path, "index.html")
            if not os.path.isfile(index_file):
                logger.debug("Skipping %s: no index.html", entry)
                continue

            manifest = None
            manifest_file = os.path.join(applet_path, "manifest.json")
            if os.path.isfile(manifest_file):
                try:
                    with open(manifest_file, "r", encoding="utf-8") as f:
                        manifest = json.load(f)
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning(
                        "Failed to load manifest for applet %s: %s", entry, e
                    )

            # Load installation metadata if present
            source_info = None
            meta_file = os.path.join(applet_path, INSTALL_META)
            if os.path.isfile(meta_file):
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        source_info = json.load(f)
                except (json.JSONDecodeError, OSError):
                    pass

            applet = Applet(entry, applet_path, manifest, source_info)
            self._applets[entry] = applet
            logger.debug("Discovered applet: %s (%s)", entry, applet.label)

    def list_applets(self):
        """Returns a list of discovered applets as dicts."""
        return [a.to_dict() for a in self._applets.values()]

    def get_applet(self, name):
        """Get an applet by name.
        @param name: applet directory name
        @returns: Applet object or None
        """
        return self._applets.get(name)

    def serve_file(self, applet_name, file_path):
        """Read a file from an applet directory.

        @param applet_name: the applet name
        @param file_path: relative file path within the applet
        @returns: tuple (content_bytes, content_type) or None if not found
        """
        applet = self._applets.get(applet_name)
        if applet is None:
            return None

        # Sanitize path - prevent directory traversal
        file_path = file_path.lstrip("/")
        if ".." in file_path or file_path.startswith("/"):
            return None

        full_path = os.path.join(applet.path, file_path)

        # Resolve symlinks and ensure we're still within applet dir
        try:
            real_path = os.path.realpath(full_path)
            real_applet = os.path.realpath(applet.path)
            if (
                not real_path.startswith(real_applet + os.sep)
                and real_path != real_applet
            ):
                return None
        except (OSError, ValueError):
            return None

        if not os.path.isfile(full_path):
            return None

        content_type = mimetypes.guess_type(full_path)[0] or "application/octet-stream"

        try:
            with open(full_path, "rb") as f:
                content = f.read()
            return content, content_type
        except OSError as e:
            logger.warning("Failed to read applet file %s: %s", full_path, e)
            return None

    def get_static_dir(self):
        """Returns path to the bundled static files directory.

        Supports both normal execution and PyInstaller frozen binaries.
        """
        # PyInstaller frozen binary: data extracted to sys._MEIPASS
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            static = os.path.join(sys._MEIPASS, "moonstone", "webbridge", "static")
            if os.path.isdir(static):
                return static
        return os.path.join(os.path.dirname(__file__), "static")

    def serve_static(self, file_path):
        """Serve a file from the bundled static directory.

        @param file_path: relative file path
        @returns: tuple (content_bytes, content_type) or None
        """
        static_dir = self.get_static_dir()
        file_path = file_path.lstrip("/")
        if ".." in file_path:
            return None

        full_path = os.path.join(static_dir, file_path)

        try:
            real_path = os.path.realpath(full_path)
            real_static = os.path.realpath(static_dir)
            if (
                not real_path.startswith(real_static + os.sep)
                and real_path != real_static
            ):
                return None
        except (OSError, ValueError):
            return None

        if not os.path.isfile(full_path):
            return None

        content_type = mimetypes.guess_type(full_path)[0] or "application/octet-stream"

        try:
            with open(full_path, "rb") as f:
                content = f.read()
            return content, content_type
        except OSError as e:
            logger.warning("Failed to read static file %s: %s", full_path, e)
            return None
