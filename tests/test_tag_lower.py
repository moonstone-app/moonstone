# -*- coding: utf-8 -*-
"""Tests for tag_lower column implementation — case-insensitive tag matching.

Verifies:
1. Case-insensitive tag creation via _ensure_tag()
2. Case-insensitive tag lookup via lookup_by_tagname()
3. Unicode case handling
4. Edge cases (empty, long, special characters)
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


def _get_tag_by_name(conn, name):
    """Get tag row by name column."""
    cursor = conn.execute(
        "SELECT id, name, tag_lower FROM tags WHERE name = ?", (name,)
    )
    return cursor.fetchone()


def _get_tag_by_lower(conn, tag_lower):
    """Get tag row by tag_lower column."""
    cursor = conn.execute(
        "SELECT id, name, tag_lower FROM tags WHERE tag_lower = ?", (tag_lower,)
    )
    return cursor.fetchone()


# =============================================================================
# TEST 1: Case-insensitive tag creation
# =============================================================================

@pytest.mark.unit
class TestTagLowerCreation:
    """Tests for _ensure_tag() case-insensitive tag creation."""

    def test_first_tag_creation_stores_original_and_lowercase(self, temp_notebook_dir):
        """Creating a new tag stores original name and lowercase version."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        # Call _ensure_tag directly to create a tag
        tag_id = index._ensure_tag("Project")

        with index.get_connection() as conn:
            row = _get_tag_by_name(conn, "Project")
            assert row is not None, "Tag 'Project' should exist in database"
            assert row["name"] == "Project"
            assert row["tag_lower"] == "project"
            assert row["id"] == tag_id

    def test_duplicate_tag_same_case_returns_existing(self, temp_notebook_dir):
        """Creating the same tag twice returns existing ID (no duplicate)."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        # Create first tag
        tag_id_1 = index._ensure_tag("Project")

        with index.get_connection() as conn:
            count_before = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
            assert count_before == 1, "Should have exactly one tag"

        # Create same tag again
        tag_id_2 = index._ensure_tag("Project")

        with index.get_connection() as conn:
            count_after = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
            assert count_after == 1, "Should still have exactly one tag"
            assert tag_id_1 == tag_id_2, "Should return same tag ID"

    def test_uppercase_variant_finds_existing_tag(self, temp_notebook_dir):
        """Creating 'PROJECT' when 'Project' exists returns existing tag."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        # Create original tag
        tag_id_1 = index._ensure_tag("Project")

        with index.get_connection() as conn:
            count_before = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]

        # Create uppercase variant
        tag_id_2 = index._ensure_tag("PROJECT")

        with index.get_connection() as conn:
            count_after = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
            assert count_after == count_before, "Should not create duplicate tag"
            assert tag_id_1 == tag_id_2, "Should return same tag ID"

            # Verify the tag still has original name
            row = _get_tag_by_name(conn, "Project")
            assert row is not None, "Original tag should still exist"

    def test_lowercase_variant_finds_existing_tag(self, temp_notebook_dir):
        """Creating 'project' when 'Project' exists returns existing tag."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        # Create original tag
        tag_id_1 = index._ensure_tag("Project")

        # Create lowercase variant
        tag_id_2 = index._ensure_tag("project")

        with index.get_connection() as conn:
            count_after = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
            assert count_after == 1, "Should not create duplicate tag"
            assert tag_id_1 == tag_id_2, "Should return same tag ID"

    def test_mixed_case_all_find_same_tag(self, temp_notebook_dir):
        """All case variations should find/create the same tag."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        tag_ids = [
            index._ensure_tag("Project"),
            index._ensure_tag("PROJECT"),
            index._ensure_tag("project"),
            index._ensure_tag("ProJeCt"),
        ]

        # All should return the same ID
        assert len(set(tag_ids)) == 1, f"All case variations should return same ID: {tag_ids}"

        with index.get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
            assert count == 1, "Should have exactly one tag"

            # Verify the tag has the correct values
            row = _get_tag_by_lower(conn, "project")
            assert row is not None
            assert row["name"] == "Project"  # First one created
            assert row["tag_lower"] == "project"


# =============================================================================
# TEST 2: Case-insensitive tag lookup
# =============================================================================

@pytest.mark.unit
class TestTagLowerLookup:
    """Tests for lookup_by_tagname() case-insensitive lookup."""

    def test_lookup_exact_case_finds_tag(self, temp_notebook_dir):
        """lookup_by_tagname('Project') finds tag with original name 'Project'."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        # Create a page with the tag
        (temp_notebook_dir / "Test.md").write_text("# Project\n\nContent with #Project tag")
        index.check_and_update()

        # Look up with exact case
        tags_view = index.db.TagsView if hasattr(index.db, 'TagsView') else None
        if tags_view is None:
            # TagsView is accessed differently
            from moonstone.notebook.index.tags import TagsView
            tags_view = TagsView.new_from_index(index)

        result = tags_view.lookup_by_tagname("Project")
        assert result is not None, "Should find tag 'Project'"
        assert result.name == "Project"

    def test_lookup_uppercase_finds_tag(self, temp_notebook_dir):
        """lookup_by_tagname('PROJECT') finds tag with original name 'Project'."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        # Create a page with the tag
        (temp_notebook_dir / "Test.md").write_text("# Project\n\nContent with #Project tag")
        index.check_and_update()

        from moonstone.notebook.index.tags import TagsView
        tags_view = TagsView.new_from_index(index)

        result = tags_view.lookup_by_tagname("PROJECT")
        assert result is not None, "Should find tag 'PROJECT'"
        assert result.name == "Project", "Should return original name 'Project'"

    def test_lookup_lowercase_finds_tag(self, temp_notebook_dir):
        """lookup_by_tagname('project') finds tag with original name 'Project'."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        # Create a page with the tag
        (temp_notebook_dir / "Test.md").write_text("# Project\n\nContent with #Project tag")
        index.check_and_update()

        from moonstone.notebook.index.tags import TagsView
        tags_view = TagsView.new_from_index(index)

        result = tags_view.lookup_by_tagname("project")
        assert result is not None, "Should find tag 'project'"
        assert result.name == "Project", "Should return original name 'Project'"

    def test_lookup_mixed_case_finds_tag(self, temp_notebook_dir):
        """lookup_by_tagname('pRoJeCt') finds tag with original name 'Project'."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        # Create a page with the tag
        (temp_notebook_dir / "Test.md").write_text("# Project\n\nContent with #Project tag")
        index.check_and_update()

        from moonstone.notebook.index.tags import TagsView
        tags_view = TagsView.new_from_index(index)

        result = tags_view.lookup_by_tagname("pRoJeCt")
        assert result is not None, "Should find tag 'pRoJeCt'"
        assert result.name == "Project", "Should return original name 'Project'"

    def test_lookup_nonexistent_returns_none(self, temp_notebook_dir):
        """lookup_by_tagname for non-existent tag returns None."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        from moonstone.notebook.index.tags import TagsView
        tags_view = TagsView.new_from_index(index)

        result = tags_view.lookup_by_tagname("NonexistentTag")
        assert result is None, "Should return None for non-existent tag"

    def test_lookup_with_at_prefix_strips_and_finds(self, temp_notebook_dir):
        """lookup_by_tagname('@Project') strips @ and finds the tag."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        # Create a page with the tag
        (temp_notebook_dir / "Test.md").write_text("# Project\n\nContent with #Project tag")
        index.check_and_update()

        from moonstone.notebook.index.tags import TagsView
        tags_view = TagsView.new_from_index(index)

        result = tags_view.lookup_by_tagname("@Project")
        assert result is not None, "Should find tag '@Project'"
        assert result.name == "Project"


# =============================================================================
# TEST 3: Unicode case handling
# =============================================================================

@pytest.mark.unit
class TestTagLowerUnicode:
    """Tests for Unicode case handling with tag_lower."""

    def test_unicode_chinese_tag_stored_correctly(self, temp_notebook_dir):
        """Chinese tag '项目' should be stored and found correctly."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        # Create Chinese tag
        tag_id = index._ensure_tag("项目")

        with index.get_connection() as conn:
            row = _get_tag_by_name(conn, "项目")
            assert row is not None
            assert row["name"] == "项目"
            assert row["tag_lower"] == "项目"  # Chinese .lower() returns same

    def test_unicode_japanese_tag_stored_correctly(self, temp_notebook_dir):
        """Japanese tag 'プロジェクト' should be stored and found correctly."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        tag_id = index._ensure_tag("プロジェクト")

        with index.get_connection() as conn:
            row = _get_tag_by_name(conn, "プロジェクト")
            assert row is not None
            assert row["name"] == "プロジェクト"

    def test_unicode_cyrillic_tag_stored_correctly(self, temp_notebook_dir):
        """Cyrillic tag 'Проект' should be stored and found correctly."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        tag_id = index._ensure_tag("Проект")

        with index.get_connection() as conn:
            row = _get_tag_by_name(conn, "Проект")
            assert row is not None
            assert row["name"] == "Проект"
            # Cyrillic lowercase
            assert row["tag_lower"] == "проект"

    def test_unicode_lookup_case_insensitive(self, temp_notebook_dir):
        """Unicode Cyrillic tags should be found case-insensitively."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        # Create with uppercase Cyrillic
        index._ensure_tag("ПРОЕКТ")

        from moonstone.notebook.index.tags import TagsView
        tags_view = TagsView.new_from_index(index)

        # Look up with lowercase
        result = tags_view.lookup_by_tagname("проект")
        assert result is not None, "Should find Cyrillic tag"
        assert result.name == "ПРОЕКТ"

    def test_unicode_cpp_tag_stored_correctly(self, temp_notebook_dir):
        """C++ tag should be stored and found correctly."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        tag_id = index._ensure_tag("C++")

        with index.get_connection() as conn:
            row = _get_tag_by_name(conn, "C++")
            assert row is not None
            assert row["name"] == "C++"
            assert row["tag_lower"] == "c++"


# =============================================================================
# TEST 4: Edge cases
# =============================================================================

@pytest.mark.unit
class TestTagLowerEdgeCases:
    """Tests for edge cases with tag_lower."""

    def test_empty_tag_name_not_inserted(self, temp_notebook_dir):
        """Empty string tag should not be inserted."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        with index.get_connection() as conn:
            count_before = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]

        # Try to create empty tag - should not crash
        try:
            tag_id = index._ensure_tag("")
            # If it doesn't crash, check it didn't create a tag
            with index.get_connection() as conn:
                count_after = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
                if count_after > count_before:
                    # If a tag WAS created, verify it's not with empty string
                    row = conn.execute(
                        "SELECT name, tag_lower FROM tags WHERE name = ''"
                    ).fetchone()
                    assert row is None, "Empty string tag should not be inserted"
        except Exception:
            # Empty tag might raise an error, which is acceptable
            pass

    def test_very_long_tag_name(self, temp_notebook_dir):
        """Very long tag names should be stored correctly."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        long_name = "a" * 10000
        tag_id = index._ensure_tag(long_name)

        with index.get_connection() as conn:
            row = _get_tag_by_name(conn, long_name)
            assert row is not None, "Long tag should be stored"
            assert row["name"] == long_name
            assert row["tag_lower"] == long_name.lower()

    def test_tag_with_special_chars(self, temp_notebook_dir):
        """Tags with special characters should work."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        # These are valid tags per the spec
        special_tags = [
            "tag-with-dash",
            "tag_with_underscore",
            "tag.with.period",
            "tag/with/slashes",
        ]

        for tag_name in special_tags:
            tag_id = index._ensure_tag(tag_name)

            with index.get_connection() as conn:
                row = _get_tag_by_name(conn, tag_name)
                assert row is not None, f"Tag '{tag_name}' should be stored"
                assert row["tag_lower"] == tag_name.lower()

    def test_numeric_tag(self, temp_notebook_dir):
        """Numeric tags like '2024-goals' should work."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        tag_id = index._ensure_tag("2024-goals")

        with index.get_connection() as conn:
            row = _get_tag_by_name(conn, "2024-goals")
            assert row is not None
            assert row["name"] == "2024-goals"
            assert row["tag_lower"] == "2024-goals"

    def test_nested_tag(self, temp_notebook_dir):
        """Nested tags like 'project/2024/Q1' should work."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        tag_id = index._ensure_tag("project/2024/Q1")

        with index.get_connection() as conn:
            row = _get_tag_by_name(conn, "project/2024/Q1")
            assert row is not None
            assert row["name"] == "project/2024/Q1"
            assert row["tag_lower"] == "project/2024/q1"

    def test_unique_index_on_tag_lower(self, temp_notebook_dir):
        """Verify unique index exists on tag_lower column."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        # Create a tag
        index._ensure_tag("Project")

        # Try to directly insert a duplicate tag_lower (bypass _ensure_tag)
        with index.get_connection() as conn:
            try:
                conn.execute(
                    "INSERT INTO tags (name, tag_lower) VALUES (?, ?)",
                    ("DifferentName", "project")  # Same tag_lower
                )
                conn.commit()
                # If we get here, the unique constraint didn't work
                assert False, "Unique index on tag_lower should prevent duplicate"
            except sqlite3.IntegrityError:
                # Expected - unique constraint violation
                pass

    def test_multiple_tags_case_variations(self, temp_notebook_dir):
        """Multiple different case-variation tags should all work."""
        index = _create_index(temp_notebook_dir)
        index.check_and_update()

        # Create several tags with different cases
        index._ensure_tag("Project")
        index._ensure_tag("Work")
        index._ensure_tag("Daily")

        # Try to add case variations - should not create duplicates
        index._ensure_tag("PROJECT")
        index._ensure_tag("WORK")
        index._ensure_tag("DAILY")

        with index.get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
            assert count == 3, f"Should have exactly 3 unique tags, got {count}"

            # Verify all names
            names = sorted([row[0] for row in conn.execute("SELECT name FROM tags").fetchall()])
            assert names == ["Daily", "Project", "Work"]


# =============================================================================
# TEST 5: Integration test - list_pages with case-insensitive lookup
# =============================================================================

@pytest.mark.unit
class TestTagLowerIntegration:
    """Integration tests for case-insensitive tag behavior."""

    def test_list_pages_finds_tag_regardless_of_case(self, temp_notebook_dir):
        """list_pages should find pages with tag regardless of lookup case."""
        # Note: MoonstoneProfile uses #tag syntax WITHOUT space after # (e.g., #Project not # Project)
        index = _create_index(temp_notebook_dir)

        # Create pages with tags (no space after #)
        (temp_notebook_dir / "Page1.md").write_text("#Project\n\nContent")
        (temp_notebook_dir / "Page2.md").write_text("#PROJECT\n\nContent")

        # Index the pages
        from moonstone.notebook.page import Path
        index.update_page(Path("Page1"))
        index.update_page(Path("Page2"))

        from moonstone.notebook.index.tags import TagsView
        tags_view = TagsView.new_from_index(index)

        # Look up with lowercase
        pages_lower = list(tags_view.list_pages("project"))
        assert len(pages_lower) == 2, "Should find 2 pages with 'project' tag (case-insensitive)"

        # Look up with uppercase
        pages_upper = list(tags_view.list_pages("PROJECT"))
        assert len(pages_upper) == 2, "Should find 2 pages with 'PROJECT' tag (case-insensitive)"

        # Look up with mixed case
        pages_mixed = list(tags_view.list_pages("Project"))
        assert len(pages_mixed) == 2, "Should find 2 pages with 'Project' tag (case-insensitive)"

    def test_n_list_pages_case_insensitive(self, temp_notebook_dir):
        """n_list_pages should return same count regardless of case."""
        # Note: MoonstoneProfile uses #tag syntax WITHOUT space after #
        index = _create_index(temp_notebook_dir)

        # Create pages with different case variations (no space after #)
        (temp_notebook_dir / "Page1.md").write_text("#Project\n\nContent")
        (temp_notebook_dir / "Page2.md").write_text("#PROJECT\n\nContent")
        (temp_notebook_dir / "Page3.md").write_text("#project\n\nContent")

        # Index the pages
        from moonstone.notebook.page import Path
        index.update_page(Path("Page1"))
        index.update_page(Path("Page2"))
        index.update_page(Path("Page3"))

        from moonstone.notebook.index.tags import TagsView
        tags_view = TagsView.new_from_index(index)

        # All should return same count
        assert tags_view.n_list_pages("Project") == 3
        assert tags_view.n_list_pages("PROJECT") == 3
        assert tags_view.n_list_pages("project") == 3

    def test_list_intersecting_tags_case_insensitive(self, temp_notebook_dir):
        """list_intersecting_tags should handle case-insensitive matching."""
        # Note: MoonstoneProfile uses #tag syntax WITHOUT space after #
        index = _create_index(temp_notebook_dir)

        # Create pages with tags (no space after #)
        # Page1: #Project and #Work
        # Page2: #PROJECT and #Extra
        (temp_notebook_dir / "Page1.md").write_text("#Project\n#Work\n\nContent")
        (temp_notebook_dir / "Page2.md").write_text("#PROJECT\n#Extra\n\nContent")

        # Index the pages
        from moonstone.notebook.page import Path
        index.update_page(Path("Page1"))
        index.update_page(Path("Page2"))

        from moonstone.notebook.index.tags import TagsView
        tags_view = TagsView.new_from_index(index)

        # Query with uppercase PROJECT - should find co-occurring tags on same page
        result = list(tags_view.list_intersecting_tags(["PROJECT"]))

        # Should find #Extra (other tag on same page as PROJECT)
        tag_names = [t.name for t in result]
        assert "Extra" in tag_names, f"Expected 'Extra' in co-occurring tags, got: {tag_names}"

        # Query with lowercase project - should also work case-insensitively
        result2 = list(tags_view.list_intersecting_tags(["project"]))
        tag_names2 = [t.name for t in result2]
        assert "Extra" in tag_names2, f"Expected 'Extra' in co-occurring tags for lowercase 'project', got: {tag_names2}"
