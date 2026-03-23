#!/usr/bin/env python3
"""Tests for content_updater link preservation on page move.

Verifies that when a page is moved/renamed, all links pointing to it
are updated correctly while preserving:
- Heading anchors (#Heading)
- Block references (^blockid)
- Display text (|Display)
- Child page paths (Old:Child -> New:Child)
"""

import pytest
import os
import sys
import xml.etree.ElementTree as ET

# Ensure moonstone is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moonstone.notebook.content_updater import (
    _parse_link_href,
    _reconstruct_link_href,
    _update_tree_links,
)
from moonstone.formats import ParseTree


class TestParseLinkHref:
    """Tests for _parse_link_href function."""

    # =========================================================================
    # BASIC PARSING
    # =========================================================================

    def test_simple_page_link(self):
        """Simple page link: [[Page]]."""
        target, heading, block_id, display = _parse_link_href("Page")
        assert target == "Page"
        assert heading is None
        assert block_id is None
        assert display is None

    def test_page_with_heading(self):
        """Page with heading anchor: [[Page#Heading]]."""
        target, heading, block_id, display = _parse_link_href("Page#Heading")
        assert target == "Page"
        assert heading == "Heading"
        assert block_id is None
        assert display is None

    def test_page_with_block_ref(self):
        """Page with block reference: [[Page^blockid]]."""
        target, heading, block_id, display = _parse_link_href("Page^blockid")
        assert target == "Page"
        assert heading is None
        assert block_id == "blockid"
        assert display is None

    def test_page_with_display(self):
        """Page with display text: [[Page|Display]]."""
        target, heading, block_id, display = _parse_link_href("Page|Display")
        assert target == "Page"
        assert heading is None
        assert block_id is None
        assert display == "Display"

    # =========================================================================
    # HEADING ANCHOR PRESERVATION
    # =========================================================================

    def test_heading_anchor_preserved(self):
        """Heading anchor preserved in link."""
        target, heading, block_id, display = _parse_link_href("Old#Heading")
        assert target == "Old"
        assert heading == "Heading"
        assert block_id is None
        assert display is None

    def test_heading_with_special_chars(self):
        """Heading anchor with special characters."""
        target, heading, block_id, display = _parse_link_href("Page#Heading-With_Dashes")
        assert target == "Page"
        assert heading == "Heading-With_Dashes"

    # =========================================================================
    # BLOCK REFERENCE PRESERVATION
    # =========================================================================

    def test_block_reference_preserved(self):
        """Block reference preserved in link."""
        target, heading, block_id, display = _parse_link_href("Old^blockid")
        assert target == "Old"
        assert heading is None
        assert block_id == "blockid"
        assert display is None

    def test_block_reference_with_alphanumeric_id(self):
        """Block reference with alphanumeric id."""
        target, heading, block_id, display = _parse_link_href("Page^abc123")
        assert target == "Page"
        assert block_id == "abc123"

    def test_block_reference_with_hyphenated_id(self):
        """Block reference with hyphenated id."""
        target, heading, block_id, display = _parse_link_href("Page^block-id")
        assert target == "Page"
        assert block_id == "block-id"

    # =========================================================================
    # DISPLAY TEXT PRESERVATION
    # =========================================================================

    def test_display_text_preserved(self):
        """Display text preserved in link."""
        target, heading, block_id, display = _parse_link_href("Old|Display")
        assert target == "Old"
        assert heading is None
        assert block_id is None
        assert display == "Display"

    def test_display_text_with_spaces(self):
        """Display text with spaces preserved."""
        target, heading, block_id, display = _parse_link_href("Page|Display Text Here")
        assert display == "Display Text Here"

    # =========================================================================
    # COMBINED PRESERVATION
    # =========================================================================

    def test_heading_and_block_combined(self):
        """Combined heading and block reference."""
        target, heading, block_id, display = _parse_link_href("Page#Heading^blockid")
        assert target == "Page"
        assert heading == "Heading"
        assert block_id == "blockid"

    def test_heading_block_display_combined(self):
        """Combined heading, block, and display."""
        target, heading, block_id, display = _parse_link_href("Old#Heading^blockid|Display")
        assert target == "Old"
        assert heading == "Heading"
        assert block_id == "blockid"
        assert display == "Display"

    def test_block_then_display_combined(self):
        """Block reference with display (no heading)."""
        target, heading, block_id, display = _parse_link_href("Page^blockid|Display")
        assert target == "Page"
        assert heading is None
        assert block_id == "blockid"
        assert display == "Display"

    # =========================================================================
    # CHILD PAGE HANDLING
    # =========================================================================

    def test_child_page_simple(self):
        """Child page: [[Old:Child]]."""
        target, heading, block_id, display = _parse_link_href("Old:Child")
        # The parsing strips leading colons from target
        assert target == "Old:Child"

    def test_child_page_with_heading(self):
        """Child page with heading: [[Old:Child#Anchor]]."""
        target, heading, block_id, display = _parse_link_href("Old:Child#Anchor")
        assert target == "Old:Child"
        assert heading == "Anchor"

    def test_child_page_with_block(self):
        """Child page with block: [[Old:Child^blockid]]."""
        target, heading, block_id, display = _parse_link_href("Old:Child^blockid")
        assert target == "Old:Child"
        assert block_id == "blockid"

    # =========================================================================
    # EDGE CASES
    # =========================================================================

    def test_empty_href(self):
        """Empty href returns all None."""
        target, heading, block_id, display = _parse_link_href("")
        assert target is None
        assert heading is None
        assert block_id is None
        assert display is None

    def test_none_href(self):
        """None href returns all None."""
        target, heading, block_id, display = _parse_link_href(None)
        assert target is None
        assert heading is None
        assert block_id is None
        assert display is None

    def test_same_page_heading_only(self):
        """Same-page heading only: [[#Heading]]."""
        target, heading, block_id, display = _parse_link_href("#Heading")
        # Target will be empty/None since it's just a heading
        assert heading == "Heading"

    def test_page_name_with_spaces(self):
        """Page name with spaces."""
        target, heading, block_id, display = _parse_link_href("My Page#Heading^blockid")
        assert target == "My Page"
        assert heading == "Heading"
        assert block_id == "blockid"


class TestReconstructLinkHref:
    """Tests for _reconstruct_link_href function."""

    def test_simple_page(self):
        """Reconstruct simple page link."""
        href = _reconstruct_link_href("Page", None, None, None)
        assert href == "Page"

    def test_with_heading(self):
        """Reconstruct with heading anchor."""
        href = _reconstruct_link_href("New", "Heading", None, None)
        assert href == "New#Heading"

    def test_with_block(self):
        """Reconstruct with block reference."""
        href = _reconstruct_link_href("New", None, "blockid", None)
        assert href == "New^blockid"

    def test_with_heading_and_block(self):
        """Reconstruct with heading and block."""
        href = _reconstruct_link_href("New", "Heading", "blockid", None)
        assert href == "New#Heading^blockid"

    def test_with_display(self):
        """Reconstruct with display text."""
        href = _reconstruct_link_href("New", None, None, "Display")
        assert href == "New|Display"

    def test_full_combined(self):
        """Reconstruct with all components."""
        href = _reconstruct_link_href("New", "Heading", "blockid", "Display")
        assert href == "New#Heading^blockid|Display"

    def test_child_page_reconstruction(self):
        """Reconstruct child page link."""
        href = _reconstruct_link_href("New:Child", "Anchor", None, None)
        assert href == "New:Child#Anchor"

    def test_none_target_returns_none(self):
        """None target returns None."""
        href = _reconstruct_link_href(None, "Heading", None, None)
        assert href is None


class TestUpdateTreeLinks:
    """Tests for _update_tree_links function."""

    def _make_tree(self, links_xml):
        """Create a ParseTree from XML string with link elements."""
        xml = f"<moonstone-tree>{links_xml}</moonstone-tree>"
        root = ET.fromstring(xml)
        return ParseTree(root)

    # =========================================================================
    # TEST CASE 1: HEADING ANCHOR PRESERVATION
    # =========================================================================

    def test_heading_anchor_preserved_on_move(self):
        """Link [[Old#Heading]] becomes [[New#Heading]] after move Old -> New."""
        tree = self._make_tree('<link href="Old#Heading"/>')
        updated = _update_tree_links(tree, "Old", "New")
        assert updated is True
        # Find the link element and check its href
        for elem in tree.getroot().iter():
            if elem.tag == "link":
                assert elem.get("href") == "New#Heading"

    def test_heading_anchor_with_display_preserved(self):
        """Link [[Old#Heading|Display]] becomes [[New#Heading|Display]] after move."""
        tree = self._make_tree('<link href="Old#Heading|Display"/>')
        updated = _update_tree_links(tree, "Old", "New")
        assert updated is True
        for elem in tree.getroot().iter():
            if elem.tag == "link":
                assert elem.get("href") == "New#Heading|Display"

    def test_block_reference_preserved_on_move(self):
        """Link [[Old^blockid]] becomes [[New^blockid]] after move Old -> New."""
        tree = self._make_tree('<link href="Old^blockid"/>')
        updated = _update_tree_links(tree, "Old", "New")
        assert updated is True
        for elem in tree.getroot().iter():
            if elem.tag == "link":
                assert elem.get("href") == "New^blockid"

    def test_block_reference_with_display_preserved(self):
        """Link [[Old^blockid|Display]] becomes [[New^blockid|Display]] after move."""
        tree = self._make_tree('<link href="Old^blockid|Display"/>')
        updated = _update_tree_links(tree, "Old", "New")
        assert updated is True
        for elem in tree.getroot().iter():
            if elem.tag == "link":
                assert elem.get("href") == "New^blockid|Display"

    def test_display_text_preserved_on_move(self):
        """Link [[Old|Display]] becomes [[New|Display]] after move Old -> New."""
        tree = self._make_tree('<link href="Old|Display"/>')
        updated = _update_tree_links(tree, "Old", "New")
        assert updated is True
        for elem in tree.getroot().iter():
            if elem.tag == "link":
                assert elem.get("href") == "New|Display"

    def test_display_text_with_spaces_preserved(self):
        """Link with display text containing spaces."""
        tree = self._make_tree('<link href="Old|Display Text Here"/>')
        updated = _update_tree_links(tree, "Old", "New")
        assert updated is True
        for elem in tree.getroot().iter():
            if elem.tag == "link":
                assert elem.get("href") == "New|Display Text Here"

    def test_combined_all_components_preserved(self):
        """Link [[Old#Heading^block|Display]] becomes [[New#Heading^block|Display]]."""
        tree = self._make_tree('<link href="Old#Heading^blockid|Display"/>')
        updated = _update_tree_links(tree, "Old", "New")
        assert updated is True
        for elem in tree.getroot().iter():
            if elem.tag == "link":
                assert elem.get("href") == "New#Heading^blockid|Display"

    def test_combined_no_display_preserved(self):
        """Link [[Old#Heading^block]] becomes [[New#Heading^block]]."""
        tree = self._make_tree('<link href="Old#Heading^blockid"/>')
        updated = _update_tree_links(tree, "Old", "New")
        assert updated is True
        for elem in tree.getroot().iter():
            if elem.tag == "link":
                assert elem.get("href") == "New#Heading^blockid"

    def test_child_page_updated_on_parent_move(self):
        """Link [[Old:Child#Anchor]] becomes [[New:Child#Anchor]] after move."""
        tree = self._make_tree('<link href="Old:Child#Anchor"/>')
        updated = _update_tree_links(tree, "Old", "New")
        assert updated is True
        for elem in tree.getroot().iter():
            if elem.tag == "link":
                assert elem.get("href") == "New:Child#Anchor"

    def test_child_page_simple_updated(self):
        """Link [[Old:Child]] becomes [[New:Child]] after parent move."""
        tree = self._make_tree('<link href="Old:Child"/>')
        updated = _update_tree_links(tree, "Old", "New")
        assert updated is True
        for elem in tree.getroot().iter():
            if elem.tag == "link":
                assert elem.get("href") == "New:Child"

    def test_grandchild_page_updated(self):
        """Link [[Old:Child:Grandchild]] becomes [[New:Child:Grandchild]]."""
        tree = self._make_tree('<link href="Old:Child:Grandchild"/>')
        updated = _update_tree_links(tree, "Old", "New")
        assert updated is True
        for elem in tree.getroot().iter():
            if elem.tag == "link":
                assert elem.get("href") == "New:Child:Grandchild"

    def test_different_page_not_changed(self):
        """Link to different page should NOT be changed."""
        tree = self._make_tree('<link href="Other#Heading"/>')
        updated = _update_tree_links(tree, "Old", "New")
        assert updated is False
        for elem in tree.getroot().iter():
            if elem.tag == "link":
                assert elem.get("href") == "Other#Heading"

    def test_partial_name_match_not_changed(self):
        """Partial name match should NOT trigger update."""
        tree = self._make_tree('<link href="OldChild#Heading"/>')
        updated = _update_tree_links(tree, "Old", "New")
        assert updated is False
        for elem in tree.getroot().iter():
            if elem.tag == "link":
                assert elem.get("href") == "OldChild#Heading"

    def test_self_link_not_updated(self):
        """Self-link check is done at caller level (update_links_on_move).
        
        When old == new, _update_tree_links still returns True because it
        processes the link - the self-link filter is in update_links_on_move.
        """
        tree = self._make_tree('<link href="Old#Heading"/>')
        updated = _update_tree_links(tree, "Old", "Old")
        # The function returns True because it processed the link
        # but the href is unchanged since old == new
        assert updated is True
        # Verify href is unchanged (still Old#Heading)
        for elem in tree.getroot().iter():
            if elem.tag == "link":
                assert elem.get("href") == "Old#Heading"

    def test_multiple_links_some_matching(self):
        """Multiple links where only some match the old name."""
        tree = self._make_tree('''
            <link href="Old#Heading"/>
            <link href="Other#Heading"/>
            <link href="Old^blockid"/>
        ''')
        updated = _update_tree_links(tree, "Old", "New")
        assert updated is True
        
        links = [elem.get("href") for elem in tree.getroot().iter() if elem.tag == "link"]
        assert "New#Heading" in links
        assert "Other#Heading" in links
        assert "New^blockid" in links

    def test_all_links_matching(self):
        """Multiple links where all match the old name."""
        tree = self._make_tree('''
            <link href="Old#Heading1"/>
            <link href="Old^blockid"/>
            <link href="Old|Display"/>
        ''')
        updated = _update_tree_links(tree, "Old", "New")
        assert updated is True
        
        links = [elem.get("href") for elem in tree.getroot().iter() if elem.tag == "link"]
        assert "New#Heading1" in links
        assert "New^blockid" in links
        assert "New|Display" in links

    def test_no_links_matching(self):
        """No links match the old name."""
        tree = self._make_tree('''
            <link href="Page1#Heading"/>
            <link href="Page2^blockid"/>
        ''')
        updated = _update_tree_links(tree, "Old", "New")
        assert updated is False

    def test_empty_href_skipped(self):
        """Empty href is skipped without error."""
        tree = self._make_tree('<link href=""/>')
        updated = _update_tree_links(tree, "Old", "New")
        assert updated is False

    def test_same_page_heading_not_updated(self):
        """Same-page heading [[#Heading]] should not be updated."""
        tree = self._make_tree('<link href="#Heading"/>')
        updated = _update_tree_links(tree, "Old", "New")
        assert updated is False

    def test_namespace_prefix_handling(self):
        """Links with namespace prefixes are handled correctly."""
        # A link to a fully-qualified path
        tree = self._make_tree('<link href="namespace:Old#Heading"/>')
        updated = _update_tree_links(tree, "namespace:Old", "namespace:New")
        assert updated is True
        for elem in tree.getroot().iter():
            if elem.tag == "link":
                assert elem.get("href") == "namespace:New#Heading"


class TestLinkPreservationRoundTrip:
    """Tests that parsing and reconstruction preserves link components."""

    def test_roundtrip_simple(self):
        """Parse then reconstruct simple link."""
        href = "Page"
        target, heading, block_id, display = _parse_link_href(href)
        result = _reconstruct_link_href(target, heading, block_id, display)
        assert result == href

    def test_roundtrip_with_heading(self):
        """Parse then reconstruct link with heading."""
        href = "Page#Heading"
        target, heading, block_id, display = _parse_link_href(href)
        result = _reconstruct_link_href(target, heading, block_id, display)
        assert result == href

    def test_roundtrip_with_block(self):
        """Parse then reconstruct link with block."""
        href = "Page^blockid"
        target, heading, block_id, display = _parse_link_href(href)
        result = _reconstruct_link_href(target, heading, block_id, display)
        assert result == href

    def test_roundtrip_with_display(self):
        """Parse then reconstruct link with display."""
        href = "Page|Display"
        target, heading, block_id, display = _parse_link_href(href)
        result = _reconstruct_link_href(target, heading, block_id, display)
        assert result == href

    def test_roundtrip_full_combined(self):
        """Parse then reconstruct full combined link."""
        href = "Old:Child#Heading^blockid|Display"
        target, heading, block_id, display = _parse_link_href(href)
        result = _reconstruct_link_href(target, heading, block_id, display)
        assert result == href
