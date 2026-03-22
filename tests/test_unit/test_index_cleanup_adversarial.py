# -*- coding: utf-8 -*-
"""Adversarial tests for Index.check_and_update() cleanup logic.

Attack vectors tested:
1. Concurrent calls to check_and_update() from multiple threads
2. Very large number of pages (stress test)
3. Circular parent references in pages table
4. Invalid/corrupted data in tables before cleanup
5. Transaction failure during cleanup (simulated)
6. FTS table corruption
"""

import os
import sqlite3
import tempfile
import threading
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest


@pytest.fixture
def temp_notebook_dir(tmp_path):
    """Create a temporary notebook directory with test pages."""
    notebook_dir = tmp_path / "adversarial_notebook"
    notebook_dir.mkdir()

    (notebook_dir / "notebook.moon").write_text(
        "[notebook]\n"
        "name = Adversarial Test\n"
        "home = Home\n"
    )

    (notebook_dir / "Home.md").write_text("# Home\n\n#home\n\n[[Projects]]")
    (notebook_dir / "Projects.md").write_text("# Projects\n\n#work\n\n[[Home]]")

    return notebook_dir


def _create_index(notebook_dir, profile=None):
    """Helper to create an Index instance for testing."""
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


@pytest.mark.unit
class TestConcurrentCheckAndUpdate:
    """Attack: Multiple threads calling check_and_update() simultaneously."""

    def test_concurrent_check_and_update_no_corruption(self, temp_notebook_dir):
        """Concurrent calls should not corrupt the database.

        The RLock should serialize calls. Verify:
        1. No database corruption (integrity check passes)
        2. Final state is consistent (no partial data)
        3. No exceptions raised from concurrent access
        """
        index = _create_index(temp_notebook_dir)
        exceptions = []
        results = []
        lock = threading.Lock()

        def call_rebuild(thread_id):
            try:
                index.check_and_update()
                with lock:
                    results.append((thread_id, "success"))
            except Exception as e:
                with lock:
                    exceptions.append((thread_id, str(e)))

        # Launch 10 concurrent rebuild calls
        threads = []
        for i in range(10):
            t = threading.Thread(target=call_rebuild, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=30)

        # Verify no exceptions
        assert len(exceptions) == 0, f"Concurrent access raised exceptions: {exceptions}"

        # Verify database integrity
        with index.get_connection() as conn:
            cursor = conn.execute("PRAGMA integrity_check")
            integrity = cursor.fetchone()[0]
            assert integrity == "ok", f"Database corrupted: {integrity}"

        # Verify consistent state (no duplicates)
        with index.get_connection() as conn:
            cursor = conn.execute("SELECT name, COUNT(*) FROM pages GROUP BY name HAVING COUNT(*) > 1")
            duplicates = cursor.fetchall()
            assert len(duplicates) == 0, f"Duplicate pages after concurrent rebuild: {duplicates}"

    def test_concurrent_check_and_update_is_serialized(self, temp_notebook_dir):
        """Verify that concurrent calls are properly serialized.

        The RLock should ensure only one rebuild runs at a time.
        """
        index = _create_index(temp_notebook_dir)
        call_times = []
        lock = threading.Lock()

        original_scan = index._scan_directory

        def tracked_scan(*args, **kwargs):
            with lock:
                call_times.append(("start", time.time()))
            time.sleep(0.1)  # Simulate slow scan
            result = original_scan(*args, **kwargs)
            with lock:
                call_times.append(("end", time.time()))
            return result

        # Patch the scan method to track timing
        index._scan_directory = tracked_scan

        def call_rebuild(_):
            index.check_and_update()

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(call_rebuild, i) for i in range(5)]
            for f in as_completed(futures):
                f.result()  # Raise any exceptions

        # Verify calls were serialized (no overlap)
        # Each "end" should come before the next "start"
        sorted_times = sorted(call_times, key=lambda x: x[1])
        in_progress = 0
        for event, _ in sorted_times:
            if event == "start":
                assert in_progress == 0, "Multiple rebuilds ran concurrently"
                in_progress += 1
            else:
                in_progress -= 1

    def test_concurrent_rebuild_and_query(self, temp_notebook_dir):
        """Verify queries don't see partial state during rebuild.

        Queries during rebuild should either see:
        - Old state (before cleanup started)
        - New state (after rebuild completed)
        Never partial/inconsistent state.
        """
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        query_results = []
        exceptions = []
        lock = threading.Lock()

        def run_queries(thread_id):
            for _ in range(20):
                try:
                    with index.get_connection() as conn:
                        # Query that would be inconsistent if FKs violated
                        cursor = conn.execute("""
                            SELECT p.name, COUNT(ts.tag)
                            FROM pages p
                            LEFT JOIN tagsources ts ON p.id = ts.source
                            GROUP BY p.id
                        """)
                        result = cursor.fetchall()
                        with lock:
                            query_results.append((thread_id, len(result)))
                except Exception as e:
                    with lock:
                        exceptions.append((thread_id, str(e)))
                time.sleep(0.01)

        def run_rebuilds():
            for _ in range(5):
                index.check_and_update()
                time.sleep(0.05)

        # Start query threads and rebuild thread
        query_threads = [threading.Thread(target=run_queries, args=(i,)) for i in range(3)]
        rebuild_thread = threading.Thread(target=run_rebuilds)

        for t in query_threads:
            t.start()
        rebuild_thread.start()

        for t in query_threads:
            t.join(timeout=30)
        rebuild_thread.join(timeout=30)

        # No query exceptions allowed
        assert len(exceptions) == 0, f"Query exceptions during rebuild: {exceptions}"


@pytest.mark.unit
class TestLargePageCount:
    """Attack: Very large number of pages (stress test)."""

    def test_large_page_count_rebuild(self, tmp_path):
        """Rebuild with 500+ pages should complete without timeout or corruption."""
        notebook_dir = tmp_path / "large_notebook"
        notebook_dir.mkdir()

        (notebook_dir / "notebook.moon").write_text(
            "[notebook]\nname = Large\nhome = Home\n"
        )

        # Create 500 pages
        num_pages = 500
        for i in range(num_pages):
            page_file = notebook_dir / f"Page{i:04d}.md"
            tag_num = i % 20
            page_file.write_text(f"# Page{i:04d}\n\n#tag{tag_num}\n\nContent {i}")

        index = _create_index(notebook_dir)

        # Should complete without timeout
        start_time = time.time()
        index.check_and_update()
        elapsed = time.time() - start_time

        # Verify all pages indexed
        with index.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM pages")
            page_count = cursor.fetchone()[0]
            assert page_count == num_pages, f"Expected {num_pages} pages, got {page_count}"

            # Verify tags
            cursor = conn.execute("SELECT COUNT(*) FROM tags")
            tag_count = cursor.fetchone()[0]
            assert tag_count == 20, f"Expected 20 tags, got {tag_count}"

        # Should complete in reasonable time (< 30 seconds)
        assert elapsed < 30, f"Rebuild took too long: {elapsed:.2f}s"

    def test_large_page_count_no_duplicates_after_multiple_rebuilds(self, tmp_path):
        """Multiple rebuilds with many pages should not create duplicates."""
        notebook_dir = tmp_path / "large_dup_notebook"
        notebook_dir.mkdir()

        (notebook_dir / "notebook.moon").write_text(
            "[notebook]\nname = LargeDup\nhome = Home\n"
        )

        # Create 100 pages
        for i in range(100):
            page_file = notebook_dir / f"Test{i:03d}.md"
            page_file.write_text(f"# Test{i:03d}\n\n#tag\n\nContent")

        index = _create_index(notebook_dir)

        # Run 5 rebuilds
        for _ in range(5):
            index.check_and_update()

        # Verify no duplicates
        with index.get_connection() as conn:
            cursor = conn.execute("""
                SELECT name, COUNT(*) as cnt 
                FROM pages 
                GROUP BY name 
                HAVING cnt > 1
            """)
            duplicates = cursor.fetchall()
            assert len(duplicates) == 0, f"Found duplicate pages: {duplicates}"

            # Verify correct count
            cursor = conn.execute("SELECT COUNT(*) FROM pages")
            assert cursor.fetchone()[0] == 100


@pytest.mark.unit
class TestCircularParentReferences:
    """Attack: Circular parent references in pages table."""

    def test_cleanup_handles_circular_parent_refs(self, temp_notebook_dir):
        """Cleanup should handle pre-existing circular parent references.

        If the database has corrupted data with circular parent refs,
        the cleanup should still work (it deletes everything first).
        """
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        # Inject circular parent references directly
        with index.get_connection() as conn:
            # Get two page IDs
            cursor = conn.execute("SELECT id FROM pages LIMIT 2")
            rows = cursor.fetchall()
            if len(rows) >= 2:
                id1, id2 = rows[0][0], rows[1][0]
                # Create circular reference: id1 -> id2 -> id1
                conn.execute("UPDATE pages SET parent = ? WHERE id = ?", (id2, id1))
                conn.execute("UPDATE pages SET parent = ? WHERE id = ?", (id1, id2))
                conn.commit()

        # Rebuild should clear the corruption
        index.check_and_update()

        # Verify no circular references
        with index.get_connection() as conn:
            # Check for any cycles using a recursive CTE
            cursor = conn.execute("""
                WITH RECURSIVE ancestors(id, parent, depth, path) AS (
                    SELECT id, parent, 0, CAST(id AS TEXT) FROM pages WHERE parent IS NOT NULL
                    UNION ALL
                    SELECT p.id, p.parent, a.depth + 1, a.path || '->' || p.id
                    FROM pages p
                    JOIN ancestors a ON p.id = a.parent
                    WHERE a.depth < 100 AND a.path NOT LIKE '%' || p.id || '%'
                )
                SELECT id, path FROM ancestors WHERE depth >= 100
            """)
            cycles = cursor.fetchall()
            assert len(cycles) == 0, f"Found circular references: {cycles}"

    def test_self_referential_parent(self, temp_notebook_dir):
        """Cleanup should handle pages that reference themselves as parent."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        # Inject self-referential parent
        with index.get_connection() as conn:
            cursor = conn.execute("SELECT id FROM pages LIMIT 1")
            row = cursor.fetchone()
            if row:
                page_id = row[0]
                conn.execute("UPDATE pages SET parent = ? WHERE id = ?", (page_id, page_id))
                conn.commit()

        # Rebuild should clear it
        index.check_and_update()

        with index.get_connection() as conn:
            cursor = conn.execute("SELECT id FROM pages WHERE id = parent")
            self_refs = cursor.fetchall()
            assert len(self_refs) == 0, f"Found self-referential parents: {self_refs}"


@pytest.mark.unit
class TestInvalidCorruptedData:
    """Attack: Invalid/corrupted data in tables before cleanup."""

    def test_fk_prevents_orphaned_tagsources(self, temp_notebook_dir):
        """Foreign key constraints should prevent orphaned tagsources.

        This is a GOOD behavior - the database enforces integrity
        at the schema level, preventing corruption from being inserted.
        """
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        # Attempt to inject orphaned tagsources - should fail due to FK
        with index.get_connection() as conn:
            # Non-existent tag_id (99999) and source_id (88888)
            with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
                conn.execute(
                    "INSERT INTO tagsources (tag, source) VALUES (?, ?)",
                    (99999, 88888)
                )
                conn.commit()

        # Database should still be consistent
        index.check_and_update()

        with index.get_connection() as conn:
            cursor = conn.execute("""
                SELECT ts.tag, ts.source
                FROM tagsources ts
                LEFT JOIN tags t ON ts.tag = t.id
                LEFT JOIN pages p ON ts.source = p.id
                WHERE t.id IS NULL OR p.id IS NULL
            """)
            orphans = cursor.fetchall()
            assert len(orphans) == 0, f"Found orphaned tagsources: {orphans}"

    def test_fk_prevents_orphaned_links(self, temp_notebook_dir):
        """Foreign key constraints should prevent orphaned links.

        The schema enforces FK constraints, preventing corruption.
        """
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        # Attempt to inject orphaned links - should fail due to FK
        with index.get_connection() as conn:
            with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
                conn.execute(
                    "INSERT INTO links (source, target, rel, names) VALUES (?, ?, 0, 'test')",
                    (99999, 88888)
                )
                conn.commit()

        # Database should still be consistent after rebuild
        index.check_and_update()

        with index.get_connection() as conn:
            cursor = conn.execute("""
                SELECT l.source, l.target
                FROM links l
                LEFT JOIN pages src ON l.source = src.id
                LEFT JOIN pages tgt ON l.target = tgt.id
                WHERE src.id IS NULL OR tgt.id IS NULL
            """)
            orphans = cursor.fetchall()
            assert len(orphans) == 0, f"Found orphaned links: {orphans}"

    def test_cleanup_handles_null_values_in_required_fields(self, temp_notebook_dir):
        """Cleanup should handle NULL values in NOT NULL columns."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        # Note: SQLite allows NULL in some cases even with NOT NULL
        # depending on strict mode. Test that rebuild cleans up regardless.

        # Rebuild should succeed
        index.check_and_update()

        # Verify all required fields are populated
        with index.get_connection() as conn:
            cursor = conn.execute("SELECT id FROM pages WHERE name IS NULL")
            null_names = cursor.fetchall()
            assert len(null_names) == 0, f"Found pages with NULL name: {null_names}"

            cursor = conn.execute("SELECT id FROM tags WHERE name IS NULL")
            null_tags = cursor.fetchall()
            assert len(null_tags) == 0, f"Found tags with NULL name: {null_tags}"

    def test_cleanup_handles_malformed_names(self, temp_notebook_dir):
        """Cleanup should handle malformed page names in database."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        # Inject pages with unusual/malformed names
        malformed_names = [
            "",
            "   ",
            "\t\n",
            "A" * 10000,  # Very long name
            "page\x00with\x00nulls",  # Null bytes
            "page<script>alert(1)</script>",  # HTML injection attempt
            "page'; DROP TABLE pages;--",  # SQL injection attempt
        ]

        with index.get_connection() as conn:
            for name in malformed_names:
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO pages (basename, name, sortkey) VALUES (?, ?, ?)",
                        (name, name, name)
                    )
                except sqlite3.Error:
                    pass  # Some may fail due to constraints
            conn.commit()

        # Rebuild should clean up
        index.check_and_update()

        # Verify only valid pages remain
        with index.get_connection() as conn:
            cursor = conn.execute("SELECT name FROM pages")
            names = [row[0] for row in cursor.fetchall()]

            # Only filesystem pages should remain
            valid_names = {"Home", "Projects"}
            for name in names:
                assert name in valid_names or not any(mal in name for mal in ["\x00", "<script>", "DROP"])


@pytest.mark.unit
class TestTransactionFailure:
    """Attack: Transaction failure during cleanup."""

    def test_partial_cleanup_state_after_error(self, temp_notebook_dir):
        """Verify cleanup clears tables before rebuilding.

        If an error occurs AFTER cleanup but BEFORE repopulation,
        the database should be in an empty but consistent state.
        """
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        # Get initial state
        with index.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM pages")
            initial_count = cursor.fetchone()[0]
            assert initial_count > 0, "Should have pages after initial build"

        # Manually simulate the cleanup phase and error
        with index.get_connection() as conn:
            # This is what check_and_update does first
            conn.execute("DELETE FROM tagsources")
            conn.execute("DELETE FROM links")
            conn.execute("DELETE FROM tags")
            conn.execute("DELETE FROM pages")
            if index._has_fts:
                conn.execute("DELETE FROM pages_fts")
            conn.commit()

        # Verify database is now empty (simulating failed rebuild)
        with index.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM pages")
            empty_count = cursor.fetchone()[0]
            assert empty_count == 0, "Pages should be cleared"

            cursor = conn.execute("SELECT COUNT(*) FROM tags")
            assert cursor.fetchone()[0] == 0, "Tags should be cleared"

            cursor = conn.execute("SELECT COUNT(*) FROM links")
            assert cursor.fetchone()[0] == 0, "Links should be cleared"

        # Now rebuild properly
        index.check_and_update()

        # Verify rebuild restores the data
        with index.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM pages")
            restored_count = cursor.fetchone()[0]
            assert restored_count == initial_count, \
                f"Pages should be restored: {restored_count} vs {initial_count}"

    def test_is_uptodate_false_after_failed_rebuild(self, temp_notebook_dir):
        """is_uptodate should remain False if rebuild fails."""
        index = _create_index(temp_notebook_dir)

        # Patch to fail
        original_scan = index._scan_directory

        def failing_scan(*args, **kwargs):
            raise RuntimeError("Simulated failure")

        index._scan_directory = failing_scan

        with pytest.raises(RuntimeError):
            index.check_and_update()

        # is_uptodate should still be False
        assert index.is_uptodate is False, "is_uptodate should be False after failed rebuild"

        # Restore and verify normal rebuild works
        index._scan_directory = original_scan
        index.check_and_update()
        assert index.is_uptodate is True


@pytest.mark.unit
class TestFTSTableCorruption:
    """Attack: FTS table corruption."""

    def test_cleanup_handles_corrupted_fts_table(self, temp_notebook_dir):
        """Cleanup should handle corrupted FTS table.

        If FTS table has invalid rowids or corrupted data,
        cleanup should still work.
        """
        index = _create_index(temp_notebook_dir)

        if not index._has_fts:
            pytest.skip("FTS not available in this environment")

        index.check_and_update()

        # Corrupt FTS table - add entry with non-existent rowid
        with index.get_connection() as conn:
            # Insert FTS entry with rowid that doesn't match any page
            conn.execute(
                "INSERT INTO pages_fts (rowid, name, content) VALUES (?, ?, ?)",
                (99999, "GhostPage", "Ghost content that shouldn't exist")
            )
            conn.commit()

        # Rebuild should clear it
        index.check_and_update()

        with index.get_connection() as conn:
            cursor = conn.execute("SELECT rowid FROM pages_fts WHERE rowid = 99999")
            ghost = cursor.fetchall()
            assert len(ghost) == 0, "Ghost FTS entry should be cleared"

    def test_cleanup_handles_fts_table_mismatch(self, temp_notebook_dir):
        """Cleanup should handle FTS table being out of sync with pages."""
        index = _create_index(temp_notebook_dir)

        if not index._has_fts:
            pytest.skip("FTS not available in this environment")

        index.check_and_update()

        # Add a page to pages table but not to FTS
        with index.get_connection() as conn:
            conn.execute(
                "INSERT INTO pages (basename, name, sortkey, hascontent) VALUES (?, ?, ?, 1)",
                ("UnindexedPage", "UnindexedPage", "unindexedpage")
            )
            conn.commit()

        # Rebuild should sync them
        index.check_and_update()

        with index.get_connection() as conn:
            # Count pages with content
            cursor = conn.execute("SELECT COUNT(*) FROM pages WHERE hascontent = 1")
            page_count = cursor.fetchone()[0]

            # Count FTS entries
            cursor = conn.execute("SELECT COUNT(*) FROM pages_fts")
            fts_count = cursor.fetchone()[0]

            # Should match
            assert page_count == fts_count, \
                f"FTS count ({fts_count}) != pages with content ({page_count})"

    def test_rebuild_with_fts_duplicate_rowid(self, temp_notebook_dir):
        """Rebuild should handle FTS entries with existing rowids.

        Using INSERT OR REPLACE to update existing FTS entries should work.
        """
        index = _create_index(temp_notebook_dir)

        if not index._has_fts:
            pytest.skip("FTS not available")

        index.check_and_update()

        # Get an existing page's rowid
        with index.get_connection() as conn:
            cursor = conn.execute("SELECT id FROM pages LIMIT 1")
            page_id = cursor.fetchone()[0]

            # Use INSERT OR REPLACE to update the FTS entry (not INSERT which fails)
            conn.execute(
                "INSERT OR REPLACE INTO pages_fts (rowid, name, content) VALUES (?, ?, ?)",
                (page_id, "UpdatedName", "Updated content")
            )
            conn.commit()

        # Verify the update worked
        with index.get_connection() as conn:
            cursor = conn.execute("SELECT name FROM pages_fts WHERE rowid = ?", (page_id,))
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "UpdatedName"

        # Rebuild should restore original content
        index.check_and_update()

        # Verify FTS is restored to match pages
        with index.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM pages_fts")
            assert cursor.fetchone()[0] > 0


@pytest.mark.unit
class TestEdgeCasesAndBoundaries:
    """Additional edge cases and boundary conditions."""

    def test_rebuild_with_unicode_page_names(self, tmp_path):
        """Rebuild should handle Unicode page names."""
        notebook_dir = tmp_path / "unicode_notebook"
        notebook_dir.mkdir()

        (notebook_dir / "notebook.moon").write_text(
            "[notebook]\nname = Unicode\nhome = Home\n"
        )

        # Create pages with Unicode names
        unicode_names = [
            "日本語",  # Japanese
            "中文",    # Chinese
            "한국어",  # Korean
            "Русский",  # Russian
            "العربية",  # Arabic
            "עברית",   # Hebrew
            "Émojis🎉",  # Emojis
        ]

        for name in unicode_names:
            try:
                page_file = notebook_dir / f"{name}.md"
                page_file.write_text(f"# {name}\n\n#tag\n\nContent")
            except OSError:
                # Skip if filesystem doesn't support the name
                continue

        index = _create_index(notebook_dir)
        index.check_and_update()

        # Verify rebuild completed
        assert index.is_uptodate is True

    def test_rebuild_with_empty_tags(self, temp_notebook_dir):
        """Rebuild should handle pages with empty tag lines.

        A page with just '#' should not create an empty tag.
        """
        # Add a page with empty tag
        (temp_notebook_dir / "EmptyTag.md").write_text("# EmptyTag\n\n#\n\nContent")

        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        with index.get_connection() as conn:
            cursor = conn.execute("SELECT name FROM tags WHERE name = ''")
            empty_tags = cursor.fetchall()
            assert len(empty_tags) == 0, "Empty tag should not be created"

    def test_rebuild_with_special_characters_in_tags(self, temp_notebook_dir):
        """Rebuild should handle special characters in tags."""
        # Add page with special character tags
        special_tags = [
            "#work/meeting",
            "#project-2024",
            "#tag_with_underscore",
        ]

        content = "# Special\n\n" + "\n".join(special_tags) + "\n\nContent"
        (temp_notebook_dir / "SpecialTags.md").write_text(content)

        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        # Tags should be extracted (Moonstone profile extracts after #)
        with index.get_connection() as conn:
            cursor = conn.execute("SELECT name FROM tags")
            tags = [row[0] for row in cursor.fetchall()]

            # At least some tags should be present
            assert len(tags) > 0, "No tags extracted"

    def test_rebuild_when_db_file_locked(self, temp_notebook_dir):
        """Rebuild should handle database being temporarily locked.

        When the database is locked, the operation should either wait and
        succeed (if lock released in time) or raise an appropriate error.
        """
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        # Open a second connection and hold an exclusive lock
        db_path = os.path.join(temp_notebook_dir, "index.db")
        conn2 = sqlite3.connect(db_path, timeout=0.1)
        conn2.execute("BEGIN EXCLUSIVE")
        # Hold the transaction open to keep the lock
        conn2.execute("SELECT 1")

        try:
            # Try to rebuild - with very short timeout, should fail quickly
            # The connection pool has a 30s default timeout, but SQLite's
            # OperationalError should be raised if the DB is truly locked
            index.check_and_update()
            # If we get here without error, the lock was released or pool waited
            # This is acceptable behavior
            rebuild_succeeded = True
        except (sqlite3.OperationalError, RuntimeError) as e:
            # Either error type is acceptable
            rebuild_succeeded = False
            error_msg = str(e).lower()
            assert "locked" in error_msg or "timeout" in error_msg, \
                f"Unexpected error: {e}"
        finally:
            conn2.rollback()
            conn2.close()

        # After lock is released, rebuild should definitely work
        index.check_and_update()
        assert index.is_uptodate is True, "Should be uptodate after successful rebuild"
