# -*- coding: utf-8 -*-
"""Tests for MoonstoneProfile encoding with use_filename_spaces=True.

The MoonstoneProfile sets use_filename_spaces=True, which means:
- Underscores in filenames are preserved (not converted to spaces)
- Spaces in page names are preserved (not converted to underscores)
- This differs from the base profile default (False) which converts between them
"""

import os
import sys
import pytest

# Ensure moonstone is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from moonstone.notebook.layout import encode_filename, decode_filename
from moonstone.profiles.moonstone_profile import MoonstoneProfile


class TestDecodeFilenameWithSpaces:
    """Test decode_filename with use_spaces=True (MoonstoneProfile behavior)."""

    def test_underscore_preserved(self):
        """decode_filename("test_file", use_spaces=True) should return "test_file"."""
        result = decode_filename("test_file", use_spaces=True)
        assert result == "test_file", f"Expected 'test_file', got '{result}'"

    def test_multiple_underscores_preserved(self):
        """Multiple underscores should be preserved, not converted to spaces."""
        result = decode_filename("my_test_page_name", use_spaces=True)
        assert result == "my_test_page_name", f"Expected underscores preserved, got '{result}'"

    def test_consecutive_underscores_preserved(self):
        """Consecutive underscores should be preserved exactly."""
        result = decode_filename("test___file", use_spaces=True)
        assert result == "test___file", f"Expected 'test___file', got '{result}'"

    def test_leading_underscores_preserved(self):
        """Leading underscores should be preserved."""
        result = decode_filename("__init__", use_spaces=True)
        assert result == "__init__", f"Expected '__init__', got '{result}'"

    def test_trailing_underscores_preserved(self):
        """Trailing underscores should be preserved."""
        result = decode_filename("test__", use_spaces=True)
        assert result == "test__", f"Expected 'test__', got '{result}'"

    def test_slash_converts_to_colon(self):
        """Path separators should still convert to namespace separator."""
        result = decode_filename("folder/file_name", use_spaces=True)
        assert result == "folder:file_name", f"Expected 'folder:file_name', got '{result}'"

    def test_backslash_converts_to_colon(self):
        """Windows path separators should convert to namespace separator."""
        result = decode_filename("folder\\file_name", use_spaces=True)
        assert result == "folder:file_name", f"Expected 'folder:file_name', got '{result}'"

    def test_no_underscores_unchanged(self):
        """Names without underscores should be unchanged."""
        result = decode_filename("simple", use_spaces=True)
        assert result == "simple", f"Expected 'simple', got '{result}'"

    def test_mixed_separators_and_underscores(self):
        """Mix of path separators and underscores."""
        result = decode_filename("Projects/Sub_Folder/Page_Name", use_spaces=True)
        assert result == "Projects:Sub_Folder:Page_Name", f"Got '{result}'"

    def test_only_underscores_preserved(self):
        """Filename consisting only of underscores should be preserved."""
        result = decode_filename("_____", use_spaces=True)
        assert result == "_____", f"Expected '_____', got '{result}'"


class TestEncodeFilenameWithSpaces:
    """Test encode_filename with use_spaces=True (MoonstoneProfile behavior)."""

    def test_space_preserved(self):
        """encode_filename("test file", use_spaces=True) should return "test file"."""
        result = encode_filename("test file", use_spaces=True)
        assert result == "test file", f"Expected 'test file', got '{result}'"

    def test_multiple_spaces_preserved(self):
        """Multiple spaces should be preserved, not converted to underscores."""
        result = encode_filename("my test page name", use_spaces=True)
        assert result == "my test page name", f"Expected spaces preserved, got '{result}'"

    def test_consecutive_spaces_preserved(self):
        """Consecutive spaces should be preserved exactly."""
        result = encode_filename("test   file", use_spaces=True)
        assert result == "test   file", f"Expected 'test   file', got '{result}'"

    def test_colon_converts_to_slash(self):
        """Namespace separator should convert to path separator."""
        result = encode_filename("folder:file name", use_spaces=True)
        assert result == "folder/file name", f"Expected 'folder/file name', got '{result}'"

    def test_no_spaces_unchanged(self):
        """Names without spaces should be unchanged."""
        result = encode_filename("simple", use_spaces=True)
        assert result == "simple", f"Expected 'simple', got '{result}'"

    def test_underscore_in_page_name_preserved(self):
        """Underscores in page names should be preserved."""
        result = encode_filename("test_file_name", use_spaces=True)
        assert result == "test_file_name", f"Expected 'test_file_name', got '{result}'"

    def test_mixed_colons_and_spaces(self):
        """Mix of namespace separators and spaces."""
        result = encode_filename("Projects:Sub Folder:Page Name", use_spaces=True)
        assert result == "Projects/Sub Folder/Page Name", f"Got '{result}'"


class TestMoonstoneProfileFilenameMapping:
    """Test MoonstoneProfile's filename_to_page_name and page_name_to_filename."""

    @pytest.fixture
    def profile(self):
        """Create a MoonstoneProfile instance."""
        return MoonstoneProfile()

    def test_profile_use_filename_spaces_is_true(self, profile):
        """MoonstoneProfile should have use_filename_spaces=True."""
        assert profile.use_filename_spaces is True, \
            "MoonstoneProfile.use_filename_spaces should be True"

    def test_filename_to_page_name_preserves_underscores(self, profile):
        """Files with underscores should map to page names with underscores."""
        result = profile.filename_to_page_name("test_file_name")
        assert result == "test_file_name", f"Expected 'test_file_name', got '{result}'"

    def test_filename_to_page_name_with_path(self, profile):
        """Nested files with underscores should preserve underscores."""
        result = profile.filename_to_page_name("Projects/My_Project/Main_Page")
        assert result == "Projects:My_Project:Main_Page", f"Got '{result}'"

    def test_filename_to_page_name_no_underscores(self, profile):
        """Files without underscores should work normally."""
        result = profile.filename_to_page_name("simplepage")
        assert result == "simplepage", f"Expected 'simplepage', got '{result}'"

    def test_page_name_to_filename_preserves_spaces(self, profile):
        """Page names with spaces should preserve spaces in filename."""
        result = profile.page_name_to_filename("test page name")
        assert result == "test page name", f"Expected 'test page name', got '{result}'"

    def test_page_name_to_filename_preserves_underscores(self, profile):
        """Page names with underscores should preserve underscores in filename."""
        result = profile.page_name_to_filename("test_file_name")
        assert result == "test_file_name", f"Expected 'test_file_name', got '{result}'"

    def test_page_name_to_filename_with_namespace(self, profile):
        """Page names with namespace separators should convert to path."""
        result = profile.page_name_to_filename("Projects:My Project:Main Page")
        assert result == "Projects/My Project/Main Page", f"Got '{result}'"

    def test_page_name_to_filename_mixed(self, profile):
        """Page names with both spaces and underscores."""
        result = profile.page_name_to_filename("My_Project:Main Page")
        assert result == "My_Project/Main Page", f"Got '{result}'"


class TestLinkTargetResolution:
    """Test that wiki links with underscores resolve correctly."""

    @pytest.fixture
    def profile(self):
        """Create a MoonstoneProfile instance."""
        return MoonstoneProfile()

    def test_link_target_preserves_underscores(self, profile):
        """Link targets with underscores should be preserved."""
        result = profile.link_target_to_page_name("My_Page_Name")
        assert result == "My_Page_Name", f"Expected 'My_Page_Name', got '{result}'"

    def test_link_target_with_namespace(self, profile):
        """Link targets with namespace separators and underscores."""
        result = profile.link_target_to_page_name("Projects:My_Project")
        assert result == "Projects:My_Project", f"Got '{result}'"

    def test_link_target_preserves_underscores_with_spaces_mode(self, profile):
        """With use_filename_spaces=True, underscores in links are NOT converted to spaces."""
        # The profile has use_filename_spaces=True
        result = profile.link_target_to_page_name("test_file")
        # Should NOT convert underscores to spaces
        assert result == "test_file", f"Expected 'test_file', got '{result}'"

    def test_page_name_to_link_target_preserves_underscores(self, profile):
        """Converting page name to link target should preserve underscores."""
        result = profile.page_name_to_link_target("My_Page:Sub_Page")
        assert result == "My_Page:Sub_Page", f"Got '{result}'"


class TestRoundtripEncoding:
    """Test that encode/decode roundtrips are consistent with use_spaces=True."""

    def test_roundtrip_with_underscores(self):
        """Page names with underscores should roundtrip correctly."""
        original = "test_file_name"
        encoded = encode_filename(original, use_spaces=True)
        decoded = decode_filename(encoded, use_spaces=True)
        assert decoded == original, f"Roundtrip failed: {original} → {encoded} → {decoded}"

    def test_roundtrip_with_spaces(self):
        """Page names with spaces should roundtrip correctly."""
        original = "test page name"
        encoded = encode_filename(original, use_spaces=True)
        decoded = decode_filename(encoded, use_spaces=True)
        assert decoded == original, f"Roundtrip failed: {original} → {encoded} → {decoded}"

    def test_roundtrip_with_namespace_and_underscores(self):
        """Namespaced page names with underscores should roundtrip correctly."""
        original = "Projects:My_Project:Main_Page"
        encoded = encode_filename(original, use_spaces=True)
        decoded = decode_filename(encoded, use_spaces=True)
        assert decoded == original, f"Roundtrip failed: {original} → {encoded} → {decoded}"

    def test_roundtrip_with_namespace_and_spaces(self):
        """Namespaced page names with spaces should roundtrip correctly."""
        original = "Projects:My Project:Main Page"
        encoded = encode_filename(original, use_spaces=True)
        decoded = decode_filename(encoded, use_spaces=True)
        assert decoded == original, f"Roundtrip failed: {original} → {encoded} → {decoded}"

    def test_roundtrip_mixed(self):
        """Page names with both spaces and underscores should roundtrip correctly."""
        original = "My_Project:Main Page"
        encoded = encode_filename(original, use_spaces=True)
        decoded = decode_filename(encoded, use_spaces=True)
        assert decoded == original, f"Roundtrip failed: {original} → {encoded} → {decoded}"


class TestProfileVsDirectFunction:
    """Test that MoonstoneProfile methods match direct function calls with use_spaces=True."""

    @pytest.fixture
    def profile(self):
        """Create a MoonstoneProfile instance."""
        return MoonstoneProfile()

    def test_profile_filename_to_page_matches_decode(self, profile):
        """Profile.filename_to_page_name should match decode_filename(use_spaces=True)."""
        filename = "test_file_name"
        profile_result = profile.filename_to_page_name(filename)
        direct_result = decode_filename(filename, use_spaces=True)
        assert profile_result == direct_result, \
            f"Profile: {profile_result}, Direct: {direct_result}"

    def test_profile_page_to_filename_matches_encode(self, profile):
        """Profile.page_name_to_filename should match encode_filename(use_spaces=True)."""
        page_name = "test page name"
        profile_result = profile.page_name_to_filename(page_name)
        direct_result = encode_filename(page_name, use_spaces=True)
        assert profile_result == direct_result, \
            f"Profile: {profile_result}, Direct: {direct_result}"


class TestComparisonWithDefaultMode:
    """Compare MoonstoneProfile (use_spaces=True) vs default (use_spaces=False)."""

    def test_decode_underscore_behavior_differs(self):
        """With use_spaces=True, underscores are preserved; with False, they become spaces."""
        filename = "test_file_name"
        
        result_true = decode_filename(filename, use_spaces=True)
        result_false = decode_filename(filename, use_spaces=False)
        
        assert result_true == "test_file_name", f"use_spaces=True should preserve underscores"
        assert result_false == "test file name", f"use_spaces=False should convert to spaces"
        assert result_true != result_false, "Results should differ"

    def test_encode_space_behavior_differs(self):
        """With use_spaces=True, spaces are preserved; with False, they become underscores."""
        page_name = "test page name"
        
        result_true = encode_filename(page_name, use_spaces=True)
        result_false = encode_filename(page_name, use_spaces=False)
        
        assert result_true == "test page name", f"use_spaces=True should preserve spaces"
        assert result_false == "test_page_name", f"use_spaces=False should convert to underscores"
        assert result_true != result_false, "Results should differ"


class TestAdversarialEncoding:
    """Adversarial tests for edge cases with use_filename_spaces=True."""

    def test_empty_string(self):
        """Empty string should be handled gracefully."""
        result = decode_filename("", use_spaces=True)
        assert result == "", f"Expected empty string, got '{result}'"
        
        result = encode_filename("", use_spaces=True)
        assert result == "", f"Expected empty string, got '{result}'"

    def test_unicode_with_underscores(self):
        """Unicode characters with underscores should be preserved."""
        result = decode_filename("тест_файл", use_spaces=True)
        assert result == "тест_файл", f"Expected 'тест_файл', got '{result}'"

    def test_emoji_with_underscores(self):
        """Emoji with underscores should be preserved."""
        result = decode_filename("🎉_party", use_spaces=True)
        assert result == "🎉_party", f"Expected '🎉_party', got '{result}'"

    def test_japanese_with_underscores(self):
        """Japanese characters with underscores should be preserved."""
        result = decode_filename("テスト_ページ", use_spaces=True)
        assert result == "テスト_ページ", f"Expected 'テスト_ページ', got '{result}'"

    def test_percent_encoded_underscore(self):
        """Percent-encoded underscore should decode correctly."""
        # %5F is underscore
        result = decode_filename("test%5Ffile", use_spaces=True)
        assert result == "test_file", f"Expected 'test_file', got '{result}'"

    def test_all_underscores(self):
        """String of only underscores should be preserved."""
        result = decode_filename("___", use_spaces=True)
        assert result == "___", f"Expected '___', got '{result}'"

    def test_long_filename_with_underscores(self):
        """Long filenames with underscores should be handled correctly."""
        filename = "a" * 100 + "_" + "b" * 100
        result = decode_filename(filename, use_spaces=True)
        assert result == filename, f"Long filename should be preserved"
        assert len(result) == 201, f"Expected length 201, got {len(result)}"

    def test_special_chars_with_underscores(self):
        """Special characters mixed with underscores."""
        result = decode_filename("file_(1)_copy", use_spaces=True)
        assert result == "file_(1)_copy", f"Expected 'file_(1)_copy', got '{result}'"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
