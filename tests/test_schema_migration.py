# -*- coding: utf-8 -*-
"""Tests for schema migration logic in Index.

Verifies:
1. Old database without schema_info table and without tag_lower column → migration runs
2. Old database without schema_info but WITH tag_lower column → skip migration (partial migration state)
3. New database with schema_info already set → skip migration

Migration adds:
- tag_lower column to tags table
- aliases table
- idx_tags_tag_lower index
- schema_info table with version '1'
"""

import os
import sqlite3
import tempfile

import pytest


@pytest.fixture
def temp_notebook_dir(tmp_path):
    """Create a temporary notebook directory."""
    notebook_dir = tmp_path / "test_notebook"
    notebook_dir.mkdir()

    # Create notebook.moon config
    (notebook_dir / "notebook.moon").write_text(
        "[notebook]\n"
        "name = Test Notebook\n"
        "home = Home\n"
    )

    # Create a minimal page
    (notebook_dir / "Home.md").write_text("# Home\n\nWelcome!")

    return notebook_dir


def _create_index(notebook_dir, profile=None):
    """Create an Index instance for testing."""
    from moonstone.notebook.index import Index
    from moonstone.notebook.layout import FilesLayout
    from moonstone.profiles.moonstone_profile import MoonstoneProfile

    if profile is None:
        profile = MoonstoneProfile()

    db_path = os.path.join(notebook_dir, "index.db")
    layout = FilesLayout(
        notebook_dir,
        default_extension=profile.file_extension,
        default_format=profile.default_format,
        use_filename_spaces=profile.use_filename_spaces,
        profile=profile,
    )

    return Index(
        db_path=db_path,
        layout=layout,
        root_folder=notebook_dir,
        profile=profile,
    )


def _get_table_columns(conn, table_name):
    """Get list of column names for a table."""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]


def _table_exists(conn, table_name):
    """Check if a table exists."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None


def _index_exists(conn, index_name):
    """Check if an index exists."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,)
    )
    return cursor.fetchone() is not None


def _get_schema_version(conn):
    """Get schema version from schema_info table."""
    cursor = conn.execute(
        "SELECT value FROM schema_info WHERE key='version'"
    )
    row = cursor.fetchone()
    return row[0] if row else None


# =============================================================================
# TEST 1: Old database without schema_info and without tag_lower
# =============================================================================

@pytest.mark.unit
class TestMigrationFromOldDatabase:
    """Tests for migration from old database format."""

    def test_migration_adds_tag_lower_column(self, temp_notebook_dir):
        """Migration adds tag_lower column to tags table."""
        db_path = temp_notebook_dir / "index.db"

        # Create old-style database WITHOUT schema_info and WITHOUT tag_lower
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent INTEGER REFERENCES pages(id),
                basename TEXT NOT NULL,
                name TEXT NOT NULL UNIQUE,
                sortkey TEXT,
                hascontent INTEGER DEFAULT 0,
                haschildren INTEGER DEFAULT 0,
                mtime REAL,
                ctime REAL
            )
        """)
        conn.execute("""
            CREATE TABLE tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
                -- NO tag_lower column - this is old format
            )
        """)
        conn.execute("""
            CREATE TABLE tagsources (
                tag INTEGER REFERENCES tags(id),
                source INTEGER REFERENCES pages(id),
                PRIMARY KEY (tag, source)
            )
        """)
        conn.execute("""
            CREATE TABLE links (
                source INTEGER REFERENCES pages(id),
                target INTEGER REFERENCES pages(id),
                rel INTEGER DEFAULT 0,
                names TEXT
            )
        """)
        # Insert some test data
        conn.execute("INSERT INTO tags (name) VALUES ('TestTag')")
        conn.commit()
        conn.close()

        # Create Index - this should trigger migration
        index = _create_index(temp_notebook_dir)

        # Verify tag_lower column was added
        with index.get_connection() as conn:
            columns = _get_table_columns(conn, "tags")
            assert "tag_lower" in columns, "tag_lower column should be added"

            # Verify tag_lower was backfilled
            cursor = conn.execute("SELECT name, tag_lower FROM tags WHERE name='TestTag'")
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "TestTag"
            assert row[1] == "testtag", "tag_lower should be lowercase of name"

    def test_migration_creates_aliases_table(self, temp_notebook_dir):
        """Migration creates aliases table if missing."""
        db_path = temp_notebook_dir / "index.db"

        # Create old-style database WITHOUT aliases table
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent INTEGER,
                basename TEXT NOT NULL,
                name TEXT NOT NULL UNIQUE,
                sortkey TEXT,
                hascontent INTEGER DEFAULT 0,
                haschildren INTEGER DEFAULT 0,
                mtime REAL,
                ctime REAL
            )
        """)
        conn.execute("""
            CREATE TABLE tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                tag_lower TEXT
            )
        """)
        conn.execute("CREATE TABLE tagsources (tag INTEGER, source INTEGER, PRIMARY KEY (tag, source))")
        conn.execute("CREATE TABLE links (source INTEGER, target INTEGER, rel INTEGER DEFAULT 0, names TEXT)")
        conn.commit()
        conn.close()

        # Create Index - this should trigger migration
        index = _create_index(temp_notebook_dir)

        # Verify aliases table was created
        with index.get_connection() as conn:
            assert _table_exists(conn, "aliases"), "aliases table should be created"

            # Verify correct schema for aliases
            columns = _get_table_columns(conn, "aliases")
            assert "page" in columns
            assert "name" in columns
            assert "name_lower" in columns

    def test_migration_creates_idx_tags_tag_lower_index(self, temp_notebook_dir):
        """Migration creates idx_tags_tag_lower index if missing."""
        db_path = temp_notebook_dir / "index.db"

        # Create old-style database WITHOUT the index
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent INTEGER,
                basename TEXT NOT NULL,
                name TEXT NOT NULL UNIQUE,
                sortkey TEXT,
                hascontent INTEGER DEFAULT 0,
                haschildren INTEGER DEFAULT 0,
                mtime REAL,
                ctime REAL
            )
        """)
        conn.execute("""
            CREATE TABLE tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                tag_lower TEXT
            )
        """)
        conn.execute("CREATE TABLE tagsources (tag INTEGER, source INTEGER, PRIMARY KEY (tag, source))")
        conn.execute("CREATE TABLE links (source INTEGER, target INTEGER, rel INTEGER DEFAULT 0, names TEXT)")
        conn.commit()
        conn.close()

        # Create Index - this should trigger migration
        index = _create_index(temp_notebook_dir)

        # Verify index was created
        with index.get_connection() as conn:
            assert _index_exists(conn, "idx_tags_tag_lower"), "idx_tags_tag_lower index should be created"

    def test_migration_creates_schema_info_table(self, temp_notebook_dir):
        """Migration creates schema_info table with version 1."""
        db_path = temp_notebook_dir / "index.db"

        # Create old-style database WITHOUT schema_info
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent INTEGER,
                basename TEXT NOT NULL,
                name TEXT NOT NULL UNIQUE,
                sortkey TEXT,
                hascontent INTEGER DEFAULT 0,
                haschildren INTEGER DEFAULT 0,
                mtime REAL,
                ctime REAL
            )
        """)
        conn.execute("""
            CREATE TABLE tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                tag_lower TEXT
            )
        """)
        conn.execute("CREATE TABLE tagsources (tag INTEGER, source INTEGER, PRIMARY KEY (tag, source))")
        conn.execute("CREATE TABLE links (source INTEGER, target INTEGER, rel INTEGER DEFAULT 0, names TEXT)")
        conn.commit()
        conn.close()

        # Create Index - this should trigger migration
        index = _create_index(temp_notebook_dir)

        # Verify schema_info table was created
        with index.get_connection() as conn:
            assert _table_exists(conn, "schema_info"), "schema_info table should be created"
            version = _get_schema_version(conn)
            assert version == "1", f"schema version should be '1', got '{version}'"

    def test_migration_runs_once_on_subsequent_opens(self, temp_notebook_dir):
        """Migration only runs once - subsequent opens should skip migration."""
        db_path = temp_notebook_dir / "index.db"

        # Create old-style database
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent INTEGER,
                basename TEXT NOT NULL,
                name TEXT NOT NULL UNIQUE,
                sortkey TEXT,
                hascontent INTEGER DEFAULT 0,
                haschildren INTEGER DEFAULT 0,
                mtime REAL,
                ctime REAL
            )
        """)
        conn.execute("""
            CREATE TABLE tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                tag_lower TEXT
            )
        """)
        conn.execute("CREATE TABLE tagsources (tag INTEGER, source INTEGER, PRIMARY KEY (tag, source))")
        conn.execute("CREATE TABLE links (source INTEGER, target INTEGER, rel INTEGER DEFAULT 0, names TEXT)")
        conn.commit()
        conn.close()

        # First open - triggers migration
        index1 = _create_index(temp_notebook_dir)
        with index1.get_connection() as conn:
            version_after_first = _get_schema_version(conn)
            assert version_after_first == "1"

        # Second open - should skip migration
        index2 = _create_index(temp_notebook_dir)
        with index2.get_connection() as conn:
            version_after_second = _get_schema_version(conn)
            assert version_after_second == "1"

        # Third open - should still skip migration
        index3 = _create_index(temp_notebook_dir)
        with index3.get_connection() as conn:
            version_after_third = _get_schema_version(conn)
            assert version_after_third == "1"


# =============================================================================
# TEST 2: Partial migration - without schema_info but WITH tag_lower
# =============================================================================

@pytest.mark.unit
class TestMigrationPartialMigration:
    """Tests for partial migration state (no schema_info but has tag_lower)."""

    def test_partial_migration_skips_when_tag_lower_exists(self, temp_notebook_dir):
        """Migration should skip when tag_lower column already exists (even without schema_info)."""
        db_path = temp_notebook_dir / "index.db"

        # Create database with tag_lower but WITHOUT schema_info
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent INTEGER,
                basename TEXT NOT NULL,
                name TEXT NOT NULL UNIQUE,
                sortkey TEXT,
                hascontent INTEGER DEFAULT 0,
                haschildren INTEGER DEFAULT 0,
                mtime REAL,
                ctime REAL
            )
        """)
        conn.execute("""
            CREATE TABLE tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                tag_lower TEXT NOT NULL
            )
        """)
        conn.execute("CREATE TABLE tagsources (tag INTEGER, source INTEGER, PRIMARY KEY (tag, source))")
        conn.execute("CREATE TABLE links (source INTEGER, target INTEGER, rel INTEGER DEFAULT 0, names TEXT)")
        # Insert test data with pre-existing tag_lower
        conn.execute("INSERT INTO tags (name, tag_lower) VALUES ('TestTag', 'testtag')")
        conn.commit()
        conn.close()

        # Create Index - this should NOT trigger full migration since tag_lower exists
        index = _create_index(temp_notebook_dir)

        # Verify schema_info was created (migration completed)
        with index.get_connection() as conn:
            assert _table_exists(conn, "schema_info"), "schema_info should be created"
            version = _get_schema_version(conn)
            assert version == "1"

            # Verify tag_lower was NOT modified (preserves existing value)
            cursor = conn.execute("SELECT name, tag_lower FROM tags WHERE name='TestTag'")
            row = cursor.fetchone()
            assert row[1] == "testtag", "tag_lower should be preserved"


# =============================================================================
# TEST 3: New database with schema_info already set
# =============================================================================

@pytest.mark.unit
class TestMigrationAlreadyMigrated:
    """Tests for database already migrated (has schema_info)."""

    def test_already_migrated_skips_migration(self, temp_notebook_dir):
        """Migration should skip when schema_info table already exists."""
        db_path = temp_notebook_dir / "index.db"

        # Create new-style database WITH schema_info
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent INTEGER,
                basename TEXT NOT NULL,
                name TEXT NOT NULL UNIQUE,
                sortkey TEXT,
                hascontent INTEGER DEFAULT 0,
                haschildren INTEGER DEFAULT 0,
                mtime REAL,
                ctime REAL
            )
        """)
        conn.execute("""
            CREATE TABLE tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                tag_lower TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page INTEGER NOT NULL REFERENCES pages(id),
                name TEXT NOT NULL,
                name_lower TEXT NOT NULL
            )
        """)
        conn.execute("CREATE TABLE tagsources (tag INTEGER, source INTEGER, PRIMARY KEY (tag, source))")
        conn.execute("CREATE TABLE links (source INTEGER, target INTEGER, rel INTEGER DEFAULT 0, names TEXT)")
        conn.execute("""
            CREATE TABLE schema_info (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.execute("INSERT INTO schema_info VALUES ('version', '1')")
        conn.execute("CREATE UNIQUE INDEX idx_tags_tag_lower ON tags(tag_lower)")
        conn.execute("CREATE UNIQUE INDEX idx_aliases_page_name_lower ON aliases(page, name_lower)")
        conn.commit()
        conn.close()

        # Create Index - this should NOT trigger migration
        index = _create_index(temp_notebook_dir)

        # Verify schema is intact
        with index.get_connection() as conn:
            assert _table_exists(conn, "schema_info")
            version = _get_schema_version(conn)
            assert version == "1"
            assert _table_exists(conn, "aliases")
            assert _index_exists(conn, "idx_tags_tag_lower")
            assert _index_exists(conn, "idx_aliases_page_name_lower")

            # Verify tags table still has tag_lower
            columns = _get_table_columns(conn, "tags")
            assert "tag_lower" in columns


# =============================================================================
# TEST 4: Migration error handling
# =============================================================================

@pytest.mark.unit
class TestMigrationErrorHandling:
    """Tests for migration error handling."""

    def test_migration_fails_on_duplicate_tag_lower(self, temp_notebook_dir):
        """Migration should fail with clear error when duplicate tags exist."""
        db_path = temp_notebook_dir / "index.db"

        # Create old-style database with duplicate tags (different case)
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent INTEGER,
                basename TEXT NOT NULL,
                name TEXT NOT NULL UNIQUE,
                sortkey TEXT,
                hascontent INTEGER DEFAULT 0,
                haschildren INTEGER DEFAULT 0,
                mtime REAL,
                ctime REAL
            )
        """)
        conn.execute("""
            CREATE TABLE tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
                -- NO tag_lower - old format
            )
        """)
        conn.execute("CREATE TABLE tagsources (tag INTEGER, source INTEGER, PRIMARY KEY (tag, source))")
        conn.execute("CREATE TABLE links (source INTEGER, target INTEGER, rel INTEGER DEFAULT 0, names TEXT)")
        # Insert duplicate tags with different cases
        conn.execute("INSERT INTO tags (name) VALUES ('Apple')")
        conn.execute("INSERT INTO tags (name) VALUES ('APPLE')")
        conn.commit()
        conn.close()

        # Create Index - should raise RuntimeError about duplicates
        with pytest.raises(RuntimeError) as exc_info:
            _create_index(temp_notebook_dir)

        assert "duplicate tags" in str(exc_info.value).lower() or "case" in str(exc_info.value).lower()


# =============================================================================
# TEST 5: Integration - ensure existing tests still pass
# =============================================================================

@pytest.mark.unit
class TestMigrationIntegration:
    """Integration tests to ensure migration doesn't break existing functionality."""

    def test_migration_then_ensure_tag_works(self, temp_notebook_dir):
        """After migration, _ensure_tag should work correctly."""
        db_path = temp_notebook_dir / "index.db"

        # Create old-style database
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent INTEGER,
                basename TEXT NOT NULL,
                name TEXT NOT NULL UNIQUE,
                sortkey TEXT,
                hascontent INTEGER DEFAULT 0,
                haschildren INTEGER DEFAULT 0,
                mtime REAL,
                ctime REAL
            )
        """)
        conn.execute("""
            CREATE TABLE tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            )
        """)
        conn.execute("CREATE TABLE tagsources (tag INTEGER, source INTEGER, PRIMARY KEY (tag, source))")
        conn.execute("CREATE TABLE links (source INTEGER, target INTEGER, rel INTEGER DEFAULT 0, names TEXT)")
        conn.commit()
        conn.close()

        # Create Index with migration
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        # Use _ensure_tag - should work after migration
        tag_id = index._ensure_tag("NewProject")

        with index.get_connection() as conn:
            cursor = conn.execute("SELECT name, tag_lower FROM tags WHERE id=?", (tag_id,))
            row = cursor.fetchone()
            assert row["name"] == "NewProject"
            assert row["tag_lower"] == "newproject"

    def test_migration_then_ensure_tag_case_insensitive(self, temp_notebook_dir):
        """After migration, _ensure_tag should be case-insensitive."""
        db_path = temp_notebook_dir / "index.db"

        # Create old-style database
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent INTEGER,
                basename TEXT NOT NULL,
                name TEXT NOT NULL UNIQUE,
                sortkey TEXT,
                hascontent INTEGER DEFAULT 0,
                haschildren INTEGER DEFAULT 0,
                mtime REAL,
                ctime REAL
            )
        """)
        conn.execute("""
            CREATE TABLE tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            )
        """)
        conn.execute("CREATE TABLE tagsources (tag INTEGER, source INTEGER, PRIMARY KEY (tag, source))")
        conn.execute("CREATE TABLE links (source INTEGER, target INTEGER, rel INTEGER DEFAULT 0, names TEXT)")
        conn.commit()
        conn.close()

        # Create Index with migration
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        # Create first tag
        tag_id_1 = index._ensure_tag("Project")

        # Create same tag with different case - should return same ID
        tag_id_2 = index._ensure_tag("PROJECT")

        assert tag_id_1 == tag_id_2, "Case variations should return same tag ID"

        with index.get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
            assert count == 1, "Should only have one tag"
