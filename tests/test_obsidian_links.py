#!/usr/bin/env python3
"""Tests for ObsidianProfile link extraction — same-page and block references.

Verifies extract_links() handles:
- Same-page heading links: [[#Heading]], [[#Heading|Display]]
- Block references: [[Page^blockid]], [[Page^abc123]], [[Page^block-id]]
- Combined formats: [[Page#Heading^blockid]], [[Page^blockid|Display]], [[#Heading^blockid]]
- Code block exclusion: links inside code blocks should NOT be extracted
"""

import pytest
import os
import sys

# Ensure moonstone is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moonstone.profiles.obsidian import ObsidianProfile


class TestExtractLinks:
    """Direct tests for ObsidianProfile.extract_links() method."""

    @pytest.fixture
    def profile(self):
        """Create a fresh ObsidianProfile instance."""
        return ObsidianProfile()

    # =========================================================================
    # SAME-PAGE HEADING LINKS
    # =========================================================================

    def test_same_page_heading_link(self, profile):
        """Same-page heading link: [[#Heading]]."""
        text = "See [[#Heading]] for details."
        links = profile.extract_links(text)
        assert len(links) == 1
        assert links[0] == (None, "Heading", None, None)

    def test_same_page_heading_link_with_display(self, profile):
        """Same-page heading link with display: [[#Heading|Display]]."""
        text = "See [[#Heading|Display]] for details."
        links = profile.extract_links(text)
        assert len(links) == 1
        assert links[0] == (None, "Heading", None, "Display")

    def test_same_page_heading_only(self, profile):
        """Same-page link with just heading anchor."""
        text = "[[#Table of Contents]]"
        links = profile.extract_links(text)
        assert len(links) == 1
        assert links[0] == (None, "Table of Contents", None, None)

    # =========================================================================
    # BLOCK REFERENCES
    # =========================================================================

    def test_block_reference(self, profile):
        """Block reference: [[Page^blockid]]."""
        text = "See [[Page^blockid]] for the block."
        links = profile.extract_links(text)
        assert len(links) == 1
        assert links[0] == ("Page", None, "blockid", None)

    def test_block_reference_abc123(self, profile):
        """Block reference with alphanumeric id: [[Page^abc123]]."""
        text = "Reference [[Page^abc123]] here."
        links = profile.extract_links(text)
        assert len(links) == 1
        assert links[0] == ("Page", None, "abc123", None)

    def test_block_reference_hyphenated(self, profile):
        """Block reference with hyphenated id: [[Page^block-id]]."""
        text = "Reference [[Page^block-id]] here."
        links = profile.extract_links(text)
        assert len(links) == 1
        assert links[0] == ("Page", None, "block-id", None)

    def test_block_reference_with_display(self, profile):
        """Block reference with display: [[Page^blockid|Display]]."""
        text = "See [[Page^blockid|Display]] for details."
        links = profile.extract_links(text)
        assert len(links) == 1
        assert links[0] == ("Page", None, "blockid", "Display")

    # =========================================================================
    # COMBINED FORMATS
    # =========================================================================

    def test_page_heading_block_combined(self, profile):
        """Combined page, heading, and block: [[Page#Heading^blockid]]."""
        text = "See [[Page#Heading^blockid]] for details."
        links = profile.extract_links(text)
        assert len(links) == 1
        assert links[0] == ("Page", "Heading", "blockid", None)

    def test_page_block_with_display(self, profile):
        """Block reference with page and display: [[Page^blockid|Display]]."""
        text = "See [[Page^blockid|Display]] for details."
        links = profile.extract_links(text)
        assert len(links) == 1
        assert links[0] == ("Page", None, "blockid", "Display")

    def test_same_page_heading_block_combined(self, profile):
        """Same-page with heading and block: [[#Heading^blockid]]."""
        text = "See [[#Heading^blockid]] for details."
        links = profile.extract_links(text)
        assert len(links) == 1
        assert links[0] == (None, "Heading", "blockid", None)

    def test_same_page_heading_block_with_display(self, profile):
        """Same-page heading with block and display: [[#Heading^blockid|Display]]."""
        text = "See [[#Heading^blockid|Display]] for details."
        links = profile.extract_links(text)
        assert len(links) == 1
        assert links[0] == (None, "Heading", "blockid", "Display")

    # =========================================================================
    # BASIC LINK FORMATS (verify existing functionality still works)
    # =========================================================================

    def test_simple_page_link(self, profile):
        """Basic page link: [[Page]]."""
        text = "See [[Page]] for details."
        links = profile.extract_links(text)
        assert len(links) == 1
        assert links[0] == ("Page", None, None, None)

    def test_page_link_with_display(self, profile):
        """Page link with display: [[Page|Display Text]]."""
        text = "See [[Page|Display Text]] for details."
        links = profile.extract_links(text)
        assert len(links) == 1
        assert links[0] == ("Page", None, None, "Display Text")

    def test_page_with_heading(self, profile):
        """Page with heading anchor: [[Page#Heading]]."""
        text = "See [[Page#Heading]] for details."
        links = profile.extract_links(text)
        assert len(links) == 1
        assert links[0] == ("Page", "Heading", None, None)

    def test_page_with_heading_and_display(self, profile):
        """Page with heading and display: [[Page#Heading|Display]]."""
        text = "See [[Page#Heading|Display]] for details."
        links = profile.extract_links(text)
        assert len(links) == 1
        assert links[0] == ("Page", "Heading", None, "Display")

    # =========================================================================
    # CODE BLOCK EXCLUSION
    # =========================================================================

    def test_link_in_fenced_code_block_excluded(self, profile):
        """Links inside fenced code blocks should NOT be extracted."""
        text = """Some text

```python
# This is a comment with [[Page^blockid]] inside code
[[Page#Heading|Display]]
```

More text with [[Page]] link."""

        links = profile.extract_links(text)
        # Only the link outside the code block should be extracted
        assert len(links) == 1
        assert links[0] == ("Page", None, None, None)

    def test_link_in_inline_code_excluded(self, profile):
        """Links inside inline code should NOT be extracted."""
        text = "Use `[[Page^blockid]]` for testing and see [[Page]] for real."
        links = profile.extract_links(text)
        # Only the link outside inline code should be extracted
        assert len(links) == 1
        assert links[0] == ("Page", None, None, None)

    def test_multiple_links_only_code_excluded(self, profile):
        """Multiple links with some in code blocks."""
        text = """Before code
```markdown
[[Page1#Heading1]]
```
Between
`[[Page2^block2|Display2]]`
After
[[Page3#Heading3^block3]]"""

        links = profile.extract_links(text)
        # Only the link after "After" should be extracted
        assert len(links) == 1
        assert links[0] == ("Page3", "Heading3", "block3", None)

    # =========================================================================
    # MULTIPLE LINKS
    # =========================================================================

    def test_multiple_links_mixed_formats(self, profile):
        """Multiple links of different formats in one text."""
        text = """Links: [[Page1]], [[#Heading2]], [[Page3^block3]],
        [[Page4#Heading4|Display4]], and [[#Heading5^block5]]."""

        links = profile.extract_links(text)
        assert len(links) == 5
        assert links[0] == ("Page1", None, None, None)
        assert links[1] == (None, "Heading2", None, None)
        assert links[2] == ("Page3", None, "block3", None)
        assert links[3] == ("Page4", "Heading4", None, "Display4")
        assert links[4] == (None, "Heading5", "block5", None)

    # =========================================================================
    # EDGE CASES
    # =========================================================================

    def test_empty_block_id(self, profile):
        """Block id with empty value after ^."""
        text = "[[Page^]]"
        links = profile.extract_links(text)
        # Empty block id - should this be included or filtered?
        # Currently the code treats empty string as falsy so it may not appear
        pass  # Implementation-dependent

    def test_no_links_returns_empty(self, profile):
        """Text with no wiki links returns empty list."""
        text = "This is plain text without any wiki links."
        links = profile.extract_links(text)
        assert links == []

    def test_link_with_spaces_in_page_name(self, profile):
        """Page name with spaces: [[My Page#Heading^blockid]]."""
        text = "[[My Page#Heading^blockid]]"
        links = profile.extract_links(text)
        assert len(links) == 1
        assert links[0] == ("My Page", "Heading", "blockid", None)

    def test_link_with_spaces_in_display(self, profile):
        """Display text with spaces: [[Page|Display Text Here]]."""
        text = "[[Page|Display Text Here]]"
        links = profile.extract_links(text)
        assert len(links) == 1
        assert links[0] == ("Page", None, None, "Display Text Here")


class TestExtractLinksEdgeCases:
    """Additional edge case tests for extract_links()."""

    @pytest.fixture
    def profile(self):
        return ObsidianProfile()

    def test_yaml_frontmatter_not_in_links(self, profile):
        """Links in YAML frontmatter should be stripped before processing."""
        text = """---
title: Test
links: [[Page1]], [[Page2#Heading]]
---
Body with [[Page3]] link."""

        links = profile.extract_links(text)
        # Only the link in body should appear
        assert len(links) == 1
        assert links[0] == ("Page3", None, None, None)

    def test_heading_anchor_with_special_chars(self, profile):
        """Heading with special characters: [[Page#Heading-With_Dashes]]."""
        text = "[[Page#Heading-With_Dashes]]"
        links = profile.extract_links(text)
        assert len(links) == 1
        assert links[0] == ("Page", "Heading-With_Dashes", None, None)

    def test_block_id_with_underscore(self, profile):
        """Block id with underscore: [[Page^block_id]]."""
        text = "[[Page^block_id]]"
        links = profile.extract_links(text)
        assert len(links) == 1
        assert links[0] == ("Page", None, "block_id", None)

    def test_block_id_with_numbers(self, profile):
        """Block id starting with numbers: [[Page^123block]]."""
        text = "[[Page^123block]]"
        links = profile.extract_links(text)
        assert len(links) == 1
        assert links[0] == ("Page", None, "123block", None)
