# -*- coding: utf-8 -*-
"""LinksView for Moonstone index.

Standalone links module — queries link data from SQLite.
"""

from moonstone.notebook.page import Path

LINK_DIR_FORWARD = 1
LINK_DIR_BACKWARD = 2
LINK_DIR_BOTH = 3


class LinkInfo:
    """Represents a link between two pages."""

    __slots__ = ("source", "target", "href")

    def __init__(self, source, target, href=""):
        self.source = source if isinstance(source, Path) else Path(source)
        self.target = target if isinstance(target, Path) else Path(target)
        self.href = href

    def __repr__(self):
        return "<LinkInfo: %s → %s>" % (self.source, self.target)


class LinksView:
    """Query links between pages from the index.

    LinksView interface.
    """

    def __init__(self, db):
        self._db = db

    @classmethod
    def new_from_index(cls, index):
        return cls(index.db)

    def list_links(self, path, direction=LINK_DIR_FORWARD):
        """List links from/to a page.

        @param path: Path object
        @param direction: LINK_DIR_FORWARD, LINK_DIR_BACKWARD, or LINK_DIR_BOTH
        @returns: iterator of LinkInfo
        """
        name = path.name if hasattr(path, "name") else str(path)
        results = []

        if direction in (LINK_DIR_FORWARD, LINK_DIR_BOTH):
            rows = self._db.execute(
                """
                SELECT p1.name as source_name, p2.name as target_name, l.names
                FROM links l
                JOIN pages p1 ON l.source = p1.id
                JOIN pages p2 ON l.target = p2.id
                WHERE p1.name = ?
            """,
                (name,),
            ).fetchall()
            for row in rows:
                results.append(
                    LinkInfo(row["source_name"], row["target_name"], row["names"] or "")
                )

        if direction in (LINK_DIR_BACKWARD, LINK_DIR_BOTH):
            rows = self._db.execute(
                """
                SELECT p1.name as source_name, p2.name as target_name, l.names
                FROM links l
                JOIN pages p1 ON l.source = p1.id
                JOIN pages p2 ON l.target = p2.id
                WHERE p2.name = ?
            """,
                (name,),
            ).fetchall()
            for row in rows:
                if direction == LINK_DIR_BOTH:
                    # Avoid duplicates if both source and target are the same page
                    link = LinkInfo(
                        row["source_name"], row["target_name"], row["names"] or ""
                    )
                    if link.source.name != name or link.target.name != name:
                        results.append(link)
                    elif not any(
                        r.source.name == link.source.name
                        and r.target.name == link.target.name
                        for r in results
                    ):
                        results.append(link)
                else:
                    results.append(
                        LinkInfo(
                            row["source_name"], row["target_name"], row["names"] or ""
                        )
                    )

        return iter(results)

    def n_list_links(self, path, direction=LINK_DIR_FORWARD):
        """Count links from/to a page."""
        name = path.name if hasattr(path, "name") else str(path)
        count = 0

        if direction in (LINK_DIR_FORWARD, LINK_DIR_BOTH):
            row = self._db.execute(
                """
                SELECT COUNT(*) FROM links l
                JOIN pages p ON l.source = p.id
                WHERE p.name = ?
            """,
                (name,),
            ).fetchone()
            count += row[0]

        if direction in (LINK_DIR_BACKWARD, LINK_DIR_BOTH):
            row = self._db.execute(
                """
                SELECT COUNT(*) FROM links l
                JOIN pages p ON l.target = p.id
                WHERE p.name = ?
            """,
                (name,),
            ).fetchone()
            count += row[0]

        return count

    def list_links_section(self, path, direction=LINK_DIR_FORWARD):
        """List links for a page and all its children."""
        name = path.name if hasattr(path, "name") else str(path)
        results = []

        if direction in (LINK_DIR_FORWARD, LINK_DIR_BOTH):
            rows = self._db.execute(
                """
                SELECT p1.name as source_name, p2.name as target_name, l.names
                FROM links l
                JOIN pages p1 ON l.source = p1.id
                JOIN pages p2 ON l.target = p2.id
                WHERE p1.name = ? OR p1.name LIKE ?
            """,
                (name, name + ":%"),
            ).fetchall()
            for row in rows:
                results.append(
                    LinkInfo(row["source_name"], row["target_name"], row["names"] or "")
                )

        if direction in (LINK_DIR_BACKWARD, LINK_DIR_BOTH):
            rows = self._db.execute(
                """
                SELECT p1.name as source_name, p2.name as target_name, l.names
                FROM links l
                JOIN pages p1 ON l.source = p1.id
                JOIN pages p2 ON l.target = p2.id
                WHERE p2.name = ? OR p2.name LIKE ?
            """,
                (name, name + ":%"),
            ).fetchall()
            for row in rows:
                results.append(
                    LinkInfo(row["source_name"], row["target_name"], row["names"] or "")
                )

        return iter(results)

    def list_floating_links(self, basename=None):
        """List links where target has no namespace (floating links)."""
        if basename:
            rows = self._db.execute(
                """
                SELECT p1.name as source_name, p2.name as target_name, l.names
                FROM links l
                JOIN pages p1 ON l.source = p1.id
                JOIN pages p2 ON l.target = p2.id
                WHERE p2.basename = ? AND p2.name NOT LIKE '%:%'
            """,
                (basename,),
            ).fetchall()
        else:
            rows = self._db.execute("""
                SELECT p1.name as source_name, p2.name as target_name, l.names
                FROM links l
                JOIN pages p1 ON l.source = p1.id
                JOIN pages p2 ON l.target = p2.id
                WHERE p2.name NOT LIKE '%:%'
            """).fetchall()

        return iter(
            LinkInfo(r["source_name"], r["target_name"], r["names"] or "") for r in rows
        )
