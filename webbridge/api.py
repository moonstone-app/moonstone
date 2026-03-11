# -*- coding: UTF-8 -*-

"""REST API handlers for WebBridge.

Provides endpoints for reading, writing, searching pages and
managing attachments in the Moonstone notebook.

ALL notebook operations are dispatched to the the main thread via
idle_add() for thread safety — SQLite objects are bound
to the thread that created them (the main thread).
"""

import json
import logging
import os
import threading
import traceback

from moonstone.mainloop import idle_add

logger = logging.getLogger("moonstone.webbridge")


class _WebBridgeLinker(object):
    """Minimal linker for page.dump('html') that passes links through as-is.

    page.dump() calls linker.set_path(page) before dumping, so we must
    implement set_path().  The HTML dumper also calls link(), img(),
    resource(), page_object(), file_object() and resolve_source_file().
    We return links unchanged — web applets handle navigation themselves.
    """

    def __init__(self):
        self.path = None

    def set_path(self, page):
        self.path = page

    def link(self, link):
        from moonstone.parse.links import link_type as _link_type

        t = _link_type(link)
        if t == "mailto" and not link.startswith("mailto:"):
            return "mailto:" + link
        return link

    def img(self, src):
        return src

    def resource(self, path):
        return path

    def resolve_source_file(self, link):
        return None

    def page_object(self, path):
        return path.name if hasattr(path, "name") else str(path)

    def file_object(self, file):
        return file.path if hasattr(file, "path") else str(file)


def _run_synchronized(func, timeout=15):
    """Run a function on the main thread and return the result.

    @param func: callable that returns (status, headers, body)
    @param timeout: max seconds to wait
    @returns: (status, headers, body) tuple
    """
    result = {"value": None, "error": None, "done": False}
    event = threading.Event()

    def _wrapper():
        try:
            result["value"] = func()
        except Exception as e:
            logger.exception("Error in main thread dispatch")
            result["error"] = e
        finally:
            result["done"] = True
            event.set()
        return False  # Don't repeat idle callback

    idle_add(_wrapper)
    event.wait(timeout=timeout)

    if not result["done"]:
        return 504, {}, {"error": "Timeout waiting for main thread operation"}
    if result["error"]:
        return 500, {}, {"error": str(result["error"])}
    return result["value"]


class NotebookAPI:
    """REST API handler for Moonstone Notebook operations.

    This class provides methods that map to REST endpoints.
    All methods return (status_code, headers_dict, body) tuples.
    All notebook access is dispatched to the main thread.
    """

    def __init__(
        self,
        notebook,
        app,
        event_manager=None,
        applet_manager=None,
        service_manager=None,
    ):
        self.notebook = notebook
        self.app = app
        self.event_manager = event_manager
        self.applet_manager = applet_manager
        self.service_manager = service_manager

    def _prepare_page_for_write(self, page):
        """Ensure page etag is initialized before writing.

        Uses etags for optimistic concurrency on the file system.
        The etag must be initialized by reading the file before writing.
        For new pages (no file on disk), we handle the missing etag.
        """
        if page._last_etag is not None:
            return  # Already initialized

        # For existing pages, read content to initialize etag
        if page.hascontent and hasattr(page, "source_file"):
            try:
                page.get_parsetree()
            except Exception:
                pass

        # Still None? Try reading the source file directly
        if page._last_etag is None and hasattr(page, "source_file"):
            sf = page.source_file
            if sf.exists():
                try:
                    _, page._last_etag = sf.readlines_with_etag()
                except Exception:
                    try:
                        page._last_etag = sf._get_etag()
                    except Exception:
                        pass

    # Formats that have a Parser and can be used for writing
    _WRITABLE_FORMATS = ("wiki", "plain", "markdown")

    def _validate_write_format(self, format):
        """Check if format supports parsing (writing). Returns error tuple or None."""
        if format not in self._WRITABLE_FORMATS:
            return (
                400,
                {},
                {
                    "error": 'Format "%s" cannot be used for writing. '
                    "Only %s formats support parsing input."
                    % (format, ", ".join(self._WRITABLE_FORMATS)),
                    "supported_write_formats": list(self._WRITABLE_FORMATS),
                },
            )
        return None

    def _get_profile_format(self):
        """Get the default write format from the notebook profile."""
        profile = getattr(self.notebook, "profile", None)
        if profile:
            return profile.default_format
        return "wiki"

    def _store_page_safe(self, page):
        """Store a page, handling etag edge cases for new pages."""
        try:
            self.notebook.store_page(page)
        except AssertionError as e:
            if "etag" in str(e).lower():
                # New page with no file on disk — write directly
                logger.debug("Etag not initialized for %s, writing directly", page.name)
                try:
                    tree = page.get_parsetree()
                    if tree is not None:
                        from moonstone.formats import get_format

                        fmt = get_format("wiki")
                        lines = fmt.Dumper().dump(tree)
                        if hasattr(page, "source_file"):
                            page.source_file.writelines(lines)
                            page._last_etag = page.source_file._get_etag()
                        # Now store_page should work for index update
                        try:
                            self.notebook.store_page(page)
                        except Exception:
                            pass  # Index update may fail but file is written
                except Exception:
                    logger.exception("Direct write also failed for %s", page.name)
                    raise
            else:
                raise

    # ---- Notebook info ----

    def get_notebook_info(self):
        """GET /api/notebook — return notebook metadata"""

        def _do():
            config = self.notebook.config["Notebook"]
            data = {
                "name": str(config.get("name", "") or ""),
                "interwiki": str(config.get("interwiki", "") or ""),
                "home": str(config.get("home", "Home") or "Home"),
                "icon": str(config.get("icon", "") or ""),
                "readonly": bool(self.notebook.readonly),
                "folder": self.notebook.folder.path if self.notebook.folder else None,
            }
            # Include vault profile info if available
            if hasattr(self.notebook, "profile") and self.notebook.profile:
                data["profile"] = self.notebook.profile.to_dict()
            return 200, {}, data

        return _run_synchronized(_do)

    # ---- Export API ----

    def export_page(self, page_path, format="html", template=None):
        """Export a page using Moonstone's export engine with optional template."""

        def _do():
            try:
                from moonstone.notebook import Path

                page_path_clean = page_path.replace("/", ":")
                path = Path(page_path_clean)
                page = self.notebook.get_page(path)
                if not page.hascontent:
                    return 404, {}, {"error": "Page not found", "page": page_path_clean}

                # Simple format dump (like get_page but explicit export)
                supported = ("wiki", "html", "plain", "markdown")
                if format not in supported:
                    return (
                        400,
                        {},
                        {
                            "error": "Unsupported format: %s" % format,
                            "supported": list(supported),
                        },
                    )

                try:
                    linker = _WebBridgeLinker()
                    lines = page.dump(format, linker=linker)
                    content = "".join(lines)
                except Exception as e:
                    logger.warning(
                        "export_page dump(%s) failed for %s: %s", format, page_path, e
                    )
                    # Fallback to wiki
                    lines = page.dump("wiki")
                    content = "".join(lines)
                    format_used = "wiki"
                else:
                    format_used = format

                mime_types = {
                    "html": "text/html",
                    "wiki": "text/plain",
                    "plain": "text/plain",
                    "markdown": "text/markdown",
                    "latex": "application/x-latex",
                    "rst": "text/x-rst",
                }

                return (
                    200,
                    {},
                    {
                        "name": page_path_clean,
                        "format": format_used,
                        "content": content,
                        "content_type": mime_types.get(format_used, "text/plain"),
                        "length": len(content),
                    },
                )
            except Exception as e:
                logger.exception("export_page error")
                return 500, {}, {"error": str(e)}

        return _run_synchronized(_do)

    def export_page_raw(self, page_path, format="html"):
        """Export page and return raw content with proper MIME type (for download)."""

        def _do():
            try:
                from moonstone.notebook import Path

                page_path_clean = page_path.replace("/", ":")
                path = Path(page_path_clean)
                page = self.notebook.get_page(path)
                if not page.hascontent:
                    return 404, {}, {"error": "Page not found"}

                supported = ("wiki", "html", "plain", "markdown")
                if format not in supported:
                    return (
                        400,
                        {},
                        {
                            "error": "Unsupported format: %s" % format,
                            "supported": list(supported),
                        },
                    )

                try:
                    linker = _WebBridgeLinker()
                    lines = page.dump(format, linker=linker)
                    content = "".join(lines)
                except Exception:
                    lines = page.dump("wiki")
                    content = "".join(lines)

                mime_types = {
                    "html": "text/html",
                    "wiki": "text/plain",
                    "plain": "text/plain",
                    "markdown": "text/markdown",
                    "latex": "application/x-latex",
                    "rst": "text/x-rst",
                }
                ext_map = {
                    "html": ".html",
                    "wiki": ".txt",
                    "plain": ".txt",
                    "markdown": ".md",
                    "latex": ".tex",
                    "rst": ".rst",
                }
                ct = mime_types.get(format, "text/plain")
                ext = ext_map.get(format, ".txt")
                filename = page_path_clean.replace(":", "_") + ext
                headers = {
                    "Content-Type": ct,
                    "Content-Disposition": 'attachment; filename="%s"' % filename,
                }
                return 200, headers, content  # raw string, not JSON
            except Exception as e:
                return 500, {}, {"error": str(e)}

        return _run_synchronized(_do)

    # ---- Templates API ----

    def list_templates(self, format_filter=None):
        """List available export templates."""
        import os

        try:
            from moonstone.config import data_dirs

            templates = {}
            for dir in data_dirs("templates"):
                tpl_base = str(dir)
                if not os.path.isdir(tpl_base):
                    continue
                for fmt_dir in sorted(os.listdir(tpl_base)):
                    fmt_path = os.path.join(tpl_base, fmt_dir)
                    if not os.path.isdir(fmt_path):
                        continue
                    if format_filter and fmt_dir != format_filter:
                        continue
                    if fmt_dir not in templates:
                        templates[fmt_dir] = []
                    for fname in sorted(os.listdir(fmt_path)):
                        # Template files have extensions matching the format
                        if (
                            os.path.isfile(os.path.join(fmt_path, fname))
                            and "." in fname
                        ):
                            name = fname.rsplit(".", 1)[0]
                            if name not in [t["name"] for t in templates[fmt_dir]]:
                                templates[fmt_dir].append(
                                    {
                                        "name": name,
                                        "file": fname,
                                        "format": fmt_dir,
                                    }
                                )

            result = []
            for fmt, tpls in sorted(templates.items()):
                for t in tpls:
                    result.append(t)

            return (
                200,
                {},
                {
                    "templates": result,
                    "count": len(result),
                    "formats": sorted(templates.keys()),
                },
            )
        except Exception as e:
            logger.exception("list_templates error")
            return 500, {}, {"error": str(e)}

    # ---- Sitemap API ----

    def get_sitemap(self, format="xml", base_url=None):
        """Generate a sitemap of all pages."""
        _base_url = base_url or "http://localhost:8090"

        def _do():
            try:
                from moonstone.notebook.index.pages import PagesView

                pagesview = PagesView.new_from_index(self.notebook.index)
                pages = []

                for pinfo in pagesview.walk():
                    entry = {
                        "name": pinfo.name,
                        "basename": pinfo.basename,
                        "path": pinfo.name.replace(":", "/"),
                    }
                    pages.append(entry)

                if format == "xml":
                    # Standard sitemap.org XML
                    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
                    lines.append(
                        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                    )
                    for p in pages:
                        lines.append(
                            "  <url><loc>%s/api/page/%s</loc></url>"
                            % (_base_url.rstrip("/"), p["path"])
                        )
                    lines.append("</urlset>")
                    xml_content = "\n".join(lines)
                    return 200, {"Content-Type": "application/xml"}, xml_content

                else:
                    # JSON format
                    return (
                        200,
                        {},
                        {
                            "pages": pages,
                            "count": len(pages),
                            "format": "json",
                        },
                    )
            except Exception as e:
                logger.exception("get_sitemap error")
                return 500, {}, {"error": str(e)}

        return _run_synchronized(_do)

    # ---- Tag Management ----

    def add_tag_to_page(self, page_path, tag_name):
        """Add a tag to a page by appending @tag to the content."""

        def _do():
            try:
                from moonstone.notebook import Path

                page_path_clean = page_path.replace("/", ":")
                path = Path(page_path_clean)
                page = self.notebook.get_page(path)

                self._prepare_page_for_write(page)

                # Use profile for tag syntax
                profile = getattr(self.notebook, "profile", None)
                tag_prefix = profile.tag_prefix if profile else "@"
                tag_regex = profile.tag_regex if profile else r"(?<!\w)@(\w+)"
                fmt = self._get_profile_format()

                # Normalize tag
                tag_bare = tag_name.lstrip(tag_prefix)
                tag = (
                    profile.format_tag(tag_bare) if profile else (tag_prefix + tag_bare)
                )

                # Get current content
                try:
                    lines = page.dump(fmt)
                    content = "".join(lines)
                except Exception:
                    content = ""

                # Check if tag already exists (case-insensitive)
                import re

                existing_tags = re.findall(tag_regex, content)
                if tag_bare.lower() in [t.lower() for t in existing_tags]:
                    return (
                        200,
                        {},
                        {
                            "ok": True,
                            "page": page_path_clean,
                            "tag": tag_bare,
                            "action": "already_exists",
                        },
                    )

                # Append tag at end of content
                if content and not content.endswith("\n"):
                    content += "\n"
                content += tag + "\n"

                page.parse(fmt, content)
                self._store_page_safe(page)

                if self.app:
                    self.app.notify_page_saved(page.name)

                return (
                    200,
                    {},
                    {
                        "ok": True,
                        "page": page_path_clean,
                        "tag": tag_bare,
                        "action": "added",
                    },
                )
            except Exception as e:
                if "read-only" in str(e).lower() or "readonly" in str(e).lower():
                    return 403, {}, {"error": "Page is read-only"}
                logger.exception("add_tag error")
                return 500, {}, {"error": str(e)}

        return _run_synchronized(_do)

    def remove_tag_from_page(self, page_path, tag_name):
        """Remove a tag from a page by removing @tag from content."""

        def _do():
            try:
                import re
                from moonstone.notebook import Path

                page_path_clean = page_path.replace("/", ":")
                path = Path(page_path_clean)
                page = self.notebook.get_page(path)

                if not page.hascontent:
                    return 404, {}, {"error": "Page not found"}

                self._prepare_page_for_write(page)

                # Use profile for tag syntax
                profile = getattr(self.notebook, "profile", None)
                tag_prefix = profile.tag_prefix if profile else "@"
                fmt = self._get_profile_format()

                # Normalize tag
                tag_bare = tag_name.lstrip(tag_prefix)

                # Get current content
                lines = page.dump(fmt)
                content = "".join(lines)

                # Remove tag (case-insensitive, preserve surrounding)
                escaped_prefix = re.escape(tag_prefix)
                original = content

                # First check if the tag exists
                import re

                if not re.search(
                    r"(?<!\w)" + escaped_prefix + re.escape(tag_bare) + r"\b",
                    content,
                    flags=re.IGNORECASE,
                ):
                    # Maybe it's in a block property
                    if not re.search(
                        r"^[ \t]*tags::.*?\b" + re.escape(tag_bare) + r"\b",
                        content,
                        flags=re.IGNORECASE | re.MULTILINE,
                    ):
                        return (
                            404,
                            {},
                            {
                                "error": "Tag %s%s not found on page %s"
                                % (tag_prefix, tag_bare, page_path_clean)
                            },
                        )

                # Remove standalone tag on its own line
                content = re.sub(
                    r"^[ \t]*" + escaped_prefix + re.escape(tag_bare) + r"[ \t]*\n",
                    "",
                    content,
                    flags=re.IGNORECASE | re.MULTILINE,
                )
                # Remove tag within text (with surrounding space normalization)
                content = re.sub(
                    r"\s*" + escaped_prefix + re.escape(tag_bare) + r"(?=\s|$)",
                    "",
                    content,
                    flags=re.IGNORECASE,
                )

                # Also check block properties format just in case
                # Remove just the tag from the tags property, or the whole line if empty
                def _remove_from_props(m):
                    line = m.group(0)
                    clean = re.sub(
                        r"(?:,?\s*)?" + re.escape(tag_bare) + r"\b",
                        "",
                        line,
                        flags=re.IGNORECASE,
                    )
                    clean = re.sub(r"tags::\s*,", "tags::", clean)
                    clean = re.sub(r",\s*$", "", clean)
                    if re.match(r"^[ \t]*tags::[ \t]*\n?$", clean):
                        return ""
                    return clean

                content = re.sub(
                    r"^[ \t]*tags::.*?\b" + re.escape(tag_bare) + r"\b.*?(?=\n|$)",
                    _remove_from_props,
                    content,
                    flags=re.IGNORECASE | re.MULTILINE,
                )

                page.parse(fmt, content)
                self._store_page_safe(page)

                if self.app:
                    self.app.notify_page_saved(page.name)

                return (
                    200,
                    {},
                    {
                        "ok": True,
                        "page": page_path_clean,
                        "tag": tag_bare,
                        "action": "removed",
                    },
                )
            except Exception as e:
                if "read-only" in str(e).lower() or "readonly" in str(e).lower():
                    return 403, {}, {"error": "Page is read-only"}
                logger.exception("remove_tag error")
                return 500, {}, {"error": str(e)}

        return _run_synchronized(_do)

    # ---- Current page (tracked by PageViewExtension) ----

    def get_current_page(self):
        """GET /api/current — return currently open page name"""
        # This is just reading a Python attribute, safe from any thread
        page_name = self.app._current_page_name
        if page_name:
            return 200, {}, {"page": page_name}
        else:
            return 200, {}, {"page": None}

    # ---- Pages API ----

    def list_pages(self, namespace=None):
        """GET /api/pages?namespace=... — list pages in a namespace"""

        def _do():
            from moonstone.notebook import Path

            pages = []

            if namespace:
                ns_path = self.notebook.pages.lookup_from_user_input(namespace)
            else:
                ns_path = Path(":")

            for page_info in self.notebook.pages.list_pages(ns_path):
                pages.append(
                    {
                        "name": page_info.name,
                        "basename": page_info.basename,
                        "haschildren": page_info.haschildren,
                        "hascontent": page_info.hascontent,
                    }
                )

            return 200, {}, {"pages": pages, "namespace": namespace or ":"}

        return _run_synchronized(_do)

    def get_page(self, page_path, format="wiki"):
        """GET /api/page/<path>?format=wiki|html|plain|markdown — get page content"""

        def _do():
            from moonstone.notebook import Path

            try:
                path = self.notebook.pages.lookup_from_user_input(page_path)
                page = self.notebook.get_page(path)
            except Exception as e:
                return (
                    404,
                    {},
                    {"error": "Page not found: %s" % page_path, "details": str(e)},
                )

            if not page.hascontent:
                return (
                    200,
                    {},
                    {
                        "name": page.name,
                        "basename": page.basename,
                        "title": page.get_title(),
                        "content": "",
                        "format": format,
                        "exists": False,
                        "haschildren": page.haschildren,
                    },
                )

            if format not in ("wiki", "html", "plain", "markdown"):
                return (
                    400,
                    {},
                    {
                        "error": "Unknown format: %s. Use wiki, html, plain, or markdown."
                        % format
                    },
                )

            content = None
            actual_format = format

            # Try to dump in requested format
            try:
                # HTML (and some other export formats) require a Linker
                # to resolve wiki links → URLs.  We use a simple linker
                # that passes links through as-is — web applets handle
                # navigation themselves.
                linker = None
                if format in ("html", "markdown", "rst"):
                    linker = _WebBridgeLinker()

                lines = page.dump(format, linker=linker)
                content = "".join(lines)
            except Exception as e:
                logger.warning("page.dump(%s) failed for %s: %s", format, page_path, e)

            # Fallback: if requested format failed, try 'wiki'
            if content is None and format != "wiki":
                try:
                    lines = page.dump("wiki")
                    content = "".join(lines)
                    actual_format = "wiki"
                    logger.info("Fell back to wiki format for %s", page_path)
                except Exception as e:
                    logger.warning(
                        "page.dump(wiki) also failed for %s: %s", page_path, e
                    )

            # Last resort: read the raw source file directly
            if content is None:
                try:
                    source = page.source
                    if (
                        source
                        and hasattr(source, "path")
                        and os.path.isfile(source.path)
                    ):
                        with open(source.path, "r", encoding="utf-8") as f:
                            content = f.read()
                        actual_format = "wiki"
                        logger.info("Read raw source file for %s", page_path)
                except Exception as e:
                    logger.warning("Raw file read failed for %s: %s", page_path, e)

            # Absolute last resort: read via page.source_file or similar
            if content is None:
                try:
                    for attr in ("source_file", "source"):
                        src = getattr(page, attr, None)
                        if src is not None:
                            if hasattr(src, "read"):
                                raw = src.read()
                                if isinstance(raw, bytes):
                                    content = raw.decode("utf-8")
                                else:
                                    content = raw
                                actual_format = "wiki"
                                break
                            elif hasattr(src, "path"):
                                with open(src.path, "r", encoding="utf-8") as f:
                                    content = f.read()
                                actual_format = "wiki"
                                break
                except Exception as e:
                    logger.exception(
                        "All content read methods failed for %s", page_path
                    )

            if content is None:
                return (
                    500,
                    {},
                    {"error": "Failed to read page content", "page": page_path},
                )

            # Get mtime/ctime for optimistic concurrency
            page_mtime = None
            page_ctime = None
            try:
                page_mtime = page.mtime
            except Exception:
                pass
            try:
                page_ctime = page.ctime
            except Exception:
                pass

            return (
                200,
                {},
                {
                    "name": page.name,
                    "basename": page.basename,
                    "title": page.get_title(),
                    "content": content,
                    "format": actual_format,
                    "exists": True,
                    "haschildren": page.haschildren,
                    "mtime": page_mtime,
                    "ctime": page_ctime,
                },
            )

        return _run_synchronized(_do)

    def save_page(self, page_path, content, format="wiki", expected_mtime=None):
        """PUT /api/page/<path> — update page content

        @param expected_mtime: if provided, check that page mtime matches
        before saving (optimistic concurrency control). Returns 409 if mismatch.
        """

        def _do():
            if self.notebook.readonly:
                return 403, {}, {"error": "Notebook is read-only"}

            from moonstone.notebook import Path

            path = self.notebook.pages.lookup_from_user_input(page_path)
            page = self.notebook.get_page(path)

            if page.readonly:
                return 403, {}, {"error": "Page is read-only"}

            # Optimistic concurrency: check mtime if provided
            if expected_mtime is not None:
                try:
                    current_mtime = page.mtime
                    if (
                        current_mtime is not None
                        and abs(current_mtime - expected_mtime) > 0.01
                    ):
                        return (
                            409,
                            {},
                            {
                                "error": "Page was modified since last read",
                                "expected_mtime": expected_mtime,
                                "current_mtime": current_mtime,
                                "page": page_path,
                            },
                        )
                except Exception:
                    pass  # If mtime is not available, skip check

            # Validate format supports parsing
            fmt_err = self._validate_write_format(format)
            if fmt_err:
                return fmt_err

            self._prepare_page_for_write(page)
            page.parse(format, content)
            self._store_page_safe(page)

            # Get new mtime after save
            new_mtime = None
            try:
                new_mtime = page.mtime
            except Exception:
                pass

            # Notify about save
            if self.app:
                self.app.notify_page_saved(page.name)

            return 200, {}, {"ok": True, "page": page_path, "mtime": new_mtime}

        return _run_synchronized(_do)

    def create_page(self, page_path, content="", format="wiki"):
        """POST /api/page/<path> — create a new page"""

        def _do():
            if self.notebook.readonly:
                return 403, {}, {"error": "Notebook is read-only"}

            from moonstone.notebook import Path

            try:
                path = self.notebook.pages.lookup_from_user_input(page_path)
                page = self.notebook.get_page(path)
                if page.hascontent:
                    return 409, {}, {"error": "Page already exists: %s" % page_path}
            except Exception:
                pass

            # Validate format supports parsing
            fmt_err = self._validate_write_format(format)
            if fmt_err:
                return fmt_err

            # Delegate to save logic
            path = self.notebook.pages.lookup_from_user_input(page_path)
            page = self.notebook.get_page(path)
            self._prepare_page_for_write(page)
            page.parse(format, content)
            self._store_page_safe(page)

            if self.app:
                self.app.notify_page_saved(page.name)

            return 200, {}, {"ok": True, "page": page_path}

        return _run_synchronized(_do)

    def delete_page(self, page_path):
        """DELETE /api/page/<path> — delete a page"""

        def _do():
            if self.notebook.readonly:
                return 403, {}, {"error": "Notebook is read-only"}

            from moonstone.notebook import Path

            path = self.notebook.pages.lookup_from_user_input(page_path)
            self.notebook.delete_page(path)
            return 200, {}, {"ok": True, "deleted": page_path}

        return _run_synchronized(_do)

    # ---- Search ----

    def search_pages(self, query):
        """GET /api/search?q=... — search pages"""
        if not query:
            return 400, {}, {"error": 'Missing query parameter "q"'}

        def _do():
            from moonstone.search import SearchSelection, Query

            query_obj = Query(query)
            selection = SearchSelection(self.notebook)
            selection.search(query_obj)

            results = []
            for path in selection:
                page_data = {
                    "name": path.name,
                    "basename": path.basename,
                }
                try:
                    page = self.notebook.get_page(path)
                    page_data["title"] = page.get_title()
                except Exception:
                    page_data["title"] = path.basename
                results.append(page_data)

            return 200, {}, {"query": query, "results": results, "count": len(results)}

        return _run_synchronized(_do)

    # ---- Attachments ----

    def list_attachments(self, page_path):
        """GET /api/attachments/<page_path> — list attachments for a page"""

        def _do():
            from moonstone.notebook import Path

            path = self.notebook.pages.lookup_from_user_input(page_path)

            # For flat-mode profiles (e.g. Obsidian), attachments are shared
            # in vault root. We must filter by what the page actually references.
            profile = getattr(self.notebook, "profile", None)
            allowed_names = None  # None = no filter (per-page dirs)
            if profile and getattr(profile, "attachments_mode", None) == "flat":
                page = self.notebook.get_page(path)
                if not page.hascontent:
                    return 200, {}, {"page": page_path, "attachments": []}
                # Read raw source to extract referenced attachments
                try:
                    raw_text = None
                    if hasattr(page, "source_file") and page.source_file.exists():
                        with open(page.source_file.path, "r", encoding="utf-8") as f:
                            raw_text = f.read()
                    if raw_text is not None and hasattr(
                        profile, "extract_attachment_refs"
                    ):
                        allowed_names = profile.extract_attachment_refs(raw_text)
                except Exception as e:
                    logger.debug(
                        "extract_attachment_refs failed for %s: %s", page_path, e
                    )

            attachments_dir = self.notebook.get_attachments_dir(path)

            files = []
            if attachments_dir.exists():
                for f in attachments_dir.list_names():
                    # Skip files not referenced by this page (flat mode)
                    if allowed_names is not None and f not in allowed_names:
                        continue
                    filepath = attachments_dir.file(f)
                    if filepath.exists() and not os.path.isdir(filepath.path):
                        try:
                            stat = os.stat(filepath.path)
                            files.append(
                                {
                                    "name": f,
                                    "size": stat.st_size,
                                    "mtime": stat.st_mtime,
                                }
                            )
                        except OSError:
                            files.append({"name": f, "size": 0, "mtime": 0})

            return 200, {}, {"page": page_path, "attachments": files}

        return _run_synchronized(_do)

    def get_attachment(self, page_path, filename):
        """GET /api/attachment/<page_path>/<filename> — download an attachment"""

        def _do():
            from moonstone.notebook import Path
            import mimetypes

            path = self.notebook.pages.lookup_from_user_input(page_path)
            attachments_dir = self.notebook.get_attachments_dir(path)
            filepath = attachments_dir.file(filename)

            if not filepath.exists():
                return 404, {}, {"error": "Attachment not found: %s" % filename}

            # Security: ensure file is within attachments dir
            real_file = os.path.realpath(filepath.path)
            real_dir = os.path.realpath(attachments_dir.path)
            if not real_file.startswith(real_dir + os.sep):
                return 403, {}, {"error": "Access denied"}

            content_type = (
                mimetypes.guess_type(filename)[0] or "application/octet-stream"
            )

            with open(filepath.path, "rb") as f:
                content = f.read()

            return 200, {"Content-Type": content_type}, content  # raw bytes

        return _run_synchronized(_do)

    def upload_attachment(self, page_path, filename, file_data):
        """POST /api/attachment/<page_path>/<filename> — upload an attachment"""

        def _do():
            if self.notebook.readonly:
                return 403, {}, {"error": "Notebook is read-only"}

            from moonstone.notebook import Path

            path = self.notebook.pages.lookup_from_user_input(page_path)
            attachments_dir = self.notebook.get_attachments_dir(path)

            if not attachments_dir.exists():
                attachments_dir.touch()

            filepath = attachments_dir.file(filename)
            with open(filepath.path, "wb") as f:
                f.write(file_data)

            return 200, {}, {"ok": True, "page": page_path, "filename": filename}

        return _run_synchronized(_do, timeout=30)

    # ---- Tags ----

    def list_tags(self):
        """GET /api/tags — list all tags in the notebook"""

        def _do():
            from moonstone.notebook.index.tags import TagsView

            tags_view = TagsView.new_from_index(self.notebook.index)
            tags = []
            for tag in tags_view.list_all_tags_by_n_pages():
                n = tags_view.n_list_pages(tag)
                tags.append(
                    {
                        "name": tag.name,
                        "count": n,
                    }
                )
            return 200, {}, {"tags": tags, "count": len(tags)}

        return _run_synchronized(_do)

    def get_page_tags(self, page_path):
        """GET /api/page/<path>/tags — list tags for a specific page"""

        def _do():
            from moonstone.notebook import Path
            from moonstone.notebook.index.tags import TagsView

            path = self.notebook.pages.lookup_from_user_input(page_path)
            tags_view = TagsView.new_from_index(self.notebook.index)
            tags = []
            try:
                for tag in tags_view.list_tags(path):
                    tags.append({"name": tag.name})
            except Exception as e:
                return (
                    404,
                    {},
                    {"error": "Page not found: %s" % page_path, "details": str(e)},
                )
            return 200, {}, {"page": page_path, "tags": tags}

        return _run_synchronized(_do)

    def get_tag_pages(self, tag_name):
        """GET /api/tags/<tag>/pages — list pages with a specific tag"""

        def _do():
            from moonstone.notebook.index.tags import TagsView, IndexTag

            tags_view = TagsView.new_from_index(self.notebook.index)
            tag = tags_view.lookup_by_tagname(tag_name)
            if tag is None:
                return 404, {}, {"error": "Tag not found: %s" % tag_name}
            pages = []
            for page_info in tags_view.list_pages(tag):
                pages.append(
                    {
                        "name": page_info.name,
                        "basename": page_info.basename,
                    }
                )
            return 200, {}, {"tag": tag_name, "pages": pages, "count": len(pages)}

        return _run_synchronized(_do)

    # ---- Links / Backlinks ----

    def get_links(self, page_path, direction="forward"):
        """GET /api/links/<path>?direction=forward|backward|both — list links"""

        def _do():
            from moonstone.notebook import Path
            from moonstone.notebook.index.links import (
                LinksView,
                LINK_DIR_FORWARD,
                LINK_DIR_BACKWARD,
                LINK_DIR_BOTH,
            )

            dir_map = {
                "forward": LINK_DIR_FORWARD,
                "backward": LINK_DIR_BACKWARD,
                "both": LINK_DIR_BOTH,
            }
            link_dir = dir_map.get(direction, LINK_DIR_FORWARD)

            path = self.notebook.pages.lookup_from_user_input(page_path)
            links_view = LinksView.new_from_index(self.notebook.index)

            links = []
            try:
                for link in links_view.list_links(path, link_dir):
                    links.append(
                        {
                            "source": link.source.name,
                            "target": link.target.name,
                        }
                    )
            except Exception as e:
                return (
                    404,
                    {},
                    {"error": "Page not found: %s" % page_path, "details": str(e)},
                )

            return (
                200,
                {},
                {
                    "page": page_path,
                    "direction": direction,
                    "links": links,
                    "count": len(links),
                },
            )

        return _run_synchronized(_do)

    # ---- Recent Changes ----

    def get_recent_changes(self, limit=20, offset=0):
        """GET /api/recent?limit=...&offset=... — list recently changed pages"""

        def _do():
            pages = []
            for page_info in self.notebook.pages.list_recent_changes(
                limit=limit, offset=offset
            ):
                pages.append(
                    {
                        "name": page_info.name,
                        "basename": page_info.basename,
                        "mtime": page_info.mtime,
                        "haschildren": page_info.haschildren,
                        "hascontent": page_info.hascontent,
                    }
                )
            return 200, {}, {"pages": pages, "limit": limit, "offset": offset}

        return _run_synchronized(_do)

    # ---- Navigate ----

    def navigate_to_page(self, page_path):
        """POST /api/navigate — request to open a page in the GUI"""

        def _do():
            # This is handled via a callback to the app context
            if self.app:
                self.app.request_navigate(page_path)
                return 200, {}, {"ok": True, "page": page_path}
            return 503, {}, {"error": "Navigation not available"}

        return _run_synchronized(_do)

    # ---- Autocomplete / Match pages ----

    def match_pages(self, query, limit=10):
        """GET /api/pages/match?q=...&limit=... — fuzzy match page names"""

        def _do():
            pages = []
            for page_info in self.notebook.pages.match_all_pages(query, limit=limit):
                pages.append(
                    {
                        "name": page_info.name,
                        "basename": page_info.basename,
                    }
                )
            return 200, {}, {"query": query, "pages": pages}

        return _run_synchronized(_do)

    # ---- Notebook Stats ----

    def get_stats(self):
        """GET /api/stats — return notebook statistics"""

        def _do():
            from moonstone.notebook.index.tags import TagsView

            n_pages = self.notebook.pages.n_all_pages()
            tags_view = TagsView.new_from_index(self.notebook.index)
            n_tags = tags_view.n_list_all_tags()
            return (
                200,
                {},
                {
                    "pages": n_pages,
                    "tags": n_tags,
                },
            )

        return _run_synchronized(_do)

    # ---- Append to page ----

    def append_to_page(self, page_path, content, format="wiki"):
        """POST /api/page/<path>/append — append content to a page.
        Reads existing content using the notebook profile's default format
        to avoid corrupting markdown/wiki content during read-back.
        """

        def _do():
            if self.notebook.readonly:
                return 403, {}, {"error": "Notebook is read-only"}

            # Use profile's default format for reading existing content
            profile_fmt = self._get_profile_format()

            # Validate write format
            fmt_err = self._validate_write_format(profile_fmt)
            if fmt_err:
                return fmt_err

            from moonstone.notebook import Path

            path = self.notebook.pages.lookup_from_user_input(page_path)
            page = self.notebook.get_page(path)

            if page.readonly:
                return 403, {}, {"error": "Page is read-only"}

            if page.hascontent:
                # Read existing content using profile format
                try:
                    lines = page.dump(profile_fmt)
                    existing = "".join(lines)
                except Exception:
                    existing = ""
                new_content = existing.rstrip("\n") + "\n" + content
            else:
                new_content = content

            self._prepare_page_for_write(page)
            page.parse(profile_fmt, new_content)
            self._store_page_safe(page)

            if self.app:
                self.app.notify_page_saved(page.name)

            return 200, {}, {"ok": True, "page": page_path}

        return _run_synchronized(_do)

    # ---- Move / Rename page ----

    def move_page(self, page_path, new_path, update_links=True):
        """POST /api/page/<path>/move — move/rename a page"""

        def _do():
            if self.notebook.readonly:
                return 403, {}, {"error": "Notebook is read-only"}

            from moonstone.notebook import Path

            old = self.notebook.pages.lookup_from_user_input(page_path)
            new = Path(new_path)

            try:
                self.notebook.move_page(old, new, update_links=update_links)
            except Exception as e:
                return 400, {}, {"error": "Move failed: %s" % str(e)}

            if self.app and self.app._event_manager:
                self.app._event_manager.emit(
                    "page-moved",
                    {
                        "old": page_path,
                        "new": new_path,
                    },
                )

            return 200, {}, {"ok": True, "old": page_path, "new": new_path}

        return _run_synchronized(_do)

    # ---- Delete attachment ----

    def delete_attachment(self, page_path, filename):
        """DELETE /api/attachment/<page_path>/<filename> — delete an attachment"""

        def _do():
            if self.notebook.readonly:
                return 403, {}, {"error": "Notebook is read-only"}

            from moonstone.notebook import Path

            path = self.notebook.pages.lookup_from_user_input(page_path)
            attachments_dir = self.notebook.get_attachments_dir(path)
            filepath = attachments_dir.file(filename)

            if not filepath.exists():
                return 404, {}, {"error": "Attachment not found: %s" % filename}

            # Security: ensure file is within attachments dir
            real_file = os.path.realpath(filepath.path)
            real_dir = os.path.realpath(attachments_dir.path)
            if not real_file.startswith(real_dir + os.sep):
                return 403, {}, {"error": "Access denied"}

            os.remove(filepath.path)
            return 200, {}, {"ok": True, "page": page_path, "deleted": filename}

        return _run_synchronized(_do)

    # ---- Page tree (full hierarchy) ----

    def get_page_tree(self, namespace=None, depth=2):
        """GET /api/pagetree?namespace=...&depth=... — get page hierarchy"""

        def _do():
            from moonstone.notebook import Path

            if namespace:
                root = self.notebook.pages.lookup_from_user_input(namespace)
            else:
                root = Path(":")

            tree = self._build_tree(root, depth, 0)
            return 200, {}, {"tree": tree, "namespace": namespace or ":"}

        return _run_synchronized(_do)

    def _build_tree(self, path, max_depth, current_depth):
        """Recursively build a page tree. Must be called from main thread."""
        children = []
        if current_depth < max_depth:
            for page_info in self.notebook.pages.list_pages(path):
                child = {
                    "name": page_info.name,
                    "basename": page_info.basename,
                    "haschildren": page_info.haschildren,
                    "hascontent": page_info.hascontent,
                }
                if page_info.haschildren and current_depth + 1 < max_depth:
                    child["children"] = self._build_tree(
                        page_info, max_depth, current_depth + 1
                    )
                children.append(child)
        return children

    # ================================================================
    # NEW API METHODS (v2.1)
    # ================================================================

    # ---- Walk (recursive page listing) ----

    def walk_pages(self, namespace=None):
        """GET /api/pages/walk?namespace=... — recursively list all pages"""

        def _do():
            from moonstone.notebook import Path

            if namespace:
                root = self.notebook.pages.lookup_from_user_input(namespace)
            else:
                root = Path(":")

            pages = []
            for page_info in self.notebook.pages.walk(root):
                pages.append(
                    {
                        "name": page_info.name,
                        "basename": page_info.basename,
                        "haschildren": page_info.haschildren,
                        "hascontent": page_info.hascontent,
                    }
                )
            return (
                200,
                {},
                {"pages": pages, "namespace": namespace or ":", "count": len(pages)},
            )

        return _run_synchronized(_do, timeout=30)

    # ---- Siblings (previous / next) ----

    def get_page_siblings(self, page_path):
        """GET /api/page/<path>/siblings — get previous and next pages"""

        def _do():
            from moonstone.notebook import Path

            path = self.notebook.pages.lookup_from_user_input(page_path)
            prev_path = self.notebook.pages.get_previous(path)
            next_path = self.notebook.pages.get_next(path)
            return (
                200,
                {},
                {
                    "page": page_path,
                    "previous": prev_path.name if prev_path else None,
                    "next": next_path.name if next_path else None,
                },
            )

        return _run_synchronized(_do)

    # ---- Trash (safe delete) ----

    def trash_page(self, page_path):
        """POST /api/page/<path>/trash — move page to trash"""

        def _do():
            if self.notebook.readonly:
                return 403, {}, {"error": "Notebook is read-only"}

            from moonstone.notebook import Path

            path = self.notebook.pages.lookup_from_user_input(page_path)

            try:
                self.notebook.trash_page(path)
            except Exception as e:
                # Fallback to delete if trash is not available
                logger.warning("trash_page failed, falling back to delete: %s", e)
                try:
                    self.notebook.delete_page(path)
                except Exception as e2:
                    return 400, {}, {"error": "Trash/delete failed: %s" % str(e2)}

            return 200, {}, {"ok": True, "trashed": page_path}

        return _run_synchronized(_do)

    # ---- Links Section (recursive links for namespace) ----

    def get_links_section(self, page_path, direction="forward"):
        """GET /api/links/<path>/section?direction=... — links for whole section"""

        def _do():
            from moonstone.notebook import Path
            from moonstone.notebook.index.links import (
                LinksView,
                LINK_DIR_FORWARD,
                LINK_DIR_BACKWARD,
                LINK_DIR_BOTH,
            )

            dir_map = {
                "forward": LINK_DIR_FORWARD,
                "backward": LINK_DIR_BACKWARD,
                "both": LINK_DIR_BOTH,
            }
            link_dir = dir_map.get(direction, LINK_DIR_FORWARD)

            path = self.notebook.pages.lookup_from_user_input(page_path)
            links_view = LinksView.new_from_index(self.notebook.index)

            links = []
            try:
                for link in links_view.list_links_section(path, link_dir):
                    links.append(
                        {
                            "source": link.source.name,
                            "target": link.target.name,
                        }
                    )
            except Exception as e:
                return (
                    404,
                    {},
                    {"error": "Page not found: %s" % page_path, "details": str(e)},
                )

            return (
                200,
                {},
                {
                    "page": page_path,
                    "direction": direction,
                    "links": links,
                    "count": len(links),
                },
            )

        return _run_synchronized(_do)

    # ---- Intersecting Tags ----

    def get_intersecting_tags(self, tag_names):
        """GET /api/tags/intersecting?tags=t1,t2 — tags co-occurring with given tags"""

        def _do():
            from moonstone.notebook.index.tags import TagsView

            tags_view = TagsView.new_from_index(self.notebook.index)

            # Resolve tag objects
            tag_objects = []
            for name in tag_names:
                tag = tags_view.lookup_by_tagname(name.strip())
                if tag is None:
                    return 404, {}, {"error": "Tag not found: %s" % name.strip()}
                tag_objects.append(tag)

            result = []
            try:
                for tag in tags_view.list_intersecting_tags(tag_objects):
                    n = tags_view.n_list_pages(tag)
                    result.append({"name": tag.name, "count": n})
            except Exception as e:
                return 500, {}, {"error": "Failed: %s" % str(e)}

            return (
                200,
                {},
                {
                    "query_tags": [t.strip() for t in tag_names],
                    "intersecting": result,
                    "count": len(result),
                },
            )

        return _run_synchronized(_do)

    # ---- Resolve Link ----

    def resolve_link(self, source, link_text):
        """POST /api/resolve-link — resolve a wiki link from a source page context"""

        def _do():
            from moonstone.notebook import Path
            from moonstone.notebook.page import HRef

            source_path = self.notebook.pages.lookup_from_user_input(source)
            href = HRef.new_from_wiki_link(link_text)
            try:
                target = self.notebook.pages.resolve_link(source_path, href)
                return (
                    200,
                    {},
                    {
                        "source": source,
                        "link": link_text,
                        "resolved": target.name,
                    },
                )
            except Exception as e:
                return 400, {}, {"error": "Cannot resolve link: %s" % str(e)}

        return _run_synchronized(_do)

    # ---- Create Link ----

    def create_link(self, source, target):
        """POST /api/create-link — create a proper wiki link between pages"""

        def _do():
            from moonstone.notebook import Path

            source_path = self.notebook.pages.lookup_from_user_input(source)
            target_path = self.notebook.pages.lookup_from_user_input(target)
            try:
                href = self.notebook.pages.create_link(source_path, target_path)
                return (
                    200,
                    {},
                    {
                        "source": source,
                        "target": target,
                        "href": href.to_wiki_link(),
                    },
                )
            except Exception as e:
                return 400, {}, {"error": "Cannot create link: %s" % str(e)}

        return _run_synchronized(_do)

    # ---- Suggest Link ----

    def suggest_link(self, source, text):
        """GET /api/suggest-link?from=...&text=... — get link suggestions"""

        def _do():
            from moonstone.notebook import Path

            source_path = self.notebook.pages.lookup_from_user_input(source)

            suggestions = []
            try:
                result = self.notebook.suggest_link(source_path, text)
                if result:
                    if hasattr(result, "name"):
                        suggestions.append({"name": result.name})
                    elif hasattr(result, "__iter__"):
                        for p in result:
                            if hasattr(p, "name"):
                                suggestions.append({"name": p.name})
            except Exception as e:
                logger.debug("suggest_link failed: %s", e)

            # Also add match_all_pages results
            try:
                for page_info in self.notebook.pages.match_all_pages(text, limit=10):
                    entry = {"name": page_info.name}
                    if entry not in suggestions:
                        suggestions.append(entry)
            except Exception:
                pass

            return (
                200,
                {},
                {
                    "source": source,
                    "text": text,
                    "suggestions": suggestions[:20],
                },
            )

        return _run_synchronized(_do)

    # ---- KV Store for Applets ----

    def store_get(self, applet, key=None):
        """GET /api/store/<applet>[/<key>] — get stored data"""
        store_dir = os.path.join(self.app.applets_dir, applet, "_data")
        if key:
            filepath = os.path.join(store_dir, key + ".json")
            if not os.path.isfile(filepath):
                return 404, {}, {"error": "Key not found: %s" % key}
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return 200, {}, {"applet": applet, "key": key, "value": data}
            except Exception as e:
                return 500, {}, {"error": "Read failed: %s" % str(e)}
        else:
            # List all keys
            keys = []
            if os.path.isdir(store_dir):
                for f in sorted(os.listdir(store_dir)):
                    if f.endswith(".json"):
                        keys.append(f[:-5])
            return 200, {}, {"applet": applet, "keys": keys}

    def store_put(self, applet, key, value):
        """PUT /api/store/<applet>/<key> — save data"""
        store_dir = os.path.join(self.app.applets_dir, applet, "_data")
        os.makedirs(store_dir, exist_ok=True)

        # Security: prevent path traversal
        if "/" in key or "\\" in key or ".." in key:
            return 400, {}, {"error": "Invalid key name"}

        filepath = os.path.join(store_dir, key + ".json")
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(value, f, ensure_ascii=False, indent=2)
            # Auto-emit SSE event for store changes
            if self.event_manager:
                self.event_manager.emit(
                    "store-changed",
                    {
                        "applet": applet,
                        "key": key,
                        "action": "put",
                    },
                )
            return 200, {}, {"ok": True, "applet": applet, "key": key}
        except Exception as e:
            return 500, {}, {"error": "Write failed: %s" % str(e)}

    def store_delete(self, applet, key):
        """DELETE /api/store/<applet>/<key> — delete stored data"""
        store_dir = os.path.join(self.app.applets_dir, applet, "_data")
        if "/" in key or "\\" in key or ".." in key:
            return 400, {}, {"error": "Invalid key name"}

        filepath = os.path.join(store_dir, key + ".json")
        if not os.path.isfile(filepath):
            return 404, {}, {"error": "Key not found: %s" % key}
        try:
            os.remove(filepath)
            # Auto-emit SSE event for store changes
            if self.event_manager:
                self.event_manager.emit(
                    "store-changed",
                    {
                        "applet": applet,
                        "key": key,
                        "action": "delete",
                    },
                )
            return 200, {}, {"ok": True, "applet": applet, "deleted": key}
        except Exception as e:
            return 500, {}, {"error": "Delete failed: %s" % str(e)}

    # ---- Batch Operations ----

    def batch(self, operations):
        """POST /api/batch — execute multiple operations in one request"""
        def _do():
            from moonstone.webbridge.endpoints import router
            import urllib.parse
            import json
            from io import BytesIO

            class MockApp:
                def __init__(self, api_instance):
                    self.api = api_instance
                    self.app = api_instance.app
                    
                def _status_string(self, status_code):
                    if status_code == 200: return "200 OK"
                    if status_code == 400: return "400 Bad Request"
                    if status_code == 403: return "403 Forbidden"
                    if status_code == 404: return "404 Not Found"
                    if status_code == 409: return "409 Conflict"
                    if status_code == 500: return "500 Internal Server Error"
                    if status_code == 501: return "501 Not Implemented"
                    if status_code == 503: return "503 Service Unavailable"
                    return f"{status_code} Unknown"
                    
                def _json_response(self, start_response, status_code, body, cors_headers=None, extra_headers=None):
                    response_body = json.dumps(body).encode("utf-8")
                    headers = [
                        ("Content-Type", "application/json; charset=utf-8"),
                        ("Content-Length", str(len(response_body))),
                    ]
                    if cors_headers:
                        headers.extend(cors_headers)
                    if extra_headers:
                        for k, v in extra_headers.items():
                            headers.append((k, str(v)))
                    start_response(self._status_string(status_code), headers)
                    return [response_body]

                def _read_request_body_raw(self, environ):
                    try:
                        length = int(environ.get("CONTENT_LENGTH", 0))
                    except ValueError:
                        length = 0
                    if length > 0:
                        return environ["wsgi.input"].read(length)
                    return b""

                def _read_request_body(self, environ):
                    data = self._read_request_body_raw(environ)
                    if not data:
                        return None
                    try:
                        return json.loads(data.decode("utf-8"))
                    except Exception:
                        return None

            mock_app = MockApp(self)

            results = []
            for i, op in enumerate(operations):
                try:
                    method = op.get("method", "GET").upper()
                    path = op.get("path", "")
                    body = op.get("body", {})

                    parsed_url = urllib.parse.urlparse(path)
                    unquoted_path = urllib.parse.unquote(parsed_url.path)
                    query_params = urllib.parse.parse_qs(parsed_url.query)

                    # Mock WSGI environment
                    environ = {
                        "REQUEST_METHOD": method,
                        "PATH_INFO": unquoted_path,
                        "QUERY_STRING": parsed_url.query,
                        "wsgi.input": BytesIO(b"")
                    }
                    if body:
                        body_bytes = json.dumps(body).encode("utf-8")
                        environ["wsgi.input"] = BytesIO(body_bytes)
                        environ["CONTENT_LENGTH"] = str(len(body_bytes))

                    response_status = [500]
                    response_headers = [{}]
                    
                    def start_response(status_str, headers):
                        response_status[0] = int(status_str.split()[0])
                        response_headers[0] = dict(headers)

                    res_bytes = router.dispatch(mock_app, method, unquoted_path, query_params, environ, start_response, [])
                    
                    if res_bytes:
                        content_str = b"".join(res_bytes).decode("utf-8")
                        try:
                            resp_body = json.loads(content_str)
                        except json.JSONDecodeError:
                            resp_body = content_str
                    else:
                        resp_body = {"error": "Not found"}
                        response_status[0] = 404

                    results.append({
                        "index": i,
                        "status": response_status[0],
                        "body": resp_body
                    })
                except Exception as e:
                    results.append({
                        "index": i,
                        "status": 500,
                        "body": {"error": str(e)}
                    })
            return 200, {}, {"results": results, "count": len(results)}

        return _run_synchronized(_do, timeout=60)

    # ---- Parse Tree as JSON ----

    def get_page_parsetree(self, page_path):
        """GET /api/page/<path>/parsetree — get structured parse tree as JSON"""

        def _do():
            from moonstone.notebook import Path

            try:
                path = self.notebook.pages.lookup_from_user_input(page_path)
                page = self.notebook.get_page(path)
            except Exception as e:
                return 404, {}, {"error": "Page not found: %s" % page_path}

            if not page.hascontent:
                return 200, {}, {"name": page.name, "tree": [], "exists": False}

            try:
                tree = page.get_parsetree()
                if tree is None:
                    return 200, {}, {"name": page.name, "tree": [], "exists": False}
                json_tree = self._parsetree_to_json(tree)
                return 200, {}, {"name": page.name, "tree": json_tree, "exists": True}
            except Exception as e:
                logger.exception("Failed to parse tree for %s", page_path)
                return 500, {}, {"error": "Parse tree failed: %s" % str(e)}

        return _run_synchronized(_do)

    def _parsetree_to_json(self, tree):
        """Convert a Moonstone ParseTree to a JSON-serializable structure."""

        def _node_to_dict(node):
            result = {"tag": node.tag}
            if node.attrib:
                result["attrib"] = dict(node.attrib)
            if node.text:
                result["text"] = node.text
            if node.tail:
                result["tail"] = node.tail
            children = []
            for child in node:
                children.append(_node_to_dict(child))
            if children:
                result["children"] = children
            return result

        root = tree._etree.getroot() if hasattr(tree, "_etree") else tree
        return _node_to_dict(root)

    # ---- Emit Custom Event (Applet-to-Applet messaging) ----

    def _get_ws_info(self):
        """Return WebSocket server info for capabilities endpoint.

        Returns url, port and enabled flag.  The ``port`` field allows
        JS clients to construct ws://window.location.hostname:PORT
        which works correctly both from localhost and from LAN.
        """
        if self.app and hasattr(self.app, "get_ws_url"):
            ws_url = self.app.get_ws_url()
            ws_port = (
                self.app.get_ws_port() if hasattr(self.app, "get_ws_port") else None
            )
            if ws_url:
                return {"url": ws_url, "port": ws_port, "enabled": True}
        return {"url": None, "port": None, "enabled": False}

    def emit_custom_event(self, event_type, data):
        """POST /api/emit — emit a custom event to all SSE clients"""
        if not event_type:
            return 400, {}, {"error": "Missing event type"}

        # Prefix custom events to avoid conflicts
        full_type = "custom:" + event_type

        if self.event_manager:
            self.event_manager.emit(full_type, data or {})
            return 200, {}, {"ok": True, "event": full_type}
        return 503, {}, {"error": "Event manager not available"}

    # ================================================================
    # NEW API METHODS (v2.2)
    # ================================================================

    # ---- Search with Snippets ----

    def search_pages_with_snippets(self, query, snippets=False, snippet_length=120):
        """GET /api/search?q=...&snippets=true — search with optional text snippets"""
        if not query:
            return 400, {}, {"error": 'Missing query parameter "q"'}

        def _do():
            import re
            from moonstone.search import SearchSelection, Query

            query_obj = Query(query)
            selection = SearchSelection(self.notebook)
            selection.search(query_obj)

            results = []
            # Extract search terms for snippet highlighting
            terms = re.findall(r"\w+", query.lower())

            for path in selection:
                page_data = {
                    "name": path.name,
                    "basename": path.basename,
                }
                try:
                    page = self.notebook.get_page(path)
                    page_data["title"] = page.get_title()
                except Exception:
                    page_data["title"] = path.basename

                if snippets:
                    try:
                        page = self.notebook.get_page(path)
                        lines = page.dump("plain")
                        text = "".join(lines)
                        snippet = self._extract_snippet(text, terms, snippet_length)
                        page_data["snippet"] = snippet
                    except Exception:
                        page_data["snippet"] = ""

                results.append(page_data)

            return 200, {}, {"query": query, "results": results, "count": len(results)}

        return _run_synchronized(_do)

    def _extract_snippet(self, text, terms, max_length=120):
        """Extract a text snippet around the first occurrence of search terms."""
        import re

        text_lower = text.lower()
        best_pos = len(text)

        for term in terms:
            pos = text_lower.find(term)
            if pos >= 0 and pos < best_pos:
                best_pos = pos

        if best_pos >= len(text):
            # No term found, return beginning
            return text[:max_length].strip() + ("..." if len(text) > max_length else "")

        start = max(0, best_pos - max_length // 3)
        end = min(len(text), start + max_length)
        snippet = text[start:end].strip()

        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."

        return snippet

    # ---- Paginated List ----

    def list_pages_paginated(self, namespace=None, limit=None, offset=0):
        """GET /api/pages?namespace=...&limit=...&offset=... — paginated page list"""

        def _do():
            from moonstone.notebook import Path

            if namespace:
                ns_path = self.notebook.pages.lookup_from_user_input(namespace)
            else:
                ns_path = Path(":")

            all_pages = []
            for page_info in self.notebook.pages.list_pages(ns_path):
                all_pages.append(
                    {
                        "name": page_info.name,
                        "basename": page_info.basename,
                        "haschildren": page_info.haschildren,
                        "hascontent": page_info.hascontent,
                    }
                )

            total = len(all_pages)

            if limit is not None:
                pages = all_pages[offset : offset + limit]
            else:
                pages = all_pages[offset:] if offset > 0 else all_pages

            return (
                200,
                {},
                {
                    "pages": pages,
                    "namespace": namespace or ":",
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                },
            )

        return _run_synchronized(_do)

    # ---- Format Discovery ----

    def list_formats(self):
        """GET /api/formats — list available export/dump formats"""

        def _do():
            formats = ["wiki", "html", "plain"]
            # Try to discover additional formats
            try:
                from moonstone.formats import get_format

                for fmt in ("markdown", "rst", "latex"):
                    try:
                        get_format(fmt)
                        formats.append(fmt)
                    except Exception:
                        pass
            except Exception:
                pass
            return 200, {}, {"formats": formats}

        return _run_synchronized(_do)

    # ---- Count-Only Queries ----

    def count_pages(self, namespace=None):
        """GET /api/pages/count?namespace=... — count pages without loading"""

        def _do():
            from moonstone.notebook import Path

            if namespace:
                ns_path = self.notebook.pages.lookup_from_user_input(namespace)
                count = self.notebook.pages.n_list_pages(ns_path)
            else:
                count = self.notebook.pages.n_all_pages()

            return 200, {}, {"count": count, "namespace": namespace or ":"}

        return _run_synchronized(_do)

    def count_links(self, page_path, direction="forward"):
        """GET /api/links/<path>/count?direction=... — count links without loading"""

        def _do():
            from moonstone.notebook import Path
            from moonstone.notebook.index.links import (
                LinksView,
                LINK_DIR_FORWARD,
                LINK_DIR_BACKWARD,
                LINK_DIR_BOTH,
            )

            dir_map = {
                "forward": LINK_DIR_FORWARD,
                "backward": LINK_DIR_BACKWARD,
                "both": LINK_DIR_BOTH,
            }
            link_dir = dir_map.get(direction, LINK_DIR_FORWARD)
            path = self.notebook.pages.lookup_from_user_input(page_path)
            links_view = LinksView.new_from_index(self.notebook.index)

            try:
                count = links_view.n_list_links(path, link_dir)
            except Exception:
                count = 0
            return 200, {}, {"page": page_path, "direction": direction, "count": count}

        return _run_synchronized(_do)

    # ---- Floating Links ----

    def list_floating_links(self):
        """GET /api/links/floating — list all floating (ambiguous) links

        Moonstone's LinksView.list_floating_links(basename) finds floating links
        to a *specific* basename.  To list *all* floating links we iterate
        over every unique basename in the notebook and aggregate results.
        """

        def _do():
            from moonstone.notebook.index.links import LinksView

            links_view = LinksView.new_from_index(self.notebook.index)

            floating = []
            seen_basenames = set()
            seen_links = set()
            try:
                for page_info in self.notebook.pages.walk():
                    basename = page_info.basename
                    if basename in seen_basenames:
                        continue
                    seen_basenames.add(basename)
                    try:
                        for link in links_view.list_floating_links(basename):
                            key = (link.source.name, link.target.name)
                            if key not in seen_links:
                                seen_links.add(key)
                                floating.append(
                                    {
                                        "source": link.source.name,
                                        "target": link.target.name,
                                    }
                                )
                    except Exception:
                        pass
            except Exception as e:
                logger.debug("list_floating_links failed: %s", e)

            return 200, {}, {"links": floating, "count": len(floating)}

        return _run_synchronized(_do, timeout=30)

    # ---- History API ----

    def get_history(self, limit=50):
        """GET /api/history?limit=... — get navigation history"""

        def _do():
            if (
                not self.app
                or not hasattr(self.app, "_history")
                or not self.app._history
            ):
                return (
                    200,
                    {},
                    {"history": [], "recent": [], "error": "History not available"},
                )

            history = self.app._history
            entries = []
            count = 0
            try:
                for record in history.get_history():
                    if count >= limit:
                        break
                    entries.append(
                        {
                            "name": record.name,
                            "basename": record.basename,
                        }
                    )
                    count += 1
            except Exception as e:
                logger.debug("get_history failed: %s", e)

            recent = []
            count = 0
            try:
                for record in history.get_recent():
                    if count >= limit:
                        break
                    recent.append(
                        {
                            "name": record.name,
                            "basename": record.basename,
                        }
                    )
                    count += 1
            except Exception as e:
                logger.debug("get_recent failed: %s", e)

            return 200, {}, {"history": entries, "recent": recent}

        return _run_synchronized(_do)

    # ---- Applet Config ----

    def get_applet_config(self, applet_name):
        """GET /api/applets/<name>/config — get applet configuration"""
        if not self.applet_manager:
            return 503, {}, {"error": "Applet manager not available"}

        applet = self.applet_manager.get_applet(applet_name)
        if not applet:
            return 404, {}, {"error": "Applet not found: %s" % applet_name}

        # Read config from store
        config = {}
        store_dir = os.path.join(self.app.applets_dir, applet_name, "_data")
        config_file = os.path.join(store_dir, "_config.json")
        if os.path.isfile(config_file):
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception:
                pass

        # Get schema from manifest
        schema = applet.manifest.get("preferences", [])

        return (
            200,
            {},
            {
                "applet": applet_name,
                "config": config,
                "schema": schema,
            },
        )

    def save_applet_config(self, applet_name, config):
        """PUT /api/applets/<name>/config — save applet configuration"""
        if not self.applet_manager:
            return 503, {}, {"error": "Applet manager not available"}

        applet = self.applet_manager.get_applet(applet_name)
        if not applet:
            return 404, {}, {"error": "Applet not found: %s" % applet_name}

        store_dir = os.path.join(self.app.applets_dir, applet_name, "_data")
        os.makedirs(store_dir, exist_ok=True)
        config_file = os.path.join(store_dir, "_config.json")

        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            return 200, {}, {"ok": True, "applet": applet_name}
        except Exception as e:
            return 500, {}, {"error": "Save failed: %s" % str(e)}

    # ---- Partial Update (PATCH) ----

    # ================================================================
    # NEW API METHODS (v2.3) — Core analytics & capabilities
    # ================================================================

    # ---- Table of Contents ----

    def get_page_toc(self, page_path):
        """GET /api/page/<path>/toc — extract headings as table of contents"""

        def _do():
            from moonstone.notebook import Path

            try:
                path = self.notebook.pages.lookup_from_user_input(page_path)
                page = self.notebook.get_page(path)
            except Exception as e:
                return 404, {}, {"error": "Page not found: %s" % page_path}

            if not page.hascontent:
                return 200, {}, {"name": page.name, "headings": [], "exists": False}

            try:
                tree = page.get_parsetree()
                if tree is None:
                    return 200, {}, {"name": page.name, "headings": [], "exists": False}

                headings = []
                root = tree._etree.getroot() if hasattr(tree, "_etree") else tree
                self._extract_headings(root, headings)

                return (
                    200,
                    {},
                    {
                        "name": page.name,
                        "headings": headings,
                        "count": len(headings),
                        "exists": True,
                    },
                )
            except Exception as e:
                logger.exception("TOC extraction failed for %s", page_path)
                return 500, {}, {"error": "TOC extraction failed: %s" % str(e)}

        return _run_synchronized(_do)

    def _extract_headings(self, node, headings, _counter=[0]):
        """Recursively extract headings from a parse tree node."""
        if node.tag == "h":
            level = int(node.attrib.get("level", 1))
            # Collect all text within the heading
            text = node.text or ""
            for child in node:
                text += (child.text or "") + (child.tail or "")
            text = text.strip()
            if text:
                headings.append(
                    {
                        "level": level,
                        "text": text,
                        "index": len(headings),
                    }
                )
        for child in node:
            self._extract_headings(child, headings)

    # ---- Page Analytics ----

    def get_page_analytics(self, page_path):
        """GET /api/page/<path>/analytics — content statistics for a page"""

        def _do():
            from moonstone.notebook import Path
            from moonstone.notebook.index.links import (
                LinksView,
                LINK_DIR_FORWARD,
                LINK_DIR_BACKWARD,
            )
            from moonstone.notebook.index.tags import TagsView
            import time

            try:
                path = self.notebook.pages.lookup_from_user_input(page_path)
                page = self.notebook.get_page(path)
            except Exception as e:
                return 404, {}, {"error": "Page not found: %s" % page_path}

            if not page.hascontent:
                return (
                    200,
                    {},
                    {
                        "name": page.name,
                        "exists": False,
                        "words": 0,
                        "characters": 0,
                        "lines": 0,
                        "reading_time_minutes": 0,
                        "headings": 0,
                        "links_out": 0,
                        "links_in": 0,
                        "images": 0,
                        "tags": 0,
                    },
                )

            # Get plain text for word/char count
            try:
                lines = page.dump("plain")
                text = "".join(lines)
            except Exception:
                text = ""

            words = len(text.split()) if text else 0
            characters = len(text)
            line_count = text.count("\n") + 1 if text else 0
            reading_time = round(words / 200, 1)  # ~200 wpm

            # Parse tree analysis
            heading_count = 0
            image_count = 0
            checkbox_count = 0
            checkbox_checked = 0
            try:
                tree = page.get_parsetree()
                if tree:
                    root = tree._etree.getroot() if hasattr(tree, "_etree") else tree
                    heading_count, image_count, checkbox_count, checkbox_checked = (
                        self._count_elements(root)
                    )
            except Exception:
                pass

            # Links
            links_view = LinksView.new_from_index(self.notebook.index)
            try:
                links_out = links_view.n_list_links(path, LINK_DIR_FORWARD)
            except Exception:
                links_out = 0
            try:
                links_in = links_view.n_list_links(path, LINK_DIR_BACKWARD)
            except Exception:
                links_in = 0

            # Tags
            tags_view = TagsView.new_from_index(self.notebook.index)
            try:
                tag_count = tags_view.n_list_tags(path)
            except Exception:
                tag_count = 0

            # Age
            page_mtime = None
            page_ctime = None
            age_days = None
            days_since_edit = None
            try:
                page_mtime = page.mtime
                if page_mtime:
                    days_since_edit = round((time.time() - page_mtime) / 86400, 1)
            except Exception:
                pass
            try:
                page_ctime = page.ctime
                if page_ctime:
                    age_days = round((time.time() - page_ctime) / 86400, 1)
            except Exception:
                pass

            return (
                200,
                {},
                {
                    "name": page.name,
                    "exists": True,
                    "words": words,
                    "characters": characters,
                    "lines": line_count,
                    "reading_time_minutes": reading_time,
                    "headings": heading_count,
                    "links_out": links_out,
                    "links_in": links_in,
                    "images": image_count,
                    "tags": tag_count,
                    "checkboxes": checkbox_count,
                    "checkboxes_checked": checkbox_checked,
                    "mtime": page_mtime,
                    "ctime": page_ctime,
                    "age_days": age_days,
                    "days_since_edit": days_since_edit,
                },
            )

        return _run_synchronized(_do)

    def _count_elements(self, node):
        """Count headings, images, checkboxes in a parse tree."""
        headings = 0
        images = 0
        checkboxes = 0
        checked = 0

        def _walk(n):
            nonlocal headings, images, checkboxes, checked
            if n.tag == "h":
                headings += 1
            elif n.tag == "img":
                images += 1
            elif n.tag in ("li",) and n.attrib.get("bullet") in (
                "checked-box",
                "unchecked-box",
                "xchecked-box",
            ):
                checkboxes += 1
                if n.attrib.get("bullet") in ("checked-box", "xchecked-box"):
                    checked += 1
            for child in n:
                _walk(child)

        _walk(node)
        return headings, images, checkboxes, checked

    # ---- Capabilities ----

    def get_capabilities(self):
        """GET /api/capabilities — report which features are available"""

        def _do():
            caps = {
                # Core (always available)
                "pages": True,
                "search": True,
                "tags": True,
                "links": True,
                "attachments": True,
                "export": True,
                "templates": True,
                "toc": True,
                "analytics": True,
                "graph": True,
                "analysis": True,
                "store": True,
                "batch": True,
                "sse": self.event_manager is not None,
                "navigate": self.app is not None
                and hasattr(self.app, "request_navigate"),
            }

            # Optional features (not yet implemented as standalone modules)
            caps["tasklist"] = False
            caps["journal"] = False
            caps["fts"] = True  # Built-in search via moonstone.search
            caps["versioncontrol"] = False
            caps["sourceview"] = False
            caps["tableeditor"] = False
            caps["bookmarksbar"] = False

            caps["readonly"] = bool(self.notebook.readonly)

            return (
                200,
                {},
                {
                    "capabilities": caps,
                    "api_version": "2.5",
                    "websocket": self._get_ws_info(),
                    "sse": {"url": "/events"},
                },
            )

        return _run_synchronized(_do)

    # ---- Analysis: Orphans ----

    def get_orphan_pages(self):
        """GET /api/analysis/orphans — pages with no incoming links"""

        def _do():
            from moonstone.notebook import Path
            from moonstone.notebook.index.links import LinksView, LINK_DIR_BACKWARD

            links_view = LinksView.new_from_index(self.notebook.index)
            orphans = []

            for page_info in self.notebook.pages.walk():
                if not page_info.hascontent:
                    continue
                try:
                    n_backlinks = links_view.n_list_links(page_info, LINK_DIR_BACKWARD)
                    if n_backlinks == 0:
                        orphans.append(
                            {
                                "name": page_info.name,
                                "basename": page_info.basename,
                                "haschildren": page_info.haschildren,
                            }
                        )
                except Exception:
                    pass

            return (
                200,
                {},
                {
                    "orphans": orphans,
                    "count": len(orphans),
                },
            )

        return _run_synchronized(_do, timeout=30)

    # ---- Analysis: Dead Links ----

    def get_dead_links(self):
        """GET /api/analysis/dead-links — links pointing to non-existent pages"""

        def _do():
            from moonstone.notebook import Path
            from moonstone.notebook.index.links import LinksView, LINK_DIR_FORWARD

            links_view = LinksView.new_from_index(self.notebook.index)
            dead = []
            seen = set()

            for page_info in self.notebook.pages.walk():
                if not page_info.hascontent:
                    continue
                try:
                    for link in links_view.list_links(page_info, LINK_DIR_FORWARD):
                        target = link.target
                        key = (page_info.name, target.name)
                        if key in seen:
                            continue
                        seen.add(key)
                        try:
                            target_record = self.notebook.pages.lookup_by_pagename(
                                target
                            )
                            if not target_record.hascontent:
                                dead.append(
                                    {
                                        "source": page_info.name,
                                        "target": target.name,
                                    }
                                )
                        except Exception:
                            dead.append(
                                {
                                    "source": page_info.name,
                                    "target": target.name,
                                }
                            )
                except Exception:
                    pass

            return (
                200,
                {},
                {
                    "dead_links": dead,
                    "count": len(dead),
                },
            )

        return _run_synchronized(_do, timeout=30)

    # ---- Graph Data ----

    def get_graph(self, namespace=None, depth=None):
        """GET /api/graph — nodes and edges for link graph visualization"""

        def _do():
            from moonstone.notebook import Path
            from moonstone.notebook.index.links import LinksView, LINK_DIR_FORWARD

            links_view = LinksView.new_from_index(self.notebook.index)

            if namespace:
                root = self.notebook.pages.lookup_from_user_input(namespace)
            else:
                root = Path(":")

            # Collect all pages as nodes
            nodes = {}
            for page_info in self.notebook.pages.walk(root):
                if not page_info.hascontent:
                    continue
                nodes[page_info.name] = {
                    "id": page_info.name,
                    "label": page_info.basename,
                    "haschildren": page_info.haschildren,
                }

            # Collect edges
            edges = []
            for name in list(nodes.keys()):
                try:
                    path = self.notebook.pages.lookup_from_user_input(name)
                    for link in links_view.list_links(path, LINK_DIR_FORWARD):
                        target_name = link.target.name
                        # Add target node if not in namespace but linked
                        if target_name not in nodes:
                            nodes[target_name] = {
                                "id": target_name,
                                "label": target_name.split(":")[-1],
                                "haschildren": False,
                                "external": True,
                            }
                        edges.append(
                            {
                                "source": name,
                                "target": target_name,
                            }
                        )
                except Exception:
                    pass

            # Calculate degree for each node
            for n in nodes.values():
                n["degree"] = 0
            for e in edges:
                if e["source"] in nodes:
                    nodes[e["source"]]["degree"] = (
                        nodes[e["source"]].get("degree", 0) + 1
                    )
                if e["target"] in nodes:
                    nodes[e["target"]]["degree"] = (
                        nodes[e["target"]].get("degree", 0) + 1
                    )

            return (
                200,
                {},
                {
                    "nodes": list(nodes.values()),
                    "edges": edges,
                    "node_count": len(nodes),
                    "edge_count": len(edges),
                    "namespace": namespace or ":",
                },
            )

        return _run_synchronized(_do, timeout=30)

    # ================================================================
    # NEW API METHODS (v2.5) — Applet Installation from Git
    # ================================================================

    def install_applet(self, url, branch=None, name=None):
        """POST /api/applets/install — install an applet from a Git repository"""
        from moonstone.webbridge.installer import AppletInstaller, InstallError

        installer = AppletInstaller(self.app.applets_dir)
        try:
            result = installer.install_from_git(url, branch, name)
            # Refresh applet manager
            if self.applet_manager:
                self.applet_manager.refresh()
            # Emit SSE event
            if self.event_manager:
                self.event_manager.emit(
                    "applet-installed",
                    {
                        "name": result["name"],
                        "repository": url,
                    },
                )
            return 200, {}, result
        except InstallError as e:
            return 400, {}, {"error": str(e)}
        except Exception as e:
            logger.exception("install_applet error")
            return 500, {}, {"error": "Installation failed: %s" % str(e)}

    def uninstall_applet(self, name):
        """DELETE /api/applets/<name> — uninstall an applet"""
        from moonstone.webbridge.installer import AppletInstaller, InstallError

        installer = AppletInstaller(self.app.applets_dir)
        try:
            result = installer.uninstall(name)
            # Refresh applet manager
            if self.applet_manager:
                self.applet_manager.refresh()
            # Emit SSE event
            if self.event_manager:
                self.event_manager.emit("applet-uninstalled", {"name": name})
            return 200, {}, result
        except InstallError as e:
            return 400, {}, {"error": str(e)}
        except Exception as e:
            logger.exception("uninstall_applet error")
            return 500, {}, {"error": "Uninstall failed: %s" % str(e)}

    def update_applet(self, name):
        """POST /api/applets/<name>/update — update a git-installed applet"""
        from moonstone.webbridge.installer import AppletInstaller, InstallError

        installer = AppletInstaller(self.app.applets_dir)
        try:
            result = installer.update(name)
            # Refresh applet manager
            if self.applet_manager:
                self.applet_manager.refresh()
            # Emit SSE event
            if self.event_manager and result.get("updated"):
                self.event_manager.emit(
                    "applet-updated",
                    {
                        "name": name,
                        "new_commit": result.get("new_commit", ""),
                    },
                )
            return 200, {}, result
        except InstallError as e:
            return 400, {}, {"error": str(e)}
        except Exception as e:
            logger.exception("update_applet error")
            return 500, {}, {"error": "Update failed: %s" % str(e)}

    def check_applet_updates(self):
        """GET /api/applets/updates — check all git-installed applets for updates"""
        from moonstone.webbridge.installer import AppletInstaller

        installer = AppletInstaller(self.app.applets_dir)
        try:
            results = installer.check_all_updates()
            has_updates = any(r.get("has_update") for r in results)
            return (
                200,
                {},
                {
                    "applets": results,
                    "count": len(results),
                    "has_updates": has_updates,
                },
            )
        except Exception as e:
            logger.exception("check_applet_updates error")
            return 500, {}, {"error": "Check failed: %s" % str(e)}

    def get_applet_source(self, name):
        """GET /api/applets/<name>/source — get installation source info"""
        from moonstone.webbridge.installer import AppletInstaller

        installer = AppletInstaller(self.app.applets_dir)
        info = installer.get_source_info(name)
        if info is None:
            return 404, {}, {"error": "Applet not found: %s" % name}
        return 200, {}, info

    def patch_page(self, page_path, operations, expected_mtime=None):
        """PATCH /api/page/<path> — apply partial updates to a page

        Operations format:
        [
                {"op": "replace", "search": "old text", "replace": "new text"},
                {"op": "insert_after", "search": "anchor text", "content": "new content"},
                {"op": "delete", "search": "text to delete"}
        ]
        """

        def _do():
            if self.notebook.readonly:
                return 403, {}, {"error": "Notebook is read-only"}

            from moonstone.notebook import Path

            path = self.notebook.pages.lookup_from_user_input(page_path)
            page = self.notebook.get_page(path)

            if not page.hascontent:
                return 404, {}, {"error": "Page has no content: %s" % page_path}

            if page.readonly:
                return 403, {}, {"error": "Page is read-only"}

            # Use profile format for reading/writing
            fmt = self._get_profile_format()

            # Optimistic concurrency check
            if expected_mtime is not None:
                try:
                    current_mtime = page.mtime
                    if (
                        current_mtime is not None
                        and abs(current_mtime - expected_mtime) > 0.01
                    ):
                        return (
                            409,
                            {},
                            {
                                "error": "Page was modified since last read",
                                "expected_mtime": expected_mtime,
                                "current_mtime": current_mtime,
                            },
                        )
                except Exception:
                    pass

            # Get current content using profile format
            try:
                lines = page.dump(fmt)
                content = "".join(lines)
            except Exception as e:
                return 500, {}, {"error": "Failed to read page: %s" % str(e)}

            # Apply operations
            applied = []
            for i, op in enumerate(operations):
                op_type = op.get("op", "replace")
                search = op.get("search", "")

                if not search:
                    applied.append(
                        {"index": i, "ok": False, "error": "Missing search text"}
                    )
                    continue

                if search not in content:
                    applied.append(
                        {"index": i, "ok": False, "error": "Search text not found"}
                    )
                    continue

                if op_type == "replace":
                    replace_text = op.get("replace", "")
                    content = content.replace(search, replace_text, 1)
                    applied.append({"index": i, "ok": True, "op": "replace"})

                elif op_type == "insert_after":
                    insert_content = op.get("content", "")
                    pos = content.find(search) + len(search)
                    content = content[:pos] + insert_content + content[pos:]
                    applied.append({"index": i, "ok": True, "op": "insert_after"})

                elif op_type == "delete":
                    content = content.replace(search, "", 1)
                    applied.append({"index": i, "ok": True, "op": "delete"})

                else:
                    applied.append(
                        {"index": i, "ok": False, "error": "Unknown op: %s" % op_type}
                    )

            # Save modified content using profile format
            page.parse(fmt, content)
            self._store_page_safe(page)

            new_mtime = None
            try:
                new_mtime = page.mtime
            except Exception:
                pass

            if self.app:
                self.app.notify_page_saved(page.name)

            return (
                200,
                {},
                {
                    "ok": True,
                    "page": page_path,
                    "mtime": new_mtime,
                    "operations": applied,
                },
            )

        return _run_synchronized(_do)

    # ================================================================
    # SERVICE API (v3.0) — Background service management
    # ================================================================

    def list_services(self):
        """GET /api/services — list all discovered services"""
        if not self.service_manager:
            return 503, {}, {"error": "Service manager not available"}
        self.service_manager.refresh()
        services = self.service_manager.list_services()
        return 200, {}, {"services": services, "count": len(services)}

    def get_service(self, name):
        """GET /api/services/<name> — get service status and metadata"""
        if not self.service_manager:
            return 503, {}, {"error": "Service manager not available"}
        svc = self.service_manager.get_service(name)
        if not svc:
            return 404, {}, {"error": "Service not found: %s" % name}
        return 200, {}, svc.to_dict()

    def start_service(self, name):
        """POST /api/services/<name>/start — start a service"""
        if not self.service_manager:
            return 503, {}, {"error": "Service manager not available"}
        result = self.service_manager.start_service(name)
        if result.get("error"):
            return 400, {}, result
        return 200, {}, result

    def stop_service(self, name):
        """POST /api/services/<name>/stop — stop a service"""
        if not self.service_manager:
            return 503, {}, {"error": "Service manager not available"}
        result = self.service_manager.stop_service(name)
        if result.get("error"):
            return 400, {}, result
        return 200, {}, result

    def restart_service(self, name):
        """POST /api/services/<name>/restart — restart a service"""
        if not self.service_manager:
            return 503, {}, {"error": "Service manager not available"}
        result = self.service_manager.restart_service(name)
        if result.get("error"):
            return 400, {}, result
        return 200, {}, result

    def get_service_logs(self, name, tail=100):
        """GET /api/services/<name>/logs?tail=... — get service log output"""
        if not self.service_manager:
            return 503, {}, {"error": "Service manager not available"}
        result = self.service_manager.get_logs(name, tail)
        if result.get("error"):
            return 404, {}, result
        return 200, {}, result

    def get_service_config(self, name):
        """GET /api/services/<name>/config — get service configuration"""
        if not self.service_manager:
            return 503, {}, {"error": "Service manager not available"}
        result, error = self.service_manager.get_config(name)
        if error:
            return 404, {}, {"error": error}
        return 200, {}, result

    def save_service_config(self, name, config):
        """PUT /api/services/<name>/config — save service configuration"""
        if not self.service_manager:
            return 503, {}, {"error": "Service manager not available"}
        result, error = self.service_manager.save_config(name, config)
        if error:
            return 400, {}, {"error": error}
        return 200, {}, result

    def install_service(self, url, branch=None, name=None):
        """POST /api/services/install — install a service from Git"""
        if not self.service_manager:
            return 503, {}, {"error": "Service manager not available"}

        from moonstone.webbridge.installer import ServiceInstaller, InstallError

        installer = ServiceInstaller(self.service_manager.services_dir)
        try:
            result = installer.install_from_git(url, branch, name)
            self.service_manager.refresh()
            if self.event_manager:
                self.event_manager.emit(
                    "service:installed",
                    {
                        "name": result["name"],
                        "repository": url,
                    },
                )
            return 200, {}, result
        except InstallError as e:
            return 400, {}, {"error": str(e)}
        except Exception as e:
            logger.exception("install_service error")
            return 500, {}, {"error": "Installation failed: %s" % str(e)}

    def uninstall_service(self, name):
        """DELETE /api/services/<name> — stop and uninstall a service"""
        if not self.service_manager:
            return 503, {}, {"error": "Service manager not available"}

        # Stop if running
        svc = self.service_manager.get_service(name)
        if svc and svc.status == "running":
            self.service_manager.stop_service(name)

        from moonstone.webbridge.installer import ServiceInstaller, InstallError

        installer = ServiceInstaller(self.service_manager.services_dir)
        try:
            result = installer.uninstall(name)
            self.service_manager.refresh()
            if self.event_manager:
                self.event_manager.emit("service:uninstalled", {"name": name})
            return 200, {}, result
        except InstallError as e:
            return 400, {}, {"error": str(e)}
        except Exception as e:
            logger.exception("uninstall_service error")
            return 500, {}, {"error": "Uninstall failed: %s" % str(e)}

    def update_service(self, name):
        """POST /api/services/<name>/update — update a git-installed service"""
        if not self.service_manager:
            return 503, {}, {"error": "Service manager not available"}

        # Stop if running (will need restart after update)
        was_running = False
        svc = self.service_manager.get_service(name)
        if svc and svc.status == "running":
            self.service_manager.stop_service(name)
            was_running = True

        from moonstone.webbridge.installer import ServiceInstaller, InstallError

        installer = ServiceInstaller(self.service_manager.services_dir)
        try:
            result = installer.update(name)
            self.service_manager.refresh()
            if self.event_manager and result.get("updated"):
                self.event_manager.emit(
                    "service:updated",
                    {
                        "name": name,
                        "new_commit": result.get("new_commit", ""),
                    },
                )
            result["was_running"] = was_running
            return 200, {}, result
        except InstallError as e:
            return 400, {}, {"error": str(e)}
        except Exception as e:
            logger.exception("update_service error")
            return 500, {}, {"error": "Update failed: %s" % str(e)}
