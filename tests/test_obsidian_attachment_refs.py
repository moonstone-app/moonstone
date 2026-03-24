# -*- coding: utf-8 -*-
"""Tests for ObsidianProfile.extract_attachment_refs()"""

import pytest
from moonstone.profiles.obsidian import ObsidianProfile


class TestExtractAttachmentRefs:
    """Test extract_attachment_refs method for ObsidianProfile."""

    @pytest.fixture
    def profile(self):
        """Create an ObsidianProfile instance."""
        return ObsidianProfile()

    def test_markdown_image_with_subfolder_preserves_path(self, profile):
        """![alt](pix/lion.png) → extracts "pix/lion.png" (preserves subfolder path)."""
        text = "Here's a photo: ![alt](pix/lion.png) of a lion."
        refs = profile.extract_attachment_refs(text)
        assert "pix/lion.png" in refs
        assert "lion.png" not in refs  # Not flattened to basename

    def test_markdown_image_url_encoded_spacing(self, profile):
        """![alt](file%20name.png) → extracts "file name.png" (URL decoded)."""
        text = "![alt](file%20name.png)"
        refs = profile.extract_attachment_refs(text)
        assert "file name.png" in refs
        # Should NOT contain the URL-encoded version
        assert "file%20name.png" not in refs

    def test_obsidian_embed_extracts_filename(self, profile):
        """![[image.png]] → extracts "image.png" (Obsidian embed)."""
        text = "![[image.png]]"
        refs = profile.extract_attachment_refs(text)
        assert "image.png" in refs

    def test_external_url_not_extracted(self, profile):
        """![alt](https://example.com/img.png) → NOT extracted (external URL)."""
        text = "![alt](https://example.com/img.png)"
        refs = profile.extract_attachment_refs(text)
        assert "https://example.com/img.png" not in refs
        assert len(refs) == 0

    def test_data_uri_not_extracted(self, profile):
        """![alt](data:image/png;base64,...) → NOT extracted (data URI)."""
        text = "![alt](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==)"
        refs = profile.extract_attachment_refs(text)
        assert len(refs) == 0

    def test_obsidian_embed_with_subfolder_path(self, profile):
        """![[subfolder/image.png]] → extracts "image.png" (basename for embeds)."""
        text = "![[subfolder/image.png]]"
        refs = profile.extract_attachment_refs(text)
        # For embeds, currently uses basename only
        assert "image.png" in refs

    def test_markdown_image_no_path_uses_basename(self, profile):
        """![alt](photo.png) → extracts "photo.png" (basename for flat files)."""
        text = "![alt](photo.png)"
        refs = profile.extract_attachment_refs(text)
        assert "photo.png" in refs

    def test_multiple_images_mixed(self, profile):
        """Multiple image refs in same text."""
        text = "![local](pix/lion.png) and ![embed](image.png) and ![remote](https://example.com/photo.png)"
        refs = profile.extract_attachment_refs(text)
        assert "pix/lion.png" in refs
        assert "image.png" in refs
        # External URL should not be extracted
        assert "https://example.com/photo.png" not in refs
        assert len(refs) == 2

    def test_markdown_image_with_parent_directory(self, profile):
        """![alt](../assets/photo.png) → extracts "../assets/photo.png" (parent path preserved)."""
        text = "![alt](../assets/photo.png)"
        refs = profile.extract_attachment_refs(text)
        assert "../assets/photo.png" in refs

    def test_encoded_slash_not_decoded(self, profile):
        """![alt](folder%2Ffile.png) → %2F decoded to /, preserves path."""
        text = "![alt](folder%2Ffile.png)"
        refs = profile.extract_attachment_refs(text)
        # %2F decodes to /, so we get "folder/file.png"
        assert "folder/file.png" in refs
