# -*- coding: utf-8 -*-
"""SQLite index for Moonstone notebook.

Standalone index module — stores page metadata, tags, and links
in a SQLite database for fast queries.

Uses ConnectionPool for thread-safe concurrent database access.
"""

import os
import re
import sqlite3
import logging
import threading
from contextlib import contextmanager

logger = logging.getLogger("moonstone.index")

# Re-export link direction constants
from moonstone.notebook.index.links import (
    LINK_DIR_FORWARD,
    LINK_DIR_BACKWARD,
    LINK_DIR_BOTH,
)

from moonstone.errors import IndexNotFoundError

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent INTEGER REFERENCES pages(id),
    basename TEXT NOT NULL,
    name TEXT NOT NULL UNIQUE,
    sortkey TEXT,
    hascontent INTEGER DEFAULT 0,
    haschildren INTEGER DEFAULT 0,
    mtime REAL,
    ctime REAL
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    tag_lower TEXT
);

CREATE TABLE IF NOT EXISTS tagsources (
    tag INTEGER REFERENCES tags(id),
    source INTEGER REFERENCES pages(id),
    PRIMARY KEY (tag, source)
);

CREATE TABLE IF NOT EXISTS links (
    source INTEGER REFERENCES pages(id),
    target INTEGER REFERENCES pages(id),
    rel INTEGER DEFAULT 0,
    names TEXT
);

CREATE TABLE IF NOT EXISTS aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page INTEGER NOT NULL REFERENCES pages(id),
    name TEXT NOT NULL,
    name_lower TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_aliases_page_name_lower ON aliases(page, name_lower);

CREATE INDEX IF NOT EXISTS idx_pages_name ON pages(name);
CREATE INDEX IF NOT EXISTS idx_pages_parent ON pages(parent);
CREATE INDEX IF NOT EXISTS idx_links_source ON links(source);
CREATE INDEX IF NOT EXISTS idx_links_target ON links(target);
CREATE INDEX IF NOT EXISTS idx_tagsources_source ON tagsources(source);
CREATE INDEX IF NOT EXISTS idx_tagsources_tag ON tagsources(tag);

CREATE TABLE IF NOT EXISTS schema_info (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

_FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts
USING fts5(name, content, tokenize='unicode61');
"""


def _natural_sort_key(text):
    return "".join(
        c.zfill(20) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", text)
    )


class _DatabaseConnectionWrapper:
    """Wrapper for ConnectionPool that provides SQLite connection interface.

    This wrapper allows the PagesView/TagsView/LinksView classes to work
    with the connection pool transparently.
    """

    def __init__(self, pool):
        self._pool = pool

    def execute(self, sql, params=None):
        """Execute SQL and return cursor."""
        return self._pool.execute(sql, params)

    def executemany(self, sql, params):
        """Execute SQL with multiple parameter sets."""
        return self._pool.execute(sql, params, many=True)

    def commit(self):
        """Commit is handled automatically by the pool."""
        pass

    def cursor(self):
        """Return a cursor - not supported with pool, use execute() instead."""
        raise NotImplementedError(
            "cursor() not supported with connection pool. Use execute() directly."
        )

    def __getattr__(self, name):
        """Proxy any other attributes to a temporary connection.

        This handles cases like row_factory, etc.
        """
        # Get a connection and proxy the attribute
        with self._pool.get_connection() as conn:
            return getattr(conn, name)


class Index:
    """SQLite index for the notebook.

    Provides:
    - is_uptodate property
    - check_and_update() — full filesystem scan
    - update_page(page, tree) — update single page
    - remove_page(path), move_page(old, new)
    - Database connection for PagesView/TagsView/LinksView
    """

    def __init__(self, db_path, layout, root_folder, profile=None, pool_size=4):
        self.db_path = db_path
        self.layout = layout
        self.root_folder = root_folder
        self._lock = threading.RLock()
        self._is_uptodate = False

        # Vault profile for format-specific tag/link extraction
        if profile is None:
            from moonstone.profiles.moonstone_profile import MoonstoneProfile

            self.profile = MoonstoneProfile()
        else:
            self.profile = profile

        # Import ConnectionPool
        from moonstone.notebook.pool import ConnectionPool

        # Create connection pool for concurrent database access
        self._pool = ConnectionPool(db_path, size=pool_size)

        # Initialize schema using pool
        with self._pool.get_connection() as conn:
            conn.executescript(_SCHEMA)
            try:
                conn.executescript(_FTS_SCHEMA)
                self._has_fts = True
            except Exception:
                self._has_fts = False
                logger.debug("FTS5 not available")
            conn.commit()

        # Run schema migrations
        self._migrate_schema()

    @property
    def db(self):
        """Return database connection wrapper for backward compatibility.

        The wrapper uses the connection pool internally, allowing concurrent
        database access while maintaining the same API as before.
        """
        if not hasattr(self, '_db_wrapper'):
            self._db_wrapper = _DatabaseConnectionWrapper(self._pool)
        return self._db_wrapper

    @contextmanager
    def get_connection(self):
        """Get a connection from the pool for direct database access.

        Use this when you need to execute multiple statements in a transaction
        or need access to raw connection features.

        Example:
            with index.get_connection() as conn:
                conn.execute("INSERT INTO pages ...")
                conn.execute("INSERT INTO links ...")
                conn.commit()
        """
        with self._pool.get_connection() as conn:
            yield conn

    def _migrate_schema(self):
        """Migrate database schema to current version.

        Handles migration from older database versions:
        - No schema_info table: adds tag_lower column, aliases table, indexes, backfills data
        - Version 1: current schema with schema_info tracking

        For case-insensitive duplicate tags, the UNIQUE constraint on tag_lower
        will fail naturally and SQLite will report the error clearly.
        """
        with self._pool.get_connection() as conn:
            # Check if schema_info table exists AND has version = '1'
            # Note: schema_info may exist but be empty if created by CREATE TABLE IF NOT EXISTS
            # in _SCHEMA before migration runs. We must check for the version key.
            cursor = conn.execute(
                "SELECT value FROM schema_info WHERE key='version'"
            )
            row = cursor.fetchone()
            if row is not None and row[0] == '1':
                # Already migrated to version 1
                return

            # Old database without schema_info or version - needs migration
            conn.execute("BEGIN TRANSACTION")
            try:
                # 1. Add tag_lower column if missing
                cursor = conn.execute("PRAGMA table_info(tags)")
                columns = [row[1] for row in cursor.fetchall()]
                if 'tag_lower' not in columns:
                    conn.execute("ALTER TABLE tags ADD COLUMN tag_lower TEXT")

                # 2. Create aliases table if missing
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='aliases'"
                )
                if cursor.fetchone() is None:
                    conn.execute("""
                        CREATE TABLE aliases (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            page INTEGER NOT NULL REFERENCES pages(id),
                            name TEXT NOT NULL,
                            name_lower TEXT NOT NULL
                        )
                    """)
                    conn.execute(
                        "CREATE UNIQUE INDEX idx_aliases_page_name_lower ON aliases(page, name_lower)"
                    )

                # 3. Add indexes if missing
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_tags_tag_lower'"
                )
                if cursor.fetchone() is None:
                    conn.execute(
                        "CREATE UNIQUE INDEX idx_tags_tag_lower ON tags(tag_lower)"
                    )

                # 4. Backfill tag_lower = LOWER(name) where tag_lower IS NULL
                # This will raise IntegrityError if there are case-insensitive duplicates
                conn.execute("UPDATE tags SET tag_lower = LOWER(name) WHERE tag_lower IS NULL")

                # 5. Create schema_info and mark as version 1
                # Use IF NOT EXISTS because schema_info may have been created empty
                # by _SCHEMA's CREATE TABLE IF NOT EXISTS before migration runs
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS schema_info (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                """)
                conn.execute("INSERT OR IGNORE INTO schema_info VALUES ('version', '1')")

                conn.commit()
                logger.info("Database migrated to schema version 1")
            except sqlite3.IntegrityError as e:
                conn.rollback()
                raise RuntimeError(
                    "Cannot migrate: duplicate tags exist that differ only by case "
                    "(e.g., 'Apple' and 'APPLE'). Please resolve duplicates before migrating."
                ) from e
            except Exception:
                conn.rollback()
                logger.error("Schema migration failed")
                raise

    @property
    def is_uptodate(self):
        return self._is_uptodate

    def check_and_update(self):
        """Full scan of filesystem → rebuild index.

        For profiles with content_dirs (e.g., Logseq with pages/ and journals/),
        scans those subdirectories instead of root, stripping the structural
        prefix from page names.
        """
        with self._lock:
            # Clear stale entries before rebuilding to prevent duplicates
            # Order matters: delete from tables with FK dependencies BEFORE their references
            with self.get_connection() as conn:
                conn.execute("DELETE FROM tagsources")
                conn.execute("DELETE FROM links")
                conn.execute("DELETE FROM aliases")  # Must be before pages (FK dependency)
                conn.execute("DELETE FROM tags")
                if self._has_fts:
                    conn.execute("DELETE FROM pages_fts")
                conn.execute("DELETE FROM pages")
                conn.commit()

            logger.info("Rebuilding index from filesystem...")

            content_dirs = getattr(self.profile, "content_dirs", None)
            if content_dirs:
                # Profile defines content directories (e.g., Logseq)
                # Scan each content dir, using profile for name mapping
                for content_dir in content_dirs:
                    dir_path = os.path.join(self.root_folder, content_dir)
                    if os.path.isdir(dir_path):
                        self._scan_content_dir(dir_path, content_dir, None)
            else:
                # Standard scan from root (Moonstone, Obsidian, Zim)
                self._scan_directory(self.root_folder, None, "")

            self._is_uptodate = True
            # Commit is handled automatically by pool
            logger.info("Index rebuild complete")

    # Regex to detect git merge conflict artifact filenames
    # Matches: 2024-01-27-BACKUP-1792.md, file-BASE-5498.md, etc.
    _GIT_ARTIFACT_RE = re.compile(r"-(BACKUP|BASE|LOCAL|REMOTE)-\d+\.", re.IGNORECASE)

    def _scan_content_dir(self, dir_path, content_dir_prefix, parent_id):
        """Scan a Logseq-style content directory (pages/ or journals/).

        Files in this directory are top-level pages — the content_dir_prefix
        is structural and stripped from page names using the profile.

        @param dir_path: absolute path to the content directory
        @param content_dir_prefix: e.g., 'pages' or 'journals'
        @param parent_id: parent page id in index (None for top-level)
        """
        ext = self.layout.default_extension

        try:
            entries = sorted(os.scandir(dir_path), key=lambda e: e.name)
        except OSError:
            return

        for entry in entries:
            if entry.name.startswith("."):
                continue

            if entry.is_file() and entry.name.endswith(ext):
                # Skip git merge conflict artifacts (e.g., file-BACKUP-1792.md)
                if self._GIT_ARTIFACT_RE.search(entry.name):
                    logger.debug("Skipping git artifact: %s", entry.name)
                    continue
                basename_enc = entry.name[: -len(ext)]
                # Use profile to convert filename to page name
                rel_path = content_dir_prefix + "/" + basename_enc
                page_name = self.profile.filename_to_page_name(rel_path)

                if not page_name:
                    continue

                # Get file metadata
                mtime = ctime = None
                try:
                    st = os.stat(entry.path)
                    mtime = st.st_mtime
                    ctime = st.st_ctime
                except OSError:
                    pass

                page_id = self._upsert_page(
                    parent_id, page_name, page_name, True, False, mtime, ctime
                )

                self._index_page_content(page_id, page_name, entry.path)

    def _scan_directory(self, dir_path, parent_id, namespace):
        """Recursively scan a directory and update the index."""
        from moonstone.notebook.page import Path
        from moonstone.notebook.layout import decode_filename

        ext = self.layout.default_extension

        try:
            entries = sorted(os.scandir(dir_path), key=lambda e: e.name)
        except OSError:
            return

        # Collect page names from both files and subdirectories
        page_names = {}  # basename -> {has_file, has_dir}
        for entry in entries:
            if entry.name.startswith("."):
                continue

            if entry.is_file() and entry.name.endswith(ext):
                basename_enc = entry.name[: -len(ext)]
                pname = decode_filename(basename_enc, self.layout.use_filename_spaces)
                info = page_names.setdefault(
                    pname, {"has_file": False, "has_dir": False}
                )
                info["has_file"] = True
                info["file_path"] = entry.path

            elif entry.is_dir():
                pname = decode_filename(entry.name, self.layout.use_filename_spaces)
                info = page_names.setdefault(
                    pname, {"has_file": False, "has_dir": False}
                )
                info["has_dir"] = True
                info["dir_path"] = entry.path

        for basename, info in sorted(page_names.items(), key=lambda x: x[0]):
            if namespace:
                full_name = namespace + ":" + basename
            else:
                full_name = basename

            page_path = Path(full_name)

            # Get file metadata
            mtime = None
            ctime = None
            hascontent = info["has_file"]
            haschildren = info["has_dir"]

            if hascontent:
                try:
                    st = os.stat(info["file_path"])
                    mtime = st.st_mtime
                    ctime = st.st_ctime
                except OSError:
                    pass

            # Upsert into pages table
            page_id = self._upsert_page(
                parent_id, basename, full_name, hascontent, haschildren, mtime, ctime
            )

            # Extract tags and links from file content
            if hascontent:
                self._index_page_content(page_id, full_name, info["file_path"])

            # Recurse into subdirectory
            if haschildren:
                self._scan_directory(info["dir_path"], page_id, full_name)

    def _upsert_page(
        self, parent_id, basename, name, hascontent, haschildren, mtime, ctime
    ):
        """Insert or update a page record."""
        sortkey = _natural_sort_key(basename)
        row = self._pool.execute(
            "SELECT id FROM pages WHERE name = ?", (name,)
        ).fetchone()

        if row:
            self._pool.execute(
                """
                UPDATE pages SET parent=?, basename=?, sortkey=?,
                    hascontent=?, haschildren=?, mtime=?, ctime=?
                WHERE id=?
            """,
                (
                    parent_id,
                    basename,
                    sortkey,
                    int(hascontent),
                    int(haschildren),
                    mtime,
                    ctime,
                    row[0],
                ),
            )
            return row[0]
        else:
            cursor = self._pool.execute(
                """
                INSERT INTO pages (parent, basename, name, sortkey,
                    hascontent, haschildren, mtime, ctime)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    parent_id,
                    basename,
                    name,
                    sortkey,
                    int(hascontent),
                    int(haschildren),
                    mtime,
                    ctime,
                ),
            )
            return cursor.lastrowid

    def _index_page_content(self, page_id, name, file_path):
        """Extract tags and links using the vault profile.

        The profile determines:
        - Tag syntax (@tag vs #tag, YAML frontmatter tags)
        - Link syntax and target resolution
        - Metadata stripping for FTS
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        except (OSError, IOError, UnicodeDecodeError):
            return

        # Use single connection for transaction
        with self.get_connection() as conn:
            # Remove old tags and links
            conn.execute("DELETE FROM tagsources WHERE source = ?", (page_id,))
            conn.execute("DELETE FROM links WHERE source = ?", (page_id,))

            # Extract tags using profile (handles @tag, #tag, YAML frontmatter)
            for tag_name in self.profile.extract_tags(text):
                tag_id = self._ensure_tag(tag_name)
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO tagsources (tag, source) VALUES (?, ?)",
                        (tag_id, page_id),
                    )
                except sqlite3.IntegrityError:
                    pass

            # Extract links using profile (handles [[Target]], [[Target|Label]], [[Target#Heading]], [[Target^blockid]])
            for target, heading_anchor, block_id, display_text in self.profile.extract_links(text):
                # Convert link target to internal page name
                target_name = self.profile.link_target_to_page_name(target)
                if not target_name:
                    continue

                # Build the names field with anchor/block_id for preservation
                # Store original link info: "target#heading^blockid|display" format
                names_parts = []
                if target:
                    names_parts.append(target)
                if heading_anchor:
                    names_parts.append("#" + heading_anchor)
                if block_id:
                    names_parts.append("^" + block_id)
                if display_text:
                    names_parts.append("|" + display_text)
                names_str = "".join(names_parts) if names_parts else target or ""

                # Find or create target page entry
                target_id = self._ensure_page_ref(target_name)
                if target_id:
                    conn.execute(
                        "INSERT INTO links (source, target, rel, names) VALUES (?, ?, 0, ?)",
                        (page_id, target_id, names_str),
                    )

            # Extract aliases using profile (handles YAML frontmatter aliases)
            conn.execute("DELETE FROM aliases WHERE page = ?", (page_id,))
            if hasattr(self.profile, 'extract_aliases'):
                for alias_name in self.profile.extract_aliases(text):
                    alias_lower = alias_name.lower()
                    conn.execute(
                        "INSERT OR IGNORE INTO aliases (page, name, name_lower) VALUES (?, ?, ?)",
                        (page_id, alias_name, alias_lower),
                    )

            # Update FTS — strip metadata for clean full-text search
            if self._has_fts:
                _meta, body = self.profile.strip_metadata(text)
                conn.execute(
                    "INSERT OR REPLACE INTO pages_fts (rowid, name, content) VALUES (?, ?, ?)",
                    (page_id, name, body),
                )

    def _ensure_tag(self, name):
        """Get or create a tag and return its id."""
        tag_lower = name.lower()
        row = self._pool.execute(
            "SELECT id, name FROM tags WHERE COALESCE(tag_lower, LOWER(name)) = ?", (tag_lower,)
        ).fetchone()
        if row:
            return row[0]
        cursor = self._pool.execute(
            "INSERT INTO tags (name, tag_lower) VALUES (?, ?)", (name, tag_lower)
        )
        return cursor.lastrowid

    def _ensure_page_ref(self, name):
        """Get page id by name. If not found, create a placeholder."""
        row = self._pool.execute(
            "SELECT id FROM pages WHERE name = ?", (name,)
        ).fetchone()
        if row:
            return row[0]

        # Create a placeholder for referenced but non-existent pages
        basename = name.split(":")[-1] if ":" in name else name
        sortkey = _natural_sort_key(basename)
        cursor = self._pool.execute(
            """
            INSERT OR IGNORE INTO pages (parent, basename, name, sortkey, hascontent, haschildren)
            VALUES (NULL, ?, ?, ?, 0, 0)
        """,
            (basename, name, sortkey),
        )
        if cursor.lastrowid:
            return cursor.lastrowid

        # Re-query if INSERT OR IGNORE didn't insert
        row = self._pool.execute(
            "SELECT id FROM pages WHERE name = ?", (name,)
        ).fetchone()
        return row[0] if row else None

    def update_page(self, page, tree=None):
        """Update a single page in the index after save."""
        with self._lock:
            from moonstone.notebook.page import Path

            path = Path(page.name) if isinstance(page, str) else page
            name = path.name
            basename = path.basename

            file_path, folder_path = self.layout.map_page(path)
            hascontent = os.path.isfile(file_path)
            haschildren = os.path.isdir(folder_path) and bool(os.listdir(folder_path))

            mtime = ctime = None
            if hascontent:
                try:
                    st = os.stat(file_path)
                    mtime = st.st_mtime
                    ctime = st.st_ctime
                except OSError:
                    pass

            # Resolve parent_id from namespace
            parent_id = None
            if ":" in name:
                parent_name = name.rsplit(":", 1)[0]
                row = self._pool.execute(
                    "SELECT id FROM pages WHERE name = ?", (parent_name,)
                ).fetchone()
                if row:
                    parent_id = row[0]
                else:
                    # Ensure parent page exists in index
                    parent_basename = (
                        parent_name.split(":")[-1]
                        if ":" in parent_name
                        else parent_name
                    )
                    parent_id = self._upsert_page(
                        None, parent_basename, parent_name, False, True, None, None
                    )

            page_id = self._upsert_page(
                parent_id, basename, name, hascontent, haschildren, mtime, ctime
            )

            if hascontent:
                self._index_page_content(page_id, name, file_path)

    def remove_page(self, path):
        """Remove a page from the index."""
        with self._lock:
            name = path.name if hasattr(path, "name") else str(path)
            row = self._pool.execute(
                "SELECT id FROM pages WHERE name = ?", (name,)
            ).fetchone()
            if row:
                page_id = row[0]
                # Use single connection for transaction
                with self.get_connection() as conn:
                    conn.execute("DELETE FROM tagsources WHERE source = ?", (page_id,))
                    conn.execute("DELETE FROM links WHERE source = ?", (page_id,))
                    conn.execute("DELETE FROM links WHERE target = ?", (page_id,))
                    conn.execute("DELETE FROM aliases WHERE page = ?", (page_id,))
                    conn.execute("DELETE FROM pages WHERE id = ?", (page_id,))
                    if self._has_fts:
                        conn.execute(
                            "DELETE FROM pages_fts WHERE rowid = ?", (page_id,)
                        )

    def move_page(self, oldpath, newpath):
        """Update the index for a moved page."""
        with self._lock:
            old_name = oldpath.name if hasattr(oldpath, "name") else str(oldpath)
            new_name = newpath.name if hasattr(newpath, "name") else str(newpath)
            new_basename = new_name.split(":")[-1] if ":" in new_name else new_name
            new_sortkey = _natural_sort_key(new_basename)

            # Use single connection for transaction
            with self.get_connection() as conn:
                conn.execute(
                    """
                    UPDATE pages SET name=?, basename=?, sortkey=?
                    WHERE name=?
                """,
                    (new_name, new_basename, new_sortkey, old_name),
                )

                # Also update child pages
                prefix = old_name + ":"
                new_prefix = new_name + ":"
                for row in conn.execute(
                    "SELECT id, name FROM pages WHERE name LIKE ?", (prefix + "%",)
                ).fetchall():
                    child_new = new_prefix + row["name"][len(prefix) :]
                    child_basename = child_new.split(":")[-1]
                    conn.execute(
                        "UPDATE pages SET name=?, basename=? WHERE id=?",
                        (child_new, child_basename, row["id"]),
                    )
