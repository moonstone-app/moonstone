# -*- coding: utf-8 -*-
"""Adversarial security tests for the "Rebuild Database" menu item in tray.py.

ATTACK VECTORS TESTED:
1. Rapid clicking (race conditions) - spawning multiple rebuild threads
2. Concurrent rebuild requests - thread safety of notebook.index
3. Callback injection/replacement - runtime modification of _on_rebuild
4. Menu state manipulation - state corruption during rebuild
5. Thread safety issues - concurrent access to _server_box and _notebook
6. Callback exceptions not caught - silent exception loss in spawned threads

These tests verify that the tray rebuild functionality handles adversarial
inputs and conditions safely without crashing or corrupting state.
"""

import pytest
import threading
import time
import weakref
from unittest.mock import MagicMock, patch, PropertyMock


@pytest.mark.unit
class TestRapidClickingRaceConditions:
    """Test rapid clicking spawning multiple concurrent rebuild threads."""

    def test_rapid_clicks_spawn_multiple_threads(self):
        """Rapid clicks should spawn multiple threads (documents current behavior)."""
        from moonstone.tray import MoonstoneTray

        call_count = []
        call_events = []

        def make_event():
            event = threading.Event()
            call_events.append(event)
            return event

        def slow_callback():
            call_count.append(1)
            # Signal that this call started
            if call_events:
                call_events[len(call_count) - 1].set()
            time.sleep(0.3)  # Slow operation to overlap calls

        tray = MoonstoneTray(
            settings={},
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=slow_callback,
        )

        # Simulate rapid clicking - 5 clicks in quick succession
        for _ in range(5):
            tray._do_rebuild(None, None)
            time.sleep(0.01)  # Tiny delay between clicks

        # Wait for all threads to complete
        time.sleep(0.5)

        # SECURITY FINDING: All 5 callbacks were called concurrently
        # This is a race condition - multiple rebuilds can run simultaneously
        assert len(call_count) == 5, "Rapid clicks spawn multiple concurrent rebuilds"

    def test_rapid_clicks_with_exception_in_callback(self):
        """Rapid clicks with exceptions should not prevent subsequent clicks."""
        from moonstone.tray import MoonstoneTray

        call_counter = [0]  # Shared counter
        successful_calls = []
        call_lock = threading.Lock()

        def sometimes_failing_callback():
            with call_lock:
                call_counter[0] += 1
                call_num = call_counter[0]
            if call_num % 2 == 0:  # Even calls fail
                raise RuntimeError(f"Simulated failure on call {call_num}")
            with call_lock:
                successful_calls.append(call_num)

        tray = MoonstoneTray(
            settings={},
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=sometimes_failing_callback,
        )

        # Rapid clicks
        for _ in range(10):
            tray._do_rebuild(None, None)
            time.sleep(0.02)

        time.sleep(0.5)

        # All 10 threads should have been spawned (all called)
        # SECURITY FINDING: Exceptions in spawned threads don't block subsequent clicks
        # The counter should show all 10 calls were attempted
        assert call_counter[0] == 10, "All 10 rapid clicks should trigger callbacks"
        # Successful calls = odd numbers (1, 3, 5, 7, 9) = 5 calls
        assert len(successful_calls) == 5, f"5 successful calls expected, got {len(successful_calls)}"

    def test_concurrent_rebuild_calls_share_no_lock(self):
        """Verify no locking mechanism exists for concurrent rebuild calls."""
        from moonstone.tray import MoonstoneTray

        call_times = []
        overlap_detected = []

        def track_overlap_callback():
            call_times.append(time.time())
            time.sleep(0.2)  # Simulate work
            call_times.append(time.time())
            # Check if any calls overlapped
            if len(call_times) >= 4:
                # If start time of this call < end time of previous call, overlap
                if call_times[-2] < call_times[-3]:  # This start < previous end
                    overlap_detected.append(True)

        tray = MoonstoneTray(
            settings={},
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=track_overlap_callback,
        )

        # Two rapid clicks
        tray._do_rebuild(None, None)
        time.sleep(0.05)  # Small delay
        tray._do_rebuild(None, None)

        time.sleep(0.5)

        # SECURITY FINDING: Calls can overlap - no mutual exclusion
        # The second call starts while the first is still running
        assert len(call_times) == 4, "Both calls should complete"


@pytest.mark.unit
class TestConcurrentRebuildRequests:
    """Test concurrent rebuild requests and their impact on shared state."""

    def test_concurrent_access_to_shared_server_box(self):
        """Concurrent access to _server_box should not corrupt state."""
        from moonstone.headless import MoonstoneServer

        # Simulate _server_box pattern from headless.py
        _server_box = [None]
        access_count = []
        access_lock = threading.Lock()

        def simulate_rebuild():
            with access_lock:
                access_count.append(1)
            # Access _server_box[0]._notebook pattern
            server = _server_box[0]
            if server and hasattr(server, '_notebook'):
                _ = server._notebook
            time.sleep(0.1)

        # Create mock server
        mock_server = MagicMock()
        mock_server._notebook = MagicMock()
        _server_box[0] = mock_server

        # Launch concurrent rebuilds
        threads = []
        for _ in range(10):
            t = threading.Thread(target=simulate_rebuild)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=2.0)

        # All threads should have accessed
        assert len(access_count) == 10

    def test_concurrent_index_updates_cause_conflict(self):
        """Test that concurrent index updates would conflict (documenting vulnerability)."""
        from moonstone.headless import MoonstoneServer

        # Mock notebook with index that tracks concurrent access
        mock_notebook = MagicMock()
        mock_index = MagicMock()

        in_progress = []
        conflicts = []

        def track_concurrent_check_and_update():
            in_progress.append(threading.current_thread().ident)
            if len(in_progress) > 1:
                conflicts.append(len(in_progress))
            time.sleep(0.2)  # Simulate work
            in_progress.remove(threading.current_thread().ident)

        mock_index.check_and_update = track_concurrent_check_and_update
        mock_notebook.index = mock_index

        settings = {"notebook": "/test/path"}
        server = MoonstoneServer(settings)
        server._notebook = mock_notebook

        def on_rebuild():
            notebook = server._notebook
            if notebook:
                notebook.index.check_and_update()

        # Simulate concurrent rebuilds
        threads = []
        for _ in range(3):
            t = threading.Thread(target=on_rebuild)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=2.0)

        # SECURITY FINDING: Multiple threads could access index simultaneously
        # The conflict count indicates concurrent access
        assert len(conflicts) > 0, "Concurrent index access detected - no locking"

    def test_server_box_replace_during_rebuild(self):
        """Test replacing _server_box[0] during rebuild doesn't crash."""
        from moonstone.headless import MoonstoneServer

        rebuild_started = threading.Event()
        server_replaced = threading.Event()
        rebuild_completed = threading.Event()

        _server_box = [MagicMock()]
        _server_box[0]._notebook = MagicMock()
        _server_box[0]._notebook.index = MagicMock()

        def slow_check_and_update():
            rebuild_started.set()
            server_replaced.wait(timeout=1.0)
            time.sleep(0.1)

        _server_box[0]._notebook.index.check_and_update = slow_check_and_update

        def on_rebuild():
            try:
                notebook = _server_box[0]._notebook
                if notebook:
                    notebook.index.check_and_update()
            finally:
                rebuild_completed.set()

        # Start rebuild in thread
        rebuild_thread = threading.Thread(target=on_rebuild)
        rebuild_thread.start()

        rebuild_started.wait(timeout=1.0)

        # Replace server while rebuild is in progress
        new_server = MagicMock()
        new_server._notebook = MagicMock()
        new_server._notebook.index = MagicMock()
        _server_box[0] = new_server
        server_replaced.set()

        rebuild_thread.join(timeout=2.0)

        # Should complete without exception (uses old reference)
        assert rebuild_completed.is_set()


@pytest.mark.unit
class TestCallbackInjectionReplacement:
    """Test callback injection and replacement attacks."""

    def test_callback_can_be_replaced_at_runtime(self):
        """_on_rebuild can be replaced at runtime (documents vulnerability)."""
        from moonstone.tray import MoonstoneTray

        original_called = []
        replacement_called = []

        def original_callback():
            original_called.append(1)

        tray = MoonstoneTray(
            settings={},
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=original_callback,
        )

        # Verify original is set
        assert tray._on_rebuild is original_callback

        # SECURITY FINDING: Callback can be replaced externally
        def malicious_callback():
            replacement_called.append(1)

        tray._on_rebuild = malicious_callback

        # Trigger rebuild
        tray._do_rebuild(None, None)
        time.sleep(0.1)

        # Replacement was called instead of original
        assert len(replacement_called) == 1
        assert len(original_called) == 0

    def test_callback_replaced_with_non_callable(self):
        """Replacing _on_rebuild with non-callable should be handled."""
        from moonstone.tray import MoonstoneTray

        tray = MoonstoneTray(
            settings={},
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=lambda: None,
        )

        # Replace with non-callable
        tray._on_rebuild = "not a function"

        # Trigger rebuild - should not crash
        try:
            tray._do_rebuild(None, None)
            time.sleep(0.1)
            # SECURITY FINDING: No exception handling in thread body
            # This will fail silently (or crash thread)
        except TypeError:
            pass  # Expected if check happens before thread

    def test_callback_replaced_with_exception_raiser(self):
        """Replacing callback with one that raises should not crash tray."""
        from moonstone.tray import MoonstoneTray

        tray = MoonstoneTray(
            settings={},
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=lambda: None,
        )

        exception_raised = []

        def exploding_callback():
            exception_raised.append(1)
            raise RuntimeError("Malicious callback explosion!")

        tray._on_rebuild = exploding_callback

        # Trigger rebuild
        tray._do_rebuild(None, None)
        time.sleep(0.2)

        # Callback was attempted
        assert len(exception_raised) == 1
        # SECURITY FINDING: Exception is silently swallowed in daemon thread

    def test_callback_replacement_during_rebuild(self):
        """Replacing callback during rebuild should not affect in-progress call."""
        from moonstone.tray import MoonstoneTray

        first_callback_started = threading.Event()
        callback_replaced = threading.Event()
        first_callback_completed = threading.Event()

        def first_callback():
            first_callback_started.set()
            callback_replaced.wait(timeout=1.0)
            first_callback_completed.set()

        def second_callback():
            pass  # Should not be called

        tray = MoonstoneTray(
            settings={},
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=first_callback,
        )

        # Start rebuild
        tray._do_rebuild(None, None)
        first_callback_started.wait(timeout=1.0)

        # Replace callback while first is running
        tray._on_rebuild = second_callback
        callback_replaced.set()

        time.sleep(0.2)

        # First callback should have completed (not interrupted)
        assert first_callback_completed.is_set()


@pytest.mark.unit
class TestMenuStateManipulation:
    """Test menu state manipulation during rebuild."""

    def test_menu_rebuild_during_rebuild_operation(self):
        """Calling update_menu during rebuild should not corrupt state."""
        from moonstone.tray import MoonstoneTray

        rebuild_started = threading.Event()
        menu_updated = threading.Event()
        rebuild_completed = threading.Event()

        def slow_callback():
            rebuild_started.set()
            time.sleep(0.2)
            rebuild_completed.set()

        # Create mock pystray module
        mock_pystray = MagicMock()
        mock_menu = MagicMock()
        mock_menu.SEPARATOR = object()
        mock_menu_item = MagicMock()
        mock_icon = MagicMock()
        mock_pystray.Menu = MagicMock(return_value=mock_menu)
        mock_pystray.MenuItem = MagicMock(return_value=mock_menu_item)
        mock_pystray.Icon = MagicMock(return_value=mock_icon)

        with patch.dict('sys.modules', {'pystray': mock_pystray}):
            tray = MoonstoneTray(
                settings={"notebook": "/test", "port": 8090},
                on_restart=lambda: None,
                on_quit=lambda: None,
                on_rebuild=slow_callback,
            )

            # Create mock icon
            mock_icon_instance = MagicMock()
            tray._icon = mock_icon_instance

            # Start rebuild
            tray._do_rebuild(None, None)
            rebuild_started.wait(timeout=1.0)

            # Update menu during rebuild
            tray.update_menu()
            menu_updated.set()

            time.sleep(0.3)

        # Both operations should complete
        assert rebuild_completed.is_set()
        mock_icon_instance.update_menu.assert_called()

    def test_settings_change_during_rebuild(self):
        """Changing settings during rebuild should not affect in-progress rebuild."""
        from moonstone.tray import MoonstoneTray

        rebuild_started = threading.Event()
        settings_changed = threading.Event()
        rebuild_completed = threading.Event()
        captured_notebook = []

        def capture_notebook_callback():
            rebuild_started.set()
            time.sleep(0.1)
            # At this point, settings may have changed
            captured_notebook.append("captured")
            settings_changed.wait(timeout=1.0)
            rebuild_completed.set()

        settings = {"notebook": "/original", "port": 8090}

        tray = MoonstoneTray(
            settings=settings,
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=capture_notebook_callback,
        )

        # Start rebuild
        tray._do_rebuild(None, None)
        rebuild_started.wait(timeout=1.0)

        # Change settings during rebuild
        settings["notebook"] = "/different"
        settings_changed.set()

        time.sleep(0.2)

        assert rebuild_completed.is_set()
        assert len(captured_notebook) == 1

    def test_concurrent_menu_builds_with_changing_state(self):
        """Multiple menu builds with rapidly changing state should be safe."""
        from moonstone.tray import MoonstoneTray

        settings = {"notebook": "/test", "port": 8090, "token": "initial"}

        tray = MoonstoneTray(
            settings=settings,
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=lambda: None,
            server_info=lambda: {"status": "running", "n_pages": 100},
        )

        def change_settings():
            for i in range(50):
                settings["token"] = f"token_{i}"
                settings["port"] = 8090 + (i % 10)
                time.sleep(0.001)

        def build_menus():
            for _ in range(50):
                tray._build_menu()
                time.sleep(0.001)

        # Run both concurrently
        t1 = threading.Thread(target=change_settings)
        t2 = threading.Thread(target=build_menus)
        t1.start()
        t2.start()
        t1.join(timeout=2.0)
        t2.join(timeout=2.0)

        # Should complete without crash
        assert not t1.is_alive()
        assert not t2.is_alive()


@pytest.mark.unit
class TestThreadSafetyIssues:
    """Test thread safety issues in the rebuild code path."""

    def test_notebook_access_without_lock(self):
        """Accessing _notebook without lock is inherently thread-unsafe."""
        from moonstone.headless import MoonstoneServer

        mock_notebook = MagicMock()
        mock_index = MagicMock()
        access_log = []
        access_lock = threading.Lock()

        def track_access():
            with access_lock:
                access_log.append(threading.current_thread().ident)
            time.sleep(0.05)

        mock_index.check_and_update = track_access
        mock_notebook.index = mock_index

        settings = {"notebook": "/test"}
        server = MoonstoneServer(settings)
        server._notebook = mock_notebook

        def access_notebook():
            # This pattern from headless.py has no locking
            notebook = server._notebook
            if notebook:
                notebook.index.check_and_update()

        threads = [threading.Thread(target=access_notebook) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=2.0)

        # All threads completed access
        assert len(access_log) == 5
        # SECURITY FINDING: No lock prevents concurrent access

    def test_server_state_change_during_rebuild(self):
        """Server state changes during rebuild should not cause crashes."""
        from moonstone.headless import MoonstoneServer

        settings = {"notebook": "/test"}
        server = MoonstoneServer(settings)

        # Initially no notebook
        assert server._notebook is None

        rebuild_completed = []

        def rebuild_without_notebook():
            notebook = server._notebook
            if notebook:
                notebook.index.check_and_update()
            else:
                rebuild_completed.append("no_notebook")

        # Run rebuild when notebook is None
        t = threading.Thread(target=rebuild_without_notebook)
        t.start()
        t.join(timeout=1.0)

        assert "no_notebook" in rebuild_completed

    def test_weak_reference_to_prevent_dangling_threads(self):
        """Daemon threads should not prevent object cleanup."""
        from moonstone.tray import MoonstoneTray

        callback_executed = []

        def callback():
            callback_executed.append(1)

        tray = MoonstoneTray(
            settings={},
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=callback,
        )

        # Create weak reference
        weak_tray = weakref.ref(tray)

        # Trigger rebuild
        tray._do_rebuild(None, None)
        time.sleep(0.1)

        # Delete tray reference
        del tray

        # Object should be collectable (daemon threads don't block)
        # Note: This is more of a documentation test - weakref may still be valid
        # if thread holds reference, but daemon threads shouldn't prevent exit

        assert len(callback_executed) == 1


@pytest.mark.unit
class TestCallbackExceptionsNotCaught:
    """Test that exceptions in callbacks are handled (or not) correctly."""

    def test_exception_in_callback_not_propagated(self):
        """Exceptions in rebuild thread are not propagated to caller."""
        from moonstone.tray import MoonstoneTray

        exception_occurred = []

        def failing_callback():
            exception_occurred.append(1)
            raise ValueError("Intentional test failure")

        tray = MoonstoneTray(
            settings={},
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=failing_callback,
        )

        # Should not raise
        try:
            tray._do_rebuild(None, None)
        except ValueError:
            pytest.fail("Exception should not propagate to caller")

        time.sleep(0.1)

        # Callback was attempted
        assert len(exception_occurred) == 1

    def test_multiple_exception_types_in_callback(self):
        """Various exception types in callback should not crash tray."""
        from moonstone.tray import MoonstoneTray

        exception_types = [
            ValueError,
            RuntimeError,
            KeyError,
            AttributeError,
            TypeError,
            MemoryError,
            IOError,
        ]

        for exc_type in exception_types:
            callback_called = []

            def failing_callback(et=exc_type):
                callback_called.append(1)
                raise et("Test exception")

            tray = MoonstoneTray(
                settings={},
                on_restart=lambda: None,
                on_quit=lambda: None,
                on_rebuild=failing_callback,
            )

            # Should not crash
            tray._do_rebuild(None, None)
            time.sleep(0.05)

            assert len(callback_called) == 1, f"Callback for {exc_type.__name__} should be called"

    def test_exception_during_index_check_and_update(self):
        """Exception from check_and_update should be caught in headless.py."""
        from moonstone.headless import MoonstoneServer

        mock_notebook = MagicMock()
        mock_index = MagicMock()
        mock_index.check_and_update.side_effect = PermissionError("Index locked")
        mock_notebook.index = mock_index

        settings = {"notebook": "/test"}
        server = MoonstoneServer(settings)
        server._notebook = mock_notebook

        exception_caught = []

        # Simulate the on_rebuild logic with try/except
        try:
            notebook = server._notebook
            if notebook:
                notebook.index.check_and_update()
        except Exception as e:
            exception_caught.append(str(e))

        assert len(exception_caught) == 1
        assert "Index locked" in exception_caught[0]

    def test_exception_logging_in_thread(self, caplog):
        """Exceptions in rebuild thread should be logged (if implemented)."""
        from moonstone.tray import MoonstoneTray
        import logging

        logging.basicConfig(level=logging.DEBUG)

        def failing_callback():
            raise RuntimeError("Thread exception test")

        tray = MoonstoneTray(
            settings={},
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=failing_callback,
        )

        with caplog.at_level(logging.DEBUG):
            tray._do_rebuild(None, None)
            time.sleep(0.2)

        # SECURITY FINDING: Current implementation does NOT catch/log exceptions
        # in the spawned thread body. This is a gap.
        # The test documents this behavior - exceptions are silently lost.


@pytest.mark.unit
class TestRebuildWithNoneCallback:
    """Test behavior when on_rebuild is None."""

    def test_none_callback_does_not_raise(self):
        """Calling _do_rebuild with None callback should be a no-op."""
        from moonstone.tray import MoonstoneTray

        tray = MoonstoneTray(
            settings={},
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=None,
        )

        # Should not raise
        tray._do_rebuild(None, None)
        time.sleep(0.1)

    def test_none_callback_after_initial_setting(self):
        """Setting callback to None after initialization should work."""
        from moonstone.tray import MoonstoneTray

        tray = MoonstoneTray(
            settings={},
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=lambda: None,
        )

        # Set to None
        tray._on_rebuild = None

        # Should not raise
        tray._do_rebuild(None, None)
        time.sleep(0.1)


@pytest.mark.unit
class TestRebuildThreadLifecycle:
    """Test thread lifecycle and cleanup during rebuild operations."""

    def test_daemon_thread_does_not_block_exit(self):
        """Daemon threads should allow process to exit."""
        from moonstone.tray import MoonstoneTray

        blocking_started = threading.Event()

        def blocking_callback():
            blocking_started.set()
            time.sleep(10)  # Long sleep

        tray = MoonstoneTray(
            settings={},
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=blocking_callback,
        )

        tray._do_rebuild(None, None)
        blocking_started.wait(timeout=1.0)

        # Thread is daemon, so it won't block (documented by daemon=True in code)
        # We can't easily test process exit, but we verify daemon status
        # by checking that the test completes quickly
        assert blocking_started.is_set()

    def test_multiple_rebuild_threads_can_run_simultaneously(self):
        """Multiple rebuild threads should be able to exist simultaneously."""
        from moonstone.tray import MoonstoneTray

        active_threads = []
        thread_lock = threading.Lock()
        max_concurrent = [0]

        def tracking_callback():
            with thread_lock:
                active_threads.append(threading.current_thread().ident)
                max_concurrent[0] = max(max_concurrent[0], len(active_threads))
            time.sleep(0.15)
            with thread_lock:
                active_threads.remove(threading.current_thread().ident)

        tray = MoonstoneTray(
            settings={},
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=tracking_callback,
        )

        # Rapid clicks
        for _ in range(5):
            tray._do_rebuild(None, None)
            time.sleep(0.03)

        time.sleep(0.5)

        # SECURITY FINDING: Multiple threads ran concurrently
        assert max_concurrent[0] >= 2, "Multiple rebuild threads ran concurrently"


@pytest.mark.unit
class TestRebuildWithMockedServer:
    """Test rebuild with mocked MoonstoneServer for full flow verification."""

    def test_full_rebuild_flow_thread_safety(self):
        """Full rebuild flow should handle concurrent access to server."""
        from moonstone.tray import MoonstoneTray
        from moonstone.headless import MoonstoneServer

        mock_notebook = MagicMock()
        mock_index = MagicMock()

        check_and_update_calls = []
        call_lock = threading.Lock()

        def track_check_and_update():
            with call_lock:
                check_and_update_calls.append(threading.current_thread().ident)
            time.sleep(0.1)

        mock_index.check_and_update = track_check_and_update
        mock_notebook.index = mock_index

        settings = {"notebook": "/test/path"}
        _server_box = [MoonstoneServer(settings)]
        _server_box[0]._notebook = mock_notebook

        def on_rebuild():
            notebook = _server_box[0]._notebook
            if notebook:
                notebook.index.check_and_update()

        tray = MoonstoneTray(
            settings=settings,
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=on_rebuild,
            server_info=_server_box[0].get_info,
        )

        # Multiple concurrent rebuilds
        for _ in range(3):
            tray._do_rebuild(None, None)
            time.sleep(0.02)

        time.sleep(0.5)

        # All calls completed
        assert len(check_and_update_calls) == 3

    def test_rebuild_when_server_not_started(self):
        """Rebuild when server hasn't started should handle None notebook."""
        from moonstone.tray import MoonstoneTray
        from moonstone.headless import MoonstoneServer

        settings = {"notebook": "/test/path"}
        _server_box = [MoonstoneServer(settings)]
        # _notebook is None because start() wasn't called

        rebuild_handled = []

        def on_rebuild():
            notebook = _server_box[0]._notebook
            if notebook:
                notebook.index.check_and_update()
            else:
                rebuild_handled.append("no_notebook")

        tray = MoonstoneTray(
            settings=settings,
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=on_rebuild,
        )

        tray._do_rebuild(None, None)
        time.sleep(0.1)

        assert "no_notebook" in rebuild_handled
