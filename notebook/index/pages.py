# -*- coding: utf-8 -*-
"""PagesView for Moonstone index.

Standalone pages module — queries page data from SQLite.
"""

import re
from moonstone.notebook.page import (
    Path,
    HRef,
    HREF_REL_ABSOLUTE,
    HREF_REL_FLOATING,
    HREF_REL_RELATIVE,
)


class PageInfo:
    """Lightweight page record from the index.

    PageIndexRecord interface — provides
    name, basename, hascontent, haschildren, mtime attributes.
    """

    __slots__ = (
        "name",
        "basename",
        "hascontent",
        "haschildren",
        "mtime",
        "ctime",
        "id",
    )

    def __init__(
        self,
        name,
        basename=None,
        hascontent=True,
        haschildren=False,
        mtime=None,
        ctime=None,
        id=None,
    ):
        self.name = name
        self.basename = basename or (name.split(":")[-1] if ":" in name else name)
        self.hascontent = bool(hascontent)
        self.haschildren = bool(haschildren)
        self.mtime = mtime
        self.ctime = ctime
        self.id = id

    def __repr__(self):
        return "<PageInfo: %s>" % self.name

    def __eq__(self, other):
        if isinstance(other, (PageInfo, Path)):
            return self.name == other.name
        return False

    def __hash__(self):
        return hash(self.name)


def _row_to_pageinfo(row):
    """Convert a sqlite3.Row to PageInfo."""
    return PageInfo(
        name=row["name"],
        basename=row["basename"],
        hascontent=bool(row["hascontent"]),
        haschildren=bool(row["haschildren"]),
        mtime=row["mtime"],
        ctime=row["ctime"] if "ctime" in row.keys() else None,
        id=row["id"],
    )


class PagesView:
    """Query pages from the index.

    PagesView interface and the
    notebook.pages proxy used by WebBridge api.py.
    """

    def __init__(self, db):
        self._db = db

    @classmethod
    def new_from_index(cls, index):
        return cls(index.db)

    def lookup_from_user_input(self, name):
        """Resolve user input to a Path."""
        name = name.strip().strip(":")
        return Path(name)

    def lookup_by_pagename(self, name):
        """Look up a page by its full name.

        @returns: PageInfo or None
        """
        if isinstance(name, Path):
            name = name.name
        name = name.strip(":")

        row = self._db.execute("SELECT * FROM pages WHERE name = ?", (name,)).fetchone()
        if row:
            return _row_to_pageinfo(row)
        return None

    def list_pages(self, path=None):
        """List direct children of a page (or root if path is None/root).

        @returns: iterator of PageInfo
        """
        if (
            path is None
            or (hasattr(path, "isroot") and path.isroot)
            or str(path) == ":"
        ):
            # Root-level pages
            rows = self._db.execute(
                "SELECT * FROM pages WHERE parent IS NULL AND (hascontent=1 OR haschildren=1) "
                "ORDER BY sortkey"
            ).fetchall()
        else:
            name = path.name if hasattr(path, "name") else str(path).strip(":")
            parent_row = self._db.execute(
                "SELECT id FROM pages WHERE name = ?", (name,)
            ).fetchone()
            if not parent_row:
                return iter([])
            rows = self._db.execute(
                "SELECT * FROM pages WHERE parent = ? AND (hascontent=1 OR haschildren=1) "
                "ORDER BY sortkey",
                (parent_row[0],),
            ).fetchall()

        return iter(_row_to_pageinfo(r) for r in rows)

    def walk(self, path=None):
        """Walk all pages recursively (depth-first).

        @returns: iterator of PageInfo
        """
        if (
            path is None
            or (hasattr(path, "isroot") and path.isroot)
            or str(path) == ":"
        ):
            rows = self._db.execute(
                "SELECT * FROM pages WHERE hascontent=1 OR haschildren=1 ORDER BY sortkey"
            ).fetchall()
        else:
            name = path.name if hasattr(path, "name") else str(path).strip(":")
            rows = self._db.execute(
                "SELECT * FROM pages WHERE (name = ? OR name LIKE ?) "
                "AND (hascontent=1 OR haschildren=1) ORDER BY sortkey",
                (name, name + ":%"),
            ).fetchall()

        return iter(_row_to_pageinfo(r) for r in rows)

    def match_all_pages(self, query, limit=10):
        """Search pages by name prefix (autocomplete).

        @returns: iterator of PageInfo
        """
        query = query.strip()
        if not query:
            return iter([])

        # Try LIKE match
        rows = self._db.execute(
            "SELECT * FROM pages WHERE name LIKE ? AND hascontent=1 "
            "ORDER BY sortkey LIMIT ?",
            ("%" + query + "%", limit),
        ).fetchall()

        return iter(_row_to_pageinfo(r) for r in rows)

    def n_all_pages(self):
        """Count total pages with content."""
        row = self._db.execute(
            "SELECT COUNT(*) FROM pages WHERE hascontent=1"
        ).fetchone()
        return row[0]

    def n_list_pages(self, path=None):
        """Count direct children of a page."""
        if (
            path is None
            or (hasattr(path, "isroot") and path.isroot)
            or str(path) == ":"
        ):
            row = self._db.execute(
                "SELECT COUNT(*) FROM pages WHERE parent IS NULL AND (hascontent=1 OR haschildren=1)"
            ).fetchone()
        else:
            name = path.name if hasattr(path, "name") else str(path).strip(":")
            parent_row = self._db.execute(
                "SELECT id FROM pages WHERE name = ?", (name,)
            ).fetchone()
            if not parent_row:
                return 0
            row = self._db.execute(
                "SELECT COUNT(*) FROM pages WHERE parent = ? AND (hascontent=1 OR haschildren=1)",
                (parent_row[0],),
            ).fetchone()
        return row[0]

    def get_previous(self, path):
        """Get the previous page in sort order.

        @returns: Path or None
        """
        name = path.name if hasattr(path, "name") else str(path).strip(":")
        row = self._db.execute(
            "SELECT sortkey FROM pages WHERE name = ?", (name,)
        ).fetchone()
        if not row:
            return None

        prev = self._db.execute(
            "SELECT name FROM pages WHERE sortkey < ? AND hascontent=1 "
            "ORDER BY sortkey DESC LIMIT 1",
            (row["sortkey"],),
        ).fetchone()
        return Path(prev["name"]) if prev else None

    def get_next(self, path):
        """Get the next page in sort order.

        @returns: Path or None
        """
        name = path.name if hasattr(path, "name") else str(path).strip(":")
        row = self._db.execute(
            "SELECT sortkey FROM pages WHERE name = ?", (name,)
        ).fetchone()
        if not row:
            return None

        nxt = self._db.execute(
            "SELECT name FROM pages WHERE sortkey > ? AND hascontent=1 "
            "ORDER BY sortkey ASC LIMIT 1",
            (row["sortkey"],),
        ).fetchone()
        return Path(nxt["name"]) if nxt else None

    def list_recent_changes(self, limit=20, offset=0):
        """List pages ordered by modification time (most recent first).

        @returns: iterator of PageInfo
        """
        rows = self._db.execute(
            "SELECT * FROM pages WHERE hascontent=1 AND mtime IS NOT NULL "
            "ORDER BY mtime DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return iter(_row_to_pageinfo(r) for r in rows)

    def resolve_link(self, source, href):
        """Resolve an HRef relative to source page.

        @param source: source Path
        @param href: HRef object
        @returns: Path
        """
        if isinstance(href, str):
            href = HRef.new_from_wiki_link(href)

        if href.rel == HREF_REL_ABSOLUTE:
            return Path(href.names)
        elif href.rel == HREF_REL_RELATIVE:
            source_name = source.name if hasattr(source, "name") else str(source)
            return Path(source_name + ":" + href.names)
        else:
            # Floating — search upward through namespaces
            source_name = source.name if hasattr(source, "name") else str(source)
            parts = source_name.split(":") if source_name else []

            # Try from deepest to shallowest namespace
            while parts:
                candidate = ":".join(parts) + ":" + href.names
                row = self._db.execute(
                    "SELECT name FROM pages WHERE name = ?", (candidate,)
                ).fetchone()
                if row:
                    return Path(row["name"])
                parts.pop()

            # Global fallback: search by basename anywhere in notebook
            row = self._db.execute(
                "SELECT name FROM pages WHERE basename = ? AND hascontent=1 LIMIT 1",
                (href.names,),
            ).fetchone()
            if row:
                return Path(row["name"])

            # Top-level (unresolved)
            return Path(href.names)

    def create_link(self, source, target):
        """Create an HRef from source to target.

        @param source: source Path
        @param target: target Path
        @returns: HRef
        """
        source_name = source.name if hasattr(source, "name") else str(source)
        target_name = target.name if hasattr(target, "name") else str(target)

        # If target is child of source, use relative
        if target_name.startswith(source_name + ":"):
            rel_name = target_name[len(source_name) + 1 :]
            return HRef(HREF_REL_RELATIVE, rel_name)

        # If in same namespace, use floating
        source_ns = source_name.rsplit(":", 1)[0] if ":" in source_name else ""
        target_ns = target_name.rsplit(":", 1)[0] if ":" in target_name else ""

        if source_ns == target_ns:
            basename = target_name.rsplit(":", 1)[-1]
            return HRef(HREF_REL_FLOATING, basename)

        # Otherwise absolute
        return HRef(HREF_REL_ABSOLUTE, target_name)
