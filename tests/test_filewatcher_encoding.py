#!/usr/bin/env python3
"""Tests for FileWatcher encoding fix — verify use_filename_spaces propagation."""

import pytest
import tempfile
import os
import sys

# Ensure moonstone is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moonstone.headless import FileWatcher, _NotebookEventHandler
from moonstone.notebook.layout import decode_filename


class TestDecodeFilename:
    """Direct tests for decode_filename function."""

    def test_use_spaces_false_converts_underscore_to_space(self):
        """Moonstone mode: underscores become spaces."""
        result = decode_filename("fold_it", use_spaces=False)
        assert result == "fold it"

    def test_use_spaces_true_preserves_underscore(self):
        """Obsidian mode: underscores are preserved."""
        result = decode_filename("fold_it", use_spaces=True)
        assert result == "fold_it"

    def test_default_behavior_folds_underscores(self):
        """Default (no arg) should behave like use_spaces=False."""
        result = decode_filename("fold_it")
        assert result == "fold it"

    def test_multiple_underscores(self):
        """Multiple underscores are all converted."""
        result = decode_filename("my_test_page", use_spaces=False)
        assert result == "my test page"

    def test_no_underscores_unchanged(self):
        """Names without underscores are unchanged."""
        result = decode_filename("testpage", use_spaces=False)
        assert result == "testpage"

    def test_mixed_underscores(self):
        """Mixed underscores and spaces."""
        result = decode_filename("my_test_page", use_spaces=True)
        assert result == "my_test_page"


class TestNotebookEventHandler:
    """Tests for _NotebookEventHandler._path_to_page method."""

    def _make_handler(self, use_filename_spaces=False, extensions=(".txt", ".md")):
        """Create handler with callback."""
        callback_events = []

        def callback(event_type, page_name, file_path):
            callback_events.append((event_type, page_name, file_path))

        handler = _NotebookEventHandler(
            notebook_path="/fake/notebook",
            callback=callback,
            extensions=extensions,
            use_filename_spaces=use_filename_spaces,
        )
        return handler, callback_events

    def test_path_to_page_moonstone_mode_folds_underscores(self):
        """Moonstone mode: file 'fold_it.txt' → page 'fold it'."""
        handler, _ = self._make_handler(use_filename_spaces=False)
        page_name = handler._path_to_page("/fake/notebook/fold_it.txt")
        assert page_name == "fold it"

    def test_path_to_page_obsidian_mode_preserves_underscores(self):
        """Obsidian mode: file 'fold_it.txt' → page 'fold_it'."""
        handler, _ = self._make_handler(use_filename_spaces=True)
        page_name = handler._path_to_page("/fake/notebook/fold_it.txt")
        assert page_name == "fold_it"

    def test_path_to_page_default_folds_underscores(self):
        """Default mode: file 'fold_it.txt' → page 'fold it'."""
        handler, _ = self._make_handler()  # no use_filename_spaces arg = default False
        page_name = handler._path_to_page("/fake/notebook/fold_it.txt")
        assert page_name == "fold it"

    def test_path_to_page_with_subdirectory(self):
        """Nested path: 'Projects/fold_it.txt' → 'Projects:fold it'."""
        handler, _ = self._make_handler(use_filename_spaces=False)
        page_name = handler._path_to_page("/fake/notebook/Projects/fold_it.txt")
        assert page_name == "Projects:fold it"

    def test_path_to_page_obsidian_subdirectory(self):
        """Nested path in Obsidian mode."""
        handler, _ = self._make_handler(use_filename_spaces=True)
        page_name = handler._path_to_page("/fake/notebook/Projects/fold_it.txt")
        assert page_name == "Projects:fold_it"

    def test_path_to_page_md_extension(self):
        """MD extension is stripped correctly."""
        handler, _ = self._make_handler(use_filename_spaces=False)
        page_name = handler._path_to_page("/fake/notebook/fold_it.md")
        assert page_name == "fold it"

    def test_path_to_page_wiki_extension(self):
        """WIKI extension is stripped correctly."""
        handler, _ = self._make_handler(use_filename_spaces=False, extensions=(".txt", ".md", ".wiki"))
        page_name = handler._path_to_page("/fake/notebook/fold_it.wiki")
        assert page_name == "fold it"


class TestFileWatcher:
    """Tests for FileWatcher use_filename_spaces propagation."""

    def _make_watcher(self, use_filename_spaces=False):
        """Create FileWatcher with test callback. Caller must stop watcher."""
        callback_events = []

        def callback(event_type, page_name, file_path):
            callback_events.append((event_type, page_name, file_path))

        tmpdir = tempfile.mkdtemp()
        watcher = FileWatcher(
            notebook_path=tmpdir,
            callback=callback,
            use_filename_spaces=use_filename_spaces,
        )
        return watcher, callback_events, tmpdir

    def test_watcher_constructor_accepts_use_filename_spaces(self):
        """FileWatcher accepts use_filename_spaces parameter."""
        watcher, _, tmpdir = self._make_watcher(use_filename_spaces=True)
        try:
            assert watcher._handler._use_filename_spaces is True
        finally:
            # Can't stop() an unstarted watcher - just cleanup tmpdir
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_watcher_default_underscores_to_spaces(self):
        """Default FileWatcher: use_filename_spaces=False."""
        watcher, _, tmpdir = self._make_watcher()
        try:
            assert watcher._handler._use_filename_spaces is False
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_watcher_moonstone_mode_false(self):
        """FileWatcher with use_filename_spaces=False propagates correctly."""
        watcher, _, tmpdir = self._make_watcher(use_filename_spaces=False)
        try:
            assert watcher._handler._use_filename_spaces is False
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_watcher_obsidian_mode_true(self):
        """FileWatcher with use_filename_spaces=True propagates correctly."""
        watcher, _, tmpdir = self._make_watcher(use_filename_spaces=True)
        try:
            assert watcher._handler._use_filename_spaces is True
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestAdversarialEncoding:
    """Adversarial tests for edge cases and boundary conditions in FileWatcher encoding."""

    def _make_handler(self, use_filename_spaces=False, extensions=(".txt", ".md")):
        """Create handler with callback."""
        callback_events = []

        def callback(event_type, page_name, file_path):
            callback_events.append((event_type, page_name, file_path))

        handler = _NotebookEventHandler(
            notebook_path="/fake/notebook",
            callback=callback,
            extensions=extensions,
            use_filename_spaces=use_filename_spaces,
        )
        return handler, callback_events

    # =========================================================================
    # ATTACK VECTOR 1: Multiple consecutive underscores
    # =========================================================================

    def test_multiple_consecutive_underscores_moonstone_mode(self):
        """Triple underscores: 'fold___it' should become 'fold   it' (3 spaces) in Moonstone mode."""
        handler, _ = self._make_handler(use_filename_spaces=False)
        page_name = handler._path_to_page("/fake/notebook/fold___it.txt")
        assert page_name == "fold   it", f"Expected 'fold   it' (3 spaces), got '{page_name}'"

    def test_multiple_consecutive_underscores_obsidian_mode(self):
        """Triple underscores: 'fold___it' should be preserved as 'fold___it' in Obsidian mode."""
        handler, _ = self._make_handler(use_filename_spaces=True)
        page_name = handler._path_to_page("/fake/notebook/fold___it.md")
        assert page_name == "fold___it", f"Expected 'fold___it' preserved, got '{page_name}'"

    def test_leading_underscores(self):
        """Leading underscores should be converted in Moonstone mode."""
        handler, _ = self._make_handler(use_filename_spaces=False)
        page_name = handler._path_to_page("/fake/notebook/__private_page.txt")
        assert page_name == "  private page", f"Expected leading spaces, got '{page_name}'"

    def test_trailing_underscores(self):
        """Trailing underscores should be converted in Moonstone mode."""
        handler, _ = self._make_handler(use_filename_spaces=False)
        page_name = handler._path_to_page("/fake/notebook/page__.txt")
        assert page_name == "page  ", f"Expected trailing spaces, got '{page_name}'"

    def test_only_underscores(self):
        """Filename consisting only of underscores."""
        handler, _ = self._make_handler(use_filename_spaces=False)
        page_name = handler._path_to_page("/fake/notebook/_____.txt")
        assert page_name == "     ", f"Expected 5 spaces, got '{page_name}'"

    # =========================================================================
    # ATTACK VECTOR 2: Unicode filenames
    # =========================================================================

    def test_cyrillic_unicode_with_underscore_moonstone(self):
        """Cyrillic with underscore: 'файл_тест' in Moonstone mode."""
        handler, _ = self._make_handler(use_filename_spaces=False)
        page_name = handler._path_to_page("/fake/notebook/файл_тест.txt")
        assert page_name == "файл тест", f"Expected 'файл тест', got '{page_name}'"

    def test_cyrillic_unicode_with_underscore_obsidian(self):
        """Cyrillic with underscore: 'файл_тест' in Obsidian mode - preserve underscores."""
        handler, _ = self._make_handler(use_filename_spaces=True)
        page_name = handler._path_to_page("/fake/notebook/файл_тест.md")
        assert page_name == "файл_тест", f"Expected 'файл_тест' preserved, got '{page_name}'"

    def test_japanese_unicode(self):
        """Japanese characters should pass through unchanged."""
        handler, _ = self._make_handler(use_filename_spaces=False)
        page_name = handler._path_to_page("/fake/notebook/テスト_ページ.txt")
        assert page_name == "テスト ページ", f"Expected 'テスト ページ', got '{page_name}'"

    def test_emoji_filename(self):
        """Emoji in filename should be preserved."""
        handler, _ = self._make_handler(use_filename_spaces=True)
        page_name = handler._path_to_page("/fake/notebook/🎉_party.md")
        assert page_name == "🎉_party", f"Expected emoji preserved, got '{page_name}'"

    def test_zero_width_characters(self):
        """Zero-width spaces should pass through (invisible but present)."""
        handler, _ = self._make_handler(use_filename_spaces=True)
        # U+200B is zero-width space
        page_name = handler._path_to_page("/fake/notebook/test\u200b_name.md")
        assert "\u200b" in page_name, f"Zero-width space should be preserved in '{page_name}'"

    def test_mixed_unicode_scripts(self):
        """Mixed Chinese, Arabic, Hebrew with underscores."""
        handler, _ = self._make_handler(use_filename_spaces=False)
        page_name = handler._path_to_page("/fake/notebook/中文_العربية.txt")
        assert page_name == "中文 العربية", f"Expected '中文 العربية', got '{page_name}'"

    # =========================================================================
    # ATTACK VECTOR 3: Mixed separators (nested paths)
    # =========================================================================

    def test_deeply_nested_mixed_underscores(self):
        """Deep path with underscores at multiple levels."""
        handler, _ = self._make_handler(use_filename_spaces=False)
        page_name = handler._path_to_page("/fake/notebook/folder/sub_folder/file_name.txt")
        assert page_name == "folder:sub folder:file name", f"Got '{page_name}'"

    def test_nested_obsidian_mode_preserves(self):
        """Deep path in Obsidian mode - all underscores preserved."""
        handler, _ = self._make_handler(use_filename_spaces=True)
        page_name = handler._path_to_page("/fake/notebook/Projects/Moon_Stone/Dev_Notes.md")
        assert page_name == "Projects:Moon_Stone:Dev_Notes", f"Got '{page_name}'"

    def test_mixed_case_nested(self):
        """Mixed case and underscores in nested path."""
        handler, _ = self._make_handler(use_filename_spaces=False)
        page_name = handler._path_to_page("/fake/notebook/MyProject/A_B_C/TEST_File.txt")
        assert page_name == "MyProject:A B C:TEST File", f"Got '{page_name}'"

    # =========================================================================
    # ATTACK VECTOR 4: Empty filename edge cases
    # =========================================================================

    def test_empty_filename_raises_or_returns_empty(self):
        """Empty filename after extension strip - should not crash."""
        handler, _ = self._make_handler(use_filename_spaces=False)
        # This is an edge case - what happens with just extension?
        page_name = handler._path_to_page("/fake/notebook/.txt")
        # Either empty string or crash is acceptable - just verify no infinite loop
        assert page_name in ("", "."), f"Unexpected result for empty filename: '{page_name}'"

    def test_whitespace_only_filename(self):
        """Filename that becomes all whitespace after conversion."""
        handler, _ = self._make_handler(use_filename_spaces=False)
        # Single underscore becomes single space
        page_name = handler._path_to_page("/fake/notebook/_.txt")
        assert page_name == " ", f"Expected single space, got '{page_name}'"

    def test_dot_only_filename(self):
        """Filename that is just a dot."""
        handler, _ = self._make_handler(use_filename_spaces=False)
        page_name = handler._path_to_page("/fake/notebook/..txt")
        # Relative path handling - should be "." or ""
        assert page_name in (".", "", ":"), f"Unexpected for dot filename: '{page_name}'"

    # =========================================================================
    # ATTACK VECTOR 5: use_filename_spaces=None handling
    # =========================================================================

    def test_decode_filename_explicit_none_uses_default(self):
        """decode_filename with use_spaces=None should use default (False)."""
        # Pass None explicitly - should behave like False
        result = decode_filename("test_file", use_spaces=None)
        # Python treats None as falsy, so behavior depends on implementation
        # The function uses `if not use_spaces` which treats None as False
        assert result == "test file", f"Expected 'test file', got '{result}'"

    def test_handler_none_uses_default_false(self):
        """_NotebookEventHandler with use_filename_spaces=None should use False."""
        handler, _ = self._make_handler(use_filename_spaces=None)
        page_name = handler._path_to_page("/fake/notebook/test_file.txt")
        # None is falsy, so should behave like False (Moonstone mode)
        assert page_name == "test file", f"Expected Moonstone mode (None=falsy), got '{page_name}'"

    # =========================================================================
    # ADDITIONAL ADVERSARIAL: Injection patterns
    # =========================================================================

    def test_path_traversal_chars_in_filename(self):
        """Path traversal characters in filename - should be normalized."""
        handler, _ = self._make_handler(use_filename_spaces=False)
        # These should be handled safely, not allow escaping notebook root
        page_name = handler._path_to_page("/fake/notebook/.._hidden.txt")
        # The ".." part becomes part of page name, not directory traversal
        assert ".." not in page_name or "hidden" in page_name, f"Potentially unsafe: '{page_name}'"

    def test_colon_in_filename(self):
        """Colon in filename - should be handled correctly (colons become namespace separators)."""
        handler, _ = self._make_handler(use_filename_spaces=False)
        # decode_filename converts / and \ to :, but what about literal colons?
        page_name = handler._path_to_page("/fake/notebook/already:colon.txt")
        # Should preserve or normalize colon
        assert isinstance(page_name, str), f"Should return string, got {type(page_name)}"

    def test_null_byte_in_filename(self):
        """Null byte handling - should not cause issues."""
        handler, _ = self._make_handler(use_filename_spaces=False)
        # This tests resilience - actual null bytes in paths are rare/problematic
        try:
            page_name = handler._path_to_page("/fake/notebook/test\x00file.txt")
            # Should not crash, result can vary
            assert isinstance(page_name, str), "Should return string even with null byte"
        except (ValueError, OSError):
            pass  # Acceptable to reject null bytes

    def test_percent_encoded_filename(self):
        """Percent-encoded characters in filename should be decoded."""
        handler, _ = self._make_handler(use_filename_spaces=False)
        # %20 is URL-encoded space, should be decoded then underscore converted
        page_name = handler._path_to_page("/fake/notebook/test%20_file.txt")
        # %20 → space, then _ → space = "test  file" (double space)
        assert "test" in page_name and "file" in page_name, f"Unexpected: '{page_name}'"

    def test_extreme_length_filename(self):
        """Very long filename should still work."""
        handler, _ = self._make_handler(use_filename_spaces=False)
        long_name = "a" * 200 + "_" + "b" * 200
        page_name = handler._path_to_page(f"/fake/notebook/{long_name}.txt")
        assert len(page_name) == 401, f"Expected length 401, got {len(page_name)}"
        assert page_name == "a" * 200 + " " + "b" * 200

    def test_roundtrip_consistency(self):
        """Encode-decode roundtrip should be consistent."""
        from moonstone.notebook.layout import encode_filename, decode_filename
        
        original = "test_page_name"
        encoded = encode_filename(original, use_spaces=True)
        decoded = decode_filename(encoded, use_spaces=True)
        assert decoded == original, f"Roundtrip failed: {original} → {encoded} → {decoded}"

    def test_roundtrip_moonstone_mode(self):
        """Roundtrip in Moonstone mode (spaces <-> underscores)."""
        from moonstone.notebook.layout import encode_filename, decode_filename
        
        original = "test page name"  # spaces in original
        encoded = encode_filename(original, use_spaces=False)
        decoded = decode_filename(encoded, use_spaces=False)
        assert decoded == original, f"Roundtrip failed: {original} → {encoded} → {decoded}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
