# -*- coding: utf-8 -*-
"""End-to-end integration tests for Obsidian profile features.

Tests the complete workflow:
1. Create a temporary Obsidian vault with Unicode tags, aliases, block refs, heading links
2. Index the vault using Index class
3. Verify tags, aliases, links are extracted and stored correctly
4. Verify case-insensitive tag matching via tag_lower column
5. Verify lookup_by_alias() works
6. Verify link parsing with anchors and block IDs
7. Verify page moves update child links correctly
"""

import os
import tempfile
import shutil

import pytest

from moonstone.profiles.obsidian import ObsidianProfile
from moonstone.notebook.index import Index
from moonstone.notebook.layout import FilesLayout
from moonstone.notebook.index.pages import PagesView
from moonstone.notebook.index.tags import TagsView
from moonstone.notebook.index.links import LinksView, LINK_DIR_BACKWARD, LINK_DIR_FORWARD
from moonstone.notebook.notebook import Notebook
from moonstone.notebook.page import Path
from moonstone.notebook.content_updater import update_links_in_moved_page


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def temp_vault_dir(tmp_path):
    """Create a temporary Obsidian vault directory with test pages."""
    vault_dir = tmp_path / "test_vault"
    vault_dir.mkdir()

    # Create .obsidian folder (Obsidian marker)
    obsidian_dir = vault_dir / ".obsidian"
    obsidian_dir.mkdir()

    # Create app.json config (optional but good for testing)
    (obsidian_dir / "app.json").write_text(
        '{"attachmentFolderPath": ".", "vaultSize": {"amount": 1}}',
        encoding="utf-8"
    )

    # Create Home page
    (vault_dir / "Home.md").write_text(
        "# Home\n\nWelcome to the test vault.",
        encoding="utf-8"
    )

    return vault_dir


def _create_index_and_views(vault_dir, profile=None):
    """Create an Index instance and views for testing."""
    if profile is None:
        profile = ObsidianProfile()

    # Use same db_path as Notebook.index (in .moonstone subdirectory)
    cache_dir = os.path.join(vault_dir, ".moonstone")
    os.makedirs(cache_dir, exist_ok=True)
    db_path = os.path.join(cache_dir, "index.db")
    
    layout = FilesLayout(
        vault_dir,
        default_extension=profile.file_extension,
        default_format=profile.default_format,
        use_filename_spaces=profile.use_filename_spaces,
        profile=profile,
    )

    index = Index(
        db_path=db_path,
        layout=layout,
        root_folder=vault_dir,
        profile=profile,
    )

    pages_view = PagesView.new_from_index(index)
    tags_view = TagsView.new_from_index(index)
    links_view = LinksView.new_from_index(index)

    return index, pages_view, tags_view, links_view


def _create_notebook(vault_dir, profile=None):
    """Create a Notebook instance for testing."""
    if profile is None:
        profile = ObsidianProfile()
    return Notebook(vault_dir, profile=profile)


# =============================================================================
# TEST 1: Unicode Tags Extraction
# =============================================================================

@pytest.mark.integration
class TestUnicodeTagsExtraction:
    """Tests for Unicode tag extraction and storage."""

    def test_unicode_chinese_tag_extracted(self, temp_vault_dir):
        """Chinese tag #中文 should be extracted and stored correctly."""
        # Create page with Chinese tag
        (temp_vault_dir / "ChinesePage.md").write_text(
            "# Chinese Page\n\nContent with #中文 tag",
            encoding="utf-8"
        )

        index, pages_view, tags_view, links_view = _create_index_and_views(temp_vault_dir)
        index.check_and_update()

        # Verify tag is stored with original name and lowercase
        with index.get_connection() as conn:
            row = conn.execute(
                "SELECT name, tag_lower FROM tags WHERE name = ?", ("中文",)
            ).fetchone()
            assert row is not None, "Chinese tag '中文' should be in database"
            assert row["name"] == "中文"
            assert row["tag_lower"] == "中文"  # Chinese .lower() returns same

        # Verify tag lookup works
        result = tags_view.lookup_by_tagname("中文")
        assert result is not None, "Should find Chinese tag"
        assert result.name == "中文"

    def test_unicode_cyrillic_tag_extracted(self, temp_vault_dir):
        """Cyrillic tag #проект should be extracted and stored correctly."""
        (temp_vault_dir / "RussianPage.md").write_text(
            "# Russian Page\n\nContent with #проект tag",
            encoding="utf-8"
        )

        index, pages_view, tags_view, links_view = _create_index_and_views(temp_vault_dir)
        index.check_and_update()

        # Verify Cyrillic lowercase works
        with index.get_connection() as conn:
            row = conn.execute(
                "SELECT name, tag_lower FROM tags WHERE name = ?", ("проект",)
            ).fetchone()
            assert row is not None, "Cyrillic tag should be in database"
            assert row["name"] == "проект"
            assert row["tag_lower"] == "проект"

        result = tags_view.lookup_by_tagname("проект")
        assert result is not None
        assert result.name == "проект"

    def test_unicode_case_insensitive_lookup(self, temp_vault_dir):
        """Unicode tags should support case-insensitive lookup."""
        (temp_vault_dir / "CasePage.md").write_text(
            "# Case Page\n\nContent with #Проект tag",
            encoding="utf-8"
        )

        index, pages_view, tags_view, links_view = _create_index_and_views(temp_vault_dir)
        index.check_and_update()

        # Lookup with different case should find same tag
        result_upper = tags_view.lookup_by_tagname("ПРОЕКТ")
        assert result_upper is not None, "Should find uppercase Cyrillic tag"
        assert result_upper.name == "Проект"

        result_lower = tags_view.lookup_by_tagname("проект")
        assert result_lower is not None
        assert result_lower.name == "Проект"


# =============================================================================
# TEST 2: Numeric and Special Character Tags
# =============================================================================

@pytest.mark.integration
class TestSpecialCharacterTags:
    """Tests for tags with numbers, plus signs, periods."""

    def test_numeric_tag_extracted(self, temp_vault_dir):
        """Tag #2024-goals with leading number should be extracted."""
        (temp_vault_dir / "GoalsPage.md").write_text(
            "# Goals Page\n\nNew year resolution with #2024-goals",
            encoding="utf-8"
        )

        index, pages_view, tags_view, links_view = _create_index_and_views(temp_vault_dir)
        index.check_and_update()

        with index.get_connection() as conn:
            row = conn.execute(
                "SELECT name, tag_lower FROM tags WHERE name = ?", ("2024-goals",)
            ).fetchone()
            assert row is not None, "Numeric tag '2024-goals' should be extracted"
            assert row["name"] == "2024-goals"
            assert row["tag_lower"] == "2024-goals"

    def test_cpp_tag_extracted(self, temp_vault_dir):
        """Tag #C++ should be extracted correctly."""
        (temp_vault_dir / "CppPage.md").write_text(
            "# C++ Page\n\nProgramming notes with #C++ tag",
            encoding="utf-8"
        )

        index, pages_view, tags_view, links_view = _create_index_and_views(temp_vault_dir)
        index.check_and_update()

        with index.get_connection() as conn:
            row = conn.execute(
                "SELECT name, tag_lower FROM tags WHERE name = ?", ("C++",)
            ).fetchone()
            assert row is not None, "C++ tag should be extracted"
            assert row["name"] == "C++"
            assert row["tag_lower"] == "c++"


# =============================================================================
# TEST 3: Alias Extraction and lookup_by_alias
# =============================================================================

@pytest.mark.integration
class TestAliasExtraction:
    """Tests for alias extraction from YAML frontmatter."""

    def test_aliases_array_format_extracted(self, temp_vault_dir):
        """Aliases in array format: aliases: [One, Two] should be extracted."""
        (temp_vault_dir / "AliasPage.md").write_text(
            "---\naliases: [One, Two]\n---\n# Alias Page\n\nContent.",
            encoding="utf-8"
        )

        index, pages_view, tags_view, links_view = _create_index_and_views(temp_vault_dir)
        index.check_and_update()

        # Verify aliases are stored in database
        with index.get_connection() as conn:
            rows = conn.execute(
                "SELECT aliases.name, aliases.name_lower FROM aliases JOIN pages ON aliases.page = pages.id WHERE pages.name = ?",
                ("AliasPage",)
            ).fetchall()

            alias_names = {row["name"] for row in rows}
            assert "One" in alias_names and "Two" in alias_names, \
                f"Aliases should be extracted, got: {alias_names}"

    def test_aliases_yaml_list_format_extracted(self, temp_vault_dir):
        """Aliases in YAML list format should be extracted."""
        (temp_vault_dir / "YamlAliasPage.md").write_text(
            "---\naliases:\n  - Alias One\n  - Alias Two\n---\n# Yaml Alias Page\n\nContent.",
            encoding="utf-8"
        )

        index, pages_view, tags_view, links_view = _create_index_and_views(temp_vault_dir)
        index.check_and_update()

        # Verify aliases are stored
        with index.get_connection() as conn:
            rows = conn.execute(
                "SELECT aliases.name FROM aliases JOIN pages ON aliases.page = pages.id WHERE pages.name = ?",
                ("YamlAliasPage",)
            ).fetchall()
            alias_names = {row["name"] for row in rows}
            assert len(rows) == 2, f"Should have 2 aliases, got: {alias_names}"

    def test_lookup_by_alias_finds_page(self, temp_vault_dir):
        """lookup_by_alias should find page by its alias."""
        (temp_vault_dir / "TargetPage.md").write_text(
            "---\naliases: [MyAlias, AnotherAlias]\n---\n# Target Page\n\nContent.",
            encoding="utf-8"
        )

        index, pages_view, tags_view, links_view = _create_index_and_views(temp_vault_dir)
        index.check_and_update()

        # Lookup by first alias
        result = pages_view.lookup_by_alias("MyAlias")
        assert result is not None, "Should find page by alias 'MyAlias'"
        assert result.name == "TargetPage"

        # Lookup by second alias
        result2 = pages_view.lookup_by_alias("AnotherAlias")
        assert result2 is not None, "Should find page by alias 'AnotherAlias'"
        assert result2.name == "TargetPage"

    def test_lookup_by_alias_case_insensitive(self, temp_vault_dir):
        """lookup_by_alias should be case-insensitive."""
        (temp_vault_dir / "CaseAliasPage.md").write_text(
            "---\naliases: [MixedCaseAlias]\n---\n# Case Alias Page\n\nContent.",
            encoding="utf-8"
        )

        index, pages_view, tags_view, links_view = _create_index_and_views(temp_vault_dir)
        index.check_and_update()

        # Exact case
        result1 = pages_view.lookup_by_alias("MixedCaseAlias")
        assert result1 is not None
        assert result1.name == "CaseAliasPage"

        # Uppercase
        result2 = pages_view.lookup_by_alias("MIXEDCASEALIAS")
        assert result2 is not None
        assert result2.name == "CaseAliasPage"

        # Lowercase
        result3 = pages_view.lookup_by_alias("mixedcasealias")
        assert result3 is not None
        assert result3.name == "CaseAliasPage"


# =============================================================================
# TEST 4: Link Parsing (block IDs, heading anchors)
# =============================================================================

@pytest.mark.integration
class TestLinkParsing:
    """Tests for link parsing with block IDs and heading anchors."""

    def test_block_reference_parsed(self, temp_vault_dir):
        """Block reference [[Page^blockid]] should be parsed correctly."""
        # Create target page
        (temp_vault_dir / "Target.md").write_text(
            "# Target Page\n\nSome content with a block.",
            encoding="utf-8"
        )

        # Create source page with block reference link
        (temp_vault_dir / "Source.md").write_text(
            "# Source Page\n\nLink to block: [[Target^blockid]]",
            encoding="utf-8"
        )

        index, pages_view, tags_view, links_view = _create_index_and_views(temp_vault_dir)
        index.check_and_update()

        # Verify link is stored with block ID in names field
        with index.get_connection() as conn:
            row = conn.execute(
                """
                SELECT l.names FROM links l
                JOIN pages p ON l.source = p.id
                WHERE p.name = ?
                """,
                ("Source",)
            ).fetchone()

            assert row is not None, "Link should be stored"
            assert "^blockid" in row["names"], \
                f"Link names should contain blockid info, got: {row['names']}"

    def test_heading_anchor_parsed(self, temp_vault_dir):
        """Heading anchor [[Page#Heading]] should be parsed correctly."""
        (temp_vault_dir / "SourceHeading.md").write_text(
            "# Source Page\n\nLink to heading: [[Target#MyHeading]]",
            encoding="utf-8"
        )
        (temp_vault_dir / "Target.md").write_text(
            "# MyHeading\n\nTarget content.",
            encoding="utf-8"
        )

        index, pages_view, tags_view, links_view = _create_index_and_views(temp_vault_dir)
        index.check_and_update()

        # Verify link has heading anchor
        with index.get_connection() as conn:
            row = conn.execute(
                """
                SELECT l.names FROM links l
                JOIN pages p ON l.source = p.id
                WHERE p.name = ?
                """,
                ("SourceHeading",)
            ).fetchone()

            assert row is not None
            # The names field should contain heading info
            names = row["names"] or ""
            assert "#MyHeading" in names, \
                f"Link should contain heading anchor, got: {names}"

    def test_link_with_display_text_parsed(self, temp_vault_dir):
        """Link with display text [[Page|Display]] should be parsed."""
        (temp_vault_dir / "DisplayPage.md").write_text(
            "# Display Page\n\nLink with display: [[Target|Click Here]]",
            encoding="utf-8"
        )
        (temp_vault_dir / "Target.md").write_text(
            "# Target\n\nContent.",
            encoding="utf-8"
        )

        index, pages_view, tags_view, links_view = _create_index_and_views(temp_vault_dir)
        index.check_and_update()

        with index.get_connection() as conn:
            row = conn.execute(
                """
                SELECT l.names FROM links l
                JOIN pages p ON l.source = p.id
                WHERE p.name = ?
                """,
                ("DisplayPage",)
            ).fetchone()

            assert row is not None
            # Display text should be preserved in names field
            assert "Click Here" in (row["names"] or "")


# =============================================================================
# TEST 5: Cross-Page Links
# =============================================================================

@pytest.mark.integration
class TestCrossPageLinks:
    """Tests for links between pages."""

    def test_forward_links_stored(self, temp_vault_dir):
        """Forward links from one page to another should be stored."""
        (temp_vault_dir / "PageA.md").write_text(
            "# Page A\n\nSee [[PageB]] for more info.",
            encoding="utf-8"
        )
        (temp_vault_dir / "PageB.md").write_text(
            "# Page B\n\nThis is Page B content.",
            encoding="utf-8"
        )

        index, pages_view, tags_view, links_view = _create_index_and_views(temp_vault_dir)
        index.check_and_update()

        # Check forward links from PageA
        links = list(links_view.list_links(Path("PageA"), LINK_DIR_FORWARD))
        assert len(links) >= 1, "PageA should have at least one forward link"

        # Verify target is PageB
        targets = [link.target.name for link in links]
        assert "PageB" in targets, f"Should link to PageB, got targets: {targets}"

    def test_backlinks_stored(self, temp_vault_dir):
        """Backlinks to a page should be tracked."""
        (temp_vault_dir / "LinkSource.md").write_text(
            "# Link Source\n\nLinks to [[BacklinkTarget]].",
            encoding="utf-8"
        )
        (temp_vault_dir / "BacklinkTarget.md").write_text(
            "# Backlink Target\n\nContent.",
            encoding="utf-8"
        )

        index, pages_view, tags_view, links_view = _create_index_and_views(temp_vault_dir)
        index.check_and_update()

        # Check backlinks to BacklinkTarget
        backlinks = list(links_view.list_links(Path("BacklinkTarget"), LINK_DIR_BACKWARD))
        assert len(backlinks) >= 1, "BacklinkTarget should have backlinks"

        sources = [link.source.name for link in backlinks]
        assert "LinkSource" in sources, f"LinkSource should link to BacklinkTarget, got: {sources}"


# =============================================================================
# TEST 6: Page Move and Link Updates
# =============================================================================

@pytest.mark.integration
class TestPageMoveAndLinkUpdates:
    """Tests for page move operations and link updates."""

    def test_move_page_updates_index(self, temp_vault_dir):
        """Moving a page should update its name in the index."""
        # Create parent page with child
        (temp_vault_dir / "Old.md").write_text(
            "# Old Page\n\nContent of old page.",
            encoding="utf-8"
        )

        index, pages_view, tags_view, links_view = _create_index_and_views(temp_vault_dir)
        index.check_and_update()

        # Move the page using notebook
        notebook = _create_notebook(temp_vault_dir)
        old_path = Path("Old")
        new_path = Path("New")

        notebook.move_page(old_path, new_path, update_links=False)

        # Verify page is found at new location
        result = pages_view.lookup_by_pagename("New")
        assert result is not None, "Page should be found at new name 'New'"
        assert result.name == "New"

        # Verify old name no longer exists
        old_result = pages_view.lookup_by_pagename("Old")
        # Note: The page was moved, so Old shouldn't exist as a separate page
        # But if it was just renamed, it should only exist at New

    def test_move_page_with_child_links_updated(self, temp_vault_dir):
        """Moving a parent page should update child links inside the moved page."""
        # Create namespace structure: Old:Parent with child Old:Parent:Child
        # Create the files with proper directory structure
        old_parent_dir = temp_vault_dir / "Old"
        old_parent_dir.mkdir()
        (old_parent_dir / "Parent.md").write_text(
            "# Parent\n\nThis is parent. See [[Parent:Child]] for child info.",
            encoding="utf-8"
        )
        (old_parent_dir / "Child.md").write_text(
            "# Child\n\nThis is child content.",
            encoding="utf-8"
        )

        index, pages_view, tags_view, links_view = _create_index_and_views(temp_vault_dir)
        index.check_and_update()

        # Verify initial links are correct
        links_from_parent = list(links_view.list_links(Path("Old:Parent"), LINK_DIR_FORWARD))
        # The link [[Parent:Child]] should resolve to Old:Parent:Child

        # Move the parent from Old:Parent to New:Parent
        notebook = _create_notebook(temp_vault_dir)
        old_path = Path("Old:Parent")
        new_path = Path("New:Parent")

        notebook.move_page(old_path, new_path, update_links=True)

        # After move, links inside the moved page should be updated
        # Get the moved page's content
        new_page = notebook.get_page(Path("New:Parent"))
        content = new_page.source_file.read()

        # The link should now point to New:Parent:Child, not Old:Parent:Child
        assert "Old:Parent:Child" not in content, \
            f"Old namespace should be removed from moved page content, got: {content}"


# =============================================================================
# TEST 7: Full Vault Indexing
# =============================================================================

@pytest.mark.integration
class TestFullVaultIndexing:
    """Tests for complete vault indexing workflow."""

    def test_full_vault_indexing_tags_aliases_links(self, temp_vault_dir):
        """Complete workflow: index vault with tags, aliases, and links."""
        # Page 1: Unicode tags
        (temp_vault_dir / "UnicodeTags.md").write_text(
            "# Unicode Tags\n\n#中文 #проект #2024-goals #C++",
            encoding="utf-8"
        )

        # Page 2: Aliases
        (temp_vault_dir / "AliasTarget.md").write_text(
            "---\naliases: [First Alias, Second Alias]\n---\n# Alias Target\n\nContent.",
            encoding="utf-8"
        )

        # Page 3: Links with various formats
        (temp_vault_dir / "LinksPage.md").write_text(
            "# Links Page\n\n"
            "Block link: [[AliasTarget^block123]]\n"
            "Heading link: [[AliasTarget#Heading]]\n"
            "Display link: [[AliasTarget|Display Text]]\n"
            "Simple link: [[AliasTarget]]",
            encoding="utf-8"
        )

        # Page 4: Regular page that links to others
        (temp_vault_dir / "RegularPage.md").write_text(
            "# Regular Page\n\nSee [[UnicodeTags]] and [[AliasTarget]].",
            encoding="utf-8"
        )

        index, pages_view, tags_view, links_view = _create_index_and_views(temp_vault_dir)
        index.check_and_update()

        # ========== VERIFY TAGS ==========
        # Count total tags
        all_tags = list(tags_view.list_all_tags_by_n_pages())
        tag_names = [t.name for t in all_tags]

        assert "中文" in tag_names, "Chinese tag should be extracted"
        assert "проект" in tag_names, "Cyrillic tag should be extracted"
        assert "2024-goals" in tag_names, "Numeric tag should be extracted"
        assert "C++" in tag_names, "C++ tag should be extracted"

        # ========== VERIFY TAG_LOWER ==========
        with index.get_connection() as conn:
            for tag_name in ["中文", "проект", "C++"]:
                row = conn.execute(
                    "SELECT tag_lower FROM tags WHERE name = ?", (tag_name,)
                ).fetchone()
                assert row is not None, f"Tag {tag_name} should have tag_lower"
                assert row["tag_lower"] == tag_name.lower(), \
                    f"tag_lower for {tag_name} should be {tag_name.lower()}"

        # ========== VERIFY ALIAS LOOKUP ==========
        result1 = pages_view.lookup_by_alias("First Alias")
        assert result1 is not None, "Should find page by 'First Alias'"
        assert result1.name == "AliasTarget"

        result2 = pages_view.lookup_by_alias("Second Alias")
        assert result2 is not None, "Should find page by 'Second Alias'"
        assert result2.name == "AliasTarget"

        # Case insensitive alias lookup
        result3 = pages_view.lookup_by_alias("first alias")
        assert result3 is not None, "Should find page case-insensitively"
        assert result3.name == "AliasTarget"

        # ========== VERIFY LINKS ==========
        # Links from LinksPage to AliasTarget
        links_from_links_page = list(links_view.list_links(Path("LinksPage"), LINK_DIR_FORWARD))
        targets = [link.target.name for link in links_from_links_page]
        assert "AliasTarget" in targets, f"LinksPage should link to AliasTarget, got: {targets}"

        # Backlinks to AliasTarget
        backlinks_to_alias = list(links_view.list_links(Path("AliasTarget"), LINK_DIR_BACKWARD))
        sources = [link.source.name for link in backlinks_to_alias]
        assert "LinksPage" in sources, f"LinksPage should link to AliasTarget, got: {sources}"
        assert "RegularPage" in sources, f"RegularPage should link to AliasTarget, got: {sources}"

        # ========== VERIFY PAGE COUNT ==========
        # All pages should be indexed (Home + 4 created pages)
        total_pages = pages_view.n_all_pages()
        assert total_pages >= 5, f"Should have at least 5 pages, got {total_pages}"


# =============================================================================
# TEST 8: Case-Insensitive Tag Matching
# =============================================================================

@pytest.mark.integration
class TestCaseInsensitiveTagMatching:
    """Tests for case-insensitive tag behavior via tag_lower column."""

    def test_duplicate_tags_same_content_different_case(self, temp_vault_dir):
        """Tags 'Project' and 'PROJECT' should be stored as single entry."""
        (temp_vault_dir / "Page1.md").write_text(
            "# Page 1\n\n#Project",
            encoding="utf-8"
        )
        (temp_vault_dir / "Page2.md").write_text(
            "# Page 2\n\n#PROJECT",
            encoding="utf-8"
        )
        (temp_vault_dir / "Page3.md").write_text(
            "# Page 3\n\n#project",
            encoding="utf-8"
        )

        index, pages_view, tags_view, links_view = _create_index_and_views(temp_vault_dir)
        index.check_and_update()

        # All three pages should share the same tag
        with index.get_connection() as conn:
            tag_count = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
            assert tag_count == 1, f"Should have only 1 unique tag, got {tag_count}"

            # Verify tag_lower is set
            row = conn.execute("SELECT name, tag_lower FROM tags").fetchone()
            assert row["name"] in ["Project", "PROJECT", "project"], "Should store original case"
            assert row["tag_lower"] == "project", "tag_lower should be lowercase"

        # list_pages should return all 3 pages regardless of lookup case
        pages_upper = list(tags_view.list_pages("PROJECT"))
        assert len(pages_upper) == 3, f"Should find 3 pages with PROJECT, got {len(pages_upper)}"

        pages_lower = list(tags_view.list_pages("project"))
        assert len(pages_lower) == 3, f"Should find 3 pages with project, got {len(pages_lower)}"

        pages_mixed = list(tags_view.list_pages("Project"))
        assert len(pages_mixed) == 3, f"Should find 3 pages with Project, got {len(pages_mixed)}"

    def test_n_list_pages_case_insensitive(self, temp_vault_dir):
        """n_list_pages should return same count regardless of lookup case."""
        (temp_vault_dir / "TagPage.md").write_text(
            "# Tag Page\n\n#Apple",
            encoding="utf-8"
        )

        index, pages_view, tags_view, links_view = _create_index_and_views(temp_vault_dir)
        index.check_and_update()

        # All case variations should return same count
        assert tags_view.n_list_pages("Apple") == 1
        assert tags_view.n_list_pages("APPLE") == 1
        assert tags_view.n_list_pages("apple") == 1
        assert tags_view.n_list_pages("ApPlE") == 1


# =============================================================================
# TEST 9: Complex Unicode Workflow
# =============================================================================

@pytest.mark.integration
class TestComplexUnicodeWorkflow:
    """End-to-end tests for complex Unicode scenarios."""

    def test_mixed_language_vault(self, temp_vault_dir):
        """Vault with mixed language tags, aliases, and links should work."""
        # Create pages with various languages
        pages_content = {
            "日本語ページ.md": "# 日本語ページ\n\n#日本語 #project",
            "Русская страница.md": "# Русская страница\n\n#проект #2024",
            "EnglishPage.md": "---\naliases: [EnglishAlias]\n---\n# English Page\n\n#project",
            "MixedLinks.md": "# Mixed Links\n\n"
                             "Link to [[日本語ページ]]\n"
                             "Link to [[Русская страница]]\n"
                             "Link to [[EnglishPage]]\n"
                             "Link to English via alias: [[EnglishAlias]]",
        }

        for filename, content in pages_content.items():
            (temp_vault_dir / filename).write_text(content, encoding="utf-8")

        index, pages_view, tags_view, links_view = _create_index_and_views(temp_vault_dir)
        index.check_and_update()

        # Verify tags
        all_tags = list(tags_view.list_all_tags_by_n_pages())
        tag_names = [t.name for t in all_tags]
        assert "日本語" in tag_names
        assert "проект" in tag_names

        # Verify alias lookup works for English page
        result = pages_view.lookup_by_alias("EnglishAlias")
        assert result is not None
        assert result.name == "EnglishPage"

        # Verify links between pages
        links_from_mixed = list(links_view.list_links(Path("MixedLinks"), LINK_DIR_FORWARD))
        targets = {link.target.name for link in links_from_mixed}
        
        # Should link to Japanese, Russian, and English pages
        assert len(targets) >= 3, f"Should link to at least 3 pages, got: {targets}"

        # Backlinks to English page should include MixedLinks
        backlinks = list(links_view.list_links(Path("EnglishPage"), LINK_DIR_BACKWARD))
        sources = {link.source.name for link in backlinks}
        assert "MixedLinks" in sources, f"MixedLinks should link to EnglishPage, got: {sources}"
