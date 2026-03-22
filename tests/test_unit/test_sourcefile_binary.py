# -*- coding: utf-8 -*-
"""Unit tests for SourceFile.is_binary() method.

Tests binary file detection using null-byte heuristic:
- Binary files (contain null bytes) return True
- Text files (no null bytes) return False
- Empty files return False
- Unreadable files return True (fail-safe)
"""

import os
import sys
import tempfile
import stat

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest

from moonstone.notebook.page import SourceFile


class TestIsBinaryBasic:
    """Test basic binary detection functionality."""

    def test_text_file_returns_false(self):
        """Plain UTF-8 text file should return False."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write("This is plain text content.\nLine 2 here.\n")
            temp_path = f.name
        
        try:
            sf = SourceFile(temp_path)
            assert sf.is_binary() is False
        finally:
            os.unlink(temp_path)

    def test_markdown_file_returns_false(self):
        """Markdown file should return False."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write("# Heading\n\nSome **markdown** content.\n")
            temp_path = f.name
        
        try:
            sf = SourceFile(temp_path)
            assert sf.is_binary() is False
        finally:
            os.unlink(temp_path)

    def test_binary_png_returns_true(self):
        """PNG file (binary) should return True."""
        # PNG magic bytes: 89 50 4E 47 0D 0A 1A 0A
        # followed by IHDR chunk which contains null bytes
        png_header = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
            0x00, 0x00, 0x00, 0x0D,  # IHDR chunk length (includes nulls)
            0x49, 0x48, 0x44, 0x52,  # "IHDR"
        ])
        
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.png', delete=False) as f:
            f.write(png_header)
            temp_path = f.name
        
        try:
            sf = SourceFile(temp_path)
            assert sf.is_binary() is True
        finally:
            os.unlink(temp_path)

    def test_binary_pdf_returns_true(self):
        """PDF file (binary) should return True."""
        # PDF starts with %PDF- but contains null bytes in content
        pdf_content = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<\x00\x00\x00>>\nendobj\n"
        
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.pdf', delete=False) as f:
            f.write(pdf_content)
            temp_path = f.name
        
        try:
            sf = SourceFile(temp_path)
            assert sf.is_binary() is True
        finally:
            os.unlink(temp_path)


class TestIsBinaryEmptyFiles:
    """Test empty file handling."""

    def test_empty_file_returns_false(self):
        """Empty file should return False (treated as text)."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.txt', delete=False) as f:
            # Write nothing - empty file
            temp_path = f.name
        
        try:
            sf = SourceFile(temp_path)
            assert sf.is_binary() is False
        finally:
            os.unlink(temp_path)

    def test_empty_binary_extension_returns_false(self):
        """Empty file with binary extension should still return False."""
        # Extension doesn't matter - we check content
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.bin', delete=False) as f:
            temp_path = f.name
        
        try:
            sf = SourceFile(temp_path)
            assert sf.is_binary() is False
        finally:
            os.unlink(temp_path)


class TestIsBinaryNullByteDetection:
    """Test null byte detection in various positions."""

    def test_null_at_start_returns_true(self):
        """File with null byte at start should return True."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.txt', delete=False) as f:
            f.write(b'\x00Hello World')
            temp_path = f.name
        
        try:
            sf = SourceFile(temp_path)
            assert sf.is_binary() is True
        finally:
            os.unlink(temp_path)

    def test_null_in_middle_returns_true(self):
        """File with null byte in middle should return True."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.dat', delete=False) as f:
            f.write(b'Some data here\x00more data')
            temp_path = f.name
        
        try:
            sf = SourceFile(temp_path)
            assert sf.is_binary() is True
        finally:
            os.unlink(temp_path)

    def test_null_at_end_returns_true(self):
        """File with null byte at end should return True."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.dat', delete=False) as f:
            f.write(b'Normal text content\x00')
            temp_path = f.name
        
        try:
            sf = SourceFile(temp_path)
            assert sf.is_binary() is True
        finally:
            os.unlink(temp_path)

    def test_null_at_8kb_boundary_excluded(self):
        """Null byte just past 8KB boundary - should return False (not read)."""
        # 8192 bytes = 8KB, null byte at position 8192 (just past the chunk)
        content = b'A' * 8192 + b'\x00'
        
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.dat', delete=False) as f:
            f.write(content)
            temp_path = f.name
        
        try:
            sf = SourceFile(temp_path)
            # The first 8KB doesn't contain null, so returns False
            assert sf.is_binary() is False
        finally:
            os.unlink(temp_path)

    def test_null_at_8kb_boundary_included(self):
        """Null byte at last position in 8KB chunk - should return True."""
        # Null byte at position 8191 (last byte of 8KB chunk)
        content = b'A' * 8191 + b'\x00'
        
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.dat', delete=False) as f:
            f.write(content)
            temp_path = f.name
        
        try:
            sf = SourceFile(temp_path)
            # The null byte is within the first 8KB
            assert sf.is_binary() is True
        finally:
            os.unlink(temp_path)


class TestIsBinaryNonExistent:
    """Test handling of non-existent and unreadable files."""

    def test_non_existent_file_returns_true(self):
        """Non-existent file should return True (fail-safe for OSError)."""
        sf = SourceFile('/non/existent/path/file.txt')
        assert sf.is_binary() is True

    def test_directory_path_returns_true(self):
        """Directory path (not a file) should return True (fail-safe)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            sf = SourceFile(temp_dir)
            # Opening directory for reading will raise OSError
            assert sf.is_binary() is True


class TestIsBinaryUnicodeContent:
    """Test handling of various text encodings and Unicode."""

    def test_utf8_with_bom_returns_false(self):
        """UTF-8 file with BOM should return False."""
        # UTF-8 BOM: EF BB BF
        content = b'\xef\xbb\xbfThis is UTF-8 with BOM'
        
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.txt', delete=False) as f:
            f.write(content)
            temp_path = f.name
        
        try:
            sf = SourceFile(temp_path)
            assert sf.is_binary() is False
        finally:
            os.unlink(temp_path)

    def test_unicode_emoji_returns_false(self):
        """Text file with emoji should return False."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write("Hello \U0001F600 World \u2764\ufe0f \u00e9\u00e8\u00ea")
            temp_path = f.name
        
        try:
            sf = SourceFile(temp_path)
            assert sf.is_binary() is False
        finally:
            os.unlink(temp_path)

    def test_japanese_text_returns_false(self):
        """Japanese text (UTF-8) should return False."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write("\u3053\u3093\u306b\u3061\u306f\u4e16\u754c")  # Hello World in Japanese
            temp_path = f.name
        
        try:
            sf = SourceFile(temp_path)
            assert sf.is_binary() is False
        finally:
            os.unlink(temp_path)


class TestIsBinaryLargeFiles:
    """Test handling of files around and at the 8KB boundary."""

    def test_large_text_file_returns_false(self):
        """Large text file without null bytes should return False."""
        # 16KB of plain text (no null bytes)
        content = b'Lorem ipsum ' * 1366  # ~16KB
        
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.txt', delete=False) as f:
            f.write(content)
            temp_path = f.name
        
        try:
            sf = SourceFile(temp_path)
            assert sf.is_binary() is False
        finally:
            os.unlink(temp_path)

    def test_exactly_8kb_text_returns_false(self):
        """Exactly 8KB text file should return False."""
        content = b'X' * 8192
        
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.txt', delete=False) as f:
            f.write(content)
            temp_path = f.name
        
        try:
            sf = SourceFile(temp_path)
            assert sf.is_binary() is False
        finally:
            os.unlink(temp_path)

    def test_exactly_8kb_binary_returns_true(self):
        """Exactly 8KB binary file with null at position 0 should return True."""
        content = b'\x00' + b'X' * 8191
        
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.bin', delete=False) as f:
            f.write(content)
            temp_path = f.name
        
        try:
            sf = SourceFile(temp_path)
            assert sf.is_binary() is True
        finally:
            os.unlink(temp_path)


class TestIsBinarySpecialCases:
    """Test special edge cases."""

    def test_single_null_byte_returns_true(self):
        """File with only a null byte should return True."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.bin', delete=False) as f:
            f.write(b'\x00')
            temp_path = f.name
        
        try:
            sf = SourceFile(temp_path)
            assert sf.is_binary() is True
        finally:
            os.unlink(temp_path)

    def test_single_text_byte_returns_false(self):
        """File with only one text byte should return False."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.txt', delete=False) as f:
            f.write(b'X')
            temp_path = f.name
        
        try:
            sf = SourceFile(temp_path)
            assert sf.is_binary() is False
        finally:
            os.unlink(temp_path)

    def test_all_control_chars_no_null_returns_false(self):
        """File with only control chars (no null) should return False."""
        # Various control characters but no null byte
        content = bytes(range(1, 32))  # 0x01 to 0x1F (excluding 0x00)
        
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.dat', delete=False) as f:
            f.write(content)
            temp_path = f.name
        
        try:
            sf = SourceFile(temp_path)
            assert sf.is_binary() is False
        finally:
            os.unlink(temp_path)

    def test_newlines_only_returns_false(self):
        """File with only newlines should return False."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.txt', delete=False) as f:
            f.write(b'\n\r\n\n')
            temp_path = f.name
        
        try:
            sf = SourceFile(temp_path)
            assert sf.is_binary() is False
        finally:
            os.unlink(temp_path)


class TestIsBinaryReturnTypes:
    """Test that return types are exactly bool."""

    def test_returns_bool_true(self):
        """is_binary() should return bool True, not truthy value."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.bin', delete=False) as f:
            f.write(b'\x00data')
            temp_path = f.name
        
        try:
            sf = SourceFile(temp_path)
            result = sf.is_binary()
            assert result is True  # Exact bool, not just truthy
            assert type(result) is bool
        finally:
            os.unlink(temp_path)

    def test_returns_bool_false(self):
        """is_binary() should return bool False, not falsy value."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("text")
            temp_path = f.name
        
        try:
            sf = SourceFile(temp_path)
            result = sf.is_binary()
            assert result is False  # Exact bool, not just falsy
            assert type(result) is bool
        finally:
            os.unlink(temp_path)


class TestIsBinaryRepeatedCalls:
    """Test that repeated calls produce consistent results."""

    def test_repeated_calls_consistent(self):
        """Multiple calls to is_binary() should return same result."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.txt', delete=False) as f:
            f.write(b'test content')
            temp_path = f.name
        
        try:
            sf = SourceFile(temp_path)
            result1 = sf.is_binary()
            result2 = sf.is_binary()
            result3 = sf.is_binary()
            
            assert result1 is False
            assert result2 is False
            assert result3 is False
        finally:
            os.unlink(temp_path)
