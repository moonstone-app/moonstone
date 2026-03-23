# -*- coding: utf-8 -*-
"""Tests for alias storage during page indexing in Index.

Verifies:
1. Aliases are stored correctly during page indexing via profile.extract_aliases()
2. name_lower column stores lowercase version for case-insensitive lookup
3. Case handling: "MyAlias" stored as name="MyAlias", name_lower="myalias"
4. Duplicate handling: INSERT OR IGNORE prevents duplicate alias errors
5. Integration: Aliases deleted when page removed, cleared during full rebuild
6. Profile compatibility: Profiles without extract_aliases() work without errors
"""

import os
import sqlite3

import pytest

from moonstone.notebook.page import Path


@pytest.fixture
def temp_notebook_dir(tmp_path):
    """Create a temporary notebook directory with config."""
    notebook_dir = tmp_path / "test_notebook"
    notebook_dir.mkdir()

    # Create notebook.moon config
    (notebook_dir / "notebook.moon").write_text(
        "[notebook]\n"
        "name = Test Notebook\n"
        "home = Home\n"
    )

    # Create a minimal home page
    (notebook_dir / "Home.md").write_text("# Home\n\nWelcome!")

    return notebook_dir


@pytest.fixture
def obsidian_notebook_dir(tmp_path):
    """Create a temporary Obsidian-style notebook directory."""
    notebook_dir = tmp_path / "obsidian_notebook"
    notebook_dir.mkdir()

    # Create .obsidian folder for detection
    obsidian_dir = notebook_dir / ".obsidian"
    obsidian_dir.mkdir()

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


# =============================================================================
# TEST 1: Alias storage during page indexing
# =============================================================================

@pytest.mark.unit
class TestAliasStorageDuringIndexing:
    """Tests that aliases are stored correctly when pages are indexed."""

    def test_aliases_stored_during_indexing(self, obsidian_notebook_dir):
        """Page with aliases in frontmatter should store them in aliases table."""
        from moonstone.profiles.obsidian import ObsidianProfile

        profile = ObsidianProfile()

        # Create page with aliases
        (obsidian_notebook_dir / "TestPage.md").write_text("""---
aliases: [First Alias, Second Alias]
---
# Test Page
Content here.
""")

        index = _create_index(obsidian_notebook_dir, profile=profile)
        index.check_and_update()

        with index.get_connection() as conn:
            # Get the page id
            page_id = conn.execute(
                "SELECT id FROM pages WHERE name = ?", ("TestPage",)
            ).fetchone()[0]

            # Verify aliases are stored
            aliases = conn.execute(
                "SELECT name, name_lower FROM aliases WHERE page = ? ORDER BY name",
                (page_id,)
            ).fetchall()

            assert len(aliases) == 2, f"Expected 2 aliases, got {len(aliases)}"
            assert aliases[0]["name"] == "First Alias"
            assert aliases[0]["name_lower"] == "first alias"
            assert aliases[1]["name"] == "Second Alias"
            assert aliases[1]["name_lower"] == "second alias"

    def test_name_lower_has_lowercase_version(self, obsidian_notebook_dir):
        """name_lower column should have lowercase version of alias."""
        from moonstone.profiles.obsidian import ObsidianProfile

        profile = ObsidianProfile()

        # Create page with mixed-case alias
        (obsidian_notebook_dir / "MyPage.md").write_text("""---
aliases: [MyAlias]
---
# My Page
""")

        index = _create_index(obsidian_notebook_dir, profile=profile)
        index.check_and_update()

        with index.get_connection() as conn:
            alias_row = conn.execute(
                "SELECT name, name_lower FROM aliases WHERE page = (SELECT id FROM pages WHERE name = ?)",
                ("MyPage",)
            ).fetchone()

            assert alias_row["name"] == "MyAlias"
            assert alias_row["name_lower"] == "myalias"

    def test_multiple_aliases_different_casing(self, obsidian_notebook_dir):
        """Multiple aliases with different casing should each be stored correctly.
        
        Note: The unique index is on (page, name_lower), so aliases that differ
        only in case will be deduplicated when lowercased. We use aliases that
        remain distinct after lowercasing.
        """
        from moonstone.profiles.obsidian import ObsidianProfile

        profile = ObsidianProfile()

        # Create page with multiple aliases of different cases
        # Using aliases that remain distinct when lowercased
        (obsidian_notebook_dir / "MultiCase.md").write_text("""---
aliases:
  - UPPERCASE
  - lowercase
  - Title Case
  - another one
---
# Multi Case Page
""")

        index = _create_index(obsidian_notebook_dir, profile=profile)
        index.check_and_update()

        with index.get_connection() as conn:
            page_id = conn.execute(
                "SELECT id FROM pages WHERE name = ?", ("MultiCase",)
            ).fetchone()[0]

            aliases = conn.execute(
                "SELECT name, name_lower FROM aliases WHERE page = ? ORDER BY name",
                (page_id,)
            ).fetchall()

            assert len(aliases) == 4
            # Each should preserve original name and have lowercase version
            for alias in aliases:
                assert alias["name_lower"] == alias["name"].lower()


# =============================================================================
# TEST 2: Case handling
# =============================================================================

@pytest.mark.unit
class TestAliasCaseHandling:
    """Tests for proper case handling in alias storage."""

    def test_mixed_case_alias_stored_correctly(self, obsidian_notebook_dir):
        """MyAlias should be stored as name='MyAlias', name_lower='myalias'."""
        from moonstone.profiles.obsidian import ObsidianProfile

        profile = ObsidianProfile()

        (obsidian_notebook_dir / "Page.md").write_text("""---
aliases: [MyAlias]
---
# Page
""")

        index = _create_index(obsidian_notebook_dir, profile=profile)
        index.check_and_update()

        with index.get_connection() as conn:
            row = conn.execute(
                "SELECT name, name_lower FROM aliases"
            ).fetchone()

            assert row["name"] == "MyAlias"
            assert row["name_lower"] == "myalias"

    def test_all_caps_alias_stored_correctly(self, obsidian_notebook_dir):
        """ALLCAPS should be stored as name='ALLCAPS', name_lower='allcaps'."""
        from moonstone.profiles.obsidian import ObsidianProfile

        profile = ObsidianProfile()

        (obsidian_notebook_dir / "Caps.md").write_text("""---
aliases: [ALLCAPS]
---
# Caps
""")

        index = _create_index(obsidian_notebook_dir, profile=profile)
        index.check_and_update()

        with index.get_connection() as conn:
            row = conn.execute(
                "SELECT name, name_lower FROM aliases"
            ).fetchone()

            assert row["name"] == "ALLCAPS"
            assert row["name_lower"] == "allcaps"


# =============================================================================
# TEST 3: Duplicate handling
# =============================================================================

@pytest.mark.unit
class TestAliasDuplicateHandling:
    """Tests for duplicate alias handling."""

    def test_duplicate_alias_same_page_no_error(self, obsidian_notebook_dir):
        """Same alias appearing twice on same page should not cause error."""
        from moonstone.profiles.obsidian import ObsidianProfile

        profile = ObsidianProfile()

        # Create page with duplicate aliases in frontmatter
        (obsidian_notebook_dir / "DupPage.md").write_text("""---
aliases: [SameAlias, SameAlias]
---
# Dup Page
""")

        index = _create_index(obsidian_notebook_dir, profile=profile)

        # Should not raise any error
        try:
            index.check_and_update()
        except sqlite3.IntegrityError:
            pytest.fail("Duplicate alias caused IntegrityError")

        with index.get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
            # Should only have one (INSERT OR IGNORE)
            assert count == 1

    def test_insert_or_ignore_handles_duplicates(self, obsidian_notebook_dir):
        """INSERT OR IGNORE should prevent duplicate (page, name_lower) errors."""
        from moonstone.profiles.obsidian import ObsidianProfile

        profile = ObsidianProfile()

        (obsidian_notebook_dir / "Page.md").write_text("""---
aliases: [TestAlias]
---
# Page
""")

        index = _create_index(obsidian_notebook_dir, profile=profile)
        index.check_and_update()

        with index.get_connection() as conn:
            page_id = conn.execute("SELECT id FROM pages WHERE name = ?", ("Page",)).fetchone()[0]

            # First insert should succeed
            conn.execute(
                "INSERT OR IGNORE INTO aliases (page, name, name_lower) VALUES (?, ?, ?)",
                (page_id, "TestAlias", "testalias")
            )
            conn.commit()

            # Second insert with same (page, name_lower) should be ignored
            conn.execute(
                "INSERT OR IGNORE INTO aliases (page, name, name_lower) VALUES (?, ?, ?)",
                (page_id, "TESTALIAS", "testalias")  # Same name_lower, different case name
            )
            conn.commit()

            count = conn.execute("SELECT COUNT(*) FROM aliases WHERE page = ?", (page_id,)).fetchone()[0]
            assert count == 1, "Duplicate should be ignored, not inserted"


# =============================================================================
# TEST 4: Integration - Aliases deleted when page removed
# =============================================================================

@pytest.mark.unit
class TestAliasDeletionOnPageRemoval:
    """Tests that aliases are properly deleted when pages are removed."""

    def test_aliases_deleted_when_page_removed(self, obsidian_notebook_dir):
        """remove_page() should delete all aliases for that page."""
        from moonstone.profiles.obsidian import ObsidianProfile

        profile = ObsidianProfile()

        # Create page with aliases
        (obsidian_notebook_dir / "RemoveMe.md").write_text("""---
aliases: [Alias1, Alias2, Alias3]
---
# Remove Me
""")

        index = _create_index(obsidian_notebook_dir, profile=profile)
        index.check_and_update()

        with index.get_connection() as conn:
            page_id = conn.execute(
                "SELECT id FROM pages WHERE name = ?", ("RemoveMe",)
            ).fetchone()[0]

            # Verify aliases exist
            alias_count = conn.execute(
                "SELECT COUNT(*) FROM aliases WHERE page = ?", (page_id,)
            ).fetchone()[0]
            assert alias_count == 3

        # Remove the page
        index.remove_page(Path("RemoveMe"))

        with index.get_connection() as conn:
            # Verify aliases are gone
            remaining = conn.execute(
                "SELECT COUNT(*) FROM aliases WHERE page = ?", (page_id,)
            ).fetchone()[0]
            assert remaining == 0, "Aliases should be deleted when page is removed"


# =============================================================================
# TEST 5: Integration - Aliases cleared during full rebuild
# =============================================================================

@pytest.mark.unit
class TestAliasClearingOnFullRebuild:
    """Tests that aliases are cleared during check_and_update() rebuild."""

    def test_aliases_cleared_during_rebuild(self, obsidian_notebook_dir):
        """check_and_update() should clear all aliases before rebuilding.
        
        This test verifies that manually-added aliases (not from file content)
        are cleared during a full rebuild. Aliases that come from file content
        will be re-populated after the clear, but manually inserted ones will be gone.
        """
        from moonstone.profiles.obsidian import ObsidianProfile

        profile = ObsidianProfile()

        # Create page WITHOUT aliases in frontmatter
        (obsidian_notebook_dir / "Page.md").write_text("""---
title: Just a Page
---
# Page
Content without aliases.
""")

        index = _create_index(obsidian_notebook_dir, profile=profile)
        index.check_and_update()

        # Verify no aliases initially
        with index.get_connection() as conn:
            count_before = conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
            assert count_before == 0

        # Manually add aliases
        with index.get_connection() as conn:
            page_id = conn.execute("SELECT id FROM pages WHERE name = ?", ("Page",)).fetchone()[0]
            conn.execute(
                "INSERT INTO aliases (page, name, name_lower) VALUES (?, ?, ?)",
                (page_id, "ManualAlias", "manualalias")
            )
            conn.commit()

            manual_count = conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
            assert manual_count == 1

        # Full rebuild
        index.check_and_update()

        with index.get_connection() as conn:
            after_count = conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
            assert after_count == 0, f"Manually added aliases should be cleared during rebuild, got {after_count}"


# =============================================================================
# TEST 6: Profile compatibility - no extract_aliases method
# =============================================================================

@pytest.mark.unit
class TestProfileCompatibility:
    """Tests that profiles without extract_aliases() work without errors."""

    def test_profile_without_extract_aliases_no_error(self, temp_notebook_dir):
        """Profile without extract_aliases() should not cause errors during indexing."""
        # MoonstoneProfile does not have extract_aliases
        index = _create_index(temp_notebook_dir)  # Uses default MoonstoneProfile

        # Create page with frontmatter (simulating content with metadata)
        (temp_notebook_dir / "Test.md").write_text("""---
title: Test Page
---
# Test
Content.
""")

        # Should not raise any error
        try:
            index.check_and_update()
        except AttributeError as e:
            if "extract_aliases" in str(e):
                pytest.fail(f"Profile without extract_aliases caused error: {e}")
            raise

        # Verify page was indexed
        with index.get_connection() as conn:
            page = conn.execute("SELECT name FROM pages WHERE name = ?", ("Test",)).fetchone()
            assert page is not None, "Page should be indexed"

    def test_no_aliases_table_touched_without_method(self, temp_notebook_dir):
        """When profile has no extract_aliases, aliases table should remain empty."""
        index = _create_index(temp_notebook_dir)  # MoonstoneProfile
        index.check_and_update()

        with index.get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
            assert count == 0, "Aliases table should be empty when profile has no extract_aliases"

    def test_hasattr_check_prevents_error(self, obsidian_notebook_dir):
        """Code uses hasattr() to check for extract_aliases before calling."""
        from moonstone.profiles.obsidian import ObsidianProfile

        profile = ObsidianProfile()

        # Verify profile has extract_aliases
        assert hasattr(profile, "extract_aliases")

        # But verify MoonstoneProfile does not
        from moonstone.profiles.moonstone_profile import MoonstoneProfile
        moonstone = MoonstoneProfile()
        assert not hasattr(moonstone, "extract_aliases")


# =============================================================================
# TEST 7: Update page also updates aliases
# =============================================================================

@pytest.mark.unit
class TestAliasUpdateOnPageUpdate:
    """Tests that updating a page correctly refreshes its aliases."""

    def test_update_page_refreshes_aliases(self, obsidian_notebook_dir):
        """update_page() should refresh aliases when page content changes."""
        from moonstone.profiles.obsidian import ObsidianProfile

        profile = ObsidianProfile()

        # Create page with initial aliases
        (obsidian_notebook_dir / "UpdateTest.md").write_text("""---
aliases: [OldAlias]
---
# Update Test
""")

        index = _create_index(obsidian_notebook_dir, profile=profile)
        index.check_and_update()

        # Verify initial alias
        with index.get_connection() as conn:
            page_id = conn.execute("SELECT id FROM pages WHERE name = ?", ("UpdateTest",)).fetchone()[0]
            initial = conn.execute("SELECT name FROM aliases WHERE page = ?", (page_id,)).fetchall()
            assert len(initial) == 1
            assert initial[0]["name"] == "OldAlias"

        # Update the page with different aliases
        (obsidian_notebook_dir / "UpdateTest.md").write_text("""---
aliases: [NewAlias1, NewAlias2]
---
# Update Test
Updated content.
""")

        index.update_page(Path("UpdateTest"))

        with index.get_connection() as conn:
            # Old alias should be gone, new aliases should exist
            current = conn.execute("SELECT name FROM aliases WHERE page = ? ORDER BY name", (page_id,)).fetchall()
            assert len(current) == 2
            assert current[0]["name"] == "NewAlias1"
            assert current[1]["name"] == "NewAlias2"

            # Old alias should not exist
            old_exists = conn.execute(
                "SELECT COUNT(*) FROM aliases WHERE page = ? AND name = ?",
                (page_id, "OldAlias")
            ).fetchone()[0]
            assert old_exists == 0, "Old alias should be removed after update"
