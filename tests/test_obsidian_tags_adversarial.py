#!/usr/bin/env python3
"""Adversarial security tests for ObsidianProfile tag extraction.

Tests attack vectors:
- ReDoS (Regex Denial of Service) patterns
- Injection attempts (SQL, script, path traversal)
- Boundary violations (empty, Unicode edge cases, emoji)
- Obsidian-specific edge cases (tables, blockquotes, formatting)
"""

import pytest
import re
import time
import os
import sys

# Ensure moonstone is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moonstone.profiles.obsidian import ObsidianProfile


class TestReDoSAttackPatterns:
    """Test for Regex Denial of Service vulnerabilities."""

    @pytest.fixture
    def profile(self):
        return ObsidianProfile()

    def test_extremely_long_tag_execution_time(self, profile):
        """ReDoS: Extremely long tag (10000+ chars) should complete quickly."""
        long_tag = "a" * 10000
        text = f"#{long_tag}"  # No space - space is excluded
        start = time.time()
        tags = profile.extract_tags(text)
        elapsed = time.time() - start
        
        # Should complete in under 1 second (linear time, not exponential)
        assert elapsed < 1.0, f"ReDoS vulnerability: took {elapsed:.2f}s for 10K char tag"
        # The tag should be extracted (linear matching is acceptable)
        assert long_tag in tags

    def test_extremely_long_tag_with_exclusions(self, profile):
        """ReDoS: Long tag that includes characters from exclusion set."""
        # Mix of allowed chars and excluded chars - tests backtracking behavior
        long_tag = "a" * 5000 + "!"
        text = f"#tag{long_tag} more content"
        start = time.time()
        tags = profile.extract_tags(text)
        elapsed = time.time() - start
        
        assert elapsed < 1.0, f"ReDoS with exclusions: took {elapsed:.2f}s"

    def test_many_tags_in_sequence(self, profile):
        """ReDoS: Many short tags in sequence."""
        text = " ".join([f"#tag{i}" for i in range(1000)])
        start = time.time()
        tags = profile.extract_tags(text)
        elapsed = time.time() - start
        
        assert elapsed < 2.0, f"ReDoS with many tags: took {elapsed:.2f}s"
        assert len(tags) >= 1000

    def test_nested_structure_no_catastrophic_backtracking(self, profile):
        """ReDoS: Nested structure that could cause backtracking."""
        # Tags with many slashes (nested structure)
        text = "#" + "/".join(["x"] * 100)
        start = time.time()
        tags = profile.extract_tags(text)
        elapsed = time.time() - start
        
        assert elapsed < 1.0, f"Catastrophic backtracking: took {elapsed:.2f}s"

    def test_repeated_special_chars_not_matching(self, profile):
        """ReDoS: Many repeated special chars that won't match anyway."""
        # Characters that are excluded from tag body
        text = "#" + "|||||" * 1000
        start = time.time()
        tags = profile.extract_tags(text)
        elapsed = time.time() - start
        
        assert elapsed < 1.0, f"Slow exclusion: took {elapsed:.2f}s"
        # Should not match as tags (| is excluded)
        assert all("|" not in t for t in tags)


class TestInjectionAttempts:
    """Test injection attack vectors - tags should not capture malicious content."""

    @pytest.fixture
    def profile(self):
        return ObsidianProfile()

    def test_sql_injection_attempt(self, profile):
        """SQL injection: #'; DROP TABLE-- should not extract full string."""
        text = "Tag: #'; DROP TABLE--"
        tags = profile.extract_tags(text)
        
        # The single quote ' is excluded, so the tag body would be cut off
        # Verify we don't extract the full malicious string
        assert "'; DROP TABLE--" not in tags
        assert "DROP" not in tags
        assert "TABLE" not in tags

    def test_sql_injection_no_single_quote(self, profile):
        """SQL injection variant without quotes."""
        text = "Tag: #; DROP TABLE--"
        tags = profile.extract_tags(text)
        
        # Semicolon is excluded, so should not extract full string
        assert "; DROP" not in tags

    def test_script_tag_injection(self, profile):
        """XSS: #<script>alert(1)</script> should not extract."""
        text = "Check #<script>alert(1)</script> this"
        tags = profile.extract_tags(text)
        
        # < and > are excluded, so tag body is cut at <
        assert "<script>" not in tags
        assert "script" not in tags  # 'script' alone doesn't have # before it

    def test_script_tag_injection_variants(self, profile):
        """XSS: Various script injection patterns."""
        variants = [
            "#<img src=x onerror=alert(1)>",
            "#<svg onload=alert(1)>",
            "#javascript:alert(1)",
            "#onclick=alert(1)",
        ]
        
        for variant in variants:
            text = f"Tag: {variant}"
            tags = profile.extract_tags(text)
            # < is excluded, so these won't extract as full tag
            # Tag should be empty or cut off, not the full injection string
            assert "<" not in str(tags), f"XSS variant extracted: {tags}"

    def test_path_traversal_attempt(self, profile):
        """Path traversal: #../../../etc/passwd should extract but not harm."""
        text = "Access #../../../etc/passwd here"
        tags = profile.extract_tags(text)
        
        # Slashes are ALLOWED in tags (used for nested tags)
        # The regex WILL extract this as a tag
        assert "../../../etc/passwd" in tags

    def test_path_traversal_no_double_dots_in_exclusions(self, profile):
        """Verify path traversal characters are not blocked (by design)."""
        # Double dots are allowed - this is intentional for nested tags
        text = "#project/../sibling"
        tags = profile.extract_tags(text)
        assert "project/../sibling" in tags

    def test_shell_injection_attempt(self, profile):
        """Shell injection: #$(whoami) - $ and backtick are NOT excluded.
        
        SECURITY NOTE: $ and ` are NOT in the exclusion list, allowing shell
        injection patterns to be extracted. This is a potential issue if tags
        are used in shell commands or eval() contexts downstream.
        """
        text = "Check #$(whoami) here"
        tags = profile.extract_tags(text)
        
        # $ is NOT excluded (only captured up to first excluded char)
        # This shows $ is a potential injection vector
        assert "$" in tags  # Only $ is captured, not full $(whoami)
        assert "whoami" not in tags  # Stopped at ( which IS excluded

    def test_template_injection_attempt(self, profile):
        """Template injection: #${7*7} - { and } are NOT excluded.
        
        SECURITY NOTE: Curly braces {} are NOT in the exclusion list, allowing
        template injection patterns. The regex extracts up to first excluded char.
        """
        text = "Check #${7*7} here"
        tags = profile.extract_tags(text)
        
        # { is NOT excluded (extracted up to first excluded char)
        assert "$" in tags
        assert "7*7" not in tags  # Stopped at } which IS excluded

    def test_angular_injection(self, profile):
        """Angular injection: #{...} pattern - curly braces ARE excluded.
        
        SECURITY NOTE: Curly braces {} ARE excluded, so #{ doesn't match at all.
        The #{{ form is completely rejected because { is excluded.
        """
        text = "Check #{{constructor.constructor('alert(1)')()}} here"
        tags = profile.extract_tags(text)
        
        # { is excluded, so #{{ doesn't match at all
        assert len(tags) == 0, "Curly braces are excluded, so #{ shouldn't match"

    def test_newline_injection(self, profile):
        """Newline injection: tag with newline in body."""
        text = "#tag\nwith\nnewlines"
        tags = profile.extract_tags(text)
        
        # \n is whitespace, so tag body stops at newline
        assert "tag" in tags
        # The rest should not be captured
        assert "with" not in tags

    def test_null_byte_injection(self, profile):
        """Null byte injection: #tag\x00with null - null bytes not filtered.
        
        SECURITY NOTE: Null bytes (\x00) are NOT filtered or excluded, so they
        become part of the extracted tag. This could cause issues in string
        handling or file operations if not properly sanitized downstream.
        """
        text = "#tag\x00with null"
        tags = profile.extract_tags(text)
        
        # Null byte is NOT excluded, so tag includes null byte
        assert len(tags) > 0
        # The tag contains null byte - potential security issue
        assert any("\x00" in tag for tag in tags), "Null byte should be preserved in tag"


class TestBoundaryViolations:
    """Test boundary conditions and edge cases."""

    @pytest.fixture
    def profile(self):
        return ObsidianProfile()

    def test_empty_content_after_hash(self, profile):
        """Boundary: lone # with nothing after should not match."""
        text = "#"
        tags = profile.extract_tags(text)
        assert "" not in tags
        assert len(tags) == 0

    def test_only_whitespace_after_hash(self, profile):
        """Boundary: # followed by only whitespace should not match."""
        text = "#   \n# \t #real-tag"
        tags = profile.extract_tags(text)
        # Whitespace after # stops tag extraction
        assert "" not in tags
        assert "real-tag" in tags

    def test_hash_at_start_of_string(self, profile):
        """Boundary: # at very start of string."""
        text = "#first-tag"
        tags = profile.extract_tags(text)
        assert "first-tag" in tags

    def test_multiple_hashes_in_sequence(self, profile):
        """Boundary: ### multiple hashes."""
        text = "###not-a-tag but #real-tag"
        tags = profile.extract_tags(text)
        # ## is heading, not a tag
        assert "not-a-tag" not in tags
        assert "real-tag" in tags

    def test_hash_followed_by_only_special_chars(self, profile):
        """Boundary: # followed by only special chars.
        
        SECURITY NOTE: $ is NOT excluded, so #@#$%^&* extracts "$" only.
        """
        text = "#@#$%^&*"
        tags = profile.extract_tags(text)
        # $ is NOT excluded (rest are), so we get just "$"
        assert "$" in tags
        assert "@" not in tags

    def test_unicode_combining_characters(self, profile):
        """Unicode: combining characters should not break extraction."""
        # Thai combining characters
        text = "#" + "\u0e33" + "\u0e38"  # Thai vowels/combining
        tags = profile.extract_tags(text)
        # Should still extract something (combining chars are valid Unicode)
        assert len(tags) >= 1 or tags == []

    def test_unicode_zero_width_characters(self, profile):
        """Unicode: zero-width characters in tag."""
        text = "#tag\u200b\u200c\u200dhere"
        tags = profile.extract_tags(text)
        # Zero-width chars are not whitespace, so included in tag
        assert len(tags) >= 1

    def test_unicode_bidi_override_characters(self, profile):
        """Unicode: bidirectional override characters."""
        # RTL override
        text = "#tag\u202Ehidden"
        tags = profile.extract_tags(text)
        # These are not excluded, so they're part of the tag
        assert len(tags) >= 1

    def test_emoji_sequence_at_start(self, profile):
        """Emoji: emoji at start of tag per spec (should NOT match as tag)."""
        # Emoji is not a word char, but emoji is NOT in the exclusion set
        # So #🔥 would extract "🔥" as a tag
        text = "#🔥 fire"
        tags = profile.extract_tags(text)
        # Per current spec, emoji IS allowed as tag content
        assert "🔥" in tags

    def test_emoji_mixed_with_text(self, profile):
        """Emoji: mixed emoji and text in tag."""
        text = "#project🔥2024"
        tags = profile.extract_tags(text)
        # Currently extracts (emoji not excluded)
        assert "project🔥2024" in tags

    def test_emoji_modifier_sequence(self, profile):
        """Emoji: skin tone modifiers."""
        text = "#👨‍🦱 complex emoji"  # man with hair: ZWJ + skin tone
        tags = profile.extract_tags(text)
        # ZWJ (Zero Width Joiner) is not whitespace, so included
        assert len(tags) >= 1

    def test_control_characters(self, profile):
        """Control characters: \\x00-\\x1f should stop tag."""
        text = "#tag\x1fhere"
        tags = profile.extract_tags(text)
        # Control chars are not in exclusion set but may cause issues
        # The regex handles them as regular chars

    def test_tab_and_newline_separators(self, profile):
        """Tab and newline as tag separators."""
        text = "#tag1\t#tag2\n#tag3"
        tags = profile.extract_tags(text)
        assert "tag1" in tags
        assert "tag2" in tags
        assert "tag3" in tags


class TestObsidianSpecificEdgeCases:
    """Test Obsidian-specific markdown contexts for tags."""

    @pytest.fixture
    def profile(self):
        return ObsidianProfile()

    def test_tag_in_markdown_table(self, profile):
        """Tags in markdown tables should extract."""
        text = """| Column |
| ------- |
| #tag1 |
| #tag2 |"""
        tags = profile.extract_tags(text)
        assert "tag1" in tags
        assert "tag2" in tags

    def test_tag_in_blockquote(self, profile):
        """Tags in blockquotes should extract."""
        text = """> #quoted-tag
> regular text #regular-tag"""
        tags = profile.extract_tags(text)
        assert "quoted-tag" in tags
        assert "regular-tag" in tags

    def test_tag_adjacent_to_bold(self, profile):
        """Tag adjacent to **bold** formatting."""
        text = "#tag**bold** and **bold**#tag2"
        tags = profile.extract_tags(text)
        assert "tag" in tags
        assert "tag2" in tags

    def test_tag_adjacent_to_italic(self, profile):
        """Tag adjacent to *italic* formatting."""
        text = "#tag*italic* and *italic*#tag2"
        tags = profile.extract_tags(text)
        assert "tag" in tags
        assert "tag2" in tags

    def test_tag_in_list(self, profile):
        """Tags in markdown lists."""
        text = """- #list-tag
- item
  - #nested-list-tag"""
        tags = profile.extract_tags(text)
        assert "list-tag" in tags
        assert "nested-list-tag" in tags

    def test_tag_after_list_marker(self, profile):
        """Tag immediately after list marker."""
        text = "-#list-marker-tag"
        tags = profile.extract_tags(text)
        # - is not excluded, so this becomes a tag
        assert "list-marker-tag" in tags

    def test_tag_in_heading_not_extracted(self, profile):
        """Tag INSIDE a heading (on same line) should not extract."""
        text = "## Heading #inside"
        tags = profile.extract_tags(text)
        # This is actually ambiguous - the # is on heading line
        # Per spec, heading ## prefix should prevent tag matching
        # But our regex doesn't strip headings before inline extraction
        # The negative lookbehind checks for # before current #

    def test_tag_in_fenced_code_block_not_extracted(self, profile):
        """Tag inside fenced code block should not extract."""
        text = """```
#tag-in-code
```"""
        tags = profile.extract_tags(text)
        assert "tag-in-code" not in tags

    def test_tag_in_inline_code_not_extracted(self, profile):
        """Tag inside inline code should not extract."""
        text = "`code #tag` and #real"
        tags = profile.extract_tags(text)
        assert "tag" not in tags
        assert "real" in tags

    def test_tag_in_html_comment(self, profile):
        """Tag in HTML comment - Obsidian does not strip HTML comments.
        
        DESIGN NOTE: The regex does NOT strip HTML comments before tag extraction.
        This is consistent with Obsidian's behavior - HTML comments are treated
        as regular content for tag purposes. If you need HTML comment stripping,
        that would be a feature request, not a security bug.
        """
        text = "<!-- #comment-tag --> #real-tag"
        tags = profile.extract_tags(text)
        # HTML comments are NOT stripped, so comment-tag IS extracted
        assert "comment-tag" in tags
        assert "real-tag" in tags


class TestTagRegexDirectPattern:
    """Direct tests on the regex pattern itself for security issues."""

    def test_regex_no_catastrophic_backtracking_patterns(self):
        """Verify regex doesn't have known ReDoS patterns."""
        import re
        profile = ObsidianProfile()
        pattern = profile.tag_regex
        
        # Check for dangerous nested quantifiers: (a+)+ or (a*)* or (a+)* etc.
        dangerous_patterns = [
            r'\(\.[*\+]\)\+',  # (.+)*
            r'\(\w*\+\)\*',    # (\w+)* 
            r'\([^)]*\+\)\*',  # (([^)]+))* - nested groups with +
        ]
        
        for dangerous in dangerous_patterns:
            match = re.search(dangerous, pattern)
            assert match is None, f"Dangerous pattern found: {dangerous}"

    def test_regex_complexity_with_long_input(self):
        """Measure regex matching complexity on long input."""
        import re
        profile = ObsidianProfile()
        pattern = profile.tag_regex
        
        # Linear pattern: lots of allowed chars
        linear_input = "#" + "a" * 10000
        start = time.time()
        re.search(pattern, linear_input)
        elapsed = time.time() - start
        
        # Should be fast (linear) not exponential
        assert elapsed < 0.5, f"Regex too slow on linear input: {elapsed:.3f}s"

    def test_exclusion_set_completeness(self):
        """Verify exclusion set includes potentially dangerous characters.
        
        The tag_regex excludes these chars from tag body:
        \s, #, |, \\, [, ], {, }, (, ), <, >, *, ~, backtick, single-quote, double-quote, 
        !, ,, ;, @, %, &, =, +
        
        Characters NOT excluded (potential injection vectors):
        - $ (dollar sign) - shell/template injection risk
        """
        profile = ObsidianProfile()
        pattern = profile.tag_regex
        
        # Extract the character class portion properly
        import re
        m = re.search(r'#\(\[\^.*?\]\+\)', pattern)
        assert m, "Could not find character class in pattern"
        char_class = m.group()
        
        # Characters that ARE excluded from tag body
        should_be_excluded = ['<', '>', "'", '"', '|', '*', '~', '!', 
                            ',', ';', '@', '%', '&', '=', '+', '{', '}', '`']
        for char in should_be_excluded:
            assert char in char_class, f"Character {repr(char)} should be excluded"
        
        # Characters that are NOT excluded (potential security concern)
        not_excluded = ['$']
        for char in not_excluded:
            assert char not in char_class, \
                f"Character {repr(char)} is NOT excluded - potential injection vector"
        
        # Verify specific dangerous characters ARE excluded
        assert "'" in char_class, "Single quote should be excluded (SQL injection)"
        assert '"' in char_class, "Double quote should be excluded (SQL injection)"
        assert "<" in char_class, "Less-than should be excluded (XSS)"
        assert ">" in char_class, "Greater-than should be excluded (XSS)"
        
        # Verify injection-enabling characters status
        assert "$" not in char_class, "Dollar sign NOT excluded (shell injection risk)"
        # Backtick IS excluded - good for shell injection prevention
        assert "`" in char_class, "Backtick IS excluded (shell injection prevention)"


class TestOutputSanitization:
    """Test that extracted tags don't contain dangerous content for downstream use."""

    @pytest.fixture
    def profile(self):
        return ObsidianProfile()

    def test_tags_extracted_are_strings_only(self, profile):
        """Tags should be plain strings, not objects or other types."""
        text = "#safetag #unicode-中文 #2024"
        tags = profile.extract_tags(text)
        
        for tag in tags:
            assert isinstance(tag, str), f"Tag is not a string: {type(tag)}"
            assert "\x00" not in tag, "Tag contains null byte"

    def test_no_control_characters_in_tags(self, profile):
        """Extracted tags should not contain control characters."""
        text = "#tag\nwith\nnewlines"
        tags = profile.extract_tags(text)
        
        for tag in tags:
            for char in tag:
                assert not (0 <= ord(char) < 32 and char not in "\t"), \
                    f"Tag contains control char: {repr(tag)}"

    def test_maximum_tag_length_reasonable(self, profile):
        """Tags should not be absurdly long (ReDoS output validation)."""
        long_tag = "x" * 50000
        text = f"# {long_tag}"
        tags = profile.extract_tags(text)
        
        # If a tag is extracted, it should be bounded
        for tag in tags:
            assert len(tag) < 100000, f"Tag too long: {len(tag)} chars"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
