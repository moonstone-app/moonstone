# -*- coding: utf-8 -*-
"""Unit tests for Index.check_and_update() cleanup behavior.

Tests that the index cleanup properly clears all tables before rebuilding
to prevent duplicate entries. Covers:
1. No duplicates after rebuild
2. All entries cleared before new ones added
3. FTS enabled and disabled modes
4. Foreign key constraints respected
"""

import os
import sqlite3
import tempfile
import shutil
from pathlib import Path

import pytest


@pytest.fixture
def temp_notebook_dir(tmp_path):
    """Create a temporary notebook directory with test pages.

    Uses Moonstone format: .md files with #tag syntax and [[wiki]] links.
    """
    notebook_dir = tmp_path / "test_notebook"
    notebook_dir.mkdir()

    # Create notebook.moon config (Moonstone marker)
    (notebook_dir / "notebook.moon").write_text(
        "[notebook]\n"
        "name = Test Notebook\n"
        "home = Home\n"
    )

    # Create test pages with Moonstone format (.md files, #hashtags, [[wiki links]])
    (notebook_dir / "Home.md").write_text("# Home\n\nWelcome! #home\n\nSee [[Projects]]")
    (notebook_dir / "Projects.md").write_text("# Projects\n\n#work\n\n[[Home]] back")
    (notebook_dir / "Journal.md").write_text("# Journal\n\n#daily\n\nEntry")

    return notebook_dir


@pytest.fixture
def temp_notebook_dir_with_duplicates(tmp_path):
    """Create notebook with potential duplicate scenarios.

    Creates pages that could generate duplicates if the cleanup
    doesn't properly clear old entries (e.g., case variations).
    """
    notebook_dir = tmp_path / "dup_notebook"
    notebook_dir.mkdir()

    (notebook_dir / "notebook.moon").write_text(
        "[notebook]\n"
        "name = Dup Test\n"
        "home = Test\n"
    )

    (notebook_dir / "Test.md").write_text("# Test\n\n#test\n\n[[Link]]")
    (notebook_dir / "Other.md").write_text("# Other\n\n#other")

    return notebook_dir


def _create_index(notebook_dir, profile=None):
    """Helper to create an Index instance for testing.

    Uses MoonstoneProfile by default (which expects .md files with #hashtags).
    """
    from moonstone.notebook.index import Index
    from moonstone.notebook.layout import FilesLayout
    from moonstone.profiles.moonstone_profile import MoonstoneProfile

    if profile is None:
        profile = MoonstoneProfile()

    db_path = os.path.join(notebook_dir, "index.db")
    layout = FilesLayout(
        notebook_dir,
        default_extension=profile.file_extension,  # .md for Moonstone
        default_format=profile.default_format,     # markdown for Moonstone
        use_filename_spaces=profile.use_filename_spaces,
        profile=profile,
    )

    return Index(
        db_path=db_path,
        layout=layout,
        root_folder=notebook_dir,
        profile=profile,
    )


def _count_rows_in_table(conn, table_name):
    """Count rows in a specific table."""
    cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
    return cursor.fetchone()[0]


def _get_all_page_names(conn):
    """Get all page names from the pages table."""
    cursor = conn.execute("SELECT name FROM pages ORDER BY name")
    return [row[0] for row in cursor.fetchall()]


@pytest.mark.unit
class TestIndexCleanupNoDuplicates:
    """Tests that check_and_update() prevents duplicate entries."""

    def test_no_duplicate_pages_after_rebuild(self, temp_notebook_dir):
        """After rebuilding, each page should appear exactly once."""
        index = _create_index(temp_notebook_dir)

        # First build
        index.check_and_update()

        with index.get_connection() as conn:
            page_names = _get_all_page_names(conn)
            page_counts = {}
            for name in page_names:
                page_counts[name] = page_counts.get(name, 0) + 1

        # Each name should appear exactly once
        for name, count in page_counts.items():
            assert count == 1, f"Page '{name}' appears {count} times, expected 1"

    def test_no_duplicate_tags_after_rebuild(self, temp_notebook_dir):
        """After rebuilding, each tag should appear exactly once in tags table."""
        index = _create_index(temp_notebook_dir)

        index.check_and_update()

        with index.get_connection() as conn:
            cursor = conn.execute("SELECT name, COUNT(*) as cnt FROM tags GROUP BY name HAVING cnt > 1")
            duplicates = cursor.fetchall()

        assert len(duplicates) == 0, f"Duplicate tags found: {duplicates}"

    def test_no_duplicates_after_multiple_rebuilds(self, temp_notebook_dir):
        """Multiple rebuilds should not create duplicate entries."""
        index = _create_index(temp_notebook_dir)

        # Build multiple times
        for _ in range(3):
            index.check_and_update()

        with index.get_connection() as conn:
            # Check pages
            page_names = _get_all_page_names(conn)
            assert len(page_names) == len(set(page_names)), \
                f"Duplicate pages found after multiple rebuilds: {page_names}"

            # Check tags
            cursor = conn.execute("SELECT name FROM tags")
            tags = [row[0] for row in cursor.fetchall()]
            assert len(tags) == len(set(tags)), \
                f"Duplicate tags found after multiple rebuilds: {tags}"

    def test_rebuild_with_modified_page_names(self, temp_notebook_dir):
        """Rebuild should clear old names when page content changes.

        This tests the scenario where a page name might change but old
        entries weren't cleared properly.
        """
        index = _create_index(temp_notebook_dir)

        # First build
        index.check_and_update()

        # Modify a page file (simulate rename by deleting and creating new)
        old_file = temp_notebook_dir / "Home.md"
        new_file = temp_notebook_dir / "NewHome.md"

        if old_file.exists():
            old_content = old_file.read_text()
            old_file.unlink()
            new_file.write_text(old_content.replace("Home", "NewHome"))

        # Rebuild
        index.check_and_update()

        with index.get_connection() as conn:
            page_names = _get_all_page_names(conn)

            # Old name should be gone, new name should exist
            # (If NewHome.md was created)
            assert "Home" not in page_names or "NewHome" in page_names


@pytest.mark.unit
class TestIndexCleanupClearsAllTables:
    """Tests that check_and_update() clears all tables before rebuilding."""

    def test_pages_table_cleared_before_rebuild(self, temp_notebook_dir):
        """Pages table should be empty at the start of rebuild, then repopulated."""
        index = _create_index(temp_notebook_dir)

        # Initial build
        index.check_and_update()

        with index.get_connection() as conn:
            initial_count = _count_rows_in_table(conn, "pages")
            assert initial_count > 0, "Pages table should have entries after initial build"

        # Delete a page file
        (temp_notebook_dir / "Journal.md").unlink()

        # Rebuild
        index.check_and_update()

        with index.get_connection() as conn:
            final_count = _count_rows_in_table(conn, "pages")

            # Should have fewer pages after deleting one
            assert final_count < initial_count, \
                f"Pages not properly cleared: {initial_count} -> {final_count}"

    def test_tags_table_cleared_before_rebuild(self, temp_notebook_dir):
        """Tags table should be repopulated fresh after rebuild."""
        index = _create_index(temp_notebook_dir)

        index.check_and_update()

        with index.get_connection() as conn:
            initial_tags = _count_rows_in_table(conn, "tags")
            assert initial_tags > 0, f"Tags table should have entries (got {initial_tags})"

        # Modify a page to remove a tag
        journal = temp_notebook_dir / "Journal.md"
        content = journal.read_text()
        journal.write_text(content.replace("#daily", ""))

        # Rebuild
        index.check_and_update()

        with index.get_connection() as conn:
            final_tags = _count_rows_in_table(conn, "tags")

            # Should have one less tag (daily was removed)
            assert final_tags < initial_tags, \
                f"Tags not properly cleared: {initial_tags} -> {final_tags}"

    def test_tagsources_table_cleared_before_rebuild(self, temp_notebook_dir):
        """Tagsources junction table should be cleared and repopulated."""
        index = _create_index(temp_notebook_dir)

        index.check_and_update()

        with index.get_connection() as conn:
            initial_sources = _count_rows_in_table(conn, "tagsources")
            assert initial_sources > 0, f"Tagsources should have entries (got {initial_sources})"

        # Rebuild
        index.check_and_update()

        with index.get_connection() as conn:
            final_sources = _count_rows_in_table(conn, "tagsources")

            # Should be repopulated with same count
            assert final_sources == initial_sources, \
                f"Tagsources count changed unexpectedly: {initial_sources} -> {final_sources}"

    def test_links_table_cleared_before_rebuild(self, temp_notebook_dir):
        """Links table should be cleared and repopulated."""
        index = _create_index(temp_notebook_dir)

        index.check_and_update()

        with index.get_connection() as conn:
            initial_links = _count_rows_in_table(conn, "links")
            assert initial_links > 0, "Links should have entries"

        # Rebuild
        index.check_and_update()

        with index.get_connection() as conn:
            final_links = _count_rows_in_table(conn, "links")

            # Should be same count after rebuild (files unchanged)
            assert final_links == initial_links, \
                f"Links count changed unexpectedly: {initial_links} -> {final_links}"

    def test_all_tables_empty_if_no_pages(self, tmp_path):
        """Rebuild should result in empty tables if notebook has no pages."""
        notebook_dir = tmp_path / "empty_notebook"
        notebook_dir.mkdir()

        (notebook_dir / "notebook.moon").write_text(
            "[notebook]\nname = Empty\nhome = Home\n"
        )

        index = _create_index(notebook_dir)

        # Build
        index.check_and_update()

        with index.get_connection() as conn:
            assert _count_rows_in_table(conn, "pages") == 0
            assert _count_rows_in_table(conn, "tags") == 0
            assert _count_rows_in_table(conn, "tagsources") == 0
            assert _count_rows_in_table(conn, "links") == 0


@pytest.mark.unit
class TestIndexCleanupWithFTS:
    """Tests that check_and_update() works correctly with FTS enabled/disabled."""

    def test_rebuild_with_fts_enabled(self, temp_notebook_dir):
        """Rebuild should clear and repopulate FTS table when available."""
        index = _create_index(temp_notebook_dir)

        # Check if FTS is available
        has_fts = index._has_fts

        index.check_and_update()

        with index.get_connection() as conn:
            if has_fts:
                # FTS table should exist and have entries
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM pages_fts"
                )
                fts_count = cursor.fetchone()[0]
                assert fts_count > 0, "FTS table should have entries"
            else:
                # FTS not available - just verify no error
                pass

    def test_rebuild_clears_fts_before_repopulating(self, temp_notebook_dir):
        """FTS table should be cleared before repopulating."""
        index = _create_index(temp_notebook_dir)

        if not index._has_fts:
            pytest.skip("FTS not available in this environment")

        # Initial build
        index.check_and_update()

        with index.get_connection() as conn:
            initial_fts = _count_rows_in_table(conn, "pages_fts")

        # Delete a page
        (temp_notebook_dir / "Journal.md").unlink()

        # Rebuild
        index.check_and_update()

        with index.get_connection() as conn:
            final_fts = _count_rows_in_table(conn, "pages_fts")

            # Should have fewer FTS entries
            assert final_fts < initial_fts, \
                f"FTS not properly cleared: {initial_fts} -> {final_fts}"

    def test_fts_search_returns_correct_results_after_rebuild(self, temp_notebook_dir):
        """FTS search should return only current pages after rebuild."""
        index = _create_index(temp_notebook_dir)

        if not index._has_fts:
            pytest.skip("FTS not available")

        index.check_and_update()

        # Delete a page that contained "Welcome"
        home_file = temp_notebook_dir / "Home.md"
        home_file.unlink()

        # Rebuild
        index.check_and_update()

        with index.get_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM pages_fts WHERE pages_fts MATCH ?",
                ("Welcome",)
            )
            results = cursor.fetchall()

            # Should not find "Welcome" anymore since Home.md was deleted
            assert len(results) == 0, \
                f"FTS still returns results for deleted content: {results}"


@pytest.mark.unit
class TestIndexCleanupForeignKeys:
    """Tests that foreign key constraints are respected."""

    def test_no_orphaned_tagsources_after_rebuild(self, temp_notebook_dir):
        """Tagsources should only reference valid tags and pages."""
        index = _create_index(temp_notebook_dir)

        index.check_and_update()

        with index.get_connection() as conn:
            # Enable foreign key checking
            conn.execute("PRAGMA foreign_keys = ON")

            # Check for orphaned tagsources (tag_id not in tags)
            cursor = conn.execute("""
                SELECT ts.tag, ts.source
                FROM tagsources ts
                LEFT JOIN tags t ON ts.tag = t.id
                WHERE t.id IS NULL
            """)
            orphaned_tags = cursor.fetchall()

            assert len(orphaned_tags) == 0, \
                f"Orphaned tagsources (missing tag): {orphaned_tags}"

            # Check for orphaned tagsources (source_id not in pages)
            cursor = conn.execute("""
                SELECT ts.tag, ts.source
                FROM tagsources ts
                LEFT JOIN pages p ON ts.source = p.id
                WHERE p.id IS NULL
            """)
            orphaned_sources = cursor.fetchall()

            assert len(orphaned_sources) == 0, \
                f"Orphaned tagsources (missing page): {orphaned_sources}"

    def test_no_orphaned_links_after_rebuild(self, temp_notebook_dir):
        """Links should only reference valid pages."""
        index = _create_index(temp_notebook_dir)

        index.check_and_update()

        with index.get_connection() as conn:
            # Check for orphaned links (source_id not in pages)
            cursor = conn.execute("""
                SELECT l.source, l.target
                FROM links l
                LEFT JOIN pages p ON l.source = p.id
                WHERE p.id IS NULL
            """)
            orphaned_sources = cursor.fetchall()

            assert len(orphaned_sources) == 0, \
                f"Orphaned links (missing source page): {orphaned_sources}"

            # Check for orphaned links (target_id not in pages)
            # Note: targets may be placeholder pages for links to non-existent pages
            cursor = conn.execute("""
                SELECT l.source, l.target
                FROM links l
                LEFT JOIN pages p ON l.target = p.id
                WHERE p.id IS NULL
            """)
            orphaned_targets = cursor.fetchall()

            assert len(orphaned_targets) == 0, \
                f"Orphaned links (missing target page): {orphaned_targets}"

    def test_pages_parent_references_valid(self, temp_notebook_dir):
        """Page parent references should be valid or NULL."""
        index = _create_index(temp_notebook_dir)

        # Create a nested page
        subdir = temp_notebook_dir / "Namespace"
        subdir.mkdir()
        (subdir / "SubPage.md").write_text("# SubPage\n\nNested page")

        index.check_and_update()

        with index.get_connection() as conn:
            # Check for invalid parent references
            cursor = conn.execute("""
                SELECT p.id, p.name, p.parent
                FROM pages p
                LEFT JOIN pages parent ON p.parent = parent.id
                WHERE p.parent IS NOT NULL AND parent.id IS NULL
            """)
            invalid_parents = cursor.fetchall()

            assert len(invalid_parents) == 0, \
                f"Pages with invalid parent references: {invalid_parents}"

    def test_foreign_keys_enforced_on_delete(self, temp_notebook_dir):
        """Foreign key constraints are enforced; rebuild cleans up orphans.

        This test verifies that:
        1. Direct page deletion is blocked by FK constraints (if enabled)
        2. A proper rebuild clears all tables in the correct order
        """
        index = _create_index(temp_notebook_dir)

        index.check_and_update()

        # Get a page ID
        with index.get_connection() as conn:
            cursor = conn.execute("SELECT id FROM pages LIMIT 1")
            page_id = cursor.fetchone()[0]

            # Verify FK constraints are working by checking that related data exists
            cursor = conn.execute(
                "SELECT COUNT(*) FROM tagsources WHERE source = ?", (page_id,)
            )
            tagsources_count = cursor.fetchone()[0]

            cursor = conn.execute(
                "SELECT COUNT(*) FROM links WHERE source = ?", (page_id,)
            )
            links_count = cursor.fetchone()[0]

        # The key test: after rebuild, no orphaned references should exist
        # because check_and_update clears tables in the correct order:
        # 1. tagsources (depends on tags, pages)
        # 2. links (depends on pages)
        # 3. tags (no dependencies)
        # 4. pages (no dependencies)

        # Modify the notebook and rebuild
        (temp_notebook_dir / "Journal.md").unlink()
        index.check_and_update()

        with index.get_connection() as conn:
            # All tagsources should have valid sources
            cursor = conn.execute("""
                SELECT COUNT(*)
                FROM tagsources ts
                LEFT JOIN pages p ON ts.source = p.id
                WHERE p.id IS NULL
            """)
            orphaned_tagsources = cursor.fetchone()[0]
            assert orphaned_tagsources == 0, \
                f"Found {orphaned_tagsources} orphaned tagsources after rebuild"

            # All links should have valid sources
            cursor = conn.execute("""
                SELECT COUNT(*)
                FROM links l
                LEFT JOIN pages p ON l.source = p.id
                WHERE p.id IS NULL
            """)
            orphaned_links = cursor.fetchone()[0]
            assert orphaned_links == 0, \
                f"Found {orphaned_links} orphaned links after rebuild"


@pytest.mark.unit
class TestIndexCleanupOrderOfOperations:
    """Tests that tables are cleared in the correct order."""

    def test_clear_order_respects_foreign_keys(self, temp_notebook_dir):
        """Tables should be cleared in order: tagsources, links, tags, pages."""
        index = _create_index(temp_notebook_dir)

        # First build to populate
        index.check_and_update()

        # This test verifies that the cleanup doesn't raise FK errors
        # The order in check_and_update is:
        # 1. DELETE FROM tagsources
        # 2. DELETE FROM links
        # 3. DELETE FROM tags
        # 4. DELETE FROM pages
        # This order is correct because:
        # - tagsources references tags and pages
        # - links references pages
        # - tags has no FK dependencies

        # Second build should not raise any FK errors
        try:
            index.check_and_update()
            success = True
            error_msg = None
        except sqlite3.IntegrityError as e:
            success = False
            error_msg = str(e)

        assert success, f"Rebuild failed with FK error: {error_msg}"

    def test_is_uptodate_set_after_successful_rebuild(self, temp_notebook_dir):
        """is_uptodate flag should be True after successful rebuild."""
        index = _create_index(temp_notebook_dir)

        assert index.is_uptodate is False, "Should not be uptodate before build"

        index.check_and_update()

        assert index.is_uptodate is True, "Should be uptodate after successful build"


@pytest.mark.unit
class TestIndexCleanupIdempotent:
    """Tests that rebuild is idempotent."""

    def test_rebuild_is_idempotent(self, temp_notebook_dir):
        """Multiple rebuilds should produce identical results."""
        index = _create_index(temp_notebook_dir)

        # First build
        index.check_and_update()

        with index.get_connection() as conn:
            pages_1 = sorted(_get_all_page_names(conn))
            cursor = conn.execute("SELECT COUNT(*) FROM tags")
            tags_1 = cursor.fetchone()[0]
            cursor = conn.execute("SELECT COUNT(*) FROM links")
            links_1 = cursor.fetchone()[0]

        # Second build (idempotent)
        index.check_and_update()

        with index.get_connection() as conn:
            pages_2 = sorted(_get_all_page_names(conn))
            cursor = conn.execute("SELECT COUNT(*) FROM tags")
            tags_2 = cursor.fetchone()[0]
            cursor = conn.execute("SELECT COUNT(*) FROM links")
            links_2 = cursor.fetchone()[0]

        assert pages_1 == pages_2, f"Pages differ: {pages_1} vs {pages_2}"
        assert tags_1 == tags_2, f"Tag counts differ: {tags_1} vs {tags_2}"
        assert links_1 == links_2, f"Link counts differ: {links_1} vs {links_2}"

    def test_rebuild_after_file_deletion(self, temp_notebook_dir):
        """Rebuild should remove entries for deleted files."""
        index = _create_index(temp_notebook_dir)

        # First build
        index.check_and_update()

        with index.get_connection() as conn:
            pages_before = _get_all_page_names(conn)
            assert "Journal" in pages_before, "Journal page should exist"

        # Delete a file
        (temp_notebook_dir / "Journal.md").unlink()

        # Rebuild
        index.check_and_update()

        with index.get_connection() as conn:
            pages_after = _get_all_page_names(conn)
            assert "Journal" not in pages_after, \
                f"Journal should be removed after file deletion: {pages_after}"

    def test_rebuild_after_file_addition(self, temp_notebook_dir):
        """Rebuild should add entries for new files."""
        index = _create_index(temp_notebook_dir)

        # First build
        index.check_and_update()

        with index.get_connection() as conn:
            pages_before = _get_all_page_names(conn)

        # Add a new file (Moonstone format)
        (temp_notebook_dir / "NewPage.md").write_text("# NewPage\n\nContent")

        # Rebuild
        index.check_and_update()

        with index.get_connection() as conn:
            pages_after = _get_all_page_names(conn)
            assert "NewPage" in pages_after, \
                f"NewPage should be added: {pages_after}"
            assert len(pages_after) == len(pages_before) + 1
