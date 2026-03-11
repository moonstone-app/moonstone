# -*- coding: utf-8 -*-
"""TagsView for Moonstone index.

Standalone tags module — queries tag data from SQLite.
"""

from moonstone.notebook.index.pages import PageInfo, _row_to_pageinfo


class IndexTag:
    """Represents a tag in the index."""

    __slots__ = ("name", "id")

    def __init__(self, name, id=None):
        self.name = name
        self.id = id

    def __repr__(self):
        return "<IndexTag: @%s>" % self.name

    def __eq__(self, other):
        if isinstance(other, IndexTag):
            return self.name == other.name
        return False

    def __hash__(self):
        return hash(self.name)

    def __str__(self):
        return self.name


class TagsView:
    """Query tags from the index.

    TagsView interface.
    """

    def __init__(self, db):
        self._db = db

    @classmethod
    def new_from_index(cls, index):
        return cls(index.db)

    def list_all_tags_by_n_pages(self):
        """List all tags ordered by number of pages (descending).

        @returns: iterator of IndexTag
        """
        rows = self._db.execute("""
            SELECT t.id, t.name, COUNT(ts.source) as n
            FROM tags t
            LEFT JOIN tagsources ts ON t.id = ts.tag
            GROUP BY t.id
            ORDER BY n DESC, t.name ASC
        """).fetchall()
        return iter(IndexTag(r["name"], r["id"]) for r in rows)

    def n_list_all_tags(self):
        """Count all distinct tags."""
        row = self._db.execute("SELECT COUNT(*) FROM tags").fetchone()
        return row[0]

    def list_tags(self, path):
        """List tags used by a specific page.

        @param path: Path object
        @returns: iterator of IndexTag
        """
        name = path.name if hasattr(path, "name") else str(path).strip(":")
        rows = self._db.execute(
            """
            SELECT t.id, t.name
            FROM tags t
            JOIN tagsources ts ON t.id = ts.tag
            JOIN pages p ON ts.source = p.id
            WHERE p.name = ?
            ORDER BY t.name
        """,
            (name,),
        ).fetchall()
        return iter(IndexTag(r["name"], r["id"]) for r in rows)

    def n_list_tags(self, path):
        """Count tags for a specific page."""
        name = path.name if hasattr(path, "name") else str(path).strip(":")
        row = self._db.execute(
            """
            SELECT COUNT(*)
            FROM tagsources ts
            JOIN pages p ON ts.source = p.id
            WHERE p.name = ?
        """,
            (name,),
        ).fetchone()
        return row[0]

    def lookup_by_tagname(self, name):
        """Look up a tag by name.

        @returns: IndexTag or None
        """
        if name.startswith("@"):
            name = name[1:]
        row = self._db.execute(
            "SELECT id, name FROM tags WHERE name = ?", (name,)
        ).fetchone()
        if row:
            return IndexTag(row["name"], row["id"])
        return None

    def list_pages(self, tag):
        """List pages that have a specific tag.

        @param tag: IndexTag object or tag name string
        @returns: iterator of PageInfo
        """
        if isinstance(tag, str):
            tag_name = tag.lstrip("@")
        else:
            tag_name = tag.name

        rows = self._db.execute(
            """
            SELECT p.*
            FROM pages p
            JOIN tagsources ts ON p.id = ts.source
            JOIN tags t ON ts.tag = t.id
            WHERE t.name = ?
            ORDER BY p.sortkey
        """,
            (tag_name,),
        ).fetchall()
        return iter(_row_to_pageinfo(r) for r in rows)

    def n_list_pages(self, tag):
        """Count pages with a given tag."""
        if isinstance(tag, str):
            tag_name = tag.lstrip("@")
        else:
            tag_name = tag.name

        row = self._db.execute(
            """
            SELECT COUNT(*)
            FROM tagsources ts
            JOIN tags t ON ts.tag = t.id
            WHERE t.name = ?
        """,
            (tag_name,),
        ).fetchone()
        return row[0]

    def list_intersecting_tags(self, tags):
        """List tags that co-occur with all given tags.

        @param tags: list of IndexTag objects or tag name strings
        @returns: iterator of IndexTag
        """
        tag_names = []
        for t in tags:
            if isinstance(t, str):
                tag_names.append(t.lstrip("@"))
            else:
                tag_names.append(t.name)

        if not tag_names:
            return iter([])

        # Find pages that have ALL the given tags
        placeholders = ",".join("?" * len(tag_names))
        n = len(tag_names)

        rows = self._db.execute(
            """
            SELECT DISTINCT t2.id, t2.name
            FROM tags t2
            JOIN tagsources ts2 ON t2.id = ts2.tag
            WHERE ts2.source IN (
                SELECT ts.source
                FROM tagsources ts
                JOIN tags t ON ts.tag = t.id
                WHERE t.name IN (%s)
                GROUP BY ts.source
                HAVING COUNT(DISTINCT t.name) = ?
            )
            AND t2.name NOT IN (%s)
            ORDER BY t2.name
        """ % (placeholders, placeholders),
            (*tag_names, n, *tag_names),
        ).fetchall()

        return iter(IndexTag(r["name"], r["id"]) for r in rows)
