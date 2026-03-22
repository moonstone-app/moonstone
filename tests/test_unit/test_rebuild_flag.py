# -*- coding: utf-8 -*-
"""Unit tests for the --rebuild CLI flag in headless.py.

Tests the --rebuild flag behavior:
- Success: valid notebook path triggers rebuild, exits 0
- Error: missing notebook path exits 1
- Error: invalid notebook path exits 1
- Error: exception during rebuild exits 1
"""

import sys
import os
import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.unit
class TestRebuildFlagArgParsing:
    """Test cases for --rebuild argument parsing."""

    def test_rebuild_flag_is_false_by_default(self, monkeypatch):
        """Without --rebuild, args.rebuild should be False."""
        monkeypatch.setattr(sys, "argv", ["moonstone"])
        from moonstone.headless import parse_args
        
        args = parse_args()
        assert args.rebuild is False

    def test_rebuild_flag_is_true_when_provided(self, monkeypatch):
        """With --rebuild, args.rebuild should be True."""
        monkeypatch.setattr(sys, "argv", ["moonstone", "--rebuild", "/tmp/notebook"])
        from moonstone.headless import parse_args
        
        args = parse_args()
        assert args.rebuild is True

    def test_rebuild_flag_with_notebook_positional(self, monkeypatch):
        """--rebuild flag works with positional notebook argument."""
        monkeypatch.setattr(sys, "argv", ["moonstone", "/some/notebook", "--rebuild"])
        from moonstone.headless import parse_args
        
        args = parse_args()
        assert args.rebuild is True
        assert args.notebook == "/some/notebook"


def _create_mock_args(notebook_path: str):
    """Create a mock args object for --rebuild testing."""
    mock_args = MagicMock()
    mock_args.rebuild = True
    mock_args.install_shortcut = False
    mock_args.uninstall_shortcut = False
    mock_args.no_tray = True  # Prevent tray from starting
    mock_args.notebook = notebook_path if notebook_path else None
    mock_args.port = 8090
    mock_args.host = "localhost"
    mock_args.token = ""
    mock_args.ws_port = None
    mock_args.applets_dir = None
    mock_args.services_dir = None
    mock_args.profile = "auto"
    mock_args.verbose = False
    mock_args.debug = False
    mock_args._explicit = {"notebook"} if notebook_path else set()
    return mock_args


def _run_main_with_rebuild(notebook_path: str, resolve_return=None, 
                           build_return=None, check_and_update_side_effect=None,
                           build_side_effect=None):
    """Helper to run main() with --rebuild flag and capture SystemExit.
    
    Returns the SystemExit exception or None if no exit occurred.
    """
    from moonstone.notebook.info import NotebookInfo
    
    mock_notebook_info = None
    if resolve_return is not None:
        mock_notebook_info = resolve_return if isinstance(resolve_return, NotebookInfo) else None
    
    mock_notebook = MagicMock()
    mock_index = MagicMock()
    if check_and_update_side_effect:
        mock_index.check_and_update = MagicMock(side_effect=check_and_update_side_effect)
    else:
        mock_index.check_and_update = MagicMock()
    mock_notebook.index = mock_index
    
    settings_dict = {"notebook": notebook_path} if notebook_path else {"notebook": ""}
    mock_args = _create_mock_args(notebook_path)
    
    build_return_value = (mock_notebook, None) if build_side_effect is None else None
    
    with patch("moonstone.headless.parse_args", return_value=mock_args):
        with patch("moonstone.settings.load", return_value=settings_dict):
            with patch("moonstone.settings.merge_cli_args", return_value=settings_dict):
                with patch("moonstone.notebook.resolve_notebook", return_value=mock_notebook_info):
                    if build_side_effect:
                        with patch("moonstone.notebook.build_notebook", side_effect=build_side_effect):
                            try:
                                from moonstone.headless import main
                                main()
                            except SystemExit as e:
                                return e, mock_index.check_and_update
                    else:
                        with patch("moonstone.notebook.build_notebook", return_value=build_return_value):
                            try:
                                from moonstone.headless import main
                                main()
                            except SystemExit as e:
                                return e, mock_index.check_and_update
    return None, mock_index.check_and_update


@pytest.mark.unit
class TestRebuildFlagSuccess:
    """Test cases for successful --rebuild execution."""

    def test_rebuild_calls_check_and_update_on_success(self, tmp_path):
        """--rebuild should call notebook.index.check_and_update() on success."""
        from moonstone.notebook.info import NotebookInfo
        
        notebook_dir = tmp_path / "test_notebook"
        notebook_dir.mkdir()
        
        mock_notebook_info = NotebookInfo(
            path=str(notebook_dir),
            name="Test Notebook",
            icon=None,
            config={},
        )
        
        exit_exc, check_and_update = _run_main_with_rebuild(
            notebook_path=str(notebook_dir),
            resolve_return=mock_notebook_info,
        )
        
        # Should exit with code 0
        assert exit_exc is not None, "main() should have called sys.exit()"
        assert exit_exc.code == 0, f"Expected exit code 0, got {exit_exc.code}"
        
        # check_and_update should have been called
        check_and_update.assert_called_once()

    def test_rebuild_exits_with_code_0_on_success(self, tmp_path):
        """--rebuild should exit with code 0 on successful rebuild."""
        from moonstone.notebook.info import NotebookInfo
        
        notebook_dir = tmp_path / "test_notebook"
        notebook_dir.mkdir()
        
        mock_notebook_info = NotebookInfo(
            path=str(notebook_dir),
            name="Test Notebook",
            icon=None,
            config={},
        )
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=str(notebook_dir),
            resolve_return=mock_notebook_info,
        )
        
        assert exit_exc is not None, "main() should have called sys.exit()"
        assert exit_exc.code == 0, f"Expected exit code 0, got {exit_exc.code}"

    def test_rebuild_with_valid_notebook_path(self, tmp_path):
        """--rebuild should succeed with a valid notebook path."""
        from moonstone.notebook.info import NotebookInfo
        
        notebook_dir = tmp_path / "valid_notebook"
        notebook_dir.mkdir()
        (notebook_dir / "notebook.zim").write_text(
            "[Notebook]\nname=Valid Notebook\nhome=Home\n"
        )
        
        mock_notebook_info = NotebookInfo(
            path=str(notebook_dir),
            name="Valid Notebook",
            icon=None,
            config={},
        )
        
        exit_exc, check_and_update = _run_main_with_rebuild(
            notebook_path=str(notebook_dir),
            resolve_return=mock_notebook_info,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 0
        check_and_update.assert_called_once()


@pytest.mark.unit
class TestRebuildFlagErrors:
    """Test cases for --rebuild error handling."""

    def test_rebuild_exits_1_when_no_notebook_specified(self, capsys):
        """--rebuild should exit with code 1 when no notebook path is set."""
        exit_exc, _ = _run_main_with_rebuild(notebook_path="")
        
        assert exit_exc is not None, "main() should have called sys.exit()"
        assert exit_exc.code == 1, f"Expected exit code 1 for missing notebook, got {exit_exc.code}"
        
        captured = capsys.readouterr()
        assert "ERROR" in captured.err
        assert "notebook" in captured.err.lower()

    def test_rebuild_exits_1_when_resolve_returns_none(self, tmp_path, capsys):
        """--rebuild should exit with code 1 when resolve_notebook returns None."""
        notebook_dir = tmp_path / "invalid_notebook"
        notebook_dir.mkdir()
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=str(notebook_dir),
            resolve_return=None,  # resolve_notebook returns None
        )
        
        assert exit_exc is not None, "main() should have called sys.exit()"
        assert exit_exc.code == 1, f"Expected exit code 1 for invalid notebook, got {exit_exc.code}"
        
        captured = capsys.readouterr()
        assert "ERROR" in captured.err
        assert "not found" in captured.err.lower()

    def test_rebuild_exits_1_on_exception_during_check_and_update(self, tmp_path, capsys):
        """--rebuild should exit with code 1 when check_and_update raises exception."""
        from moonstone.notebook.info import NotebookInfo
        
        notebook_dir = tmp_path / "test_notebook"
        notebook_dir.mkdir()
        
        mock_notebook_info = NotebookInfo(
            path=str(notebook_dir),
            name="Test Notebook",
            icon=None,
            config={},
        )
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=str(notebook_dir),
            resolve_return=mock_notebook_info,
            check_and_update_side_effect=RuntimeError("Database locked"),
        )
        
        assert exit_exc is not None, "main() should have called sys.exit()"
        assert exit_exc.code == 1, f"Expected exit code 1 for exception, got {exit_exc.code}"
        
        captured = capsys.readouterr()
        assert "ERROR" in captured.err
        assert "Database locked" in captured.err

    def test_rebuild_exits_1_on_exception_during_build_notebook(self, tmp_path, capsys):
        """--rebuild should exit with code 1 when build_notebook raises exception."""
        from moonstone.notebook.info import NotebookInfo
        
        notebook_dir = tmp_path / "test_notebook"
        notebook_dir.mkdir()
        
        mock_notebook_info = NotebookInfo(
            path=str(notebook_dir),
            name="Test Notebook",
            icon=None,
            config={},
        )
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=str(notebook_dir),
            resolve_return=mock_notebook_info,
            build_side_effect=OSError("Cannot build notebook"),
        )
        
        assert exit_exc is not None, "main() should have called sys.exit()"
        assert exit_exc.code == 1, f"Expected exit code 1 for exception, got {exit_exc.code}"
        
        captured = capsys.readouterr()
        assert "ERROR" in captured.err

    def test_rebuild_error_message_format(self, capsys):
        """--rebuild error messages should be formatted correctly."""
        exit_exc, _ = _run_main_with_rebuild(notebook_path="")
        
        captured = capsys.readouterr()
        assert "ERROR:" in captured.err, "Error should contain 'ERROR:'"


@pytest.mark.unit
class TestRebuildFlagOutput:
    """Test cases for --rebuild stdout/stderr output."""

    def test_rebuild_prints_success_message(self, tmp_path, capsys):
        """--rebuild should print success message on completion."""
        from moonstone.notebook.info import NotebookInfo
        
        notebook_dir = tmp_path / "test_notebook"
        notebook_dir.mkdir()
        
        mock_notebook_info = NotebookInfo(
            path=str(notebook_dir),
            name="Test Notebook",
            icon=None,
            config={},
        )
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=str(notebook_dir),
            resolve_return=mock_notebook_info,
        )
        
        assert exit_exc.code == 0
        
        captured = capsys.readouterr()
        assert "rebuilt successfully" in captured.out.lower()

    def test_rebuild_prints_error_to_stderr_not_stdout(self, capsys):
        """--rebuild errors should go to stderr, not stdout."""
        exit_exc, _ = _run_main_with_rebuild(notebook_path="")
        
        captured = capsys.readouterr()
        assert "ERROR" in captured.err
        assert "ERROR" not in captured.out


@pytest.mark.unit
class TestRebuildFlagEdgeCases:
    """Test cases for edge cases in --rebuild handling."""

    def test_rebuild_with_whitespace_only_path(self, capsys):
        """--rebuild with whitespace-only path should fail."""
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path="   ",
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1

    def test_rebuild_with_nonexistent_path(self, capsys):
        """--rebuild with non-existent path should fail."""
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path="/nonexistent/path/to/notebook",
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1
        
        captured = capsys.readouterr()
        assert "ERROR" in captured.err

    def test_rebuild_with_permission_error(self, tmp_path, capsys):
        """--rebuild should handle permission errors gracefully."""
        from moonstone.notebook.info import NotebookInfo
        
        notebook_dir = tmp_path / "test_notebook"
        notebook_dir.mkdir()
        
        mock_notebook_info = NotebookInfo(
            path=str(notebook_dir),
            name="Test Notebook",
            icon=None,
            config={},
        )
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=str(notebook_dir),
            resolve_return=mock_notebook_info,
            check_and_update_side_effect=PermissionError("Cannot write to index"),
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1
        
        captured = capsys.readouterr()
        assert "ERROR" in captured.err

    def test_rebuild_with_unicode_path(self, tmp_path, capsys):
        """--rebuild should handle Unicode notebook paths."""
        from moonstone.notebook.info import NotebookInfo
        
        # Create directory with Unicode characters
        notebook_dir = tmp_path / "тествbuch中文"
        notebook_dir.mkdir()
        
        mock_notebook_info = NotebookInfo(
            path=str(notebook_dir),
            name="Unicode Notebook",
            icon=None,
            config={},
        )
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=str(notebook_dir),
            resolve_return=mock_notebook_info,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 0


@pytest.mark.unit
class TestRebuildFlagDoesNotStartServer:
    """Test that --rebuild exits without starting the server."""

    def test_rebuild_does_not_call_server_start(self, tmp_path):
        """--rebuild should not start the HTTP server."""
        from moonstone.notebook.info import NotebookInfo
        
        notebook_dir = tmp_path / "test_notebook"
        notebook_dir.mkdir()
        
        mock_notebook_info = NotebookInfo(
            path=str(notebook_dir),
            name="Test Notebook",
            icon=None,
            config={},
        )
        
        mock_args = _create_mock_args(str(notebook_dir))
        mock_args.no_tray = False  # Even with tray enabled
        
        mock_notebook = MagicMock()
        mock_index = MagicMock()
        mock_index.check_and_update = MagicMock()
        mock_notebook.index = mock_index
        
        settings_dict = {"notebook": str(notebook_dir)}
        
        with patch("moonstone.headless.parse_args", return_value=mock_args):
            with patch("moonstone.settings.load", return_value=settings_dict):
                with patch("moonstone.settings.merge_cli_args", return_value=settings_dict):
                    with patch("moonstone.notebook.resolve_notebook", return_value=mock_notebook_info):
                        with patch("moonstone.notebook.build_notebook", return_value=(mock_notebook, None)):
                            with patch("moonstone.headless.MoonstoneServer") as mock_server_class:
                                try:
                                    from moonstone.headless import main
                                    main()
                                except SystemExit as e:
                                    exit_exc = e
        
        # MoonstoneServer should NOT be instantiated when --rebuild is set
        mock_server_class.assert_not_called()
        assert exit_exc.code == 0

    def test_rebuild_does_not_start_tray(self, tmp_path):
        """--rebuild should not start the system tray."""
        from moonstone.notebook.info import NotebookInfo
        
        notebook_dir = tmp_path / "test_notebook"
        notebook_dir.mkdir()
        
        mock_notebook_info = NotebookInfo(
            path=str(notebook_dir),
            name="Test Notebook",
            icon=None,
            config={},
        )
        
        mock_args = _create_mock_args(str(notebook_dir))
        mock_args.no_tray = False  # Even with tray enabled
        
        mock_notebook = MagicMock()
        mock_index = MagicMock()
        mock_index.check_and_update = MagicMock()
        mock_notebook.index = mock_index
        
        settings_dict = {"notebook": str(notebook_dir)}
        
        with patch("moonstone.headless.parse_args", return_value=mock_args):
            with patch("moonstone.settings.load", return_value=settings_dict):
                with patch("moonstone.settings.merge_cli_args", return_value=settings_dict):
                    with patch("moonstone.notebook.resolve_notebook", return_value=mock_notebook_info):
                        with patch("moonstone.notebook.build_notebook", return_value=(mock_notebook, None)):
                            with patch("moonstone.tray.MoonstoneTray") as mock_tray_class:
                                try:
                                    from moonstone.headless import main
                                    main()
                                except SystemExit as e:
                                    exit_exc = e
        
        # MoonstoneTray should NOT be instantiated when --rebuild is set
        mock_tray_class.assert_not_called()
        assert exit_exc.code == 0
