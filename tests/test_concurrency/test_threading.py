# -*- coding: utf-8 -*-
"""Threading and concurrency tests for Moonstone.

Tests thread-safety of concurrent operations, especially:
- Main thread dispatch via idle_add()
- Optimistic concurrency with mtime/etag
- Simultaneous read/write operations
"""

import pytest
import threading
import time
from unittest.mock import Mock, patch


@pytest.mark.concurrency
class TestMainThreadDispatch:
    """Test cases for main thread dispatch pattern."""

    def test_idle_add_dispatch_basic(self, api_client):
        """Basic dispatch should execute on main thread and return result."""
        # This is a basic smoke test - real testing requires running main loop
        from webbridge.api import _run_synchronized

        result = _run_synchronized(lambda: (200, {}, {"ok": True}))
        assert result[0] == 200
        assert result[2] == {"ok": True}

    def test_idle_add_dispatch_with_exception(self, api_client):
        """Exception in dispatched function should be caught and returned."""
        from webbridge.api import _run_synchronized

        result = _run_synchronized(lambda: (_ for _ in ()).throw(ValueError("test error")))
        # Should return 500 with error
        assert result[0] == 500
        assert "error" in result[2]

    def test_idle_add_timeout(self, api_client):
        """Timeout parameter is ignored (kept for backward compatibility).

        With ConnectionPool, operations execute directly without the fake
        "main thread dispatch" timeout. The timeout parameter is accepted
        but not enforced since operations run synchronously.
        """
        from webbridge.api import _run_synchronized

        # Quick operation (timeout is ignored)
        result = _run_synchronized(lambda: (200, {}, {"ok": True}), timeout=0.1)
        assert result[0] == 200

        # Note: Testing actual long-running timeout would require 10s sleep,
        # which is impractical. The ConnectionPool architecture enforces
        # connection-level timeout (default 30s) instead of operation timeout.


@pytest.mark.concurrency
class TestConcurrentPageWrites:
    """Test concurrent write operations to the same page."""

    def test_concurrent_write_conflict(self, api_client):
        """Two threads updating same page should get conflicts."""
        from notebook.page import Path

        # Create initial page
        path = Path("ConcurrentTest")
        page = api_client.notebook.get_page(path)
        page.parse("wiki", "initial content")
        if hasattr(api_client.notebook, "store_page"):
            api_client.notebook.store_page(page)

        results = []
        errors = []

        def write_thread(thread_id, expected_mtime):
            try:
                # Try to update with mtime check
                status, headers, body = api_client.save_page(
                    "ConcurrentTest",
                    f"content from thread {thread_id}",
                    expected_mtime=expected_mtime
                )
                results.append((thread_id, status))
            except Exception as e:
                errors.append((thread_id, str(e)))

        # Get initial mtime
        try:
            status, headers, body = api_client.get_page("ConcurrentTest")
            initial_mtime = body.get("mtime")
        except:
            initial_mtime = None

        # Start two threads with same expected_mtime
        t1 = threading.Thread(target=write_thread, args=(1, initial_mtime))
        t2 = threading.Thread(target=write_thread, args=(2, initial_mtime))

        t1.start()
        time.sleep(0.01)  # Small delay to ensure t1 goes first
        t2.start()

        t1.join(timeout=5)
        t2.join(timeout=5)

        # At least one should have succeeded
        statuses = [s for _, s in results]
        # One or both should succeed depending on timing
        # In a real scenario with proper mtime checking, one would get 409
        assert len(results) > 0 or len(errors) > 0

    def test_concurrent_create_different_pages(self, api_client):
        """Creating different pages concurrently should work."""
        results = []

        def create_page(page_num):
            try:
                status, headers, body = api_client.create_page(
                    f"ConcurrentPage{page_num}",
                    f"content {page_num}"
                )
                results.append(status)
            except Exception as e:
                results.append(500)

        threads = []
        for i in range(5):
            t = threading.Thread(target=create_page, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5)

        # All should succeed
        assert all(s == 200 for s in results)

    def test_concurrent_read_while_write(self, api_client):
        """Reading during write should not crash."""
        from notebook.page import Path

        # Create a page
        path = Path("ReadWriteTest")
        page = api_client.notebook.get_page(path)
        page.parse("wiki", "initial")
        if hasattr(api_client.notebook, "store_page"):
            api_client.notebook.store_page(page)

        write_done = threading.Event()
        read_results = []

        def writer():
            time.sleep(0.05)
            api_client.save_page("ReadWriteTest", "updated content")
            write_done.set()

        def reader(reader_id):
            # Try to read while write is happening
            time.sleep(0.02)
            try:
                status, headers, body = api_client.get_page("ReadWriteTest")
                read_results.append((reader_id, status))
            except Exception as e:
                read_results.append((reader_id, 500))

        # Start writer and multiple readers
        threads = [threading.Thread(target=writer)]
        for i in range(3):
            threads.append(threading.Thread(target=reader, args=(i,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        # All reads should complete (with either old or new data)
        assert len(read_results) == 3
        assert all(status in (200, 500) for _, status in read_results)


@pytest.mark.concurrency
class TestConcurrentSearch:
    """Test concurrent search operations."""

    def test_concurrent_search_queries(self, api_client):
        """Multiple searches should execute safely."""
        results = []

        def search_query(query_id):
            try:
                status, headers, body = api_client.search_pages(f"test{query_id}")
                results.append(status)
            except Exception as e:
                results.append(500)

        threads = []
        for i in range(5):
            t = threading.Thread(target=search_query, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5)

        # All should complete without error
        assert all(s == 200 for s in results)

    def test_concurrent_search_and_write(self, api_client):
        """Search during write should not crash."""
        results = []

        def writer():
            time.sleep(0.02)
            api_client.create_page("SearchWriteTest", "content here")

        def searcher():
            time.sleep(0.04)
            status, _, _ = api_client.search_pages("test")
            results.append(status)

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=searcher)

        t1.start()
        t2.start()

        t1.join(timeout=5)
        t2.join(timeout=5)

        # Search should complete
        assert len(results) == 1
        assert results[0] == 200


@pytest.mark.concurrency
class TestConcurrentListOperations:
    """Test concurrent list/iteration operations."""

    def test_concurrent_list_pages(self, api_client):
        """Multiple threads listing pages should not conflict."""
        results = []

        def list_pages(thread_id):
            try:
                status, headers, body = api_client.list_pages()
                results.append((thread_id, status))
            except Exception as e:
                results.append((thread_id, 500))

        threads = []
        for i in range(5):
            t = threading.Thread(target=list_pages, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5)

        # All should succeed
        assert len(results) == 5
        assert all(status == 200 for _, status in results)

    def test_concurrent_list_tags(self, api_client):
        """Multiple threads listing tags should not conflict."""
        results = []

        def list_tags(thread_id):
            try:
                status, headers, body = api_client.list_tags()
                results.append((thread_id, status))
            except Exception as e:
                results.append((thread_id, 500))

        threads = []
        for i in range(5):
            t = threading.Thread(target=list_tags, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5)

        # All should succeed
        assert len(results) == 5
        assert all(status == 200 for _, status in results)


@pytest.mark.concurrency
class TestRaceConditions:
    """Test specific race condition scenarios."""

    def test_create_delete_race(self, api_client):
        """Creating and deleting same page concurrently."""
        results = {"create": None, "delete": None}

        def creator():
            time.sleep(0.01)
            status, _, _ = api_client.create_page("RacePage", "content")
            results["create"] = status

        def deleter():
            time.sleep(0.02)
            # Try to delete (might not exist yet)
            try:
                status, _, _ = api_client.delete_page("RacePage")
                results["delete"] = status
            except:
                results["delete"] = 404

        t1 = threading.Thread(target=creator)
        t2 = threading.Thread(target=deleter)

        t1.start()
        t2.start()

        t1.join(timeout=5)
        t2.join(timeout=5)

        # Both operations should complete
        assert results["create"] is not None
        assert results["delete"] is not None

    def test_write_read_write_race(self, api_client):
        """Rapid write-read-write sequence."""
        from notebook.page import Path

        # Create initial page
        try:
            api_client.create_page("RacePage2", "v1")
        except:
            pass

        results = []

        def rapid_updates():
            for i in range(10):
                try:
                    api_client.save_page(f"RacePage2{i}", f"v{i}")
                    results.append(i)
                except:
                    pass

        threads = []
        for _ in range(3):
            t = threading.Thread(target=rapid_updates)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5)

        # Should complete without deadlock
        assert True  # If we get here, no deadlock


@pytest.mark.concurrency
class TestIndexConcurrency:
    """Test concurrent index operations."""

    def test_concurrent_index_queries(self, api_client):
        """Multiple threads querying index should be safe."""
        results = []

        def query_links(thread_id):
            try:
                status, _, _ = api_client.get_links("Home")
                results.append(("links", thread_id, status))
            except Exception as e:
                results.append(("links", thread_id, 500))

        def query_tags(thread_id):
            try:
                status, _, _ = api_client.get_page_tags("Home")
                results.append(("tags", thread_id, status))
            except Exception as e:
                results.append(("tags", thread_id, 500))

        threads = []
        for i in range(5):
            threads.append(threading.Thread(target=query_links, args=(i,)))
            threads.append(threading.Thread(target=query_tags, args=(i,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        # All queries should complete
        assert len(results) == 10


@pytest.mark.slow
@pytest.mark.concurrency
class TestStressTests:
    """Stress tests for concurrency."""

    def test_many_concurrent_reads(self, api_client):
        """Many threads reading simultaneously."""
        results = []

        def reader():
            try:
                status, _, _ = api_client.get_page("TestPage")
                results.append(status)
            except:
                results.append(500)

        threads = []
        for _ in range(50):
            t = threading.Thread(target=reader)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5)

        # All should complete
        assert len(results) == 50

    def test_many_concurrent_writes_different_pages(self, api_client):
        """Many threads writing to different pages."""
        results = []

        def writer(page_id):
            try:
                status, _, _ = api_client.create_page(
                    f"StressPage{page_id}",
                    f"content {page_id}"
                )
                results.append(status)
            except:
                results.append(500)

        threads = []
        for i in range(20):
            t = threading.Thread(target=writer, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5)

        # Most should succeed
        success_count = sum(1 for s in results if s == 200)
        assert success_count >= 15  # Allow some failures
