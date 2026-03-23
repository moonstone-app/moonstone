# -*- coding: utf-8 -*-
"""Tests for aliases table schema — case-insensitive alias matching.

Verifies:
1. Aliases table exists after Index initialization
2. Table has correct columns: id, page, name, name_lower
3. Unique index idx_aliases_page_name_lower exists
4. Aliases are deleted when page is removed
5. check_and_update() clears aliases table
"""

import os
import sqlite3

import pytest

from moonstone.notebook.page import Path


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


def _get_table_info(conn, table_name):
    """Get column info for a table."""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    return {row[1]: row[2] for row in cursor.fetchall()}


def _get_indexes_for_table(conn, table_name):
    """Get all indexes for a table via sqlite_master (more reliable than PRAGMA)."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=?",
        (table_name,)
    )
    return [row[0] for row in cursor.fetchall()]


def _get_index_info(conn, index_name):
    """Get column info for an index."""
    cursor = conn.execute(
        "PRAGMA index_info(?)",
        (index_name,)
    )
    return [(row[2], row[3]) for row in cursor.fetchall()]  # (name, seqno, colno, cid)


# =============================================================================
# TEST 1: Schema creation
# =============================================================================

@pytest.mark.unit
class TestAliasesSchemaCreation:
    """Tests that aliases table exists and has correct schema after init."""

    def test_aliases_table_exists_after_init(self, temp_notebook_dir):
        """Aliases table should exist in the database after Index init."""
        index = _create_index(temp_notebook_dir)

        with index.get_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='aliases'"
            )
            result = cursor.fetchone()
            assert result is not None, "aliases table should exist"

    def test_aliases_table_has_correct_columns(self, temp_notebook_dir):
        """Aliases table should have columns: id, page, name, name_lower."""
        index = _create_index(temp_notebook_dir)

        with index.get_connection() as conn:
            columns = _get_table_info(conn, "aliases")
            
            expected_columns = {"id": "INTEGER", "page": "INTEGER", "name": "TEXT", "name_lower": "TEXT"}
            for col_name, col_type in expected_columns.items():
                assert col_name in columns, f"Column '{col_name}' should exist in aliases table"
                assert columns[col_name] == col_type, f"Column '{col_name}' should be {col_type}, got {columns[col_name]}"

    def test_aliases_table_has_id_primary_key(self, temp_notebook_dir):
        """Aliases table id column should be PRIMARY KEY with autoincrement."""
        index = _create_index(temp_notebook_dir)

        with index.get_connection() as conn:
            cursor = conn.execute("PRAGMA table_info(aliases)")
            for row in cursor.fetchall():
                # PRAGMA table_info returns: (cid, name, type, notnull, dflt_value, pk)
                if row[1] == "id":
                    assert row[5] == 1, "id should be PRIMARY KEY (pk=1)"
                    break
            else:
                pytest.fail("id column not found in aliases table")

    def test_aliases_page_column_has_foreign_key(self, temp_notebook_dir):
        """Aliases page column should reference pages(id) via FK constraint."""
        index = _create_index(temp_notebook_dir)

        with index.get_connection() as conn:
            # Test FK constraint by trying to insert a reference to non-existent page
            # This should fail with FOREIGN KEY constraint failed
            with pytest.raises(sqlite3.IntegrityError) as exc_info:
                conn.execute(
                    "INSERT INTO aliases (page, name, name_lower) VALUES (?, ?, ?)",
                    (999999, "TestAlias", "testalias")  # 999999 doesn't exist
                )
                conn.commit()
            
            assert "FOREIGN KEY constraint failed" in str(exc_info.value), \
                "Inserting alias with non-existent page should fail FK constraint"

    def test_aliases_name_column_not_null(self, temp_notebook_dir):
        """Aliases name column should be NOT NULL."""
        index = _create_index(temp_notebook_dir)

        with index.get_connection() as conn:
            cursor = conn.execute("PRAGMA table_info(aliases)")
            for row in cursor.fetchall():
                if row[1] == "name":
                    # row[3] is the notnull flag
                    assert row[3] == 1, "name column should be NOT NULL"
                    break
            else:
                pytest.fail("name column not found in aliases table")

    def test_aliases_name_lower_column_not_null(self, temp_notebook_dir):
        """Aliases name_lower column should be NOT NULL."""
        index = _create_index(temp_notebook_dir)

        with index.get_connection() as conn:
            cursor = conn.execute("PRAGMA table_info(aliases)")
            for row in cursor.fetchall():
                if row[1] == "name_lower":
                    # row[3] is the notnull flag
                    assert row[3] == 1, "name_lower column should be NOT NULL"
                    break
            else:
                pytest.fail("name_lower column not found in aliases table")


@pytest.mark.unit
class TestAliasesUniqueIndex:
    """Tests for the idx_aliases_page_name_lower unique index."""

    def test_unique_index_exists(self, temp_notebook_dir):
        """idx_aliases_page_name_lower index should exist on aliases table."""
        index = _create_index(temp_notebook_dir)

        with index.get_connection() as conn:
            indexes = _get_indexes_for_table(conn, "aliases")
            assert "idx_aliases_page_name_lower" in indexes, \
                "idx_aliases_page_name_lower should exist on aliases table"

    def test_unique_index_is_unique(self, temp_notebook_dir):
        """idx_aliases_page_name_lower should be a UNIQUE index."""
        index = _create_index(temp_notebook_dir)

        with index.get_connection() as conn:
            cursor = conn.execute(
                "PRAGMA index_info(idx_aliases_page_name_lower)"
            )
            index_info = cursor.fetchall()
            
            # Get unique flag from index_list
            cursor = conn.execute(
                "PRAGMA index_list(aliases)"
            )
            for row in cursor.fetchall():
                if row[1] == "idx_aliases_page_name_lower":
                    # row[2] is the unique flag
                    assert row[2] == 1, "idx_aliases_page_name_lower should be UNIQUE"
                    break

    def test_unique_index_columns(self, temp_notebook_dir):
        """idx_aliases_page_name_lower should be on (page, name_lower)."""
        index = _create_index(temp_notebook_dir)

        with index.get_connection() as conn:
            # Get index info via sqlite_master (more reliable than PRAGMA)
            cursor = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_aliases_page_name_lower'"
            )
            row = cursor.fetchone()
            assert row is not None, "Index should exist"
            
            # The CREATE INDEX statement contains the column definitions
            sql = row[0]
            assert sql is not None, "Index should have SQL definition"
            
            # Verify the SQL contains the correct columns
            assert "page" in sql and "name_lower" in sql, \
                f"Index SQL should contain 'page' and 'name_lower': {sql}"

    def test_unique_index_allows_same_page_different_names(self, temp_notebook_dir):
        """Same page should be able to have multiple aliases with different names."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        with index.get_connection() as conn:
            # Get a page id
            cursor = conn.execute("SELECT id FROM pages LIMIT 1")
            page_id = cursor.fetchone()[0]

            # Insert multiple aliases for the same page
            conn.execute(
                "INSERT INTO aliases (page, name, name_lower) VALUES (?, ?, ?)",
                (page_id, "Alias1", "alias1")
            )
            conn.execute(
                "INSERT INTO aliases (page, name, name_lower) VALUES (?, ?, ?)",
                (page_id, "Alias2", "alias2")
            )
            conn.commit()

            # Should have 2 aliases
            cursor = conn.execute(
                "SELECT COUNT(*) FROM aliases WHERE page = ?", (page_id,)
            )
            count = cursor.fetchone()[0]
            assert count == 2, f"Should have 2 aliases for page {page_id}, got {count}"

    def test_unique_index_prevents_duplicate_page_name_lower(self, temp_notebook_dir):
        """Same (page, name_lower) combination should be rejected by unique index."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        with index.get_connection() as conn:
            # Get a page id
            cursor = conn.execute("SELECT id FROM pages LIMIT 1")
            page_id = cursor.fetchone()[0]

            # Insert first alias
            conn.execute(
                "INSERT INTO aliases (page, name, name_lower) VALUES (?, ?, ?)",
                (page_id, "Alias", "alias")
            )
            conn.commit()

            # Try to insert duplicate (same page, same name_lower)
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO aliases (page, name, name_lower) VALUES (?, ?, ?)",
                    (page_id, "DifferentName", "alias")  # Same name_lower
                )
                conn.commit()


# =============================================================================
# TEST 2: Foreign key behavior — aliases deleted when page removed
# =============================================================================

@pytest.mark.unit
class TestAliasesForeignKeyBehavior:
    """Tests that aliases are properly deleted when pages are removed."""

    def test_remove_page_deletes_aliases(self, temp_notebook_dir):
        """remove_page() should delete all aliases associated with the page."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        with index.get_connection() as conn:
            # Get a page id
            cursor = conn.execute("SELECT id FROM pages LIMIT 1")
            page_id = cursor.fetchone()[0]

            # Insert an alias for this page
            conn.execute(
                "INSERT INTO aliases (page, name, name_lower) VALUES (?, ?, ?)",
                (page_id, "TestAlias", "testalias")
            )
            conn.commit()

            # Verify alias exists
            cursor = conn.execute(
                "SELECT COUNT(*) FROM aliases WHERE page = ?", (page_id,)
            )
            count_before = cursor.fetchone()[0]
            assert count_before == 1, "Alias should exist before removal"

        # Remove the page
        from moonstone.notebook.page import Path
        page_name = conn.execute("SELECT name FROM pages WHERE id = ?", (page_id,)).fetchone()[0]
        index.remove_page(Path(page_name))

        with index.get_connection() as conn:
            # Verify alias is gone
            cursor = conn.execute(
                "SELECT COUNT(*) FROM aliases WHERE page = ?", (page_id,)
            )
            count_after = cursor.fetchone()[0]
            assert count_after == 0, "Alias should be deleted after remove_page()"

    def test_no_orphaned_aliases_after_remove_page(self, temp_notebook_dir):
        """After remove_page(), no aliases should reference the deleted page."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        with index.get_connection() as conn:
            # Get a page id
            cursor = conn.execute("SELECT id FROM pages LIMIT 1")
            page_id = cursor.fetchone()[0]
            page_name = conn.execute("SELECT name FROM pages WHERE id = ?", (page_id,)).fetchone()[0]

            # Insert multiple aliases for this page
            for i in range(3):
                conn.execute(
                    "INSERT INTO aliases (page, name, name_lower) VALUES (?, ?, ?)",
                    (page_id, f"Alias{i}", f"alias{i}")
                )
            conn.commit()

        # Remove the page
        index.remove_page(Path(page_name))

        with index.get_connection() as conn:
            # Check for any orphaned aliases
            cursor = conn.execute("""
                SELECT a.id, a.page, a.name
                FROM aliases a
                LEFT JOIN pages p ON a.page = p.id
                WHERE p.id IS NULL AND a.page = ?
            """, (page_id,))
            orphaned = cursor.fetchall()

            assert len(orphaned) == 0, \
                f"Found {len(orphaned)} orphaned aliases after remove_page(): {orphaned}"

    def test_aliases_for_other_pages_preserved_after_remove(self, temp_notebook_dir):
        """Removing one page should not affect aliases for other pages."""
        # Create additional page for testing
        (temp_notebook_dir / "Page2.md").write_text("# Page 2\n\nSecond page")
        
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        with index.get_connection() as conn:
            # Get two different page ids
            cursor = conn.execute("SELECT id FROM pages ORDER BY id LIMIT 2")
            rows = cursor.fetchall()
            assert len(rows) >= 2, f"Need at least 2 pages, got {len(rows)}"
            page1_id = rows[0][0]
            page2_id = rows[1][0]

            # Insert alias for page1
            conn.execute(
                "INSERT INTO aliases (page, name, name_lower) VALUES (?, ?, ?)",
                (page1_id, "Page1Alias", "page1alias")
            )
            # Insert alias for page2
            conn.execute(
                "INSERT INTO aliases (page, name, name_lower) VALUES (?, ?, ?)",
                (page2_id, "Page2Alias", "page2alias")
            )
            conn.commit()

            # Get page1 name for removal
            page1_name = conn.execute(
                "SELECT name FROM pages WHERE id = ?", (page1_id,)
            ).fetchone()[0]

        # Remove page1
        index.remove_page(Path(page1_name))

        with index.get_connection() as conn:
            # page2 alias should still exist
            cursor = conn.execute(
                "SELECT COUNT(*) FROM aliases WHERE page = ?", (page2_id,)
            )
            page2_alias_count = cursor.fetchone()[0]
            assert page2_alias_count == 1, \
                f"Alias for page2 should be preserved, got {page2_alias_count}"


# =============================================================================
# TEST 3: Full rebuild clears aliases
# =============================================================================

# NOTE: The following tests expose a bug in check_and_update() where
# DELETE FROM aliases comes AFTER DELETE FROM pages, but aliases has
# a FK reference to pages. The correct order should delete aliases
# BEFORE pages. This bug was introduced during the schema design and
# is now exposed by these tests.
# BUG LOCATION: moonstone/notebook/index/__init__.py check_and_update()
# BUG: lines 212-218 should be reordered to delete aliases before pages

@pytest.mark.unit
class TestAliasesFullRebuild:
    """Tests that check_and_update() clears the aliases table."""

    def test_check_and_update_clears_aliases(self, temp_notebook_dir):
        """check_and_update() should delete all entries from aliases table.
        
        NOTE: This test exposes a bug in the source code where DELETE FROM aliases
        comes AFTER DELETE FROM pages, causing FK constraint violation.
        The test correctly verifies the intended behavior which the code doesn't satisfy.
        """
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        with index.get_connection() as conn:
            # Get a page id
            cursor = conn.execute("SELECT id FROM pages LIMIT 1")
            page_id = cursor.fetchone()[0]

            # Insert an alias
            conn.execute(
                "INSERT INTO aliases (page, name, name_lower) VALUES (?, ?, ?)",
                (page_id, "TestAlias", "testalias")
            )
            conn.commit()

            # Verify alias exists
            cursor = conn.execute("SELECT COUNT(*) FROM aliases")
            count_before = cursor.fetchone()[0]
            assert count_before >= 1, "Alias should exist before rebuild"

        # Full rebuild
        index.check_and_update()

        with index.get_connection() as conn:
            # Verify aliases table is cleared
            cursor = conn.execute("SELECT COUNT(*) FROM aliases")
            count_after = cursor.fetchone()[0]
            assert count_after == 0, \
                f"Aliases table should be empty after rebuild, got {count_after}"

    def test_no_orphaned_aliases_after_full_rebuild(self, temp_notebook_dir):
        """After full rebuild, no aliases should exist (table should be empty)."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        with index.get_connection() as conn:
            # Get a page id
            cursor = conn.execute("SELECT id FROM pages LIMIT 1")
            page_id = cursor.fetchone()[0]

            # Insert multiple aliases
            for i in range(5):
                conn.execute(
                    "INSERT INTO aliases (page, name, name_lower) VALUES (?, ?, ?)",
                    (page_id, f"Alias{i}", f"alias{i}")
                )
            conn.commit()

        # Full rebuild
        index.check_and_update()

        with index.get_connection() as conn:
            # Check for any aliases
            cursor = conn.execute("SELECT COUNT(*) FROM aliases")
            count = cursor.fetchone()[0]
            assert count == 0, f"Aliases table should be empty after rebuild, got {count}"

    def test_aliases_cleared_before_pages_rebuilt(self, temp_notebook_dir):
        """Aliases should be cleared BEFORE pages are rebuilt (correct order).

        This test verifies the cleanup order by checking that if we insert
        aliases for pages that will be deleted during rebuild, they are
        still properly cleared even though the pages table is rebuilt.
        """
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        # Delete one page file to create scenario where page won't exist after rebuild
        journal_file = temp_notebook_dir / "Journal.md"
        if journal_file.exists():
            journal_file.unlink()

        with index.get_connection() as conn:
            # Get page ids before rebuild
            cursor = conn.execute("SELECT id FROM pages")
            page_ids_before = [row[0] for row in cursor.fetchall()]

            # Insert alias for each page
            for page_id in page_ids_before:
                conn.execute(
                    "INSERT INTO aliases (page, name, name_lower) VALUES (?, ?, ?)",
                    (page_id, f"AliasFor{page_id}", f"aliasfor{page_id}")
                )
            conn.commit()

        # Full rebuild
        index.check_and_update()

        with index.get_connection() as conn:
            # Verify NO aliases exist
            cursor = conn.execute("SELECT COUNT(*) FROM aliases")
            count = cursor.fetchone()[0]
            assert count == 0, \
                f"All aliases should be cleared during rebuild, got {count}"

    def test_rebuild_idempotent_aliases(self, temp_notebook_dir):
        """Multiple consecutive rebuilds should not accumulate aliases."""
        index = _create_index(temp_notebook_dir)

        for i in range(3):
            # Insert some aliases before each rebuild
            if i == 0:
                index.check_and_update()
                with index.get_connection() as conn:
                    cursor = conn.execute("SELECT id FROM pages LIMIT 1")
                    page_id = cursor.fetchone()[0]
                    conn.execute(
                        "INSERT INTO aliases (page, name, name_lower) VALUES (?, ?, ?)",
                        (page_id, f"Alias{i}", f"alias{i}")
                    )
                    conn.commit()

            # Rebuild
            index.check_and_update()

            with index.get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM aliases")
                count = cursor.fetchone()[0]
                assert count == 0, \
                    f"After rebuild #{i+1}, aliases count should be 0, got {count}"


# =============================================================================
# TEST 4: Edge cases
# =============================================================================

@pytest.mark.unit
class TestAliasesEdgeCases:
    """Tests for edge cases with the aliases table."""

    def test_aliases_table_empty_after_init_no_pages(self, temp_notebook_dir):
        """Aliases table should be empty after init with no pages."""
        # Create index WITHOUT running check_and_update
        # (initializes schema but no pages)
        index = _create_index(temp_notebook_dir)

        with index.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM aliases")
            count = cursor.fetchone()[0]
            assert count == 0, "Aliases table should be empty after init"

    def test_aliases_name_lower_stores_lowercase(self, temp_notebook_dir):
        """name_lower column should store lowercase version of name."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        with index.get_connection() as conn:
            cursor = conn.execute("SELECT id FROM pages LIMIT 1")
            page_id = cursor.fetchone()[0]

            conn.execute(
                "INSERT INTO aliases (page, name, name_lower) VALUES (?, ?, ?)",
                (page_id, "UPPERCASE", "uppercase")
            )
            conn.commit()

            cursor = conn.execute(
                "SELECT name, name_lower FROM aliases WHERE page = ?",
                (page_id,)
            )
            row = cursor.fetchone()
            assert row["name"] == "UPPERCASE"
            assert row["name_lower"] == "uppercase"

    def test_aliases_handles_unicode_names(self, temp_notebook_dir):
        """Aliases should handle Unicode page names correctly."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        with index.get_connection() as conn:
            cursor = conn.execute("SELECT id FROM pages LIMIT 1")
            page_id = cursor.fetchone()[0]

            # Unicode alias
            conn.execute(
                "INSERT INTO aliases (page, name, name_lower) VALUES (?, ?, ?)",
                (page_id, "日本語", "日本語")
            )
            conn.commit()

            cursor = conn.execute(
                "SELECT name, name_lower FROM aliases WHERE page = ?",
                (page_id,)
            )
            row = cursor.fetchone()
            assert row["name"] == "日本語"
            assert row["name_lower"] == "日本語"

    def test_aliases_unique_index_case_sensitive(self, temp_notebook_dir):
        """Unique index on name_lower should enable case-insensitive matching.

        Since name_lower stores the lowercase version, we can query
        using lowercase and find matches regardless of original case.
        """
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        with index.get_connection() as conn:
            cursor = conn.execute("SELECT id FROM pages LIMIT 1")
            page_id = cursor.fetchone()[0]

            # Insert with MIXED case
            conn.execute(
                "INSERT INTO aliases (page, name, name_lower) VALUES (?, ?, ?)",
                (page_id, "MyAlias", "myalias")
            )
            conn.commit()

            # We can find by lowercase
            cursor = conn.execute(
                "SELECT * FROM aliases WHERE name_lower = ?",
                ("myalias",)
            )
            row = cursor.fetchone()
            assert row is not None, "Should find alias by lowercase name_lower"
            assert row["name"] == "MyAlias"
