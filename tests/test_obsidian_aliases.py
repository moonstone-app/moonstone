#!/usr/bin/env python3
"""Tests for ObsidianProfile.extract_aliases() method.

Verifies correct handling of:
- Array format: aliases: [One, Two]
- YAML list format: multi-line list syntax
- Single string alias
- Mixed content with tags
- Missing aliases field
- Unicode aliases
- Empty input
"""

import pytest
import os
import sys

# Ensure moonstone is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moonstone.profiles.obsidian import ObsidianProfile


class TestExtractAliases:
    """Direct tests for ObsidianProfile.extract_aliases() method."""

    @pytest.fixture
    def profile(self):
        """Create a fresh ObsidianProfile instance."""
        return ObsidianProfile()

    # =========================================================================
    # HAPPY PATH: Array format
    # =========================================================================

    def test_array_format(self, profile):
        """Array format: aliases: [One, Two]"""
        text = """---
aliases: [One, Two]
---
# My Page
"""
        aliases = profile.extract_aliases(text)
        assert aliases == ["One", "Two"]

    def test_array_format_three_items(self, profile):
        """Array format with three items."""
        text = """---
aliases: [Alpha, Beta, Gamma]
---
# Page
"""
        aliases = profile.extract_aliases(text)
        assert aliases == ["Alpha", "Beta", "Gamma"]

    def test_array_format_with_spaces(self, profile):
        """Array format with spaces around items."""
        text = """---
aliases: [ One , Two , Three ]
---
# Page
"""
        aliases = profile.extract_aliases(text)
        assert aliases == ["One", "Two", "Three"]

    # =========================================================================
    # HAPPY PATH: YAML list format (multi-line)
    # =========================================================================

    def test_yaml_list_format(self, profile):
        """YAML list format: multi-line syntax."""
        text = """---
aliases:
  - One
  - Two
---
# My Page
"""
        aliases = profile.extract_aliases(text)
        assert aliases == ["One", "Two"]

    def test_yaml_list_format_three_items(self, profile):
        """YAML list format with three items."""
        text = """---
aliases:
  - Alpha
  - Beta
  - Gamma
---
# Page
"""
        aliases = profile.extract_aliases(text)
        assert aliases == ["Alpha", "Beta", "Gamma"]

    def test_yaml_list_format_with_quotes(self, profile):
        """YAML list format with quoted items."""
        text = """---
aliases:
  - "First Alias"
  - 'Second Alias'
---
# Page
"""
        aliases = profile.extract_aliases(text)
        assert aliases == ["First Alias", "Second Alias"]

    # =========================================================================
    # HAPPY PATH: Single string
    # =========================================================================

    def test_single_string(self, profile):
        """Single alias as string: aliases: One"""
        text = """---
aliases: One
---
# My Page
"""
        aliases = profile.extract_aliases(text)
        assert aliases == ["One"]

    def test_single_string_with_spaces(self, profile):
        """Single alias with extra spaces."""
        text = """---
aliases:   Single Alias  
---
# Page
"""
        aliases = profile.extract_aliases(text)
        assert aliases == ["Single Alias"]

    # =========================================================================
    # EDGE CASES: Mixed content
    # =========================================================================

    def test_mixed_content_with_aliases_and_tags(self, profile):
        """Mixed content with aliases and tags in frontmatter."""
        text = """---
title: My Page
aliases: [One, Two]
tags: [tag1, tag2]
---
# My Page
Some content here.
"""
        aliases = profile.extract_aliases(text)
        assert aliases == ["One", "Two"]
        # Also verify tags are separate (not mixed)
        tags = profile.extract_tags(text)
        assert "tag1" in tags
        assert "tag2" in tags

    def test_aliases_with_wiki_links_in_body(self, profile):
        """Aliases extracted when body contains wiki links."""
        text = """---
aliases: [Primary, Secondary]
---
# My Page
See [[Other Page]] for details.
"""
        aliases = profile.extract_aliases(text)
        assert aliases == ["Primary", "Secondary"]

    def test_aliases_with_hash_tags_in_body(self, profile):
        """Aliases extracted when body contains #tags."""
        text = """---
aliases: [One, Two]
---
# My Page
This has #tag1 and #tag2 in the body.
"""
        aliases = profile.extract_aliases(text)
        assert aliases == ["One", "Two"]

    # =========================================================================
    # EDGE CASES: Missing or empty
    # =========================================================================

    def test_missing_aliases_field(self, profile):
        """No aliases field in frontmatter."""
        text = """---
title: My Page
tags: [tag1]
---
# My Page
"""
        aliases = profile.extract_aliases(text)
        assert aliases == []

    def test_no_frontmatter(self, profile):
        """Text without frontmatter."""
        text = """# My Page
Some content without any YAML frontmatter.
"""
        aliases = profile.extract_aliases(text)
        assert aliases == []

    def test_empty_frontmatter(self, profile):
        """Empty frontmatter block."""
        text = """---
---
# My Page
"""
        aliases = profile.extract_aliases(text)
        assert aliases == []

    def test_empty_string_input(self, profile):
        """Empty input string."""
        aliases = profile.extract_aliases("")
        assert aliases == []

    # =========================================================================
    # EDGE CASES: Unicode
    # =========================================================================

    def test_unicode_alias_chinese(self, profile):
        """Chinese characters as aliases."""
        text = """---
aliases: [项目, 项目管理]
---
# Page
"""
        aliases = profile.extract_aliases(text)
        assert aliases == ["项目", "项目管理"]

    def test_unicode_alias_japanese(self, profile):
        """Japanese characters as aliases."""
        text = """---
aliases:
  - テスト
  - プロジェクト
---
# Page
"""
        aliases = profile.extract_aliases(text)
        assert aliases == ["テスト", "プロジェクト"]

    def test_unicode_alias_cyrillic(self, profile):
        """Cyrillic characters as aliases."""
        text = """---
aliases: [проект, управление]
---
# Page
"""
        aliases = profile.extract_aliases(text)
        assert aliases == ["проект", "управление"]

    def test_unicode_alias_mixed_with_ascii(self, profile):
        """Unicode aliases mixed with ASCII aliases."""
        text = """---
aliases: [English, 中文, テスト, Greek]
---
# Page
"""
        aliases = profile.extract_aliases(text)
        assert aliases == ["English", "中文", "テスト", "Greek"]

    # =========================================================================
    # EDGE CASES: Whitespace handling
    # =========================================================================

    def test_aliases_with_leading_trailing_whitespace(self, profile):
        """Items with leading/trailing whitespace in array."""
        text = """---
aliases: [  Alpha  ,   Beta   ]
---
# Page
"""
        aliases = profile.extract_aliases(text)
        assert aliases == ["Alpha", "Beta"]

    def test_aliases_empty_array(self, profile):
        """Empty array for aliases."""
        text = """---
aliases: []
---
# Page
"""
        aliases = profile.extract_aliases(text)
        assert aliases == []

    def test_aliases_empty_yaml_list(self, profile):
        """Empty YAML list (just key, no items)."""
        text = """---
aliases:
---
# Page
"""
        aliases = profile.extract_aliases(text)
        assert aliases == []

    # =========================================================================
    # EDGE CASES: Special characters
    # =========================================================================

    def test_aliases_with_hyphens(self, profile):
        """Aliases containing hyphens."""
        text = """---
aliases: [my-alias, another-alias]
---
# Page
"""
        aliases = profile.extract_aliases(text)
        assert aliases == ["my-alias", "another-alias"]

    def test_aliases_with_underscores(self, profile):
        """Aliases containing underscores."""
        text = """---
aliases: [my_alias, another_alias]
---
# Page
"""
        aliases = profile.extract_aliases(text)
        assert aliases == ["my_alias", "another_alias"]

    def test_aliases_with_numbers(self, profile):
        """Aliases containing numbers."""
        text = """---
aliases: [v1, v2, 2024]
---
# Page
"""
        aliases = profile.extract_aliases(text)
        assert aliases == ["v1", "v2", "2024"]

    # =========================================================================
    # PROPERTY-BASED TESTS
    # =========================================================================

    def test_aliases_preserves_original_casing(self, profile):
        """Aliases should preserve original casing."""
        text = """---
aliases: [MixedCase, ALLCAPS, alllower]
---
# Page
"""
        aliases = profile.extract_aliases(text)
        assert aliases == ["MixedCase", "ALLCAPS", "alllower"]

    def test_multiple_calls_idempotent(self, profile):
        """Multiple calls with same input produce same output."""
        text = """---
aliases: [One, Two]
---
# Page
"""
        result1 = profile.extract_aliases(text)
        result2 = profile.extract_aliases(text)
        assert result1 == result2
        assert result1 == ["One", "Two"]

    def test_round_trip_with_add_metadata(self, profile):
        """extract_aliases should find aliases we add with add_metadata."""
        original_text = "# My Page\nSome content."
        metadata = {"aliases": ["First", "Second"]}
        text_with_metadata = profile.add_metadata(original_text, metadata)
        
        aliases = profile.extract_aliases(text_with_metadata)
        assert aliases == ["First", "Second"]
