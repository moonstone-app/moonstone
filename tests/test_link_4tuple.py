# -*- coding: utf-8 -*-
"""Tests for link 4-tuple extraction — target, heading_anchor, block_id, display_text.

Verifies:
1. Basic link formats: [[Page]], [[Page|Display]]
2. Heading anchors: [[Page#Heading]], [[Page#Heading|Display]]
3. Code block exclusion: links inside code blocks should NOT be extracted
4. Edge cases: empty link [[]], multiple links in same line
5. Index integration: links.names column stores anchor info, target_id created correctly
"""

import os
import sqlite3
import tempfile

import pytest


@pytest.fixture
def temp_notebook_dir(tmp_path):
    """Create a temporary notebook directory."""
    notebook_dir = tmp_path / "test_notebook"
    notebook_dir.mkdir()

    # Create notebook.moon config
    (notebook_dir / "notebook.moon").write_text(
        "[notebook]\n"
        "name = Test Notebook\n"
        "home = Home\n"
    )

    # Create a minimal page
    (notebook_dir / "Home.md").write_text("# Home\n\nWelcome!")

    return notebook_dir


def _create_index(notebook_dir, profile=None):
    """Create an Index instance for testing."""
    from moonstone.notebook.index import Index
    from moonstone.notebook.layout import FilesLayout
    from moonstone.profiles.moonstone_profile import MoonstoneProfile

    if profile is None:
        profile = MoonstoneProfile()

    db_path = os.path.join(notebook_dir, "index.db")
    layout = FilesLayout(
        notebook_dir,
        default_extension=profile.file_extension,
        default_format=profile.default_format,
        use_filename_spaces=profile.use_filename_spaces,
        profile=profile,
    )

    return Index(
        db_path=db_path,
        layout=layout,
        root_folder=notebook_dir,
        profile=profile,
    )


def _create_obsidian_index(notebook_dir):
    """Create an Index instance with ObsidianProfile for testing."""
    from moonstone.notebook.index import Index
    from moonstone.notebook.layout import FilesLayout
    from moonstone.profiles.obsidian import ObsidianProfile

    profile = ObsidianProfile()

    db_path = os.path.join(notebook_dir, "index.db")
    layout = FilesLayout(
        notebook_dir,
        default_extension=profile.file_extension,
        default_format=profile.default_format,
        use_filename_spaces=profile.use_filename_spaces,
        profile=profile,
    )

    return Index(
        db_path=db_path,
        layout=layout,
        root_folder=notebook_dir,
        profile=profile,
    )


# =============================================================================
# TEST 1: Basic link format extraction (BaseProfile)
# =============================================================================

@pytest.mark.unit
class TestLink4TupleBasicFormats:
    """Tests for basic link format extraction returning 4-tuples."""

    def test_simple_link_returns_4tuple(self):
        """[[Page]] should return ("Page", None, None, None)."""
        from moonstone.profiles.base import BaseProfile

        profile = BaseProfile()
        result = profile.extract_links("[[Page]]")

        assert len(result) == 1
        assert result[0] == ("Page", None, None, None)

    def test_link_with_display_returns_4tuple(self):
        """[[Page|Display]] should return ("Page", None, None, "Display")."""
        from moonstone.profiles.base import BaseProfile

        profile = BaseProfile()
        result = profile.extract_links("[[Page|Display]]")

        assert len(result) == 1
        assert result[0] == ("Page", None, None, "Display")

    def test_link_with_display_no_extra_spaces(self):
        """[[Page|Display Text]] should return ("Page", None, None, "Display Text")."""
        from moonstone.profiles.base import BaseProfile

        profile = BaseProfile()
        result = profile.extract_links("[[Page|Display Text]]")

        assert len(result) == 1
        assert result[0] == ("Page", None, None, "Display Text")

    def test_multiple_links_same_line(self):
        """Multiple links on same line should all be extracted."""
        from moonstone.profiles.base import BaseProfile

        profile = BaseProfile()
        result = profile.extract_links("[[Page1]] and [[Page2|Link2]] and [[Page3]]")

        assert len(result) == 3
        assert result[0] == ("Page1", None, None, None)
        assert result[1] == ("Page2", None, None, "Link2")
        assert result[2] == ("Page3", None, None, None)


# =============================================================================
# TEST 2: Heading anchor extraction (BaseProfile)
# =============================================================================

@pytest.mark.unit
class TestLink4TupleHeadingAnchors:
    """Tests for heading anchor extraction in 4-tuples."""

    def test_link_with_heading_returns_anchor(self):
        """[[Page#Heading]] should return ("Page", "Heading", None, None)."""
        from moonstone.profiles.base import BaseProfile

        profile = BaseProfile()
        result = profile.extract_links("[[Page#Heading]]")

        assert len(result) == 1
        assert result[0] == ("Page", "Heading", None, None)

    def test_link_with_heading_and_display_returns_anchor_and_display(self):
        """[[Page#Heading|Display]] should return ("Page", "Heading", None, "Display")."""
        from moonstone.profiles.base import BaseProfile

        profile = BaseProfile()
        result = profile.extract_links("[[Page#Heading|Display]]")

        assert len(result) == 1
        assert result[0] == ("Page", "Heading", None, "Display")

    def test_link_with_multilevel_heading(self):
        """[[Page#Chapter 1#Section A]] should return anchor "Chapter 1#Section A"."""
        from moonstone.profiles.base import BaseProfile

        profile = BaseProfile()
        result = profile.extract_links("[[Page#Chapter 1#Section A]]")

        assert len(result) == 1
        assert result[0] == ("Page", "Chapter 1#Section A", None, None)

    def test_link_with_heading_and_block_id(self):
        """[[Page#Heading^blockid]] should return ("Page", "Heading", "blockid", None)."""
        from moonstone.profiles.base import BaseProfile

        profile = BaseProfile()
        result = profile.extract_links("[[Page#Heading^blockid]]")

        assert len(result) == 1
        assert result[0] == ("Page", "Heading", "blockid", None)

    def test_link_with_block_id_only(self):
        """[[Page^blockid]] should return ("Page", None, "blockid", None)."""
        from moonstone.profiles.base import BaseProfile

        profile = BaseProfile()
        result = profile.extract_links("[[Page^blockid]]")

        assert len(result) == 1
        assert result[0] == ("Page", None, "blockid", None)


# =============================================================================
# TEST 3: Code block exclusion (BaseProfile)
# =============================================================================

@pytest.mark.unit
class TestLink4TupleCodeBlockExclusion:
    """Tests for code block exclusion in link extraction."""

    def test_link_in_fenced_code_block_not_extracted(self):
        """Links inside fenced code blocks should NOT be extracted."""
        from moonstone.profiles.base import BaseProfile

        profile = BaseProfile()
        text = """
Some text before
```
[[Page1]] and [[Page2|Link]]
```
Some text after
"""
        result = profile.extract_links(text)

        # No links should be extracted from inside code blocks
        assert len(result) == 0

    def test_link_in_inline_code_not_extracted(self):
        """Links inside inline code should NOT be extracted."""
        from moonstone.profiles.base import BaseProfile

        profile = BaseProfile()
        text = "Use `[[Page1]]` for the link."
        result = profile.extract_links(text)

        assert len(result) == 0

    def test_link_outside_code_block_still_extracted(self):
        """Links outside code blocks should still be extracted."""
        from moonstone.profiles.base import BaseProfile

        profile = BaseProfile()
        text = """
```
[[Page1]] not extracted
```
[[Page2]] should be extracted
"""
        result = profile.extract_links(text)

        assert len(result) == 1
        assert result[0] == ("Page2", None, None, None)

    def test_multiple_links_in_text_with_code_block(self):
        """Multiple links with code block exclusion should work correctly."""
        from moonstone.profiles.base import BaseProfile

        profile = BaseProfile()
        text = """
Before code: [[Page1]]
```
[[Page2]] inside code
[[Page3]] also inside
```
After code: [[Page4|Display]]
"""
        result = profile.extract_links(text)

        assert len(result) == 2
        assert result[0] == ("Page1", None, None, None)
        assert result[1] == ("Page4", None, None, "Display")


# =============================================================================
# TEST 4: Edge cases (BaseProfile)
# =============================================================================

@pytest.mark.unit
class TestLink4TupleEdgeCases:
    """Tests for edge cases in link extraction."""

    def test_empty_link_does_not_crash(self):
        """Empty link [[]] should not crash and should be filtered out."""
        from moonstone.profiles.base import BaseProfile

        profile = BaseProfile()
        result = profile.extract_links("[[]]")

        # Empty links are filtered out (no point linking to nothing)
        # This is correct behavior - it should not crash
        assert len(result) == 0

    def test_empty_link_in_text_does_not_crash(self):
        """Empty link in middle of text should not crash and should be filtered out."""
        from moonstone.profiles.base import BaseProfile

        profile = BaseProfile()
        text = "Text before [[]] text after"
        result = profile.extract_links(text)

        # Empty links are filtered out
        assert len(result) == 0

    def test_link_with_only_spaces(self):
        """[[   ]] link with spaces should be handled."""
        from moonstone.profiles.base import BaseProfile

        profile = BaseProfile()
        result = profile.extract_links("[[   ]]")

        assert len(result) == 1
        assert result[0][0] == ""  # spaces collapse to empty

    def test_malformed_link_not_extracted(self):
        """Malformed links like [Page] (single bracket) should not be extracted."""
        from moonstone.profiles.base import BaseProfile

        profile = BaseProfile()
        text = "This is [not a link] and [[this is]]."
        result = profile.extract_links(text)

        assert len(result) == 1
        assert result[0] == ("this is", None, None, None)

    def test_link_with_pipes_in_target(self):
        """Links where target contains pipes are split on first | as separator."""
        from moonstone.profiles.base import BaseProfile

        profile = BaseProfile()
        # The | character is the separator, so || splits into target and display
        text = "[[Page With Pipe || in target]]"
        result = profile.extract_links(text)

        assert len(result) == 1
        # First | splits target from display text
        assert result[0][0] == "Page With Pipe"
        assert result[0][3] == "| in target"


# =============================================================================
# TEST 5: ObsidianProfile link extraction
# =============================================================================

@pytest.mark.unit
class TestObsidianLink4Tuple:
    """Tests for ObsidianProfile link extraction."""

    def test_obsidian_simple_link(self):
        """[[Page]] should return ("Page", None, None, None)."""
        from moonstone.profiles.obsidian import ObsidianProfile

        profile = ObsidianProfile()
        result = profile.extract_links("[[Page]]")

        assert len(result) == 1
        assert result[0] == ("Page", None, None, None)

    def test_obsidian_link_with_display(self):
        """[[Page|Display]] should return ("Page", None, None, "Display")."""
        from moonstone.profiles.obsidian import ObsidianProfile

        profile = ObsidianProfile()
        result = profile.extract_links("[[Page|Display Text]]")

        assert len(result) == 1
        assert result[0] == ("Page", None, None, "Display Text")

    def test_obsidian_link_with_heading(self):
        """[[Page#Heading]] should return ("Page", "Heading", None, None)."""
        from moonstone.profiles.obsidian import ObsidianProfile

        profile = ObsidianProfile()
        result = profile.extract_links("[[Page#Heading]]")

        assert len(result) == 1
        assert result[0] == ("Page", "Heading", None, None)

    def test_obsidian_link_with_heading_and_display(self):
        """[[Page#Heading|Display]] should return ("Page", "Heading", None, "Display")."""
        from moonstone.profiles.obsidian import ObsidianProfile

        profile = ObsidianProfile()
        result = profile.extract_links("[[Page#Heading|Display]]")

        assert len(result) == 1
        assert result[0] == ("Page", "Heading", None, "Display")

    def test_obsidian_code_block_exclusion(self):
        """Links inside code blocks should not be extracted."""
        from moonstone.profiles.obsidian import ObsidianProfile

        profile = ObsidianProfile()
        text = """
```
[[Page1]] inside code
```
[[Page2]] outside code
"""
        result = profile.extract_links(text)

        assert len(result) == 1
        assert result[0] == ("Page2", None, None, None)

    def test_obsidian_inline_code_exclusion(self):
        """Links inside inline code should not be extracted."""
        from moonstone.profiles.obsidian import ObsidianProfile

        profile = ObsidianProfile()
        text = "Use `[[Page1]]` for the link."
        result = profile.extract_links(text)

        assert len(result) == 0


# =============================================================================
# TEST 6: Index integration — links.names column
# =============================================================================

@pytest.mark.unit
class TestLink4TupleIndexIntegration:
    """Tests for index integration with link 4-tuples."""

    def test_links_names_column_stores_simple_link(self, temp_notebook_dir):
        """links.names column should store simple link target."""
        index = _create_index(temp_notebook_dir)

        # Create page with link
        (temp_notebook_dir / "Page1.md").write_text("# Page1\n\nLink to [[Target Page]]")
        (temp_notebook_dir / "Target_Page.md").write_text("# Target Page\n\nContent")

        index.check_and_update()

        with index.get_connection() as conn:
            # Get the link from Page1 to Target Page
            result = conn.execute("""
                SELECT l.names
                FROM links l
                JOIN pages p ON l.source = p.id
                WHERE p.name = 'Page1'
            """).fetchone()

            assert result is not None
            # names should contain "Target Page"
            assert "Target Page" in result[0]

    def test_links_names_column_stores_heading_anchor(self, temp_notebook_dir):
        """links.names column should store heading anchor info."""
        index = _create_index(temp_notebook_dir)

        # Create page with link to heading
        (temp_notebook_dir / "Page1.md").write_text("# Page1\n\nLink to [[Target Page#Section One]]")
        (temp_notebook_dir / "Target_Page.md").write_text("# Target Page\n## Section One\n\nContent")

        index.check_and_update()

        with index.get_connection() as conn:
            result = conn.execute("""
                SELECT l.names
                FROM links l
                JOIN pages p ON l.source = p.id
                WHERE p.name = 'Page1'
            """).fetchone()

            assert result is not None
            names = result[0]
            # Should contain heading anchor
            assert "#Section One" in names
            # Should NOT contain the display part incorrectly
            assert "||" not in names

    def test_links_names_column_stores_display_text(self, temp_notebook_dir):
        """links.names column should store display text after |."""
        index = _create_index(temp_notebook_dir)

        # Create page with link with display text
        (temp_notebook_dir / "Page1.md").write_text("# Page1\n\nLink to [[Target Page|Display Text]]")
        (temp_notebook_dir / "Target_Page.md").write_text("# Target Page\n\nContent")

        index.check_and_update()

        with index.get_connection() as conn:
            result = conn.execute("""
                SELECT l.names
                FROM links l
                JOIN pages p ON l.source = p.id
                WHERE p.name = 'Page1'
            """).fetchone()

            assert result is not None
            names = result[0]
            # Should contain display text after |
            assert "|Display Text" in names

    def test_target_id_created_for_linked_page(self, temp_notebook_dir):
        """target_id in links table should reference existing page or create placeholder."""
        index = _create_index(temp_notebook_dir)

        # Create page with link to non-existent page
        (temp_notebook_dir / "Page1.md").write_text("# Page1\n\nLink to [[NonExistent Page]]")

        index.check_and_update()

        with index.get_connection() as conn:
            # Should have created a placeholder for the non-existent page
            result = conn.execute("""
                SELECT l.target, p.name
                FROM links l
                JOIN pages p ON l.source = p.id
                WHERE p.name = 'Page1'
            """).fetchone()

            assert result is not None
            target_id, source_name = result
            assert target_id is not None
            assert target_id > 0

    def test_multiple_links_stored_correctly(self, temp_notebook_dir):
        """Multiple links from one page should all be stored."""
        index = _create_index(temp_notebook_dir)

        # Create page with multiple links
        (temp_notebook_dir / "Page1.md").write_text(
            "# Page1\n\n"
            "Link to [[Page2]] and [[Page3|Third]] and [[Page4#Heading|Fourth]]"
        )
        (temp_notebook_dir / "Page2.md").write_text("# Page2\n\nContent")
        (temp_notebook_dir / "Page3.md").write_text("# Page3\n\nContent")
        (temp_notebook_dir / "Page4.md").write_text("# Page4\n## Heading\n\nContent")

        index.check_and_update()

        with index.get_connection() as conn:
            results = conn.execute("""
                SELECT p.name, l.names
                FROM links l
                JOIN pages p ON l.source = p.id
                WHERE p.name = 'Page1'
                ORDER BY l.rowid
            """).fetchall()

            assert len(results) == 3

            # Link to Page2 - simple
            assert "Page2" in results[0][1]

            # Link to Page3 with display
            assert "Page3" in results[1][1]
            assert "|Third" in results[1][1]

            # Link to Page4 with heading and display
            assert "Page4" in results[2][1]
            assert "#Heading" in results[2][1]
            assert "|Fourth" in results[2][1]

    def test_links_with_block_id_stored_in_names(self, temp_notebook_dir):
        """Block IDs (^) should be stored in links.names column."""
        index = _create_index(temp_notebook_dir)

        # Create page with link containing block ID
        (temp_notebook_dir / "Page1.md").write_text("# Page1\n\nLink to [[Page2#Section^abc123]]")
        (temp_notebook_dir / "Page2.md").write_text("# Page2\n## Section\n^abc123 block content\n\nMore content")

        index.check_and_update()

        with index.get_connection() as conn:
            result = conn.execute("""
                SELECT l.names
                FROM links l
                JOIN pages p ON l.source = p.id
                WHERE p.name = 'Page1'
            """).fetchone()

            assert result is not None
            names = result[0]
            # Should contain block ID with ^
            assert "^abc123" in names


# =============================================================================
# TEST 7: Moonstone vs Obsidian profile comparison
# =============================================================================

@pytest.mark.unit
class TestLink4TupleProfileComparison:
    """Compare link extraction between Moonstone and Obsidian profiles."""

    def test_moonstone_simple_link(self):
        """Test MoonstoneProfile simple link extraction."""
        from moonstone.profiles.moonstone_profile import MoonstoneProfile

        profile = MoonstoneProfile()
        result = profile.extract_links("[[Page]]")

        assert len(result) == 1
        assert result[0][0] == "Page"  # target
        assert result[0][1] is None  # heading_anchor
        assert result[0][2] is None  # block_id
        assert result[0][3] is None  # display_text

    def test_moonstone_link_with_display(self):
        """Test MoonstoneProfile link with display text."""
        from moonstone.profiles.moonstone_profile import MoonstoneProfile

        profile = MoonstoneProfile()
        result = profile.extract_links("[[Page|Display]]")

        assert len(result) == 1
        assert result[0] == ("Page", None, None, "Display")

    def test_moonstone_link_with_heading(self):
        """Test MoonstoneProfile link with heading anchor."""
        from moonstone.profiles.moonstone_profile import MoonstoneProfile

        profile = MoonstoneProfile()
        result = profile.extract_links("[[Page#Heading]]")

        assert len(result) == 1
        assert result[0] == ("Page", "Heading", None, None)

    def test_moonstone_link_with_heading_and_display(self):
        """Test MoonstoneProfile link with heading anchor and display."""
        from moonstone.profiles.moonstone_profile import MoonstoneProfile

        profile = MoonstoneProfile()
        result = profile.extract_links("[[Page#Heading|Display]]")

        assert len(result) == 1
        assert result[0] == ("Page", "Heading", None, "Display")

    def test_moonstone_link_with_block_id(self):
        """Test MoonstoneProfile link with block ID."""
        from moonstone.profiles.moonstone_profile import MoonstoneProfile

        profile = MoonstoneProfile()
        result = profile.extract_links("[[Page^blockid]]")

        assert len(result) == 1
        assert result[0] == ("Page", None, "blockid", None)

    def test_moonstone_link_with_heading_and_block_id(self):
        """Test MoonstoneProfile link with heading and block ID."""
        from moonstone.profiles.moonstone_profile import MoonstoneProfile

        profile = MoonstoneProfile()
        result = profile.extract_links("[[Page#Heading^blockid]]")

        assert len(result) == 1
        assert result[0] == ("Page", "Heading", "blockid", None)

    def test_both_profiles_return_same_4tuple_structure(self):
        """Both Moonstone and Obsidian profiles should return 4-tuples."""
        from moonstone.profiles.moonstone_profile import MoonstoneProfile
        from moonstone.profiles.obsidian import ObsidianProfile

        moonstone = MoonstoneProfile()
        obsidian = ObsidianProfile()

        text = "[[Page#Heading|Display]]"

        m_result = moonstone.extract_links(text)
        o_result = obsidian.extract_links(text)

        assert len(m_result) == 1
        assert len(o_result) == 1

        # Both should return 4-tuples with same structure
        assert len(m_result[0]) == 4
        assert len(o_result[0]) == 4

        # Values should match
        assert m_result[0][0] == o_result[0][0]  # target
        assert m_result[0][1] == o_result[0][1]  # heading_anchor
        assert m_result[0][2] == o_result[0][2]  # block_id
        assert m_result[0][3] == o_result[0][3]  # display_text
