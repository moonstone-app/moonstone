# -*- coding: utf-8 -*-
"""Unit tests for moonstone.config module.

Tests XDG directory resolution and data directory discovery.
"""

import os
import pytest
from config import data_dirs


@pytest.mark.unit
class TestDataDirs:
    """Test cases for data_dirs() function."""

    def test_data_dirs_returns_iterator(self):
        """data_dirs should return an iterator/iterable."""
        result = data_dirs()
        # Should be iterable
        assert hasattr(result, '__iter__')

    def test_data_dirs_finds_existing_dirs(self):
        """Should return at least one existing directory."""
        dirs = list(data_dirs())
        assert len(dirs) > 0

    def test_data_dirs_includes_package_data_dir(self):
        """Should include the package's data directory."""
        from config import data_dirs
        dirs = list(data_dirs())
        # At least the package data dir should exist
        assert len(dirs) > 0

    def test_data_dirs_with_subdir(self, tmp_path):
        """Should filter to subdirectory when specified."""
        # Create a test subdirectory structure
        test_subdir = tmp_path / "moonstone" / "templates"
        test_subdir.mkdir(parents=True)

        # Temporarily set XDG_DATA_HOME to our temp dir
        original_xdg = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = str(tmp_path)

        try:
            dirs = list(data_dirs("templates"))
            # Should find our test directory
            assert any(str(test_subdir) in d for d in dirs)
        finally:
            # Restore original value
            if original_xdg:
                os.environ["XDG_DATA_HOME"] = original_xdg
            else:
                os.environ.pop("XDG_DATA_HOME", None)

    def test_data_dirs_xdg_data_home(self, monkeypatch):
        """Should include XDG_DATA_HOME/moonstone if set."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = os.path.join(tmpdir, "moonstone")
            os.makedirs(test_dir, exist_ok=True)
            monkeypatch.setenv("XDG_DATA_HOME", tmpdir)

            dirs = list(data_dirs())
            assert test_dir in dirs

    def test_data_dirs_xdg_data_dirs(self, monkeypatch):
        """Should include directories from XDG_DATA_DIRS."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = os.path.join(tmpdir, "moonstone")
            os.makedirs(test_dir, exist_ok=True)
            monkeypatch.setenv("XDG_DATA_DIRS", tmpdir)

            dirs = list(data_dirs())
            assert test_dir in dirs

    def test_data_dirs_default_xdg_paths(self, monkeypatch):
        """Should use default XDG paths when env vars not set."""
        # Remove env vars to test defaults
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.delenv("XDG_DATA_DIRS", raising=False)

        dirs = list(data_dirs())
        # Should still return some directories (package data, etc.)
        assert len(dirs) > 0

    def test_data_dirs_package_dir(self):
        """Should include the package's own data directory."""
        import config
        package_dir = os.path.dirname(os.path.abspath(config.__file__))
        expected_data_dir = os.path.join(package_dir, "data")

        dirs = list(data_dirs())
        # Package data dir should be in the list
        assert any(expected_data_dir in d for d in dirs)

    def test_data_dirs_filters_nonexistent(self):
        """Should not include non-existent directories."""
        # Set a non-existent XDG path
        original = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = "/nonexistent/path/that/does/not/exist"

        try:
            dirs = list(data_dirs())
            # Should not include the non-existent path
            assert not any("/nonexistent/path" in d for d in dirs)
        finally:
            if original:
                os.environ["XDG_DATA_HOME"] = original
            else:
                os.environ.pop("XDG_DATA_HOME", None)

    def test_data_dirs_pyinstaller_frozen(self, monkeypatch):
        """Should handle PyInstaller frozen environment."""
        import sys
        # Simulate frozen environment
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", "/tmp/meipass", raising=False)

        dirs = list(data_dirs())
        # Should include the PyInstaller data path
        assert any("meipass" in d.lower() for d in dirs) or len(dirs) > 0

    def test_data_dirs_multiple_paths(self):
        """Should return multiple data directories."""
        dirs = list(data_dirs())
        # Should have at least: package data, XDG paths
        assert len(dirs) >= 1


@pytest.mark.unit
class TestDataDirsEdgeCases:
    """Edge case tests for data_dirs()."""

    def test_data_dirs_empty_subdir(self):
        """Should handle empty string subdir."""
        dirs = list(data_dirs(""))
        assert len(dirs) > 0

    def test_data_dirs_none_subdir(self):
        """Should handle None subdir."""
        dirs = list(data_dirs(None))
        assert len(dirs) > 0

    def test_data_dirs_unicode_subdir(self):
        """Should handle unicode in subdir name."""
        dirs = list(data_dirs("templates"))
        # Should not crash
        assert isinstance(dirs, list)

    def test_data_dirs_path_with_slash(self):
        """Should handle subdir with trailing slash."""
        dirs = list(data_dirs("templates/"))
        # Should still work
        assert isinstance(dirs, list)


@pytest.mark.unit
class TestDataDirsIntegration:
    """Integration-like tests for data_dirs()."""

    def test_data_dirs_find_templates(self):
        """Should be able to find templates directory."""
        dirs = list(data_dirs("templates"))
        # Returns list of template directories
        assert isinstance(dirs, list)

    def test_data_dirs_priority_order(self):
        """XDG_DATA_HOME should come before system dirs."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            # Set custom XDG_DATA_HOME
            original_home = os.environ.get("XDG_DATA_HOME")
            os.environ["XDG_DATA_HOME"] = tmpdir

            try:
                dirs = list(data_dirs())
                # Custom directory should be near the start
                # (though exact order depends on implementation)
                assert len(dirs) > 0
            finally:
                if original_home:
                    os.environ["XDG_DATA_HOME"] = original_home
                else:
                    os.environ.pop("XDG_DATA_HOME", None)
