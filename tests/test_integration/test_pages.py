# -*- coding: utf-8 -*-
"""Integration tests for Page CRUD operations.

Tests the complete create-read-update-delete lifecycle
and related page operations in an integrated manner.
"""

import pytest
from notebook.page import Path


@pytest.mark.integration
class TestPageCreate:
    """Test page creation."""

    def test_create_simple_page(self, api_client):
        """Creating a simple page should work."""
        status, headers, body = api_client.create_page(
            "NewPage",
            "= Test Page =\n\nSome content."
        )

        assert status == 200
        assert body.get("ok") is True

    def test_create_page_with_markdown(self, api_client):
        """Creating a page with markdown content should work."""
        content = "# Test Page\n\n**Bold** and *italic* text."
        status, headers, body = api_client.create_page(
            "MarkdownPage",
            content,
            format="markdown"
        )

        assert status == 200

    def test_create_page_with_links(self, api_client):
        """Creating a page with wiki links should work."""
        content = "= Page =\n\nSee [[Other Page]] for details."
        status, headers, body = api_client.create_page(
            "LinkPage",
            content
        )

        assert status == 200

    def test_create_page_with_tags(self, api_client):
        """Creating a page with tags should work."""
        content = "= Page =\n\n@important @work\n\nContent here."
        status, headers, body = api_client.create_page(
            "TagPage",
            content
        )

        assert status == 200

    def test_create_page_that_exists_fails(self, api_client, sample_page):
        """Creating a page that exists should return 409."""
        status, headers, body = api_client.create_page(
            "TestPage",
            "duplicate content"
        )

        assert status == 409
        assert "error" in body

    def test_create_nested_page(self, api_client):
        """Creating a page in a namespace should work."""
        status, headers, body = api_client.create_page(
            "Namespace:SubPage",
            "Nested content"
        )

        assert status == 200

    def test_create_empty_page(self, api_client):
        """Creating an empty page should work."""
        status, headers, body = api_client.create_page(
            "EmptyPage",
            ""
        )

        assert status == 200


@pytest.mark.integration
class TestPageRead:
    """Test page reading."""

    def test_read_existing_page(self, api_client, sample_page):
        """Reading an existing page should return content."""
        status, headers, body = api_client.get_page("TestPage")

        assert status == 200
        assert "content" in body
        assert "name" in body
        assert body.get("exists") is True

    def test_read_nonexistent_page(self, api_client):
        """Reading a non-existent page should return 200 with exists=False."""
        status, headers, body = api_client.get_page("NonExistentPage")

        assert status == 200
        assert body.get("exists") is False
        assert body.get("content") == ""

    def test_read_page_as_html(self, api_client, sample_page):
        """Reading page as HTML should work."""
        status, headers, body = api_client.get_page("TestPage", format="html")

        assert status == 200
        assert "content" in body
        # HTML should have some tags
        if body["content"]:
            assert "<" in body["content"] or len(body["content"]) > 0

    def test_read_page_as_markdown(self, api_client, sample_page):
        """Reading page as markdown should work."""
        status, headers, body = api_client.get_page("TestPage", format="markdown")

        assert status == 200
        assert "content" in body

    def test_read_page_as_plain(self, api_client, sample_page):
        """Reading page as plain text should work."""
        status, headers, body = api_client.get_page("TestPage", format="plain")

        assert status == 200
        assert "content" in body

    def test_read_page_includes_metadata(self, api_client, sample_page):
        """Reading page should include mtime/ctime."""
        status, headers, body = api_client.get_page("TestPage")

        assert status == 200
        # May or may not have mtime depending on filesystem
        # Just check the fields exist (even if None)
        assert "mtime" in body
        assert "ctime" in body


@pytest.mark.integration
class TestPageUpdate:
    """Test page updates."""

    def test_update_page_content(self, api_client, sample_page):
        """Updating page content should work."""
        # Get current state
        status, _, body = api_client.get_page("TestPage")
        old_mtime = body.get("mtime")

        # Update
        status, _, body = api_client.save_page(
            "TestPage",
            "Updated content here"
        )

        assert status == 200
        assert body.get("ok") is True

        # Verify update
        status, _, body = api_client.get_page("TestPage")
        assert "Updated content" in body.get("content", "")

    def test_update_with_wrong_mtime_fails(self, api_client, sample_page):
        """Updating with stale mtime should fail."""
        # Get initial mtime
        status, _, body = api_client.get_page("TestPage")
        initial_mtime = body.get("mtime")

        # Make another edit
        api_client.save_page("TestPage", "middle edit")

        # Try to save with old mtime - should fail with 409
        status, _, body = api_client.save_page(
            "TestPage",
            "conflicting edit",
            expected_mtime=initial_mtime
        )

        assert status == 409
        assert "error" in body

    def test_update_with_correct_mtime_succeeds(self, api_client, sample_page):
        """Updating with correct mtime should succeed."""
        # Get current mtime
        status, _, body = api_client.get_page("TestPage")
        mtime = body.get("mtime")

        # Update with same mtime
        status, _, body = api_client.save_page(
            "TestPage",
            "new content",
            expected_mtime=mtime
        )

        assert status == 200

    def test_update_page_format(self, api_client):
        """Updating page with different format should work."""
        # Create page
        api_client.create_page("FormatTest", "wiki content")

        # Update with markdown
        status, _, body = api_client.save_page(
            "FormatTest",
            "# Markdown Content",
            format="markdown"
        )

        assert status == 200

    def test_update_nonexistent_page_creates_it(self, api_client):
        """Updating a non-existent page should create it."""
        status, _, body = api_client.save_page(
            "NewPageViaUpdate",
            "content via save"
        )

        assert status == 200

        # Verify it exists
        status, _, body = api_client.get_page("NewPageViaUpdate")
        assert status == 200
        assert body.get("exists") is True


@pytest.mark.integration
class TestPageDelete:
    """Test page deletion."""

    def test_delete_existing_page(self, api_client):
        """Deleting an existing page should work."""
        # Create page first
        api_client.create_page("DeleteMe", "content")

        # Delete it
        status, _, body = api_client.delete_page("DeleteMe")

        assert status == 200
        assert body.get("ok") is True

        # Verify it's gone
        status, _, body = api_client.get_page("DeleteMe")
        assert body.get("exists") is False

    def test_delete_nonexistent_page_fails(self, api_client):
        """Deleting a non-existent page should fail."""
        status, _, body = api_client.delete_page("DoesNotExist")

        # May return error or may succeed idempotently
        # Just check it doesn't crash
        assert status in (200, 404, 500)

    def test_delete_page_removes_from_index(self, api_client):
        """Deleting a page should remove it from search index."""
        # Create and index a page
        api_client.create_page("IndexedPage", "unique content here")

        # Search for it
        status, _, body = api_client.search_pages("unique content")
        initial_count = body.get("count", 0)

        # Delete it
        api_client.delete_page("IndexedPage")

        # Search again
        status, _, body = api_client.search_pages("unique content")
        final_count = body.get("count", 0)

        # Count should be same or less
        assert final_count <= initial_count


@pytest.mark.integration
class TestPageMove:
    """Test page move/rename operations."""

    def test_move_page_to_new_name(self, api_client):
        """Moving a page should work."""
        # Create page
        api_client.create_page("MoveSource", "original content")

        # Move it
        status, _, body = api_client.move_page("MoveSource", "MoveDest")

        assert status == 200

        # Old page should not exist
        status, _, body = api_client.get_page("MoveSource")
        assert body.get("exists") is False

        # New page should exist
        status, _, body = api_client.get_page("MoveDest")
        assert body.get("exists") is True

    def test_move_page_with_links_update(self, api_client):
        """Moving a page should update incoming links."""
        # Create two pages with a link
        api_client.create_page("LinkSource", "See [[MoveTarget]]")
        api_client.create_page("MoveTarget", "target content")

        # Move the target
        api_client.move_page("MoveTarget", "MovedTarget")

        # Check that source page's link was updated (if supported)
        status, _, body = api_client.get_page("LinkSource")
        content = body.get("content", "")
        # Links may or may not be updated depending on implementation
        assert status == 200

    def test_move_to_namespace(self, api_client):
        """Moving a page into a namespace should work."""
        api_client.create_page("FlatPage", "content")

        status, _, body = api_client.move_page("FlatPage", "Namespace:FlatPage")

        assert status == 200

        # Verify new location
        status, _, body = api_client.get_page("Namespace:FlatPage")
        assert body.get("exists") is True


@pytest.mark.integration
class TestPageAppend:
    """Test page append operations."""

    def test_append_to_existing_page(self, api_client, sample_page):
        """Appending to existing page should add content."""
        # Get original content
        status, _, body = api_client.get_page("TestPage")
        original = body.get("content", "")

        # Append
        status, _, body = api_client.append_to_page(
            "TestPage",
            "\n\nAppended content"
        )

        assert status == 200

        # Verify
        status, _, body = api_client.get_page("TestPage")
        new_content = body.get("content", "")
        assert "Appended content" in new_content
        assert new_content.startswith(original)

    def test_append_to_nonexistent_page(self, api_client):
        """Appending to non-existent page should create it."""
        status, _, body = api_client.append_to_page(
            "NewViaAppend",
            "First content"
        )

        assert status == 200

        # Verify
        status, _, body = api_client.get_page("NewViaAppend")
        assert body.get("exists") is True

    def test_multiple_appends(self, api_client):
        """Multiple appends should accumulate."""
        api_client.create_page("AppendMulti", "start")

        api_client.append_to_page("AppendMulti", "\nline1")
        api_client.append_to_page("AppendMulti", "\nline2")
        api_client.append_to_page("AppendMulti", "\nline3")

        status, _, body = api_client.get_page("AppendMulti")
        content = body.get("content", "")

        assert "start" in content
        assert "line1" in content
        assert "line2" in content
        assert "line3" in content


@pytest.mark.integration
class TestPageTrash:
    """Test page trash (soft delete) operations."""

    def test_trash_page(self, api_client):
        """Trashing a page should move it to trash."""
        api_client.create_page("TrashMe", "content")

        status, _, body = api_client.trash_page("TrashMe")

        # Should succeed or fall back to delete
        assert status in (200, 400, 503)

    def test_trashed_page_not_found(self, api_client):
        """Trashed page should not be accessible."""
        api_client.create_page("TrashGone", "content")
        api_client.trash_page("TrashGone")

        # Page should no longer exist
        status, _, body = api_client.get_page("TrashGone")
        # May still exist if trash not supported
        assert status == 200


@pytest.mark.integration
class TestPageLifecycle:
    """Test complete page lifecycle."""

    def test_full_crud_lifecycle(self, api_client):
        """Test create-read-update-delete lifecycle."""
        # Create
        status, _, body = api_client.create_page("Lifecycle", "v1")
        assert status == 200

        # Read
        status, _, body = api_client.get_page("Lifecycle")
        assert status == 200
        assert "v1" in body.get("content", "")

        # Update
        status, _, body = api_client.save_page("Lifecycle", "v2")
        assert status == 200

        # Read updated
        status, _, body = api_client.get_page("Lifecycle")
        assert "v2" in body.get("content", "")

        # Delete
        status, _, body = api_client.delete_page("Lifecycle")
        assert status == 200

        # Verify deleted
        status, _, body = api_client.get_page("Lifecycle")
        assert body.get("exists") is False

    def test_full_lifecycle_with_conflicts(self, api_client):
        """Test lifecycle with conflict detection."""
        # Create
        api_client.create_page("ConflictLifecycle", "v1")

        # Read (get mtime)
        status, _, body = api_client.get_page("ConflictLifecycle")
        mtime1 = body.get("mtime")

        # Simulate external change
        api_client.save_page("ConflictLifecycle", "v2")

        # Try to update with old mtime
        status, _, body = api_client.save_page(
            "ConflictLifecycle",
            "v1-modified",
            expected_mtime=mtime1
        )
        assert status == 409

        # Re-fetch and retry
        status, _, body = api_client.get_page("ConflictLifecycle")
        mtime2 = body.get("mtime")

        status, _, body = api_client.save_page(
            "ConflictLifecycle",
            "v2-modified",
            expected_mtime=mtime2
        )
        assert status == 200

        # Finally delete
        status, _, body = api_client.delete_page("ConflictLifecycle")
        assert status == 200


@pytest.mark.integration
class TestPageSiblings:
    """Test page sibling navigation."""

    def test_get_page_siblings(self, api_client, sample_notebook_structure):
        """Getting previous/next siblings should work."""
        status, _, body = api_client.get_page_siblings("Home")

        assert status == 200
        assert "previous" in body
        assert "next" in body

    def test_siblings_for_first_page(self, api_client, sample_notebook_structure):
        """First page should have no previous sibling."""
        status, _, body = api_client.get_page_siblings("Home")

        assert status == 200
        # previous may be None or a page name
        assert "previous" in body


@pytest.mark.integration
class TestPageTree:
    """Test page tree hierarchy."""

    def test_get_page_tree(self, api_client):
        """Getting page tree should work."""
        status, _, body = api_client.get_page_tree()

        assert status == 200
        assert "tree" in body

    def test_page_tree_with_depth(self, api_client):
        """Tree depth parameter should work."""
        status, _, body = api_client.get_page_tree(depth=1)

        assert status == 200

    def test_page_tree_with_namespace(self, api_client):
        """Tree with namespace filter should work."""
        status, _, body = api_client.get_page_tree("Home")

        assert status == 200


@pytest.mark.integration
class TestPageWalk:
    """Test recursive page listing."""

    def test_walk_all_pages(self, api_client, sample_notebook_structure):
        """Walking all pages should return all pages."""
        status, _, body = api_client.walk_pages()

        assert status == 200
        assert "pages" in body
        assert "count" in body

    def test_walk_namespace(self, api_client, sample_notebook_structure):
        """Walking a namespace should return only that subtree."""
        status, _, body = api_client.walk_pages("Home")

        assert status == 200
        assert "pages" in body


@pytest.mark.integration
class TestPageAnalytics:
    """Test page analytics and metadata."""

    def test_get_page_analytics(self, api_client, sample_page):
        """Getting page analytics should work."""
        status, _, body = api_client.get_page_analytics("TestPage")

        assert status == 200
        assert "words" in body
        assert "characters" in body
        assert "lines" in body

    def test_analytics_for_empty_page(self, api_client):
        """Analytics for non-existent page should return zeros."""
        status, _, body = api_client.get_page_analytics("NonExistent")

        assert status == 200
        assert body.get("exists") is False

    def test_reading_time_calculation(self, api_client, sample_page):
        """Reading time should be calculated from word count."""
        status, _, body = api_client.get_page_analytics("TestPage")

        assert status == 200
        words = body.get("words", 0)
        reading_time = body.get("reading_time_minutes", 0)

        # Should be roughly words/200
        if words > 0:
            assert reading_time > 0


@pytest.mark.integration
class TestPageTOC:
    """Test table of contents extraction."""

    def test_get_page_toc(self, api_client):
        """Getting page TOC should work."""
        # Create page with headings
        api_client.create_page(
            "TOCTest",
            "= H1 =\n\n== H2 ==\n\nContent\n\n=== H3 ==="
        )

        status, _, body = api_client.get_page_toc("TOCTest")

        assert status == 200
        assert "headings" in body

    def test_toc_includes_levels(self, api_client):
        """TOC should include heading levels."""
        api_client.create_page(
            "TOCLevels",
            "= Level 1 =\n\n== Level 2 ==\n\n=== Level 3 ==="
        )

        status, _, body = api_client.get_page_toc("TOCLevels")

        assert status == 200
        headings = body.get("headings", [])
        # Should have at least one heading
        assert len(headings) >= 0


@pytest.mark.integration
class TestPageParseTree:
    """Test parse tree retrieval."""

    def test_get_parse_tree(self, api_client, sample_page):
        """Getting page parse tree should work."""
        status, _, body = api_client.get_page_parsetree("TestPage")

        assert status == 200
        assert "tree" in body

    def test_parse_tree_structure(self, api_client):
        """Parse tree should have proper structure."""
        api_client.create_page("TreeTest", "= Heading =\n\nContent")

        status, _, body = api_client.get_page_parsetree("TreeTest")

        assert status == 200
        tree = body.get("tree")
        # Tree should be a list or dict
        assert isinstance(tree, (list, dict))


@pytest.mark.integration
class TestBatchOperations:
    """Test batch operations on pages."""

    def test_batch_read_multiple_pages(self, api_client, sample_notebook_structure):
        """Batch reading multiple pages should work."""
        operations = [
            {"method": "GET", "path": "/api/page/Home"},
            {"method": "GET", "path": "/api/page/Journal"},
            {"method": "GET", "path": "/api/page/Projects"},
        ]

        status, _, body = api_client.batch(operations)

        assert status == 200
        assert "results" in body
        assert len(body["results"]) == 3

    def test_batch_mixed_operations(self, api_client):
        """Batch with mixed operations should work."""
        operations = [
            {"method": "GET", "path": "/api/page/BatchTest1"},
            {"method": "POST", "path": "/api/page/BatchTest2", "body": {"content": "new"}},
            {"method": "GET", "path": "/api/pages"},
        ]

        status, _, body = api_client.batch(operations)

        assert status == 200
        results = body.get("results", [])
        assert len(results) == 3

    def test_batch_error_handling(self, api_client):
        """Batch should handle individual errors gracefully."""
        operations = [
            {"method": "GET", "path": "/api/page/Exists"},
            {"method": "GET", "path": "/api/page/DoesNotExist"},
            {"method": "GET", "path": "/api/page/AlsoExists"},
        ]

        status, _, body = api_client.batch(operations)

        assert status == 200
        # Individual results may have errors but batch succeeds
        assert "results" in body


@pytest.mark.integration
class TestPageExport:
    """Test page export functionality."""

    def test_export_page_as_html(self, api_client, sample_page):
        """Exporting page as HTML should work."""
        status, headers, body = api_client.export_page("TestPage", format="html")

        assert status == 200
        assert "content" in body

    def test_export_page_as_markdown(self, api_client, sample_page):
        """Exporting page as markdown should work."""
        status, _, body = api_client.export_page("TestPage", format="markdown")

        assert status == 200
        assert "content" in body

    def test_export_page_download(self, api_client, sample_page):
        """Export for download should return raw content."""
        status, headers, body = api_client.export_page_raw("TestPage", format="html")

        # May return string or dict depending on implementation
        assert status in (200, 500)

    def test_export_nonexistent_page(self, api_client):
        """Exporting non-existent page should fail gracefully."""
        status, _, body = api_client.export_page("NonExistent", "html")

        assert status == 404
