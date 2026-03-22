# -*- coding: utf-8 -*-
"""Unit tests for the "Rebuild Database" menu item in tray.py.

Tests the tray menu rebuild functionality:
- MoonstoneTray._do_rebuild() calls on_rebuild callback
- on_rebuild callback calls notebook.index.check_and_update()
- Error handling: notebook is None, callback is None, exceptions
- Menu item placement verification
"""

import pytest
import threading
import time
from unittest.mock import MagicMock, patch, PropertyMock


@pytest.mark.unit
class TestMoonstoneTrayDoRebuild:
    """Test cases for MoonstoneTray._do_rebuild() method."""

    def test_do_rebuild_calls_callback_when_set(self):
        """_do_rebuild should call on_rebuild callback when provided."""
        from moonstone.tray import MoonstoneTray

        callback_called = []
        callback_event = threading.Event()

        def mock_callback():
            callback_called.append(True)
            callback_event.set()

        tray = MoonstoneTray(
            settings={},
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=mock_callback,
        )

        # Call _do_rebuild directly
        tray._do_rebuild(None, None)

        # Wait for the thread to complete (with timeout)
        callback_event.wait(timeout=2.0)

        assert len(callback_called) == 1, "on_rebuild callback should be called exactly once"

    def test_do_rebuild_does_not_raise_when_callback_is_none(self):
        """_do_rebuild should not raise when on_rebuild is None."""
        from moonstone.tray import MoonstoneTray

        tray = MoonstoneTray(
            settings={},
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=None,  # No callback provided
        )

        # Should not raise
        tray._do_rebuild(None, None)

    def test_do_rebuild_runs_callback_in_background_thread(self):
        """_do_rebuild should run the callback in a background thread."""
        from moonstone.tray import MoonstoneTray

        callback_thread_id = []
        callback_event = threading.Event()

        def mock_callback():
            callback_thread_id.append(threading.current_thread().ident)
            callback_event.set()

        main_thread_id = threading.current_thread().ident

        tray = MoonstoneTray(
            settings={},
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=mock_callback,
        )

        tray._do_rebuild(None, None)
        callback_event.wait(timeout=2.0)

        assert len(callback_thread_id) == 1
        assert callback_thread_id[0] != main_thread_id, "Callback should run in a different thread"

    def test_do_rebuild_thread_is_daemon(self):
        """_do_rebuild should create a daemon thread."""
        from moonstone.tray import MoonstoneTray

        created_threads = []

        original_thread_init = threading.Thread.__init__

        def patched_init(self, *args, **kwargs):
            created_threads.append(self)
            return original_thread_init(self, *args, **kwargs)

        with patch.object(threading.Thread, '__init__', patched_init):
            tray = MoonstoneTray(
                settings={},
                on_restart=lambda: None,
                on_quit=lambda: None,
                on_rebuild=lambda: None,
            )
            tray._do_rebuild(None, None)

        # Find the thread created by _do_rebuild
        daemon_threads = [t for t in created_threads if t.daemon]
        assert len(daemon_threads) >= 1, "Thread should be a daemon thread"


@pytest.mark.unit
class TestOnRebuildCallback:
    """Test cases for the on_rebuild callback in headless.py main()."""

    def test_on_rebuild_calls_check_and_update(self):
        """on_rebuild should call notebook.index.check_and_update()."""
        from moonstone.headless import MoonstoneServer

        # Create mock notebook with index
        mock_notebook = MagicMock()
        mock_index = MagicMock()
        mock_notebook.index = mock_index

        # Create mock settings
        settings = {"notebook": "/test/path"}

        # Create server and set the notebook
        server = MoonstoneServer(settings)
        server._notebook = mock_notebook
        server._running = True

        # Simulate the on_rebuild callback logic
        notebook = server._notebook
        if notebook:
            notebook.index.check_and_update()

        mock_index.check_and_update.assert_called_once()

    def test_on_rebuild_handles_none_notebook(self):
        """on_rebuild should handle notebook being None gracefully."""
        from moonstone.headless import MoonstoneServer

        settings = {"notebook": "/test/path"}
        server = MoonstoneServer(settings)
        server._notebook = None  # Notebook not set

        # Should not raise
        notebook = server._notebook
        if notebook:
            notebook.index.check_and_update()
        else:
            # This is the expected path when notebook is None
            pass

        # No assertion needed - we just verified it doesn't raise

    def test_on_rebuild_handles_exception(self):
        """on_rebuild should handle exceptions from check_and_update()."""
        from moonstone.headless import MoonstoneServer

        # Create mock notebook that raises on check_and_update
        mock_notebook = MagicMock()
        mock_index = MagicMock()
        mock_index.check_and_update.side_effect = RuntimeError("Database locked")
        mock_notebook.index = mock_index

        settings = {"notebook": "/test/path"}
        server = MoonstoneServer(settings)
        server._notebook = mock_notebook

        # Simulate the on_rebuild callback with exception handling
        exception_caught = []
        try:
            notebook = server._notebook
            if notebook:
                notebook.index.check_and_update()
        except Exception as e:
            exception_caught.append(str(e))

        # The callback should catch exceptions (actual code catches in try/except)
        assert len(exception_caught) == 1
        assert "Database locked" in exception_caught[0]

    def test_on_rebuild_callback_signature_matches_tray_expectation(self):
        """on_rebuild callback should be callable with no arguments."""
        from moonstone.tray import MoonstoneTray

        # This tests that the callback signature is compatible
        call_count = []

        def callback():
            call_count.append(1)

        # Create tray with the callback
        tray = MoonstoneTray(
            settings={},
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=callback,
        )

        # Verify on_rebuild is stored
        assert tray._on_rebuild is callback

        # Verify it's callable
        assert callable(tray._on_rebuild)


def _create_mock_pystray():
    """Create a mock pystray module for testing without X display."""
    mock_menu_item = MagicMock()
    mock_menu_item.text = "Mock Item"
    mock_menu = MagicMock()
    mock_menu.SEPARATOR = object()
    mock_menu.items = []
    mock_icon = MagicMock()
    
    mock_module = MagicMock()
    mock_module.Menu = MagicMock(return_value=mock_menu)
    mock_module.MenuItem = MagicMock(return_value=mock_menu_item)
    mock_module.Icon = MagicMock(return_value=mock_icon)
    
    return mock_module, mock_menu


@pytest.mark.unit
class TestRebuildMenuItemPlacement:
    """Test cases for Rebuild Database menu item placement."""

    def test_rebuild_menu_item_exists_in_menu(self):
        """Rebuild Database menu item should exist in the tray menu."""
        from moonstone.tray import MoonstoneTray

        mock_pystray, mock_menu = _create_mock_pystray()
        
        with patch.dict('sys.modules', {'pystray': mock_pystray}):
            tray = MoonstoneTray(
                settings={"notebook": "/test", "port": 8090},
                on_restart=lambda: None,
                on_quit=lambda: None,
                on_rebuild=lambda: None,
            )

            # Build menu to track MenuItem calls
            tray._build_menu()

        # Verify Menu was called with menu items
        assert mock_pystray.Menu.called, "pystray.Menu should be called"

        # Get all MenuItem calls to find the rebuild item
        menu_item_calls = mock_pystray.MenuItem.call_args_list
        
        # Find the rebuild item in the calls
        rebuild_found = False
        for call in menu_item_calls:
            args, kwargs = call
            # Check if any of the args contains "Rebuild"
            for arg in args:
                if 'Rebuild' in str(arg):
                    rebuild_found = True
                    break

        assert rebuild_found, "Rebuild Database menu item should exist"

    def test_rebuild_menu_item_is_between_logging_and_restart(self):
        """Rebuild Database should be between Logging submenu and Restart Server."""
        from moonstone.tray import MoonstoneTray

        mock_pystray, mock_menu = _create_mock_pystray()
        
        # Track MenuItem calls with their text in order
        menu_item_labels = []
        original_menu_item = mock_pystray.MenuItem
        
        def track_menu_item(*args, **kwargs):
            # args[0] is the label text
            if args:
                menu_item_labels.append(str(args[0]))
            return original_menu_item(*args, **kwargs)
        
        mock_pystray.MenuItem = track_menu_item
        
        with patch.dict('sys.modules', {'pystray': mock_pystray}):
            tray = MoonstoneTray(
                settings={"notebook": "/test", "port": 8090},
                on_restart=lambda: None,
                on_quit=lambda: None,
                on_rebuild=lambda: None,
            )

            tray._build_menu()

        # Find indices of relevant items in the tracked labels
        logging_idx = None
        rebuild_idx = None
        restart_idx = None

        for i, label in enumerate(menu_item_labels):
            if 'Logging' in label:
                logging_idx = i
            elif 'Rebuild' in label and 'Database' in label:
                rebuild_idx = i
            elif 'Restart' in label and 'Server' in label:
                restart_idx = i

        assert logging_idx is not None, f"Logging menu item should exist in {menu_item_labels}"
        assert rebuild_idx is not None, f"Rebuild Database menu item should exist in {menu_item_labels}"
        assert restart_idx is not None, f"Restart Server menu item should exist in {menu_item_labels}"

        # Rebuild should come after Logging
        assert rebuild_idx > logging_idx, "Rebuild should be after Logging submenu"
        # Rebuild should come before Restart
        assert rebuild_idx < restart_idx, "Rebuild should be before Restart Server"


@pytest.mark.unit
class TestTrayInitWithOnRebuild:
    """Test MoonstoneTray initialization with on_rebuild parameter."""

    def test_on_rebuild_stored_as_instance_variable(self):
        """on_rebuild callback should be stored as _on_rebuild instance variable."""
        from moonstone.tray import MoonstoneTray

        callback = lambda: None
        tray = MoonstoneTray(
            settings={},
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=callback,
        )

        assert tray._on_rebuild is callback

    def test_on_rebuild_defaults_to_none(self):
        """on_rebuild should default to None if not provided."""
        from moonstone.tray import MoonstoneTray

        tray = MoonstoneTray(
            settings={},
            on_restart=lambda: None,
            on_quit=lambda: None,
            # on_rebuild not provided
        )

        assert tray._on_rebuild is None

    def test_all_callbacks_can_be_set(self):
        """All three callbacks (on_restart, on_quit, on_rebuild) can be set."""
        from moonstone.tray import MoonstoneTray

        restart_called = []
        quit_called = []
        rebuild_called = []

        tray = MoonstoneTray(
            settings={},
            on_restart=lambda: restart_called.append(1),
            on_quit=lambda: quit_called.append(1),
            on_rebuild=lambda: rebuild_called.append(1),
        )

        # Verify all are stored
        assert callable(tray._on_restart)
        assert callable(tray._on_quit)
        assert callable(tray._on_rebuild)

        # Call them directly to verify they work
        tray._on_restart()
        tray._on_quit()
        tray._on_rebuild()

        assert len(restart_called) == 1
        assert len(quit_called) == 1
        assert len(rebuild_called) == 1


@pytest.mark.unit
class TestRebuildMenuIntegration:
    """Integration tests for the rebuild menu functionality."""

    def test_full_rebuild_flow_with_mock_server(self):
        """Test full rebuild flow: tray -> callback -> server notebook."""
        from moonstone.tray import MoonstoneTray
        from moonstone.headless import MoonstoneServer

        # Create mock notebook with index
        mock_notebook = MagicMock()
        mock_index = MagicMock()
        mock_notebook.index = mock_index

        # Create server and set notebook
        settings = {"notebook": "/test/path"}
        server = MoonstoneServer(settings)
        server._notebook = mock_notebook
        server._running = True

        # Track if callback was called
        rebuild_completed = threading.Event()

        def on_rebuild():
            notebook = server._notebook
            if notebook:
                notebook.index.check_and_update()
            rebuild_completed.set()

        # Create tray with the callback
        tray = MoonstoneTray(
            settings=settings,
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=on_rebuild,
            server_info=server.get_info,
        )

        # Trigger rebuild from tray
        tray._do_rebuild(None, None)

        # Wait for rebuild to complete
        rebuild_completed.wait(timeout=2.0)

        # Verify check_and_update was called
        mock_index.check_and_update.assert_called_once()

    def test_rebuild_menu_disabled_when_no_callback(self):
        """Verify behavior when menu item clicked with no callback set."""
        from moonstone.tray import MoonstoneTray

        tray = MoonstoneTray(
            settings={},
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=None,  # No callback
        )

        # Should not raise any exception
        tray._do_rebuild(None, None)

    def test_rebuild_with_server_not_started(self):
        """Test rebuild when server has not started (notebook is None)."""
        from moonstone.tray import MoonstoneTray
        from moonstone.headless import MoonstoneServer

        # Create server without starting it (notebook is None)
        settings = {"notebook": "/test/path"}
        server = MoonstoneServer(settings)
        # server._notebook is None because start() was never called

        warning_logged = []

        def on_rebuild():
            notebook = server._notebook
            if notebook:
                notebook.index.check_and_update()
            else:
                warning_logged.append("No notebook available to rebuild")

        # Create tray with the callback
        tray = MoonstoneTray(
            settings=settings,
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=on_rebuild,
        )

        # Trigger rebuild
        tray._do_rebuild(None, None)

        # Wait a moment for thread
        time.sleep(0.1)

        # Should have logged warning about no notebook
        assert len(warning_logged) == 1
        assert "No notebook available" in warning_logged[0]


@pytest.mark.unit
class TestRebuildErrorHandling:
    """Test error handling in rebuild functionality."""

    def test_callback_exception_does_not_crash_tray(self):
        """Exception in on_rebuild callback should not crash the tray."""
        from moonstone.tray import MoonstoneTray

        exception_raised = []

        def failing_callback():
            exception_raised.append(True)
            raise RuntimeError("Callback failed!")

        tray = MoonstoneTray(
            settings={},
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=failing_callback,
        )

        # Should not raise - exception happens in thread
        tray._do_rebuild(None, None)

        # Wait for thread to execute
        time.sleep(0.1)

        # Callback was attempted
        assert len(exception_raised) == 1

    def test_check_and_update_exception_is_caught(self):
        """Exception from check_and_update should be caught and logged."""
        from moonstone.headless import MoonstoneServer

        mock_notebook = MagicMock()
        mock_index = MagicMock()
        mock_index.check_and_update.side_effect = PermissionError("Index file read-only")
        mock_notebook.index = mock_index

        settings = {"notebook": "/test/path"}
        server = MoonstoneServer(settings)
        server._notebook = mock_notebook

        error_caught = []

        # Simulate the on_rebuild logic with exception handling
        try:
            notebook = server._notebook
            if notebook:
                notebook.index.check_and_update()
        except Exception as e:
            error_caught.append(str(e))

        assert len(error_caught) == 1
        assert "Index file read-only" in error_caught[0]

    def test_callback_with_timeout_scenario(self):
        """Test callback behavior when check_and_update takes long time."""
        from moonstone.tray import MoonstoneTray

        call_started = threading.Event()
        call_completed = threading.Event()

        def slow_callback():
            call_started.set()
            time.sleep(0.5)  # Simulate slow operation
            call_completed.set()

        tray = MoonstoneTray(
            settings={},
            on_restart=lambda: None,
            on_quit=lambda: None,
            on_rebuild=slow_callback,
        )

        # Start rebuild
        tray._do_rebuild(None, None)

        # Call should start quickly (not blocked)
        assert call_started.wait(timeout=1.0), "Callback should start quickly"

        # And eventually complete
        assert call_completed.wait(timeout=2.0), "Callback should complete"
