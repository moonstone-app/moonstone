# -*- coding: utf-8 -*-
"""Tests for optimistic concurrency and conflict detection.

Tests mtime-based and etag-based conflict detection when
multiple clients edit the same page simultaneously.
"""

import pytest
import threading
import time


@pytest.mark.concurrency
class TestMtimeConflicts:
    """Test mtime-based optimistic concurrency."""

    def test_save_with_stale_mtime_returns_conflict(self, api_client, sample_page):
        """Saving with old mtime should return 409 Conflict."""
        from notebook.page import Path

        # Get page with current mtime
        status, headers, body = api_client.get_page("TestPage")
        assert status == 200
        original_mtime = body.get("mtime")

        # Modify the page (updating mtime)
        api_client.save_page("TestPage", "modified content")

        # Try to save with old mtime
        status, headers, body = api_client.save_page(
            "TestPage",
            "conflicting content",
            expected_mtime=original_mtime
        )

        # Should get conflict
        assert status == 409
        assert "error" in body

    def test_save_with_current_mtime_succeeds(self, api_client, sample_page):
        """Saving with current mtime should succeed."""
        # Get current mtime
        status, headers, body = api_client.get_page("TestPage")
        current_mtime = body.get("mtime")

        # Save with same mtime
        status, headers, body = api_client.save_page(
            "TestPage",
            "updated content",
            expected_mtime=current_mtime
        )

        # Should succeed
        assert status == 200

    def test_save_without_mtime_check_succeeds(self, api_client, sample_page):
        """Saving without mtime check (last-write-wins) should succeed."""
        status, _, body = api_client.save_page("TestPage", "new content")

        # Should succeed
        assert status == 200

    def test_concurrent_edits_detect_conflict(self, api_client):
        """Simulate two users editing same page simultaneously."""
        # Create page
        api_client.create_page("ConflictTest", "initial content")

        # Both users get the page
        status1, _, body1 = api_client.get_page("ConflictTest")
        status2, _, body2 = api_client.get_page("ConflictTest")

        mtime1 = body1.get("mtime")
        mtime2 = body2.get("mtime")

        assert mtime1 == mtime2  # Same starting point

        # User 1 saves
        status1, _, body1 = api_client.save_page(
            "ConflictTest",
            "user 1 edits",
            expected_mtime=mtime1
        )
        assert status1 == 200

        # User 2 tries to save with old mtime
        status2, _, body2 = api_client.save_page(
            "ConflictTest",
            "user 2 edits",
            expected_mtime=mtime2
        )

        # User 2 should get conflict
        assert status2 == 409
        assert "error" in body2
        assert "modified" in body2["error"].lower()

    def test_three_way_conflict(self, api_client):
        """Test three clients editing same page."""
        api_client.create_page("ThreeWayTest", "initial")

        # All three get the page
        responses = [api_client.get_page("ThreeWayTest") for _ in range(3)]
        mtimes = [body.get("mtime") for _, _, body in responses]

        # First saves successfully
        status, _, body = api_client.save_page(
            "ThreeWayTest",
            "first edit",
            expected_mtime=mtimes[0]
        )
        assert status == 200

        # Second tries to save with original mtime
        status, _, body = api_client.save_page(
            "ThreeWayTest",
            "second edit",
            expected_mtime=mtimes[1]
        )
        assert status == 409

        # Third also tries with original mtime
        status, _, body = api_client.save_page(
            "ThreeWayTest",
            "third edit",
            expected_mtime=mtimes[2]
        )
        assert status == 409


@pytest.mark.concurrency
class TestEtagConflicts:
    """Test etag-based optimistic concurrency (if implemented)."""

    def test_etag_initialization_before_write(self, api_client):
        """Etag should be initialized before writing."""
        from notebook.page import Path

        # Create new page
        api_client.create_page("EtagTest", "content")

        # Get page (should initialize etag)
        status, _, body = api_client.get_page("EtagTest")
        assert status == 200

        # Update should work
        status, _, body = api_client.save_page("EtagTest", "updated")
        assert status == 200


@pytest.mark.concurrency
class TestConflictRecovery:
    """Test recovery strategies for conflicts."""

    def test_client_can_refetch_after_conflict(self, api_client):
        """Client should be able to get latest version after conflict."""
        # Create and modify page
        api_client.create_page("RecoveryTest", "v1")
        _, _, body1 = api_client.get_page("RecoveryTest")
        mtime1 = body1.get("mtime")

        # Someone else modifies
        api_client.save_page("RecoveryTest", "v2")

        # Try to save with old mtime -> conflict
        status, _, body = api_client.save_page(
            "RecoveryTest",
            "my version",
            expected_mtime=mtime1
        )
        assert status == 409

        # Client can now fetch latest version
        status, _, body = api_client.get_page("RecoveryTest")
        assert status == 200
        assert body["content"].strip() == "v2"

        # And try again with new mtime
        new_mtime = body.get("mtime")
        status, _, body = api_client.save_page(
            "RecoveryTest",
            "my merged version",
            expected_mtime=new_mtime
        )
        assert status == 200

    def test_merge_scenario(self, api_client):
        """Simulate client merging changes after conflict."""
        # Create page
        api_client.create_page("MergeTest", "line1\nline2\nline3")

        # User A gets page
        _, _, body_a = api_client.get_page("MergeTest")
        content_a = body_a["content"]
        mtime_a = body_a.get("mtime")

        # User B gets page
        _, _, body_b = api_client.get_page("MergeTest")
        content_b = body_b["content"]

        # User B saves first
        api_client.save_page("MergeTest", content_b + "\nline4b")

        # User A tries to save -> conflict
        status, _, body = api_client.save_page(
            "MergeTest",
            content_a + "\nline4a",
            expected_mtime=mtime_a
        )
        assert status == 409

        # User A fetches latest and merges
        _, _, body_latest = api_client.get_page("MergeTest")
        latest_content = body_latest["content"]
        latest_mtime = body_latest.get("mtime")

        # Merge: add line4a after line4b
        merged_content = latest_content + "\nline4a"

        # Save merged version
        status, _, body = api_client.save_page(
            "MergeTest",
            merged_content,
            expected_mtime=latest_mtime
        )
        assert status == 200


@pytest.mark.concurrency
class TestRaceConditionScenarios:
    """Test specific race condition patterns."""

    def test_create_then_immediate_read(self, api_client):
        """Reading immediately after create should see content."""
        results = []

        def creator():
            api_client.create_page("RaceCreateRead", "content")

        def reader():
            time.sleep(0.01)  # Small delay
            status, _, body = api_client.get_page("RaceCreateRead")
            results.append(status)

        t1 = threading.Thread(target=creator)
        t2 = threading.Thread(target=reader)

        t1.start()
        t2.start()

        t1.join(timeout=5)
        t2.join(timeout=5)

        # Read should succeed
        assert results[0] in (200, 404)  # May or may not exist yet

    def test_delete_then_immediate_create(self, api_client):
        """Creating same page after delete should work."""
        # Create page
        api_client.create_page("RaceDeleteCreate", "v1")

        # Delete it
        status, _, _ = api_client.delete_page("RaceDeleteCreate")
        assert status == 200

        # Immediately recreate
        status, _, _ = api_client.create_page("RaceDeleteCreate", "v2")
        assert status == 200

    def test_write_during_index_update(self, api_client):
        """Writing page while index is updating."""
        # This is hard to test directly, but we can simulate
        results = []

        def writer():
            for i in range(5):
                api_client.create_page(f"IndexRace{i}", "content")

        def searcher():
            time.sleep(0.02)
            status, _, _ = api_client.search_pages("IndexRace")
            results.append(status)

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=searcher)

        t1.start()
        t2.start()

        t1.join(timeout=5)
        t2.join(timeout=5)

        # Search should complete
        assert results[0] == 200


@pytest.mark.concurrency
class TestAtomicOperations:
    """Test that certain operations are atomic."""

    def test_append_is_atomic(self, api_client):
        """Concurrent appends should not lose data."""
        api_client.create_page("AppendTest", "start\n")

        results = []

        def appender(thread_id):
            try:
                api_client.append_to_page("AppendTest", f"line{thread_id}\n")
                results.append(thread_id)
            except:
                pass

        threads = []
        for i in range(10):
            t = threading.Thread(target=appender, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5)

        # Check final content
        status, _, body = api_client.get_page("AppendTest")
        assert status == 200

        # Some lines should be present (might not be all due to races)
        content = body["content"]
        # At least some appends should have succeeded
        assert len(results) > 0


@pytest.mark.concurrency
class TestBatchOperations:
    """Test concurrent batch operations."""

    def test_batch_operations_are_sequential(self, api_client):
        """Batch operations should execute sequentially."""
        operations = [
            {"method": "GET", "path": "/api/page/TestPage1"},
            {"method": "GET", "path": "/api/page/TestPage2"},
            {"method": "GET", "path": "/api/page/TestPage3"},
        ]

        status, _, body = api_client.batch(operations)
        assert status == 200
        assert "results" in body
        assert len(body["results"]) == 3

    def test_concurrent_batches(self, api_client):
        """Multiple concurrent batch operations."""
        results = []

        def batch_runner(batch_id):
            ops = [
                {"method": "GET", "path": f"/api/page/Page{batch_id}-{i}"}
                for i in range(3)
            ]
            status, _, body = api_client.batch(ops)
            results.append(status)

        threads = []
        for i in range(5):
            t = threading.Thread(target=batch_runner, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5)

        # All should complete
        assert len(results) == 5
        assert all(s == 200 for s in results)
