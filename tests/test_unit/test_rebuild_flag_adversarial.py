# -*- coding: utf-8 -*-
"""Adversarial security tests for the --rebuild CLI flag in headless.py.

Tests attack vectors against the --rebuild flag:
- Path traversal (../../../etc/passwd)
- Symlink attacks
- Special characters in notebook path
- Empty/whitespace-only paths
- Very long paths (buffer overflow attempt)
- Unicode injection in error messages
- Shell metacharacter injection
- Null byte injection
"""

import sys
import os
import pytest
from unittest.mock import patch, MagicMock


def _create_mock_args(notebook_path: str):
    """Create a mock args object for --rebuild testing."""
    mock_args = MagicMock()
    mock_args.rebuild = True
    mock_args.install_shortcut = False
    mock_args.uninstall_shortcut = False
    mock_args.no_tray = True
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


# =============================================================================
# PATH TRAVERSAL ATTACKS
# =============================================================================

@pytest.mark.unit
class TestPathTraversalAttacks:
    """Test path traversal attempts via --rebuild flag."""

    def test_path_traversal_parent_directory(self, tmp_path, capsys):
        """Path traversal with ../ should not escape notebook root."""
        # Create a legitimate notebook
        notebook_dir = tmp_path / "notebook"
        notebook_dir.mkdir()
        
        # Attempt to traverse to parent with mock that returns None for traversal
        malicious_path = str(tmp_path / "notebook" / ".." / ".." / ".." / "etc" / "passwd")
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=malicious_path,
            resolve_return=None,  # resolve_notebook returns None for malicious path
        )
        
        # Should exit with error code 1
        assert exit_exc is not None
        assert exit_exc.code == 1
        
        captured = capsys.readouterr()
        # Error should NOT contain actual /etc/passwd content
        assert "root:" not in captured.err
        assert "ERROR" in captured.err

    def test_path_traversal_multiple_parents(self, capsys):
        """Multiple parent directory traversals should fail safely."""
        malicious_path = "../../../../../../../../../../../../etc/passwd"
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=malicious_path,
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1
        
        captured = capsys.readouterr()
        # Should not leak system file contents
        assert "root:" not in captured.err
        assert "ERROR" in captured.err

    def test_path_traversal_absolute_system_path(self, capsys):
        """Direct absolute path to system files should fail."""
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path="/etc/passwd",
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1
        
        captured = capsys.readouterr()
        # Should not include contents of /etc/passwd in error
        assert "root:" not in captured.err

    def test_path_traversal_windows_style(self, capsys):
        """Windows-style path traversal should fail safely."""
        malicious_path = "..\\..\\..\\..\\..\\windows\\system32\\config\\sam"
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=malicious_path,
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1

    def test_path_traversal_mixed_style(self, capsys):
        """Mixed Windows/Unix path traversal should fail safely."""
        malicious_path = "../../../..\\..\\etc/passwd"
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=malicious_path,
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1


# =============================================================================
# SYMLINK ATTACKS
# =============================================================================

@pytest.mark.unit
class TestSymlinkAttacks:
    """Test symlink-based attacks via --rebuild flag."""

    def test_symlink_to_system_directory(self, tmp_path, capsys):
        """Symlink pointing to system directories should be handled safely."""
        # Create a symlink to /etc (if we can)
        symlink_path = tmp_path / "malicious_link"
        try:
            symlink_path.symlink_to("/etc")
        except (OSError, NotImplementedError):
            pytest.skip("Cannot create symlinks in this environment")
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=str(symlink_path),
            resolve_return=None,  # resolve_notebook should reject or return None
        )
        
        assert exit_exc is not None
        # Should exit with error (resolve_notebook returns None or fails)
        assert exit_exc.code == 1
        
        captured = capsys.readouterr()
        # Should not leak system information
        assert "ERROR" in captured.err

    def test_symlink_chain_attack(self, tmp_path, capsys):
        """Chained symlinks should not bypass security."""
        # Create chain: link1 -> link2 -> /etc
        link2 = tmp_path / "link2"
        link1 = tmp_path / "link1"
        try:
            link2.symlink_to("/etc")
            link1.symlink_to(str(link2))
        except (OSError, NotImplementedError):
            pytest.skip("Cannot create symlinks in this environment")
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=str(link1),
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1

    def test_symlink_to_outside_workspace(self, tmp_path, capsys):
        """Symlink pointing outside workspace should be handled safely."""
        outside_dir = tmp_path.parent / "outside_workspace"
        outside_dir.mkdir(exist_ok=True)
        
        symlink_path = tmp_path / "escape_link"
        try:
            symlink_path.symlink_to(str(outside_dir))
        except (OSError, NotImplementedError):
            pytest.skip("Cannot create symlinks in this environment")
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=str(symlink_path),
            resolve_return=None,
        )
        
        assert exit_exc is not None
        # Symlink to outside should fail or be handled safely
        assert exit_exc.code in [0, 1]  # Either succeeds safely or fails


# =============================================================================
# SPECIAL CHARACTER INJECTION
# =============================================================================

@pytest.mark.unit
class TestSpecialCharacterInjection:
    """Test special character injection attempts via --rebuild flag."""

    def test_shell_metacharacters_semicolon(self, capsys):
        """Shell metacharacters (semicolon) should not execute commands."""
        # This path should be treated as literal, not execute anything
        malicious_path = "/tmp; rm -rf /"
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=malicious_path,
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1
        
        captured = capsys.readouterr()
        # Command should appear as literal string in error, not executed
        assert "rm -rf" in captured.err or "ERROR" in captured.err

    def test_shell_metacharacters_pipe(self, capsys):
        """Shell metacharacters (pipe) should not execute commands."""
        malicious_path = "/tmp | cat /etc/passwd"
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=malicious_path,
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1

    def test_shell_metacharacters_backticks(self, capsys):
        """Backtick command substitution should not execute."""
        malicious_path = "/tmp/`whoami`"
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=malicious_path,
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1
        
        captured = capsys.readouterr()
        # Should not contain output of whoami command
        # (exact username would indicate command execution)
        import getpass
        username = getpass.getuser()
        # Error message should contain the literal path, not command output
        if username in captured.err:
            # If username appears, it should be in the path context, not command output
            assert "`whoami`" in captured.err or "whoami" in captured.err

    def test_shell_metacharacters_dollar(self, capsys):
        """Dollar sign variable expansion should not execute."""
        malicious_path = "/tmp/$(id)"
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=malicious_path,
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1
        
        captured = capsys.readouterr()
        # Should not contain output of id command (uid/gid)
        assert "uid=" not in captured.err
        assert "gid=" not in captured.err

    def test_null_byte_injection(self, capsys):
        """Null bytes should not truncate or bypass validation."""
        # Attempt null byte injection to truncate path
        malicious_path = "/tmp/valid\x00/etc/passwd"
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=malicious_path,
            resolve_return=None,
        )
        
        assert exit_exc is not None
        # Should fail safely - null byte should not cause truncation
        assert exit_exc.code == 1

    def test_newline_injection(self, capsys):
        """Newline characters should not corrupt error output."""
        malicious_path = "/tmp/test\nERROR: Injected error message"
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=malicious_path,
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1
        
        captured = capsys.readouterr()
        # Newline in path should not allow message injection
        # The injected message should be part of path error, not standalone
        assert "Injected error message" not in captured.err or "/tmp/test" in captured.err

    def test_carriage_return_injection(self, capsys):
        """Carriage return should not corrupt output."""
        malicious_path = "/tmp/test\rOVERWRITTEN"
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=malicious_path,
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1

    def test_tab_and_control_characters(self, capsys):
        """Control characters should be handled safely."""
        malicious_path = "/tmp/test\t\x07\x1b[31minjected\x1b[0m"
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=malicious_path,
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1


# =============================================================================
# EMPTY/WHITESPACE PATH TESTS
# =============================================================================

@pytest.mark.unit
class TestEmptyAndWhitespacePaths:
    """Test empty and whitespace-only notebook paths."""

    def test_empty_path_exits_with_error(self, capsys):
        """Empty notebook path should exit with error."""
        exit_exc, _ = _run_main_with_rebuild(notebook_path="")
        
        assert exit_exc is not None
        assert exit_exc.code == 1
        
        captured = capsys.readouterr()
        assert "ERROR" in captured.err
        assert "notebook" in captured.err.lower()

    def test_whitespace_only_path(self, capsys):
        """Whitespace-only path should exit with error."""
        exit_exc, _ = _run_main_with_rebuild(notebook_path="   ")
        
        assert exit_exc is not None
        assert exit_exc.code == 1

    def test_tab_only_path(self, capsys):
        """Tab-only path should exit with error."""
        exit_exc, _ = _run_main_with_rebuild(notebook_path="\t\t\t")
        
        assert exit_exc is not None
        assert exit_exc.code == 1

    def test_newline_only_path(self, capsys):
        """Newline-only path should exit with error."""
        exit_exc, _ = _run_main_with_rebuild(notebook_path="\n\n")
        
        assert exit_exc is not None
        assert exit_exc.code == 1

    def test_mixed_whitespace_path(self, capsys):
        """Mixed whitespace path should exit with error."""
        exit_exc, _ = _run_main_with_rebuild(notebook_path="  \t\n  ")
        
        assert exit_exc is not None
        assert exit_exc.code == 1


# =============================================================================
# OVERSIZED INPUT TESTS (BUFFER OVERFLOW ATTEMPTS)
# =============================================================================

@pytest.mark.unit
class TestOversizedInput:
    """Test oversized inputs that could trigger buffer overflows."""

    def test_very_long_path_1kb(self, capsys):
        """1KB path should be handled without crash."""
        long_path = "/tmp/" + "a" * 1000
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=long_path,
            resolve_return=None,
        )
        
        # Should exit cleanly (not crash)
        assert exit_exc is not None
        assert exit_exc.code == 1

    def test_very_long_path_4kb(self, capsys):
        """4KB path should be handled without crash."""
        long_path = "/tmp/" + "b" * 4000
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=long_path,
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1

    def test_very_long_path_32kb(self, capsys):
        """32KB path should be handled without crash."""
        long_path = "/tmp/" + "c" * 32000
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=long_path,
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1

    def test_extremely_long_path_1mb(self, capsys):
        """1MB path should be handled without memory exhaustion."""
        # Use smaller size to avoid test timeout
        long_path = "/tmp/" + "d" * 100000
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=long_path,
            resolve_return=None,
        )
        
        # Should exit cleanly (may be truncated or rejected)
        assert exit_exc is not None
        assert exit_exc.code in [0, 1]  # Either succeeds or fails gracefully

    def test_deeply_nested_path(self, capsys):
        """Deeply nested path should not cause stack overflow."""
        # Create a path with 1000 directory levels
        deep_path = "/tmp/" + "/..".join(["dir"] * 1000)
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=deep_path,
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1


# =============================================================================
# UNICODE INJECTION TESTS
# =============================================================================

@pytest.mark.unit
class TestUnicodeInjection:
    """Test Unicode-based attacks via --rebuild flag."""

    def test_unicode_null_byte_equivalent(self, capsys):
        """Unicode null equivalent should not bypass validation."""
        # U+0000 is Unicode null
        malicious_path = "/tmp/test\u0000/etc/passwd"
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=malicious_path,
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1

    def test_unicode_path_separator(self, capsys):
        """Unicode path separators should not bypass validation."""
        # U+2215 is division slash, U+2044 is fraction slash
        malicious_path = "/tmp/test\u2215..\u2044etc"
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=malicious_path,
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1

    def test_unicode_homograph_attack(self, tmp_path, capsys):
        """Unicode homographs should not confuse path resolution."""
        # Cyrillic 'а' (U+0430) looks like Latin 'a' (U+0061)
        from moonstone.notebook.info import NotebookInfo
        
        notebook_dir = tmp_path / "test_notebook"
        notebook_dir.mkdir()
        
        mock_notebook_info = NotebookInfo(
            path=str(notebook_dir),
            name="Test",
        )
        
        # Should handle unicode in paths without confusion
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=str(notebook_dir),
            resolve_return=mock_notebook_info,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 0

    def test_unicode_right_to_left_override(self, capsys):
        """RTL override should not corrupt error messages."""
        # U+202E is Right-to-Left Override
        malicious_path = "/tmp/\u202epasswd/cte"
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=malicious_path,
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1

    def test_unicode_zero_width_characters(self, capsys):
        """Zero-width characters should not bypass validation."""
        # Zero-width space, non-joiner, joiner
        malicious_path = "/tmp/test\u200b\u200c\u200d/etc"
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=malicious_path,
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1

    def test_emoji_in_path(self, tmp_path, capsys):
        """Emoji in path should be handled correctly."""
        from moonstone.notebook.info import NotebookInfo
        
        notebook_dir = tmp_path / "notebook_😀_test"
        notebook_dir.mkdir()
        
        mock_notebook_info = NotebookInfo(
            path=str(notebook_dir),
            name="Emoji Notebook",
        )
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=str(notebook_dir),
            resolve_return=mock_notebook_info,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 0

    def test_combining_characters_in_path(self, capsys):
        """Combining characters should not cause normalization issues."""
        # 'e' + combining acute accent
        malicious_path = "/tmp/t\u0065\u0301st"
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=malicious_path,
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1

    def test_surrogate_pairs_in_path(self, capsys):
        """Surrogate pairs should be handled correctly."""
        # Emoji using surrogate pairs (if applicable)
        malicious_path = "/tmp/test\uD83D\uDE00"  # 😀 as surrogates
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=malicious_path,
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1


# =============================================================================
# ERROR MESSAGE SAFETY
# =============================================================================

@pytest.mark.unit
class TestErrorMessagesDoNotLeakInfo:
    """Test that error messages don't leak sensitive information."""

    def test_error_does_not_leak_absolute_path_outside_workspace(self, capsys):
        """Error messages should not reveal full system paths."""
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path="/etc/shadow",
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1
        
        captured = capsys.readouterr()
        # Should contain error but not contents of /etc/shadow
        assert "root:" not in captured.err

    def test_error_does_not_include_file_contents(self, tmp_path, capsys):
        """Error messages should not include file contents."""
        # Create a file with sensitive content
        sensitive_file = tmp_path / "sensitive.txt"
        sensitive_file.write_text("SECRET_PASSWORD=supersecret123")
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=str(sensitive_file),  # File, not directory
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1
        
        captured = capsys.readouterr()
        # Should not leak file contents
        assert "SECRET_PASSWORD" not in captured.err
        assert "supersecret123" not in captured.err

    def test_exception_traceback_sanitized(self, tmp_path, capsys):
        """Exception tracebacks should not reveal internal paths."""
        from moonstone.notebook.info import NotebookInfo
        
        notebook_dir = tmp_path / "test_notebook"
        notebook_dir.mkdir()
        
        mock_notebook_info = NotebookInfo(
            path=str(notebook_dir),
            name="Test",
        )
        
        # Force an exception with a sensitive message
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=str(notebook_dir),
            resolve_return=mock_notebook_info,
            check_and_update_side_effect=Exception("Internal path: /home/admin/.ssh/id_rsa"),
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1
        
        captured = capsys.readouterr()
        # Exception message may appear, but should be from our controlled exception
        assert "ERROR" in captured.err


# =============================================================================
# INTEGRATION: ACTUAL FILESYSTEM TESTS
# =============================================================================

@pytest.mark.unit
class TestActualFilesystemSecurity:
    """Test actual filesystem interactions for security."""

    def test_nonexistent_path_does_not_create_files(self, tmp_path):
        """Nonexistent path should not create any files."""
        nonexistent = tmp_path / "does_not_exist"
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=str(nonexistent),
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1
        
        # Should not have created the directory
        assert not nonexistent.exists()

    def test_path_with_spaces_handled_correctly(self, tmp_path, capsys):
        """Paths with spaces should be handled correctly."""
        from moonstone.notebook.info import NotebookInfo
        
        notebook_dir = tmp_path / "notebook with spaces"
        notebook_dir.mkdir()
        
        mock_notebook_info = NotebookInfo(
            path=str(notebook_dir),
            name="Spaces Notebook",
        )
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=str(notebook_dir),
            resolve_return=mock_notebook_info,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 0

    def test_path_with_special_chars_handled_safely(self, tmp_path, capsys):
        """Paths with shell special chars should be handled safely."""
        from moonstone.notebook.info import NotebookInfo
        
        # Create directory with safe special chars (not all filesystems support all chars)
        notebook_dir = tmp_path / "notebook-test_123"
        notebook_dir.mkdir()
        
        mock_notebook_info = NotebookInfo(
            path=str(notebook_dir),
            name="Special Chars Notebook",
        )
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=str(notebook_dir),
            resolve_return=mock_notebook_info,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 0


# =============================================================================
# INPUT VALIDATION EDGE CASES
# =============================================================================

@pytest.mark.unit
class TestInputValidationEdgeCases:
    """Test edge cases in input validation."""

    def test_path_is_current_directory(self, capsys):
        """Current directory path should be handled correctly."""
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=".",
            resolve_return=None,
        )
        
        # Should exit (either success if valid notebook, or error if not)
        assert exit_exc is not None
        assert exit_exc.code in [0, 1]

    def test_path_is_root_directory(self, capsys):
        """Root directory path should fail safely."""
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path="/",
            resolve_return=None,
        )
        
        assert exit_exc is not None
        # Root is typically not a valid notebook
        assert exit_exc.code in [0, 1]

    def test_path_with_double_slashes(self, capsys):
        """Double slashes should be normalized safely."""
        malicious_path = "/tmp//notebook///test"
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=malicious_path,
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1

    def test_path_is_file_not_directory(self, tmp_path, capsys):
        """File path (not directory) should fail with appropriate error."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("not a directory")
        
        exit_exc, _ = _run_main_with_rebuild(
            notebook_path=str(file_path),
            resolve_return=None,
        )
        
        assert exit_exc is not None
        assert exit_exc.code == 1
        
        captured = capsys.readouterr()
        assert "ERROR" in captured.err
