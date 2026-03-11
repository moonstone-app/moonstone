# -*- coding: utf-8 -*-
"""Notebook class for Moonstone.

Standalone notebook module — provides CRUD operations on pages,
config reading, signal emission, and attachment handling.
"""

import os
import re
import shutil
import logging
import configparser
import threading

from moonstone.signals import SignalEmitter
from moonstone.errors import (
    PageNotFoundError,
    PageExistsError,
    PageReadOnlyError,
    TrashNotSupportedError,
)
from moonstone.notebook.page import Path, Page, SourceFile
from moonstone.notebook.layout import FilesLayout
from moonstone.formats import get_format

logger = logging.getLogger("moonstone.notebook")


def natural_sort_key(text):
    """Natural sort key: "Page 2" < "Page 10"."""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", text)]


class FolderLike:
    """Simple object with .path attribute for duck-typing."""

    def __init__(self, path):
        self.path = path

    def __str__(self):
        return self.path


class NotebookConfig:
    """Reads and provides access to notebook.moon config.

    NotebookConfig interface:
        config['Notebook'] → dict-like with name, interwiki, home, icon
    """

    def __init__(self, path):
        """@param path: path to the notebook directory (not the file)"""
        self._path = path
        from moonstone.profiles import get_all_config_markers

        NOTEBOOK_CONFIGS = get_all_config_markers()
        # Prefer notebook.moon, fall back to other profile configs
        self._file = os.path.join(path, NOTEBOOK_CONFIGS[0])
        for cfg_name in NOTEBOOK_CONFIGS:
            candidate = os.path.join(path, cfg_name)
            if os.path.isfile(candidate):
                self._file = candidate
                break
        self._data = {}
        self._read()

    def _read(self):
        if not os.path.isfile(self._file):
            self._data = {
                "Notebook": {
                    "name": os.path.basename(self._path),
                    "interwiki": "",
                    "home": "Home",
                    "icon": "",
                }
            }
            return

        config = configparser.RawConfigParser()
        try:
            config.read(self._file, encoding="utf-8")
        except Exception:
            pass

        self._data = {}
        for section in config.sections():
            self._data[section] = dict(config[section])

        # Ensure defaults
        nb = self._data.setdefault("Notebook", {})
        nb.setdefault("name", os.path.basename(self._path))
        nb.setdefault("interwiki", "")
        nb.setdefault("home", "Home")
        nb.setdefault("icon", "")

    def __getitem__(self, section):
        return self._data.get(section, {})

    def __contains__(self, section):
        return section in self._data

    def get(self, section, key=None, default=None):
        if key is None:
            return self._data.get(section, default)
        return self._data.get(section, {}).get(key, default)

    def write(self):
        config = configparser.ConfigParser()
        for section, values in self._data.items():
            config[section] = values
        with open(self._file, "w", encoding="utf-8") as f:
            config.write(f)


class Notebook(SignalEmitter):
    """Main Notebook class.

    Provides the duck-typing interface expected by WebBridge api.py:
    - .readonly, .folder.path, .config['Notebook'], .index
    - .pages (PagesView proxy)
    - get_page, store_page, delete_page, trash_page, move_page
    - get_attachments_dir, suggest_link
    - connect/emit for signals
    """

    def __init__(self, folder_path, profile=None):
        super().__init__()

        self.folder = FolderLike(os.path.abspath(folder_path))
        self.config = NotebookConfig(self.folder.path)

        # Auto-detect or use provided vault profile
        if profile is None:
            from moonstone.profiles import auto_detect

            self.profile = auto_detect(self.folder.path)

            # If folder is completely empty and detected as default (Moonstone),
            # mark it explicitly so subsequent loads also see it as Moonstone
            if self.profile.name == "moonstone":
                try:
                    if not os.listdir(self.folder.path):
                        # It's an empty directory, let's create the notebook.moon marker
                        marker_path = os.path.join(self.folder.path, "notebook.moon")
                        with open(marker_path, "w", encoding="utf-8") as f:
                            f.write(
                                "[Notebook]\nname = %s\n"
                                % os.path.basename(self.folder.path)
                            )
                except OSError:
                    pass
        else:
            self.profile = profile

        logger.info(
            "Vault profile: %s (%s)", self.profile.display_name, self.profile.name
        )

        # Apply profile settings, with config overrides
        eol = self.config.get("Notebook", "endofline", "unix")
        ext = self.config.get(
            "Notebook", "default_file_extension", self.profile.file_extension
        )
        fmt = self.profile.default_format

        self.layout = FilesLayout(
            root_folder=self.folder.path,
            endofline=eol,
            default_extension=ext,
            default_format=fmt,
            use_filename_spaces=self.profile.use_filename_spaces,
            profile=self.profile,
        )

        # Load vault-specific config (e.g., Obsidian's app.json)
        if hasattr(self.profile, "load_vault_config"):
            self.profile.load_vault_config(self.folder.path)

        # Page cache
        self._page_cache = {}
        self._lock = threading.RLock()

        # Index (lazy init)
        self._index = None

        # Read-only flag
        self._readonly = not os.access(self.folder.path, os.W_OK)

    @property
    def readonly(self):
        return self._readonly

    @readonly.setter
    def readonly(self, value):
        self._readonly = value

    @property
    def index(self):
        if self._index is None:
            from moonstone.notebook.index import Index

            cache_dir = os.path.join(self.folder.path, ".moonstone")
            os.makedirs(cache_dir, exist_ok=True)
            db_path = os.path.join(cache_dir, "index.db")
            self._index = Index(
                db_path, self.layout, self.folder.path, profile=self.profile
            )
        return self._index

    @property
    def pages(self):
        """PagesView proxy — provides list_pages, walk, lookup, etc."""
        from moonstone.notebook.index.pages import PagesView

        return PagesView.new_from_index(self.index)

    def get_page(self, path):
        """Get a Page object for the given path.

        @param path: a Path object
        @returns: Page object
        """
        if isinstance(path, str):
            path = Path(path)

        with self._lock:
            # Check cache — invalidate if file changed on disk
            if path.name in self._page_cache:
                cached = self._page_cache[path.name]
                try:
                    disk_mtime = cached.source_file.mtime()
                    cached_mtime = cached._cached_mtime
                    if disk_mtime is not None and disk_mtime != cached_mtime:
                        # File changed externally — drop cache
                        del self._page_cache[path.name]
                    else:
                        return cached
                except (OSError, AttributeError):
                    return cached

            file_path, folder_path = self.layout.map_page(path)
            source = SourceFile(file_path)

            # Determine haschildren
            haschildren = (
                os.path.isdir(folder_path)
                and any(
                    f.endswith(self.layout.default_extension)
                    for f in os.listdir(folder_path)
                    if os.path.isfile(os.path.join(folder_path, f))
                )
                if os.path.isdir(folder_path)
                else False
            )

            page = Page(
                path=path,
                haschildren=haschildren,
                file=source,
                folder=folder_path,
                format=self.layout.default_format_name,
            )

            if self._readonly:
                page._readonly = True

            self._page_cache[path.name] = page
            return page

    def store_page(self, page):
        """Save a page to disk and update the index.

        @param page: a Page object with modified content
        """
        if self.readonly:
            raise PageReadOnlyError(page)

        with self._lock:
            page._store()
            page.set_modified(False)

            # Update index
            try:
                tree = page.get_parsetree()
                self.index.update_page(page, tree)
            except Exception:
                logger.debug("Index update failed for %s", page.name, exc_info=True)

            # Emit signal
            self.emit("stored-page", page)

    def delete_page(self, path, update_links=False):
        """Delete a page from disk and index."""
        if self.readonly:
            raise PageReadOnlyError(path)

        if isinstance(path, str):
            path = Path(path)

        with self._lock:
            file_path, folder_path = self.layout.map_page(path)

            # Remove file
            if os.path.isfile(file_path):
                os.remove(file_path)

            # Remove folder if empty and it's not root
            if os.path.isdir(folder_path) and folder_path != self.folder.path:
                try:
                    # Only remove if empty
                    if not os.listdir(folder_path):
                        os.rmdir(folder_path)
                except OSError:
                    pass

            # Update index
            try:
                self.index.remove_page(path)
            except Exception:
                logger.debug("Index remove failed for %s", path.name, exc_info=True)

            # Clean cache
            self._page_cache.pop(path.name, None)

            self.emit("deleted-page", path)

    def trash_page(self, path, update_links=False):
        """Move page to trash (or delete if trash not available)."""
        if isinstance(path, str):
            path = Path(path)

        try:
            import send2trash

            file_path, folder_path = self.layout.map_page(path)
            if os.path.isfile(file_path):
                send2trash.send2trash(file_path)

            # Update index
            try:
                self.index.remove_page(path)
            except Exception:
                pass

            self._page_cache.pop(path.name, None)
            self.emit("deleted-page", path)
        except ImportError:
            # Fallback to delete
            self.delete_page(path, update_links)

    def move_page(self, oldpath, newpath, update_links=True, update_heading=False):
        """Move/rename a page."""
        if self.readonly:
            raise PageReadOnlyError(oldpath)

        if isinstance(oldpath, str):
            oldpath = Path(oldpath)
        if isinstance(newpath, str):
            newpath = Path(newpath)

        with self._lock:
            old_file, old_folder = self.layout.map_page(oldpath)
            new_file, new_folder = self.layout.map_page(newpath)

            if not os.path.isfile(old_file):
                raise PageNotFoundError(oldpath)

            if os.path.isfile(new_file):
                raise PageExistsError(newpath)

            # Create target directory
            os.makedirs(os.path.dirname(new_file), exist_ok=True)

            # Move file
            shutil.move(old_file, new_file)

            # Move folder if exists (children pages)
            if os.path.isdir(old_folder):
                if not os.path.isdir(new_folder):
                    shutil.move(old_folder, new_folder)
                else:
                    # Merge folders
                    for item in os.listdir(old_folder):
                        shutil.move(
                            os.path.join(old_folder, item),
                            os.path.join(new_folder, item),
                        )
                    os.rmdir(old_folder)

            # Clean up empty parent dirs
            old_parent = os.path.dirname(old_file)
            while old_parent != self.folder.path:
                try:
                    if not os.listdir(old_parent):
                        os.rmdir(old_parent)
                        old_parent = os.path.dirname(old_parent)
                    else:
                        break
                except OSError:
                    break

            # Update index
            try:
                self.index.move_page(oldpath, newpath)
            except Exception:
                logger.debug("Index move failed", exc_info=True)

            # Update links in other pages if requested
            if update_links:
                try:
                    from moonstone.notebook.content_updater import update_links_on_move

                    update_links_on_move(self, oldpath, newpath)
                except Exception:
                    logger.debug("Link update after move failed", exc_info=True)

            # Clear cache
            self._page_cache.pop(oldpath.name, None)
            self._page_cache.pop(newpath.name, None)

            self.emit("moved-page", oldpath, newpath)

    def get_attachments_dir(self, path):
        """Get the attachments folder for a page.

        Uses the profile's attachment settings:
        - Moonstone: page subfolder (same name as page file)
        - Obsidian: vault root or configured folder (flat mode)
        """
        if isinstance(path, str):
            path = Path(path)

        # Use profile's attachment path if it has a custom method
        if hasattr(self.profile, "get_attachments_path"):
            from moonstone.notebook.layout import FilesAttachmentFolder

            att_path = self.profile.get_attachments_path(path.name, self.folder.path)
            return FilesAttachmentFolder(att_path, self.layout.is_source_file)

        # Fallback: Moonstone-style page subfolder
        return self.layout.get_attachments_folder(path)

    def suggest_link(self, source, text):
        """Suggest a link target for the given text.

        @param source: source Path
        @param text: text to match
        @returns: Path or None
        """
        try:
            results = list(self.pages.match_all_pages(text, limit=1))
            if results:
                return Path(results[0].name)
        except Exception:
            pass
        return None
