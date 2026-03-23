# -*- coding: utf-8 -*-
"""Tests for PagesView.lookup_by_alias() method.

Verifies:
1. Basic alias lookup returns correct PageInfo
2. Case-insensitive alias matching works
3. Non-existent aliases return None
4. Empty/whitespace aliases return None
5. Edge cases (Unicode, special characters)
"""

import os
import pytest

from moonstone.notebook.index.pages import PagesView


@pytest.fixture
def temp_notebook_dir(tmp_path):
    """Create a temporary notebook directory with pages and aliases."""
    notebook_dir = tmp_path / "test_notebook"
    notebook_dir.mkdir()

    # Create notebook.moon config
    (notebook_dir / "notebook.moon").write_text(
        "[notebook]\n"
        "name = Test Notebook\n"
        "home = Home\n"
    )

    # Create pages with aliases in frontmatter
    (notebook_dir / "Home.md").write_text("# Home\n\nWelcome!")
    
    # Page with an alias
    (notebook_dir / "MyPage.md").write_text(
        "---\naliases:\n  - Myalias\n---\n# My Page\n\nContent here."
    )
    
    # Page with multiple aliases
    (notebook_dir / "MultiAlias.md").write_text(
        "---\naliases:\n  - Alias1\n  - Alias2\n  - ALIAS3\n---\n# Multi Alias Page\n\nMultiple aliases here."
    )
    
    # Page with no aliases
    (notebook_dir / "NoAlias.md").write_text("# No Alias Page\n\nNo aliases here.")

    return notebook_dir


def _create_index_and_pages(notebook_dir, profile=None):
    """Create an Index instance and PagesView for testing."""
    from moonstone.notebook.index import Index
    from moonstone.notebook.layout import FilesLayout
    from moonstone.profiles.obsidian import ObsidianProfile

    if profile is None:
        profile = ObsidianProfile()

    db_path = os.path.join(notebook_dir, "index.db")
    layout = FilesLayout(
        notebook_dir,
        default_extension=profile.file_extension,
        default_format=profile.default_format,
        use_filename_spaces=profile.use_filename_spaces,
        profile=profile,
    )

    index = Index(
        db_path=db_path,
        layout=layout,
        root_folder=notebook_dir,
        profile=profile,
    )
    
    # Create PagesView from the index's database
    pages_view = PagesView.new_from_index(index)
    
    return index, pages_view


# =============================================================================
# TEST 1: Basic alias lookup
# =============================================================================

@pytest.mark.unit
class TestLookupByAliasBasic:
    """Tests for basic alias lookup functionality."""

    def test_lookup_by_alias_returns_pageinfo(self, temp_notebook_dir):
        """lookup_by_alias('Myalias') should return PageInfo for MyPage."""
        index, pages_view = _create_index_and_pages(temp_notebook_dir)
        index.check_and_update()

        result = pages_view.lookup_by_alias("Myalias")

        assert result is not None, "Should find page by alias 'Myalias'"
        assert result.name == "MyPage", f"Expected name 'MyPage', got '{result.name}'"

    def test_lookup_by_alias_original_case(self, temp_notebook_dir):
        """lookup_by_alias('Myalias') should find page regardless of case used in alias."""
        index, pages_view = _create_index_and_pages(temp_notebook_dir)
        index.check_and_update()

        # Original case: "Myalias"
        result = pages_view.lookup_by_alias("Myalias")
        assert result is not None
        assert result.name == "MyPage"

    def test_lookup_by_alias_uppercase(self, temp_notebook_dir):
        """lookup_by_alias('MYALIAS') should find page with alias 'Myalias'."""
        index, pages_view = _create_index_and_pages(temp_notebook_dir)
        index.check_and_update()

        result = pages_view.lookup_by_alias("MYALIAS")

        assert result is not None, "Should find page with alias 'Myalias' using 'MYALIAS'"
        assert result.name == "MyPage", f"Expected name 'MyPage', got '{result.name}'"

    def test_lookup_by_alias_mixed_case(self, temp_notebook_dir):
        """lookup_by_alias('MYAlias') should find page with alias 'Myalias'."""
        index, pages_view = _create_index_and_pages(temp_notebook_dir)
        index.check_and_update()

        result = pages_view.lookup_by_alias("MYAlias")

        assert result is not None, "Should find page with alias 'Myalias' using 'MYAlias'"
        assert result.name == "MyPage", f"Expected name 'MyPage', got '{result.name}'"

    def test_lookup_by_alias_all_lowercase(self, temp_notebook_dir):
        """lookup_by_alias('myalias') should find page with alias 'Myalias'."""
        index, pages_view = _create_index_and_pages(temp_notebook_dir)
        index.check_and_update()

        result = pages_view.lookup_by_alias("myalias")

        assert result is not None, "Should find page with alias 'Myalias' using 'myalias'"
        assert result.name == "MyPage", f"Expected name 'MyPage', got '{result.name}'"


# =============================================================================
# TEST 2: Case-insensitive matching
# =============================================================================

@pytest.mark.unit
class TestLookupByAliasCaseInsensitive:
    """Tests for case-insensitive alias matching."""

    def test_lookup_by_alias_multiple_aliases_different_cases(self, temp_notebook_dir):
        """lookup_by_alias should find page regardless of which alias is used or its case."""
        index, pages_view = _create_index_and_pages(temp_notebook_dir)
        index.check_and_update()

        # First alias, original case
        result = pages_view.lookup_by_alias("Alias1")
        assert result is not None, "Should find page by 'Alias1'"
        assert result.name == "MultiAlias"

        # First alias, uppercase
        result = pages_view.lookup_by_alias("ALIAS1")
        assert result is not None, "Should find page by 'ALIAS1'"
        assert result.name == "MultiAlias"

        # Second alias
        result = pages_view.lookup_by_alias("Alias2")
        assert result is not None, "Should find page by 'Alias2'"
        assert result.name == "MultiAlias"

        # Third alias (already uppercase in frontmatter)
        result = pages_view.lookup_by_alias("alias3")
        assert result is not None, "Should find page by 'alias3'"
        assert result.name == "MultiAlias"

        result = pages_view.lookup_by_alias("ALIAS3")
        assert result is not None, "Should find page by 'ALIAS3'"
        assert result.name == "MultiAlias"


# =============================================================================
# TEST 3: Non-existent aliases
# =============================================================================

@pytest.mark.unit
class TestLookupByAliasNonExistent:
    """Tests for non-existent alias handling."""

    def test_lookup_by_alias_returns_none_for_nonexistent(self, temp_notebook_dir):
        """lookup_by_alias('OtherAlias') should return None for non-existent alias."""
        index, pages_view = _create_index_and_pages(temp_notebook_dir)
        index.check_and_update()

        result = pages_view.lookup_by_alias("OtherAlias")

        assert result is None, f"Should return None for non-existent alias 'OtherAlias', got {result}"

    def test_lookup_by_alias_returns_none_for_page_without_alias(self, temp_notebook_dir):
        """lookup_by_alias should return None when querying alias that belongs to page with no aliases."""
        index, pages_view = _create_index_and_pages(temp_notebook_dir)
        index.check_and_update()

        # NoAlias page has no aliases
        result = pages_view.lookup_by_alias("NoAlias")
        assert result is None, "Should return None for alias on page with no aliases"

    def test_lookup_by_alias_returns_none_for_completely_nonexistent(self, temp_notebook_dir):
        """lookup_by_alias should return None for alias that doesn't exist at all."""
        index, pages_view = _create_index_and_pages(temp_notebook_dir)
        index.check_and_update()

        result = pages_view.lookup_by_alias("CompletelyFakeAlias12345")
        assert result is None


# =============================================================================
# TEST 4: Empty and whitespace inputs
# =============================================================================

@pytest.mark.unit
class TestLookupByAliasEdgeCases:
    """Tests for edge cases with empty/whitespace inputs."""

    def test_lookup_by_alias_empty_string_returns_none(self, temp_notebook_dir):
        """lookup_by_alias('') should return None."""
        index, pages_view = _create_index_and_pages(temp_notebook_dir)
        index.check_and_update()

        result = pages_view.lookup_by_alias("")
        assert result is None, "Empty string should return None"

    def test_lookup_by_alias_whitespace_only_returns_none(self, temp_notebook_dir):
        """lookup_by_alias('   ') should return None (whitespace-only)."""
        index, pages_view = _create_index_and_pages(temp_notebook_dir)
        index.check_and_update()

        result = pages_view.lookup_by_alias("   ")
        assert result is None, "Whitespace-only string should return None"

    def test_lookup_by_alias_none_returns_none(self, temp_notebook_dir):
        """lookup_by_alias(None) should return None."""
        index, pages_view = _create_index_and_pages(temp_notebook_dir)
        index.check_and_update()

        result = pages_view.lookup_by_alias(None)
        assert result is None, "None input should return None"


# =============================================================================
# TEST 5: Unicode and special character handling
# =============================================================================

@pytest.mark.unit
class TestLookupByAliasUnicode:
    """Tests for Unicode alias handling."""

    def test_lookup_by_alias_unicode_alias(self, temp_notebook_dir):
        """lookup_by_alias should handle Unicode aliases."""
        index, pages_view = _create_index_and_pages(temp_notebook_dir)
        index.check_and_update()

        # Insert Unicode alias directly
        with index.get_connection() as conn:
            cursor = conn.execute("SELECT id FROM pages WHERE name = ?", ("Home",))
            home_id = cursor.fetchone()[0]
            conn.execute(
                "INSERT INTO aliases (page, name, name_lower) VALUES (?, ?, ?)",
                (home_id, "日本語", "日本語")
            )
            conn.commit()

        # Should find with exact Unicode
        result = pages_view.lookup_by_alias("日本語")
        assert result is not None, "Should find page with Unicode alias"
        assert result.name == "Home"


# =============================================================================
# TEST 6: Returns PageInfo object
# =============================================================================

@pytest.mark.unit
class TestLookupByAliasReturnsPageInfo:
    """Tests that lookup_by_alias returns proper PageInfo object."""

    def test_lookup_by_alias_returns_pageinfo_with_correct_attributes(self, temp_notebook_dir):
        """lookup_by_alias should return PageInfo with all expected attributes."""
        index, pages_view = _create_index_and_pages(temp_notebook_dir)
        index.check_and_update()

        result = pages_view.lookup_by_alias("Myalias")

        assert result is not None
        assert hasattr(result, 'name')
        assert hasattr(result, 'basename')
        assert hasattr(result, 'hascontent')
        assert hasattr(result, 'haschildren')
        assert hasattr(result, 'id')
        # Verify it's the correct page
        assert result.name == "MyPage"
        assert result.basename == "MyPage"
        assert result.hascontent is True
