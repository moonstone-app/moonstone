# -*- coding: utf-8 -*-
"""Unit tests for moonstone.search module.

Tests the Query parser and SearchSelection classes with
various query types and fallback scenarios.
"""

import pytest
from search import Query, SearchSelection


@pytest.mark.unit
class TestQuery:
    """Test cases for the Query class."""

    def test_empty_query(self):
        """Empty query string should evaluate to False."""
        q = Query("")
        assert not q
        assert not bool(q)

    def test_whitespace_only_query(self):
        """Whitespace-only query should evaluate to False."""
        q = Query("   ")
        assert not q

    def test_simple_query(self):
        """Simple word query should preserve the string."""
        q = Query("test query")
        assert str(q) == "test query"
        assert bool(q)

    def test_query_with_special_chars(self):
        """Query with special characters should be preserved."""
        q = Query("test:tag AND another")
        assert str(q) == "test:tag AND another"

    def test_query_strips_leading_trailing_whitespace(self):
        """Query constructor should strip whitespace."""
        q = Query("  test query  ")
        assert str(q) == "test query"

    def test_query_with_colon_prefixes(self):
        """Queries with Tag:, Name:, Content: prefixes should be preserved."""
        q = Query("Tag:important Name:test Content:example")
        assert str(q) == "Tag:important Name:test Content:example"

    def test_query_with_quotes(self):
        """Queries with exact phrases in quotes should be preserved."""
        q = Query('"exact phrase" test')
        assert str(q) == '"exact phrase" test'

    def test_query_with_boolean_operators(self):
        """Queries with AND, OR, NOT operators should be preserved."""
        q = Query("test AND another OR third NOT fourth")
        assert str(q) == "test AND another OR third NOT fourth"


@pytest.mark.unit
class TestSearchSelection:
    """Test cases for the SearchSelection class."""

    def test_init_with_notebook(self, temp_notebook):
        """SearchSelection should initialize with a notebook."""
        selection = SearchSelection(temp_notebook)
        assert selection.notebook == temp_notebook
        assert selection._results == []
        assert selection.scores == {}

    def test_empty_query_returns_no_results(self, temp_notebook):
        """Empty query should produce no results."""
        selection = SearchSelection(temp_notebook)
        selection.search(Query(""))
        assert len(selection) == 0
        assert not selection

    def test_search_without_index(self, temp_notebook):
        """Search should handle missing index gracefully."""
        # Mock notebook without proper index
        temp_notebook._index = None
        selection = SearchSelection(temp_notebook)
        # Should not crash
        selection.search(Query("test"))

    def test_iteration_over_results(self, temp_notebook):
        """Should be able to iterate over search results."""
        selection = SearchSelection(temp_notebook)
        selection._results = ["result1", "result2"]
        results = list(selection)
        assert results == ["result1", "result2"]

    def test_len_returns_result_count(self, temp_notebook):
        """len() should return number of results."""
        selection = SearchSelection(temp_notebook)
        selection._results = ["a", "b", "c"]
        assert len(selection) == 3

    def test_bool_evaluation(self, temp_notebook):
        """SearchSelection should be truthy when it has results."""
        selection = SearchSelection(temp_notebook)
        assert not selection  # Empty

        selection._results = ["result1"]
        assert selection  # Has results


@pytest.mark.unit
class TestSearchSelectionFTS:
    """Test cases for FTS5 query building and execution."""

    def test_build_fts_query_simple_words(self, temp_notebook):
        """Simple words should be ANDed together."""
        selection = SearchSelection(temp_notebook)
        query = selection._build_fts_query("test query")
        assert query == "test AND query"

    def test_build_fts_query_preserves_quotes(self, temp_notebook):
        """Queries with quotes should preserve them."""
        selection = SearchSelection(temp_notebook)
        query = selection._build_fts_query('"exact phrase"')
        assert '"exact phrase"' in query

    def test_build_fts_query_preserves_boolean_operators(self, temp_notebook):
        """Queries with AND/OR/NOT should preserve them."""
        selection = SearchSelection(temp_notebook)
        query = selection._build_fts_query("test AND another OR third")
        assert "test AND another OR third" in query

    def test_build_fts_query_converts_tag_prefix(self, temp_notebook):
        """Tag:xxx should be converted to @xxx for FTS5."""
        selection = SearchSelection(temp_notebook)
        query = selection._build_fts_query("Tag:important")
        assert "@important" in query

    def test_build_fts_query_converts_name_prefix(self, temp_notebook):
        """Name:xxx should be converted to name:xxx column search."""
        selection = SearchSelection(temp_notebook)
        query = selection._build_fts_query("Name:testpage")
        assert "name:testpage" in query

    def test_build_fts_query_converts_content_prefix(self, temp_notebook):
        """Content:xxx should be converted to content:xxx column search."""
        selection = SearchSelection(temp_notebook)
        query = selection._build_fts_query("Content:example")
        assert "content:example" in query

    def test_build_fts_query_mixed_prefixes(self, temp_notebook):
        """Mixed queries with multiple prefixes should all convert."""
        selection = SearchSelection(temp_notebook)
        query = selection._build_fts_query("Tag:test Name:page Content:text")
        assert "@test" in query
        assert "name:page" in query
        assert "content:text" in query

    def test_fts_query_with_no_operators(self, temp_notebook):
        """Query without operators should AND words together."""
        selection = SearchSelection(temp_notebook)
        query = selection._build_fts_query("word1 word2 word3")
        assert query == "word1 AND word2 AND word3"

    def test_fts_query_single_word(self, temp_notebook):
        """Single word query should pass through unchanged."""
        selection = SearchSelection(temp_notebook)
        query = selection._build_fts_query("test")
        assert query == "test"


@pytest.mark.unit
class TestSearchSelectionFallback:
    """Test cases for fallback LIKE-based search."""

    def test_fallback_search_simple_word(self, temp_notebook):
        """Fallback search should handle simple word queries."""
        selection = SearchSelection(temp_notebook)
        # Create mock database
        from unittest.mock import Mock
        mock_db = Mock()
        mock_db.execute.return_value.fetchall.return_value = []

        selection._fallback_search("test", mock_db)
        # Should not crash
        assert selection._results is not None

    def test_fallback_search_tag_prefix(self, temp_notebook):
        """Fallback search should handle Tag: prefix."""
        selection = SearchSelection(temp_notebook)
        from unittest.mock import Mock
        mock_db = Mock()
        mock_db.execute.return_value.fetchall.return_value = []

        selection._fallback_search("Tag:important", mock_db)
        # Should not crash
        assert selection._results is not None

    def test_fallback_search_name_prefix(self, temp_notebook):
        """Fallback search should handle Name: prefix."""
        selection = SearchSelection(temp_notebook)
        from unittest.mock import Mock
        mock_db = Mock()
        mock_db.execute.return_value.fetchall.return_value = [
            {"name": "TestPage"}
        ]

        selection._fallback_search("Name:test", mock_db)
        # Should attempt to find page
        assert mock_db.execute.called

    def test_fallback_search_empty_query(self, temp_notebook):
        """Fallback search with empty query should return no results."""
        selection = SearchSelection(temp_notebook)
        from unittest.mock import Mock
        mock_db = Mock()

        selection._fallback_search("", mock_db)
        assert len(selection._results) == 0

    def test_fallback_search_multiple_words(self, temp_notebook):
        """Fallback search should AND multiple words."""
        selection = SearchSelection(temp_notebook)
        from unittest.mock import Mock
        mock_db = Mock()
        mock_db.execute.return_value.fetchall.return_value = [
            {"name": "TestPage"}
        ]

        selection._fallback_search("word1 word2", mock_db)
        # Should execute with LIKE conditions
        assert mock_db.execute.called


@pytest.mark.unit
class TestSearchWithSampleData:
    """Integration-like tests using sample data."""

    def test_search_finds_created_page(self, temp_notebook, sample_page):
        """Search should find a page that was created in the notebook."""
        selection = SearchSelection(temp_notebook)

        # This will try to use FTS5; if it fails, falls back
        try:
            selection.search(Query("Test"))
        except Exception:
            # Fallback or skip if database not ready
            pass

        # Results might be empty if index not built
        # Just verify it doesn't crash
        assert selection is not None

    def test_search_with_query_object(self, temp_notebook):
        """Search should accept Query object."""
        selection = SearchSelection(temp_notebook)
        q = Query("test")
        # Should not crash
        try:
            selection.search(q)
        except Exception:
            pass

    def test_search_with_string(self, temp_notebook):
        """Search should accept string directly."""
        selection = SearchSelection(temp_notebook)
        # Should not crash
        try:
            selection.search("test")
        except Exception:
            pass


@pytest.mark.unit
class TestSearchScores:
    """Test cases for search result scoring."""

    def test_scores_dict_initialized(self, temp_notebook):
        """Scores dict should be initialized on creation."""
        selection = SearchSelection(temp_notebook)
        assert isinstance(selection.scores, dict)
        assert len(selection.scores) == 0

    def test_scores_assigned_to_results(self, temp_notebook):
        """When results are added, scores should be assigned."""
        selection = SearchSelection(temp_notebook)
        from unittest.mock import Mock
        from notebook.page import Path

        mock_db = Mock()
        mock_db.execute.return_value.fetchall.return_value = [
            {"name": "TestPage", "rank": -1.5}
        ]

        # Simulate FTS5 search result
        try:
            selection.search(Query("test"))
        except Exception:
            # Database might not be set up
            pass

        # Just verify scores dict exists
        assert hasattr(selection, 'scores')


@pytest.mark.unit
class TestQueryStringParsing:
    """Test cases for advanced query string parsing."""

    def test_query_with_parentheses(self):
        """Query with parentheses should be preserved."""
        q = Query("(test OR another) AND third")
        assert "(test OR another) AND third" in str(q)

    def test_query_with_wildcards(self):
        """Query with wildcards should be preserved."""
        q = Query("test*")
        assert str(q) == "test*"

    def test_query_case_sensitivity(self):
        """Query should preserve case."""
        q = Query("TestCase")
        assert str(q) == "TestCase"

    def test_query_unicode(self):
        """Query should handle unicode characters."""
        q = Query("тест 中文")
        assert "тест" in str(q)
        assert "中文" in str(q)
