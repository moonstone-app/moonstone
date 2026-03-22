# -*- coding: utf-8 -*-
"""API endpoint tests for binary file detection in get_page().

Tests the binary file handling in GET /api/page/<path> endpoint:
- Binary files (images, PDFs, etc.) return is_binary=True with metadata
- Text files return is_binary=False with content
- No UnicodeDecodeError is raised for binary files
"""

import os
import sys
import tempfile
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


@pytest.mark.api
class TestBinaryFileDetection:
    """Test binary file detection in get_page() API."""

    def _create_mock_page_with_source(self, name, content_bytes, is_binary_val, hascontent=True):
        """Helper to create a mock Page with configured source_file.is_binary()."""
        mock_page = Mock()
        mock_page.name = name
        mock_page.basename = name.split(":")[-1] if ":" in name else name
        mock_page.hascontent = hascontent
        mock_page.haschildren = False
        mock_page.readonly = False
        mock_page.get_title.return_value = name
        
        # Create mock source_file with is_binary() method
        mock_source = Mock()
        mock_source.is_binary.return_value = is_binary_val
        
        # Set path for file size detection
        if is_binary_val:
            # Create a temp file for binary files so os.path.getsize works
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.bin', delete=False) as f:
                f.write(content_bytes)
                temp_path = f.name
            mock_source.path = temp_path
        else:
            mock_source.path = None
        
        mock_page.source_file = mock_source
        mock_page.source = mock_source
        
        return mock_page

    def test_png_file_returns_is_binary_true(self, tmp_path):
        """PNG file should return is_binary=True with correct mime_type."""
        from moonstone.webbridge.api import NotebookAPI
        
        # Create a minimal PNG file (valid PNG header with null bytes)
        png_header = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
            0x00, 0x00, 0x00, 0x0D,  # IHDR chunk length (includes nulls)
            0x49, 0x48, 0x44, 0x52,  # "IHDR"
            0x00, 0x00, 0x00, 0x01,  # Width: 1
            0x00, 0x00, 0x00, 0x01,  # Height: 1
            0x08, 0x02,              # Bit depth: 8, Color type: RGB
            0x00, 0x00, 0x00,        # Compression, filter, interlace
        ])
        
        # Create a real notebook with a binary file
        notebook_dir = tmp_path / "test_notebook"
        notebook_dir.mkdir()
        (notebook_dir / "notebook.zim").write_text(
            "[Notebook]\nname=Test Notebook\nhome=Home\n"
        )
        
        # Create pages directory
        pages_dir = notebook_dir / "pages"
        pages_dir.mkdir()
        
        # Create the binary file as a "page" file
        image_path = pages_dir / "TestImage.png"
        image_path.write_bytes(png_header)
        
        # Now test the API
        from moonstone.notebook.notebook import Notebook
        from moonstone.notebook.page import Path, SourceFile
        
        notebook = Notebook(str(notebook_dir))
        
        # Create mock app
        mock_app = Mock()
        mock_app._current_page_name = None
        
        api = NotebookAPI(notebook, mock_app)
        
        # Create a page that points to our binary file
        # We need to mock get_page to return a page with the binary source
        original_get_page = notebook.get_page
        
        def mock_get_page(path):
            if isinstance(path, str):
                path = Path(path)
            
            # For the image file, create a page with binary source
            if "TestImage" in str(path.name):
                page = Mock()
                page.name = path.name
                page.basename = path.basename if hasattr(path, 'basename') else path.name
                page.hascontent = True
                page.haschildren = False
                page.readonly = False
                page.get_title.return_value = path.name
                
                # Create SourceFile for the binary file
                source = SourceFile(str(image_path))
                page.source_file = source
                page.source = source
                return page
            
            return original_get_page(path)
        
        with patch.object(notebook, 'get_page', side_effect=mock_get_page):
            status, headers, body = api.get_page("TestImage.png")
        
        assert status == 200
        assert body.get("is_binary") is True
        assert body.get("mime_type") == "image/png"
        assert body.get("file_size") == len(png_header)
        assert body.get("content") == ""  # No content for binary files
        assert body.get("exists") is True

    def test_pdf_file_returns_is_binary_true(self, tmp_path):
        """PDF file should return is_binary=True with correct mime_type."""
        from moonstone.webbridge.api import NotebookAPI
        from moonstone.notebook.notebook import Notebook
        from moonstone.notebook.page import Path, SourceFile
        
        # Create PDF content with null bytes
        pdf_content = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<\x00\x00\x00>>\nendobj\n"
        
        # Create notebook
        notebook_dir = tmp_path / "test_notebook"
        notebook_dir.mkdir()
        (notebook_dir / "notebook.zim").write_text(
            "[Notebook]\nname=Test Notebook\nhome=Home\n"
        )
        
        pages_dir = notebook_dir / "pages"
        pages_dir.mkdir()
        
        pdf_path = pages_dir / "TestDoc.pdf"
        pdf_path.write_bytes(pdf_content)
        
        notebook = Notebook(str(notebook_dir))
        mock_app = Mock()
        mock_app._current_page_name = None
        
        api = NotebookAPI(notebook, mock_app)
        
        original_get_page = notebook.get_page
        
        def mock_get_page(path):
            if isinstance(path, str):
                path = Path(path)
            
            if "TestDoc" in str(path.name):
                page = Mock()
                page.name = path.name
                page.basename = path.basename if hasattr(path, 'basename') else path.name
                page.hascontent = True
                page.haschildren = False
                page.readonly = False
                page.get_title.return_value = path.name
                
                source = SourceFile(str(pdf_path))
                page.source_file = source
                page.source = source
                return page
            
            return original_get_page(path)
        
        with patch.object(notebook, 'get_page', side_effect=mock_get_page):
            status, headers, body = api.get_page("TestDoc.pdf")
        
        assert status == 200
        assert body.get("is_binary") is True
        assert body.get("mime_type") == "application/pdf"
        assert body.get("file_size") == len(pdf_content)
        assert body.get("content") == ""
        assert body.get("exists") is True

    def test_text_file_returns_is_binary_false_with_content(self, tmp_path):
        """Text file (UTF-8 .md) should return is_binary=False with content."""
        from moonstone.webbridge.api import NotebookAPI
        from moonstone.notebook.notebook import Notebook
        from moonstone.notebook.page import Path
        
        # Create notebook with a text page
        notebook_dir = tmp_path / "test_notebook"
        notebook_dir.mkdir()
        (notebook_dir / "notebook.zim").write_text(
            "[Notebook]\nname=Test Notebook\nhome=Home\n"
        )
        
        notebook = Notebook(str(notebook_dir))
        
        # Create a text page
        path = Path("TestMarkdown")
        page = notebook.get_page(path)
        content = "# Test Page\n\nThis is **markdown** content.\n\n- Item 1\n- Item 2\n"
        page.parse("markdown", content)
        notebook.store_page(page)
        
        mock_app = Mock()
        mock_app._current_page_name = None
        
        api = NotebookAPI(notebook, mock_app)
        
        status, headers, body = api.get_page("TestMarkdown")
        
        assert status == 200
        # is_binary should NOT be True (either False or absent)
        assert body.get("is_binary") is not True
        assert body.get("exists") is True
        # Content should be present (not empty for text files)
        assert len(body.get("content", "")) > 0
        # Verify content contains expected text
        assert "Test Page" in body.get("content", "") or "TestMarkdown" in body.get("content", "")

    def test_empty_text_file_returns_is_binary_false_with_empty_content(self, tmp_path):
        """Empty text file should return is_binary=False with empty content."""
        from moonstone.webbridge.api import NotebookAPI
        from moonstone.notebook.notebook import Notebook
        from moonstone.notebook.page import Path
        
        # Create notebook with an empty text page
        notebook_dir = tmp_path / "test_notebook"
        notebook_dir.mkdir()
        (notebook_dir / "notebook.zim").write_text(
            "[Notebook]\nname=Test Notebook\nhome=Home\n"
        )
        
        notebook = Notebook(str(notebook_dir))
        
        # Create an empty page
        path = Path("EmptyPage")
        page = notebook.get_page(path)
        page.parse("wiki", "")  # Empty content
        notebook.store_page(page)
        
        mock_app = Mock()
        mock_app._current_page_name = None
        
        api = NotebookAPI(notebook, mock_app)
        
        status, headers, body = api.get_page("EmptyPage")
        
        assert status == 200
        # is_binary should NOT be True for empty text files
        assert body.get("is_binary") is not True
        # Empty content - but exists may be False since page.hascontent is False for empty
        # Actually, after parse() and store_page(), hascontent may be True with empty string
        # The key is: no is_binary=True
        assert body.get("content") == "" or body.get("exists") is False

    def test_no_unicode_decode_error_for_binary_files(self, tmp_path):
        """Binary files should not raise UnicodeDecodeError during get_page()."""
        from moonstone.webbridge.api import NotebookAPI
        from moonstone.notebook.notebook import Notebook
        from moonstone.notebook.page import Path, SourceFile
        
        # Create binary content with invalid UTF-8 sequences and null bytes
        # This simulates a file that would cause UnicodeDecodeError if read as text
        binary_content = bytes([
            0x89, 0x50, 0x4E, 0x47,          # Start of PNG-like header
            0x00, 0x00, 0x00, 0x0D,          # Null bytes
            0xFF, 0xFE, 0xFD, 0xFC,          # Invalid UTF-8 bytes
            0x80, 0x81, 0x82, 0x83,          # More invalid UTF-8
        ]) + (b'\x00' * 100)                  # Lots of null bytes
        
        notebook_dir = tmp_path / "test_notebook"
        notebook_dir.mkdir()
        (notebook_dir / "notebook.zim").write_text(
            "[Notebook]\nname=Test Notebook\nhome=Home\n"
        )
        
        pages_dir = notebook_dir / "pages"
        pages_dir.mkdir()
        
        binary_path = pages_dir / "BinaryFile.bin"
        binary_path.write_bytes(binary_content)
        
        notebook = Notebook(str(notebook_dir))
        mock_app = Mock()
        mock_app._current_page_name = None
        
        api = NotebookAPI(notebook, mock_app)
        
        original_get_page = notebook.get_page
        
        def mock_get_page(path):
            if isinstance(path, str):
                path = Path(path)
            
            if "BinaryFile" in str(path.name):
                page = Mock()
                page.name = path.name
                page.basename = path.basename if hasattr(path, 'basename') else path.name
                page.hascontent = True
                page.haschildren = False
                page.readonly = False
                page.get_title.return_value = path.name
                
                source = SourceFile(str(binary_path))
                page.source_file = source
                page.source = source
                return page
            
            return original_get_page(path)
        
        # This should NOT raise UnicodeDecodeError
        try:
            with patch.object(notebook, 'get_page', side_effect=mock_get_page):
                status, headers, body = api.get_page("BinaryFile.bin")
            
            # Should succeed without exception
            assert status == 200
            assert body.get("is_binary") is True
            assert body.get("content") == ""  # No content for binary files
        except UnicodeDecodeError as e:
            pytest.fail(f"UnicodeDecodeError was raised for binary file: {e}")


@pytest.mark.api
class TestBinaryFileMimeTypeDetection:
    """Test MIME type detection for various binary file types."""

    def _create_notebook_with_binary(self, tmp_path, filename, content):
        """Helper to create notebook with binary file."""
        from moonstone.webbridge.api import NotebookAPI
        from moonstone.notebook.notebook import Notebook
        from moonstone.notebook.page import Path, SourceFile
        
        notebook_dir = tmp_path / "test_notebook"
        notebook_dir.mkdir()
        (notebook_dir / "notebook.zim").write_text(
            "[Notebook]\nname=Test Notebook\nhome=Home\n"
        )
        
        pages_dir = notebook_dir / "pages"
        pages_dir.mkdir()
        
        file_path = pages_dir / filename
        file_path.write_bytes(content)
        
        notebook = Notebook(str(notebook_dir))
        mock_app = Mock()
        mock_app._current_page_name = None
        
        api = NotebookAPI(notebook, mock_app)
        
        return api, notebook, file_path
    
    def test_jpeg_mime_type_detection(self, tmp_path):
        """JPEG file should return correct MIME type."""
        # JPEG starts with FF D8 FF
        jpeg_content = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
        
        api, notebook, file_path = self._create_notebook_with_binary(
            tmp_path, "Photo.jpg", jpeg_content
        )
        
        from moonstone.notebook.page import Path, SourceFile
        
        original_get_page = notebook.get_page
        
        def mock_get_page(path):
            if isinstance(path, str):
                path = Path(path)
            if "Photo" in str(path.name):
                page = Mock()
                page.name = path.name
                page.basename = path.basename if hasattr(path, 'basename') else path.name
                page.hascontent = True
                page.haschildren = False
                page.get_title.return_value = path.name
                source = SourceFile(str(file_path))
                page.source_file = source
                page.source = source
                return page
            return original_get_page(path)
        
        with patch.object(notebook, 'get_page', side_effect=mock_get_page):
            status, _, body = api.get_page("Photo.jpg")
        
        assert status == 200
        assert body.get("is_binary") is True
        assert body.get("mime_type") in ("image/jpeg", "image/jpg")

    def test_gif_mime_type_detection(self, tmp_path):
        """GIF file should return correct MIME type."""
        # GIF89a header
        gif_content = b'GIF89a\x01\x00\x01\x00\x00\x00\x00;'
        
        api, notebook, file_path = self._create_notebook_with_binary(
            tmp_path, "Animation.gif", gif_content
        )
        
        from moonstone.notebook.page import Path, SourceFile
        
        original_get_page = notebook.get_page
        
        def mock_get_page(path):
            if isinstance(path, str):
                path = Path(path)
            if "Animation" in str(path.name):
                page = Mock()
                page.name = path.name
                page.basename = path.basename if hasattr(path, 'basename') else path.name
                page.hascontent = True
                page.haschildren = False
                page.get_title.return_value = path.name
                source = SourceFile(str(file_path))
                page.source_file = source
                page.source = source
                return page
            return original_get_page(path)
        
        with patch.object(notebook, 'get_page', side_effect=mock_get_page):
            status, _, body = api.get_page("Animation.gif")
        
        assert status == 200
        assert body.get("is_binary") is True
        assert body.get("mime_type") == "image/gif"

    def test_zip_mime_type_detection(self, tmp_path):
        """ZIP file should return correct MIME type."""
        # ZIP file starts with PK\x03\x04
        zip_content = b'PK\x03\x04\x14\x00\x00\x00\x08\x00'
        
        api, notebook, file_path = self._create_notebook_with_binary(
            tmp_path, "Archive.zip", zip_content
        )
        
        from moonstone.notebook.page import Path, SourceFile
        
        original_get_page = notebook.get_page
        
        def mock_get_page(path):
            if isinstance(path, str):
                path = Path(path)
            if "Archive" in str(path.name):
                page = Mock()
                page.name = path.name
                page.basename = path.basename if hasattr(path, 'basename') else path.name
                page.hascontent = True
                page.haschildren = False
                page.get_title.return_value = path.name
                source = SourceFile(str(file_path))
                page.source_file = source
                page.source = source
                return page
            return original_get_page(path)
        
        with patch.object(notebook, 'get_page', side_effect=mock_get_page):
            status, _, body = api.get_page("Archive.zip")
        
        assert status == 200
        assert body.get("is_binary") is True
        assert body.get("mime_type") in ("application/zip", "application/octet-stream")


@pytest.mark.api
class TestBinaryFileResponseStructure:
    """Test the structure of binary file API responses."""

    def test_binary_response_includes_required_fields(self, tmp_path):
        """Binary file response must include name, is_binary, mime_type, file_size."""
        from moonstone.webbridge.api import NotebookAPI
        from moonstone.notebook.notebook import Notebook
        from moonstone.notebook.page import Path, SourceFile
        
        # Create binary content
        content = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' + b'\x00' * 50
        
        notebook_dir = tmp_path / "test_notebook"
        notebook_dir.mkdir()
        (notebook_dir / "notebook.zim").write_text(
            "[Notebook]\nname=Test Notebook\nhome=Home\n"
        )
        
        pages_dir = notebook_dir / "pages"
        pages_dir.mkdir()
        
        file_path = pages_dir / "Binary.png"
        file_path.write_bytes(content)
        
        notebook = Notebook(str(notebook_dir))
        mock_app = Mock()
        mock_app._current_page_name = None
        
        api = NotebookAPI(notebook, mock_app)
        
        original_get_page = notebook.get_page
        
        def mock_get_page(path):
            if isinstance(path, str):
                path = Path(path)
            if "Binary" in str(path.name):
                page = Mock()
                page.name = path.name
                page.basename = path.basename if hasattr(path, 'basename') else path.name
                page.hascontent = True
                page.haschildren = False
                page.get_title.return_value = path.name
                source = SourceFile(str(file_path))
                page.source_file = source
                page.source = source
                return page
            return original_get_page(path)
        
        with patch.object(notebook, 'get_page', side_effect=mock_get_page):
            status, headers, body = api.get_page("Binary.png")
        
        assert status == 200
        # Required fields for binary response
        assert "name" in body
        assert "basename" in body
        assert "is_binary" in body
        assert "mime_type" in body
        assert "file_size" in body
        # Exact values
        assert body["is_binary"] is True
        assert isinstance(body["file_size"], int)
        assert body["file_size"] == len(content)
        assert isinstance(body["mime_type"], str)

    def test_binary_response_has_empty_content(self, tmp_path):
        """Binary file response should have empty content field."""
        from moonstone.webbridge.api import NotebookAPI
        from moonstone.notebook.notebook import Notebook
        from moonstone.notebook.page import Path, SourceFile
        
        content = b'\x00\x00\x00\x00binary data here'
        
        notebook_dir = tmp_path / "test_notebook"
        notebook_dir.mkdir()
        (notebook_dir / "notebook.zim").write_text(
            "[Notebook]\nname=Test Notebook\nhome=Home\n"
        )
        
        pages_dir = notebook_dir / "pages"
        pages_dir.mkdir()
        
        file_path = pages_dir / "Data.bin"
        file_path.write_bytes(content)
        
        notebook = Notebook(str(notebook_dir))
        mock_app = Mock()
        mock_app._current_page_name = None
        
        api = NotebookAPI(notebook, mock_app)
        
        original_get_page = notebook.get_page
        
        def mock_get_page(path):
            if isinstance(path, str):
                path = Path(path)
            if "Data" in str(path.name):
                page = Mock()
                page.name = path.name
                page.basename = path.basename if hasattr(path, 'basename') else path.name
                page.hascontent = True
                page.haschildren = False
                page.get_title.return_value = path.name
                source = SourceFile(str(file_path))
                page.source_file = source
                page.source = source
                return page
            return original_get_page(path)
        
        with patch.object(notebook, 'get_page', side_effect=mock_get_page):
            status, _, body = api.get_page("Data.bin")
        
        assert status == 200
        assert body.get("content") == ""


@pytest.mark.api
class TestTextFileNotDetectedAsBinary:
    """Test that text files are correctly identified as non-binary."""

    def test_markdown_file_not_binary(self, tmp_path):
        """Markdown file should NOT be detected as binary."""
        from moonstone.webbridge.api import NotebookAPI
        from moonstone.notebook.notebook import Notebook
        from moonstone.notebook.page import Path
        
        notebook_dir = tmp_path / "test_notebook"
        notebook_dir.mkdir()
        (notebook_dir / "notebook.zim").write_text(
            "[Notebook]\nname=Test Notebook\nhome=Home\n"
        )
        
        notebook = Notebook(str(notebook_dir))
        
        # Create markdown page
        path = Path("ReadMe")
        page = notebook.get_page(path)
        content = "# ReadMe\n\nThis is a readme file.\n\n- Point 1\n- Point 2\n"
        page.parse("markdown", content)
        notebook.store_page(page)
        
        mock_app = Mock()
        mock_app._current_page_name = None
        
        api = NotebookAPI(notebook, mock_app)
        
        status, _, body = api.get_page("ReadMe")
        
        assert status == 200
        # is_binary should not be True (may be absent or False)
        assert body.get("is_binary") is not True
        assert body.get("exists") is True
        assert len(body.get("content", "")) > 0

    def test_wiki_file_not_binary(self, tmp_path):
        """Wiki format file should NOT be detected as binary."""
        from moonstone.webbridge.api import NotebookAPI
        from moonstone.notebook.notebook import Notebook
        from moonstone.notebook.page import Path
        
        notebook_dir = tmp_path / "test_notebook"
        notebook_dir.mkdir()
        (notebook_dir / "notebook.zim").write_text(
            "[Notebook]\nname=Test Notebook\nhome=Home\n"
        )
        
        notebook = Notebook(str(notebook_dir))
        
        # Create wiki page
        path = Path("WikiPage")
        page = notebook.get_page(path)
        content = "= Wiki Page =\n\nContent here.\n\n[[Link|Other Page]]\n"
        page.parse("wiki", content)
        notebook.store_page(page)
        
        mock_app = Mock()
        mock_app._current_page_name = None
        
        api = NotebookAPI(notebook, mock_app)
        
        status, _, body = api.get_page("WikiPage")
        
        assert status == 200
        assert body.get("is_binary") is not True
        assert body.get("exists") is True

    def test_unicode_text_file_not_binary(self, tmp_path):
        """Unicode text file should NOT be detected as binary."""
        from moonstone.webbridge.api import NotebookAPI
        from moonstone.notebook.notebook import Notebook
        from moonstone.notebook.page import Path
        
        notebook_dir = tmp_path / "test_notebook"
        notebook_dir.mkdir()
        (notebook_dir / "notebook.zim").write_text(
            "[Notebook]\nname=Test Notebook\nhome=Home\n"
        )
        
        notebook = Notebook(str(notebook_dir))
        
        # Create page with unicode content
        path = Path("UnicodePage")
        page = notebook.get_page(path)
        content = "# Unicode Test \U0001F600 \u2764\ufe0f\n\nJapanese: \u3053\u3093\u306b\u3061\u306f\n"
        page.parse("markdown", content)
        notebook.store_page(page)
        
        mock_app = Mock()
        mock_app._current_page_name = None
        
        api = NotebookAPI(notebook, mock_app)
        
        status, _, body = api.get_page("UnicodePage")
        
        assert status == 200
        assert body.get("is_binary") is not True
        assert body.get("exists") is True


@pytest.mark.api
class TestBinaryFileAttachmentUrl:
    """Test attachment_url field in binary file get_page() responses."""

    def _create_notebook_with_binary_file(self, tmp_path, filename, content, page_name=None):
        """Helper to create a notebook with a binary file and return API, notebook, file_path."""
        from moonstone.webbridge.api import NotebookAPI
        from moonstone.notebook.notebook import Notebook
        from moonstone.notebook.page import Path, SourceFile
        
        notebook_dir = tmp_path / "test_notebook"
        notebook_dir.mkdir()
        (notebook_dir / "notebook.zim").write_text(
            "[Notebook]\nname=Test Notebook\nhome=Home\n"
        )
        
        pages_dir = notebook_dir / "pages"
        pages_dir.mkdir()
        
        file_path = pages_dir / filename
        file_path.write_bytes(content)
        
        notebook = Notebook(str(notebook_dir))
        mock_app = Mock()
        mock_app._current_page_name = None
        
        api = NotebookAPI(notebook, mock_app)
        
        return api, notebook, file_path, page_name or filename

    def test_binary_file_includes_attachment_url(self, tmp_path):
        """Binary file response must include attachment_url field."""
        import urllib.parse
        from moonstone.notebook.page import Path, SourceFile
        
        # Create binary content
        png_content = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' + b'\x00' * 50
        
        api, notebook, file_path, page_name = self._create_notebook_with_binary_file(
            tmp_path, "TestImage.png", png_content, "TestImage.png"
        )
        
        original_get_page = notebook.get_page
        
        def mock_get_page(path):
            if isinstance(path, str):
                path = Path(path)
            if "TestImage" in str(path.name):
                page = Mock()
                page.name = path.name
                page.basename = path.basename if hasattr(path, 'basename') else path.name
                page.hascontent = True
                page.haschildren = False
                page.readonly = False
                page.get_title.return_value = path.name
                source = SourceFile(str(file_path))
                page.source_file = source
                page.source = source
                return page
            return original_get_page(path)
        
        with patch.object(notebook, 'get_page', side_effect=mock_get_page):
            status, headers, body = api.get_page("TestImage.png")
        
        assert status == 200
        assert "attachment_url" in body, "Binary response must include attachment_url field"
        # Verify the URL format
        expected_url = "/api/page/%s/raw" % urllib.parse.quote("TestImage.png", safe='')
        assert body["attachment_url"] == expected_url

    def test_attachment_url_format_is_correct(self, tmp_path):
        """attachment_url must follow format /api/page/{encoded_path}/raw."""
        import urllib.parse
        from moonstone.notebook.page import Path, SourceFile
        
        content = b'\x89PNG\r\n\x1a\n' + b'\x00' * 20
        
        api, notebook, file_path, page_name = self._create_notebook_with_binary_file(
            tmp_path, "MyImage.png", content, "MyImage.png"
        )
        
        original_get_page = notebook.get_page
        
        def mock_get_page(path):
            if isinstance(path, str):
                path = Path(path)
            if "MyImage" in str(path.name):
                page = Mock()
                page.name = path.name
                page.basename = path.basename if hasattr(path, 'basename') else path.name
                page.hascontent = True
                page.haschildren = False
                page.readonly = False
                page.get_title.return_value = path.name
                source = SourceFile(str(file_path))
                page.source_file = source
                page.source = source
                return page
            return original_get_page(path)
        
        with patch.object(notebook, 'get_page', side_effect=mock_get_page):
            status, _, body = api.get_page("MyImage.png")
        
        assert status == 200
        # Verify exact URL format
        expected_encoded = urllib.parse.quote("MyImage.png", safe='')
        expected_url = "/api/page/%s/raw" % expected_encoded
        assert body["attachment_url"] == expected_url
        # Verify it starts with /api/page/ and ends with /raw
        assert body["attachment_url"].startswith("/api/page/")
        assert body["attachment_url"].endswith("/raw")

    def test_attachment_url_encoding_colon_character(self, tmp_path):
        """attachment_url must properly encode colons in page names."""
        import urllib.parse
        from moonstone.notebook.page import Path, SourceFile
        
        content = b'\x00\x00\x00\x00binary'
        
        api, notebook, file_path, page_name = self._create_notebook_with_binary_file(
            tmp_path, "Namespace_Page.bin", content, "Namespace:Page"
        )
        
        original_get_page = notebook.get_page
        
        def mock_get_page(path):
            if isinstance(path, str):
                path = Path(path)
            if "Namespace" in str(path.name):
                page = Mock()
                page.name = "Namespace:Page"
                page.basename = "Page"
                page.hascontent = True
                page.haschildren = False
                page.readonly = False
                page.get_title.return_value = "Namespace:Page"
                source = SourceFile(str(file_path))
                page.source_file = source
                page.source = source
                return page
            return original_get_page(path)
        
        with patch.object(notebook, 'get_page', side_effect=mock_get_page):
            status, _, body = api.get_page("Namespace:Page")
        
        assert status == 200
        # Colon should be URL-encoded
        expected_encoded = urllib.parse.quote("Namespace:Page", safe='')
        expected_url = "/api/page/%s/raw" % expected_encoded
        assert body["attachment_url"] == expected_url
        # Verify colon is encoded (not present as literal)
        assert ":" not in body["attachment_url"].split("/")[-2]  # The path segment should not contain literal colon

    def test_attachment_url_encoding_space_character(self, tmp_path):
        """attachment_url must properly encode spaces in page names."""
        import urllib.parse
        from moonstone.notebook.page import Path, SourceFile
        
        content = b'\x89PNG\r\n\x1a\n' + b'\x00' * 10
        
        api, notebook, file_path, page_name = self._create_notebook_with_binary_file(
            tmp_path, "My Image.png", content, "My Image.png"
        )
        
        original_get_page = notebook.get_page
        
        def mock_get_page(path):
            if isinstance(path, str):
                path = Path(path)
            if "My Image" in str(path.name):
                page = Mock()
                page.name = path.name
                page.basename = path.basename if hasattr(path, 'basename') else path.name
                page.hascontent = True
                page.haschildren = False
                page.readonly = False
                page.get_title.return_value = path.name
                source = SourceFile(str(file_path))
                page.source_file = source
                page.source = source
                return page
            return original_get_page(path)
        
        with patch.object(notebook, 'get_page', side_effect=mock_get_page):
            status, _, body = api.get_page("My Image.png")
        
        assert status == 200
        # Space should be URL-encoded as %20
        expected_encoded = urllib.parse.quote("My Image.png", safe='')
        expected_url = "/api/page/%s/raw" % expected_encoded
        assert body["attachment_url"] == expected_url
        # Space should not appear literally in URL path
        assert " " not in body["attachment_url"]

    def test_attachment_url_encoding_special_characters(self, tmp_path):
        """attachment_url must properly encode various special characters."""
        import urllib.parse
        from moonstone.notebook.page import Path, SourceFile
        
        content = b'\x00binary data'
        
        # Page name with multiple special characters
        special_name = "Test:File (1).png"
        
        api, notebook, file_path, page_name = self._create_notebook_with_binary_file(
            tmp_path, "TestFile_1.png", content, special_name
        )
        
        original_get_page = notebook.get_page
        
        def mock_get_page(path):
            if isinstance(path, str):
                path = Path(path)
            if "Test" in str(path.name):
                page = Mock()
                page.name = special_name
                page.basename = special_name.split(":")[-1] if ":" in special_name else special_name
                page.hascontent = True
                page.haschildren = False
                page.readonly = False
                page.get_title.return_value = special_name
                source = SourceFile(str(file_path))
                page.source_file = source
                page.source = source
                return page
            return original_get_page(path)
        
        with patch.object(notebook, 'get_page', side_effect=mock_get_page):
            status, _, body = api.get_page(special_name)
        
        assert status == 200
        expected_encoded = urllib.parse.quote(special_name, safe='')
        expected_url = "/api/page/%s/raw" % expected_encoded
        assert body["attachment_url"] == expected_url


@pytest.mark.api
class TestGetPageRawEndpoint:
    """Test get_page_raw() endpoint for serving raw binary content."""

    def _create_notebook_with_binary(self, tmp_path, filename, content):
        """Helper to create notebook with binary file."""
        from moonstone.webbridge.api import NotebookAPI
        from moonstone.notebook.notebook import Notebook
        from moonstone.notebook.page import Path, SourceFile
        
        notebook_dir = tmp_path / "test_notebook"
        notebook_dir.mkdir()
        (notebook_dir / "notebook.zim").write_text(
            "[Notebook]\nname=Test Notebook\nhome=Home\n"
        )
        
        pages_dir = notebook_dir / "pages"
        pages_dir.mkdir()
        
        file_path = pages_dir / filename
        file_path.write_bytes(content)
        
        notebook = Notebook(str(notebook_dir))
        mock_app = Mock()
        mock_app._current_page_name = None
        
        api = NotebookAPI(notebook, mock_app)
        
        return api, notebook, file_path

    def test_get_page_raw_returns_binary_content(self, tmp_path):
        """get_page_raw must return binary content as bytes."""
        from moonstone.notebook.page import Path, SourceFile
        
        # Create binary content
        png_content = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' + b'\x00' * 50
        
        api, notebook, file_path = self._create_notebook_with_binary(
            tmp_path, "TestImage.png", png_content
        )
        
        original_get_page = notebook.get_page
        
        def mock_get_page(path):
            if isinstance(path, str):
                path = Path(path)
            if "TestImage" in str(path.name):
                page = Mock()
                page.name = path.name
                page.basename = path.basename if hasattr(path, 'basename') else path.name
                page.hascontent = True
                page.haschildren = False
                page.readonly = False
                page.get_title.return_value = path.name
                source = SourceFile(str(file_path))
                page.source_file = source
                page.source = source
                return page
            return original_get_page(path)
        
        with patch.object(notebook, 'get_page', side_effect=mock_get_page):
            status, headers, body = api.get_page_raw("TestImage.png")
        
        assert status == 200
        assert isinstance(body, bytes), "get_page_raw must return bytes, not string"
        assert body == png_content, "Returned content must match original binary data"

    def test_get_page_raw_returns_correct_content_type_png(self, tmp_path):
        """get_page_raw must return correct Content-Type for PNG files."""
        from moonstone.notebook.page import Path, SourceFile
        
        png_content = b'\x89PNG\r\n\x1a\n' + b'\x00' * 20
        
        api, notebook, file_path = self._create_notebook_with_binary(
            tmp_path, "Image.png", png_content
        )
        
        original_get_page = notebook.get_page
        
        def mock_get_page(path):
            if isinstance(path, str):
                path = Path(path)
            if "Image" in str(path.name):
                page = Mock()
                page.name = path.name
                page.basename = path.basename if hasattr(path, 'basename') else path.name
                page.hascontent = True
                page.haschildren = False
                page.readonly = False
                page.get_title.return_value = path.name
                source = SourceFile(str(file_path))
                page.source_file = source
                page.source = source
                return page
            return original_get_page(path)
        
        with patch.object(notebook, 'get_page', side_effect=mock_get_page):
            status, headers, body = api.get_page_raw("Image.png")
        
        assert status == 200
        assert "Content-Type" in headers
        assert headers["Content-Type"] == "image/png"

    def test_get_page_raw_returns_correct_content_type_pdf(self, tmp_path):
        """get_page_raw must return correct Content-Type for PDF files."""
        from moonstone.notebook.page import Path, SourceFile
        
        pdf_content = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n"
        
        api, notebook, file_path = self._create_notebook_with_binary(
            tmp_path, "Document.pdf", pdf_content
        )
        
        original_get_page = notebook.get_page
        
        def mock_get_page(path):
            if isinstance(path, str):
                path = Path(path)
            if "Document" in str(path.name):
                page = Mock()
                page.name = path.name
                page.basename = path.basename if hasattr(path, 'basename') else path.name
                page.hascontent = True
                page.haschildren = False
                page.readonly = False
                page.get_title.return_value = path.name
                source = SourceFile(str(file_path))
                page.source_file = source
                page.source = source
                return page
            return original_get_page(path)
        
        with patch.object(notebook, 'get_page', side_effect=mock_get_page):
            status, headers, body = api.get_page_raw("Document.pdf")
        
        assert status == 200
        assert "Content-Type" in headers
        assert headers["Content-Type"] == "application/pdf"

    def test_get_page_raw_returns_correct_content_type_jpeg(self, tmp_path):
        """get_page_raw must return correct Content-Type for JPEG files."""
        from moonstone.notebook.page import Path, SourceFile
        
        jpeg_content = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
        
        api, notebook, file_path = self._create_notebook_with_binary(
            tmp_path, "Photo.jpg", jpeg_content
        )
        
        original_get_page = notebook.get_page
        
        def mock_get_page(path):
            if isinstance(path, str):
                path = Path(path)
            if "Photo" in str(path.name):
                page = Mock()
                page.name = path.name
                page.basename = path.basename if hasattr(path, 'basename') else path.name
                page.hascontent = True
                page.haschildren = False
                page.readonly = False
                page.get_title.return_value = path.name
                source = SourceFile(str(file_path))
                page.source_file = source
                page.source = source
                return page
            return original_get_page(path)
        
        with patch.object(notebook, 'get_page', side_effect=mock_get_page):
            status, headers, body = api.get_page_raw("Photo.jpg")
        
        assert status == 200
        assert "Content-Type" in headers
        assert headers["Content-Type"] in ("image/jpeg", "image/jpg")

    def test_get_page_raw_returns_404_for_nonexistent_page(self, tmp_path):
        """get_page_raw must return 404 for non-existent page."""
        from moonstone.webbridge.api import NotebookAPI
        from moonstone.notebook.notebook import Notebook
        
        notebook_dir = tmp_path / "test_notebook"
        notebook_dir.mkdir()
        (notebook_dir / "notebook.zim").write_text(
            "[Notebook]\nname=Test Notebook\nhome=Home\n"
        )
        
        notebook = Notebook(str(notebook_dir))
        mock_app = Mock()
        mock_app._current_page_name = None
        
        api = NotebookAPI(notebook, mock_app)
        
        status, headers, body = api.get_page_raw("NonExistentPage")
        
        assert status == 404
        assert "error" in body

    def test_get_page_raw_returns_404_for_page_without_source(self, tmp_path):
        """get_page_raw must return 404 for page without source file."""
        from moonstone.webbridge.api import NotebookAPI
        from moonstone.notebook.notebook import Notebook
        from moonstone.notebook.page import Path
        
        notebook_dir = tmp_path / "test_notebook"
        notebook_dir.mkdir()
        (notebook_dir / "notebook.zim").write_text(
            "[Notebook]\nname=Test Notebook\nhome=Home\n"
        )
        
        notebook = Notebook(str(notebook_dir))
        
        # Create a text page (not binary, has no source_file with path)
        path = Path("TextPage")
        page = notebook.get_page(path)
        page.parse("wiki", "Some content\n")
        notebook.store_page(page)
        
        mock_app = Mock()
        mock_app._current_page_name = None
        
        api = NotebookAPI(notebook, mock_app)
        
        # For a text page, get_page_raw should return 404 because there's no source file path
        # Actually, text pages DO have source files. Let's mock it to not have source
        original_get_page = notebook.get_page
        
        def mock_get_page_no_source(path):
            if isinstance(path, str):
                path = Path(path)
            if "TextPage" in str(path.name):
                page = Mock()
                page.name = path.name
                page.basename = path.basename if hasattr(path, 'basename') else path.name
                page.hascontent = True
                page.haschildren = False
                page.readonly = False
                page.get_title.return_value = path.name
                page.source_file = None
                page.source = None
                return page
            return original_get_page(path)
        
        with patch.object(notebook, 'get_page', side_effect=mock_get_page_no_source):
            status, headers, body = api.get_page_raw("TextPage")
        
        assert status == 404
        assert "error" in body

    def test_get_page_raw_content_type_octet_stream_for_unknown(self, tmp_path):
        """get_page_raw must return application/octet-stream for unknown file types."""
        from moonstone.notebook.page import Path, SourceFile
        
        # Binary content with truly unknown extension (mimetypes doesn't recognize .xyztest)
        binary_content = b'\x00\x01\x02\x03\x04\x05unknown binary'
        
        api, notebook, file_path = self._create_notebook_with_binary(
            tmp_path, "Data.xyztest", binary_content
        )
        
        original_get_page = notebook.get_page
        
        def mock_get_page(path):
            if isinstance(path, str):
                path = Path(path)
            if "Data" in str(path.name):
                page = Mock()
                page.name = path.name
                page.basename = path.basename if hasattr(path, 'basename') else path.name
                page.hascontent = True
                page.haschildren = False
                page.readonly = False
                page.get_title.return_value = path.name
                source = SourceFile(str(file_path))
                page.source_file = source
                page.source = source
                return page
            return original_get_page(path)
        
        with patch.object(notebook, 'get_page', side_effect=mock_get_page):
            status, headers, body = api.get_page_raw("Data.xyztest")
        
        assert status == 200
        assert "Content-Type" in headers
        assert headers["Content-Type"] == "application/octet-stream"

    def test_get_page_raw_exact_binary_content_match(self, tmp_path):
        """get_page_raw must return exact binary content without modification."""
        from moonstone.notebook.page import Path, SourceFile
        
        # Create specific binary content to verify exact match
        original_content = bytes(range(256))  # All possible byte values
        
        api, notebook, file_path = self._create_notebook_with_binary(
            tmp_path, "AllBytes.bin", original_content
        )
        
        original_get_page = notebook.get_page
        
        def mock_get_page(path):
            if isinstance(path, str):
                path = Path(path)
            if "AllBytes" in str(path.name):
                page = Mock()
                page.name = path.name
                page.basename = path.basename if hasattr(path, 'basename') else path.name
                page.hascontent = True
                page.haschildren = False
                page.readonly = False
                page.get_title.return_value = path.name
                source = SourceFile(str(file_path))
                page.source_file = source
                page.source = source
                return page
            return original_get_page(path)
        
        with patch.object(notebook, 'get_page', side_effect=mock_get_page):
            status, headers, body = api.get_page_raw("AllBytes.bin")
        
        assert status == 200
        assert body == original_content
        # Verify length matches
        assert len(body) == 256
