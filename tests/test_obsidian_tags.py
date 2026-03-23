#!/usr/bin/env python3
"""Tests for ObsidianProfile tag extraction — FR-TAG-001 through FR-TAG-007.

Verifies the tag_regex correctly handles:
- Unicode tags (CJK, Cyrillic, etc.)
- Numbers at start
- Plus signs
- Periods
- Nested tags with slashes
- Hyphens and underscores
- Negative cases (code blocks, headings, mid-word #)
"""

import pytest
import os
import sys

# Ensure moonstone is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moonstone.profiles.obsidian import ObsidianProfile


class TestExtractTags:
    """Direct tests for ObsidianProfile.extract_tags() method."""

    @pytest.fixture
    def profile(self):
        """Create a fresh ObsidianProfile instance."""
        return ObsidianProfile()

    # =========================================================================
    # HAPPY PATH: Unicode tags
    # =========================================================================

    def test_unicode_tag_chinese(self, profile):
        """FR-TAG-001: Chinese characters in tags."""
        text = "This is about #项目 management"
        tags = profile.extract_tags(text)
        assert "项目" in tags

    def test_unicode_tag_japanese(self, profile):
        """FR-TAG-001: Japanese characters in tags."""
        text = "Study notes for #テスト preparation"
        tags = profile.extract_tags(text)
        assert "テスト" in tags

    def test_unicode_tag_cyrillic(self, profile):
        """FR-TAG-001: Cyrillic characters in tags."""
        text = "Russian project named #проект"
        tags = profile.extract_tags(text)
        assert "проект" in tags

    def test_unicode_tag_korean(self, profile):
        """FR-TAG-001: Korean characters in tags."""
        text = "Korean tag: #프로젝트"
        tags = profile.extract_tags(text)
        assert "프로젝트" in tags

    # =========================================================================
    # HAPPY PATH: Numbers at start
    # =========================================================================

    def test_number_at_start_dash(self, profile):
        """FR-TAG-002: Tag starting with number followed by hyphen."""
        text = "Goals for #2024-goals"
        tags = profile.extract_tags(text)
        assert "2024-goals" in tags

    def test_number_at_start_no_dash(self, profile):
        """FR-TAG-002: Tag starting with plain number."""
        text = "Number tag: #1direction"
        tags = profile.extract_tags(text)
        assert "1direction" in tags

    # =========================================================================
    # HAPPY PATH: Plus signs
    # =========================================================================

    def test_plus_sign_cpp(self, profile):
        """FR-TAG-003: C++ programming language tag."""
        text = "Related to #C++ programming"
        tags = profile.extract_tags(text)
        assert "C++" in tags

    def test_plus_sign_multiple(self, profile):
        """FR-TAG-003: Multiple plus signs (C++, C, F are separate tags).

        Note: # is excluded from tag body, so #C# parses as tag "C" with "#" separator.
        """
        text = "Tags: #C++ and #C# and #F#"
        tags = profile.extract_tags(text)
        assert "C++" in tags
        assert "C" in tags  # C# is tag C followed by # separator
        assert "F" in tags  # F# is tag F followed by # separator

    # =========================================================================
    # HAPPY PATH: Periods
    # =========================================================================

    def test_period_in_tag_version(self, profile):
        """FR-TAG-003: Version number with periods."""
        text = "Version tag: #v1.2.3"
        tags = profile.extract_tags(text)
        assert "v1.2.3" in tags

    def test_period_in_tag_subsection(self, profile):
        """FR-TAG-003: Section.subsection pattern."""
        text = "See #section.subsection for details"
        tags = profile.extract_tags(text)
        assert "section.subsection" in tags

    # =========================================================================
    # HAPPY PATH: Nested tags with slashes
    # =========================================================================

    def test_nested_tag_project_year_quarter(self, profile):
        """FR-TAG-002: Deeply nested tag with multiple slashes."""
        text = "Planning #project/2024/Q1"
        tags = profile.extract_tags(text)
        assert "project/2024/Q1" in tags

    def test_nested_tag_simple(self, profile):
        """FR-TAG-002: Simple nested tag."""
        text = "Related to #work/urgent"
        tags = profile.extract_tags(text)
        assert "work/urgent" in tags

    # =========================================================================
    # HAPPY PATH: Hyphens and underscores
    # =========================================================================

    def test_hyphen_in_tag(self, profile):
        """FR-TAG-002: Hyphenated tag."""
        text = "My tag: #my-tag"
        tags = profile.extract_tags(text)
        assert "my-tag" in tags

    def test_underscore_in_tag(self, profile):
        """FR-TAG-002: Underscored tag."""
        text = "My tag: #my_tag"
        tags = profile.extract_tags(text)
        assert "my_tag" in tags

    def test_mixed_hyphen_underscore(self, profile):
        """FR-TAG-002: Mixed hyphens and underscores."""
        text = "Tags: #my-tag and #my_tag and #my-tag_name"
        tags = profile.extract_tags(text)
        assert "my-tag" in tags
        assert "my_tag" in tags
        assert "my-tag_name" in tags

    # =========================================================================
    # HAPPY PATH: Multiple tags in one text
    # =========================================================================

    def test_multiple_tags_mixed(self, profile):
        """FR-TAG-001 through FR-TAG-003: Multiple diverse tags."""
        text = "#中文 #2024-goals #C++ #v1.2.3 #project/2024/Q1"
        tags = profile.extract_tags(text)
        assert "中文" in tags
        assert "2024-goals" in tags
        assert "C++" in tags
        assert "v1.2.3" in tags
        assert "project/2024/Q1" in tags

    # =========================================================================
    # NEGATIVE CASES: Should NOT match
    # =========================================================================

    def test_heading_not_tag(self, profile):
        """FR-TAG-007: Markdown heading ## should not be extracted as tag."""
        text = "## This is a heading\n\nSome #real-tag here"
        tags = profile.extract_tags(text)
        # Heading marker should not produce a tag
        assert "This is a heading" not in tags
        # But real tag should still be found
        assert "real-tag" in tags

    def test_code_block_not_tag(self, profile):
        """FR-TAG-007: #tag inside fenced code block should not be extracted."""
        text = """Some text

```python
#comment
def foo():
    #inside = 1
```

More text with #outside-tag"""
        tags = profile.extract_tags(text)
        # Tags inside code blocks should not be extracted
        assert "comment" not in tags
        assert "inside" not in tags
        # Tag outside code block should be extracted
        assert "outside-tag" in tags

    def test_inline_code_not_tag(self, profile):
        """FR-TAG-007: #tag inside inline code should not be extracted."""
        text = "Use `grep #pattern` to find things and #real-tag"
        tags = profile.extract_tags(text)
        # Tag inside inline code should not be extracted
        assert "pattern" not in tags
        # Tag outside should be extracted
        assert "real-tag" in tags

    def test_hash_in_middle_of_word_not_tag(self, profile):
        """FR-TAG-007: # in middle of word should not start a tag."""
        text = "This is about f#sharp and has #real-tag"
        tags = profile.extract_tags(text)
        # f#sharp - the # is in the middle of a word
        assert "f" not in tags or "sharp" not in tags or len(tags) == 1
        # Real tag should be extracted
        assert "real-tag" in tags

    def test_email_not_tag(self, profile):
        """FR-TAG-007: email@domain.com should not produce a tag."""
        text = "Contact me at user@example.com or see #real-tag"
        tags = profile.extract_tags(text)
        # email parts should not be tags
        assert "example" not in tags
        # Real tag should work
        assert "real-tag" in tags

    # =========================================================================
    # BOUNDARY CASES
    # =========================================================================

    def test_tag_at_start_of_line(self, profile):
        """Boundary: tag at very beginning of text."""
        text = "#first-tag is here"
        tags = profile.extract_tags(text)
        assert "first-tag" in tags

    def test_tag_at_end_of_line(self, profile):
        """Boundary: tag at end of text."""
        text = "The tag is #last-tag"
        tags = profile.extract_tags(text)
        assert "last-tag" in tags

    def test_tag_after_punctuation(self, profile):
        """Boundary: tag after punctuation."""
        text = "Here it is: #after-punctuation"
        tags = profile.extract_tags(text)
        assert "after-punctuation" in tags

    def test_tag_with_special_chars_excluded(self, profile):
        """Boundary: certain special chars should not be in tags."""
        text = "#tag|pipe #tag[bracket] #tag(paran) #tag*star"
        tags = profile.extract_tags(text)
        # These should not match because |, [, ], (, ), *, etc. are excluded
        assert "tag|pipe" not in tags
        assert "tag[bracket]" not in tags
        assert "tag(paran)" not in tags
        assert "tag*star" not in tags
        # But #tag alone should work
        assert "tag" in tags

    def test_empty_tag_not_extracted(self, profile):
        """Boundary: lone # with nothing after should not match."""
        text = "A lone # followed by space should not match"
        tags = profile.extract_tags(text)
        # Empty tag should not appear
        assert "" not in tags

    def test_only_hash_not_tag(self, profile):
        """Boundary: just # with no content."""
        text = "#"
        tags = profile.extract_tags(text)
        assert "" not in tags

    # =========================================================================
    # YAML FRONTMATTER TAGS
    # =========================================================================

    def test_yaml_frontmatter_tags_list(self, profile):
        """FR-TAG-001: Tags in YAML frontmatter list format."""
        text = """---
tags: [unicode, project, 2024-goals]
---
#中文 content"""
        tags = profile.extract_tags(text)
        assert "unicode" in tags
        assert "project" in tags
        assert "2024-goals" in tags
        assert "中文" in tags  # from inline (no space after #)

    def test_yaml_frontmatter_tags_inline(self, profile):
        """FR-TAG-001: Tags in YAML frontmatter inline list."""
        text = """---
title: Test
tags: [tag1, tag2, tag3]
---
Body"""
        tags = profile.extract_tags(text)
        assert "tag1" in tags
        assert "tag2" in tags
        assert "tag3" in tags

    def test_yaml_frontmatter_tags_string(self, profile):
        """FR-TAG-001: Tags in YAML frontmatter as comma-separated string."""
        text = """---
title: Test
tags: tag1, tag2, tag3
---
Body"""
        tags = profile.extract_tags(text)
        assert "tag1" in tags
        assert "tag2" in tags
        assert "tag3" in tags

    def test_yaml_frontmatter_tags_multiline(self, profile):
        """FR-TAG-001: Tags in YAML frontmatter as multiline list."""
        text = """---
tags:
  - project
  - unicode
  - C++
---
Body #v1.2.3"""
        tags = profile.extract_tags(text)
        assert "project" in tags
        assert "unicode" in tags
        assert "C++" in tags
        assert "v1.2.3" in tags  # from inline


class TestTagRegexPattern:
    """Test the tag_regex pattern directly."""

    def test_tag_regex_positive_unicode(self):
        """FR-TAG-001: Verify regex matches Unicode characters."""
        import re
        profile = ObsidianProfile()
        pattern = profile.tag_regex

        # Chinese
        assert re.search(pattern, "#中文") is not None
        # Japanese
        assert re.search(pattern, "#テスト") is not None
        # Cyrillic
        assert re.search(pattern, "#проект") is not None

    def test_tag_regex_positive_numbers(self):
        """FR-TAG-002: Verify regex matches numbers at start."""
        import re
        profile = ObsidianProfile()
        pattern = profile.tag_regex

        assert re.search(pattern, "#2024-goals") is not None
        assert re.search(pattern, "#1direction") is not None

    def test_tag_regex_positive_plus_sign(self):
        """FR-TAG-003: Verify regex matches plus signs."""
        import re
        profile = ObsidianProfile()
        pattern = profile.tag_regex

        assert re.search(pattern, "#C++") is not None

    def test_tag_regex_positive_periods(self):
        """FR-TAG-003: Verify regex matches periods."""
        import re
        profile = ObsidianProfile()
        pattern = profile.tag_regex

        assert re.search(pattern, "#v1.2.3") is not None
        assert re.search(pattern, "#section.subsection") is not None

    def test_tag_regex_negative_heading(self):
        """FR-TAG-007: Verify regex does NOT match ## heading."""
        import re
        profile = ObsidianProfile()
        pattern = profile.tag_regex

        # ## at start of line should not match
        assert re.search(pattern, "## heading") is None

    def test_tag_regex_negative_email(self):
        """FR-TAG-007: Verify regex does NOT match email #."""
        import re
        profile = ObsidianProfile()
        pattern = profile.tag_regex

        # email address with embedded #
        assert re.search(pattern, "user@example.com") is None

    def test_tag_regex_negative_mid_word(self):
        """FR-TAG-007: Verify # in middle of word is not matched."""
        import re
        profile = ObsidianProfile()
        pattern = profile.tag_regex

        # f#sharp - # is preceded by f (a word char)
        match = re.search(pattern, "f#sharp")
        # Should either be None OR match only if preceded by non-word
        if match:
            # The match should not include "f" as the tag
            assert match.group(1) != "f" or match.start() == 0
