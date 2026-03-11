# -*- coding: utf-8 -*-
"""Full-text search for Moonstone.

Standalone search module — provides Query and SearchSelection using FTS5.
"""

import re


class Query:
    """Parsed search query.

    Supports: simple words (AND), "exact phrase",
    Content:xxx, Name:xxx, Tag:xxx prefixes.
    """

    def __init__(self, query_string):
        self.string = query_string.strip()

    def __str__(self):
        return self.string

    def __bool__(self):
        return bool(self.string)


class SearchSelection:
    """Search results container.

    Usage::
        selection = SearchSelection(notebook)
        selection.search(query)
        for path in selection:
            print(path.name, selection.scores[path])
    """

    def __init__(self, notebook):
        self.notebook = notebook
        self._results = []
        self.scores = {}

    def search(self, query, callback=None):
        """Execute the search query."""
        from moonstone.notebook.page import Path

        query_str = query.string if isinstance(query, Query) else str(query)
        if not query_str:
            return

        self._results = []
        self.scores = {}

        db = self.notebook.index.db

        # Try FTS5 first
        try:
            fts_query = self._build_fts_query(query_str)
            rows = db.execute(
                """
                SELECT p.name, rank
                FROM pages_fts
                JOIN pages p ON p.id = pages_fts.rowid
                WHERE pages_fts MATCH ?
                ORDER BY rank
                LIMIT 100
            """,
                (fts_query,),
            ).fetchall()

            for row in rows:
                path = Path(row["name"])
                self._results.append(path)
                self.scores[path] = -row["rank"]  # FTS5 rank is negative

        except Exception:
            # Fallback: LIKE search on page names and content
            self._fallback_search(query_str, db)

    def _build_fts_query(self, query_str):
        """Convert query string to FTS5 syntax."""
        # Handle Tag:xxx → search in content for @xxx
        query_str = re.sub(r"Tag:(\w+)", r"@\1", query_str)
        # Handle Name:xxx → search in name column
        query_str = re.sub(r"Name:(\w+)", r"name:\1", query_str)
        # Handle Content:xxx → search in content
        query_str = re.sub(r"Content:(\w+)", r"content:\1", query_str)

        # Simple words → AND them
        parts = query_str.split()
        if len(parts) > 1 and not any(
            op in query_str for op in ["AND", "OR", "NOT", '"']
        ):
            return " AND ".join(parts)
        return query_str

    def _fallback_search(self, query_str, db):
        """Simple LIKE-based search fallback."""
        from moonstone.notebook.page import Path

        words = query_str.split()
        if not words:
            return

        conditions = []
        params = []
        for word in words:
            if word.startswith("Tag:"):
                tag_name = word[4:]
                # Search in tags
                tag_rows = db.execute(
                    """
                    SELECT p.name FROM pages p
                    JOIN tagsources ts ON p.id = ts.source
                    JOIN tags t ON ts.tag = t.id
                    WHERE t.name LIKE ?
                """,
                    ("%" + tag_name + "%",),
                ).fetchall()
                for tr in tag_rows:
                    path = Path(tr["name"])
                    if path not in self._results:
                        self._results.append(path)
                        self.scores[path] = 1.0
            elif word.startswith("Name:"):
                conditions.append("name LIKE ?")
                params.append("%" + word[5:] + "%")
            else:
                conditions.append("(name LIKE ? OR content LIKE ?)")
                val = "%" + word + "%"
                params.extend([val, val])

        if conditions:
            sql = (
                "SELECT name FROM pages WHERE hascontent=1 AND "
                + " AND ".join(conditions)
                + " ORDER BY sortkey LIMIT 100"
            )
            rows = db.execute(sql, params).fetchall()
            for row in rows:
                path = Path(row["name"])
                if path not in self._results:
                    self._results.append(path)
                    self.scores[path] = 1.0

    def __iter__(self):
        return iter(self._results)

    def __len__(self):
        return len(self._results)

    def __bool__(self):
        return bool(self._results)
