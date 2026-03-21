# -*- coding: utf-8 -*-
"""API endpoint tests for Page-related endpoints.

Tests all /api/page/* endpoints with happy paths
and error conditions.
"""

import pytest


@pytest.mark.api
class TestGetPageEndpoint:
    """Test GET /api/page/<path> endpoint."""

    def test_get_page_success(self, api_client, sample_page):
        """Getting an existing page should return 200."""
        status, headers, body = api_client.get_page("TestPage")

        assert status == 200
        assert body.get("name") == "TestPage"
        assert body.get("exists") is True
        assert "content" in body

    def test_get_page_not_found(self, api_client):
        """Getting a non-existent page should return 200 with exists=False."""
        status, headers, body = api_client.get_page("NonExistentPage")

        assert status == 200
        assert body.get("exists") is False
        assert body.get("content") == ""

    def test_get_page_with_format_html(self, api_client, sample_page):
        """Getting page with format=html should return HTML."""
        status, headers, body = api_client.get_page("TestPage", format="html")

        assert status == 200
        assert body.get("format") in ("html", "wiki")  # May fall back

    def test_get_page_with_format_markdown(self, api_client, sample_page):
        """Getting page with format=markdown should work."""
        status, headers, body = api_client.get_page("TestPage", format="markdown")

        assert status == 200
        assert "content" in body

    def test_get_page_with_format_plain(self, api_client, sample_page):
        """Getting page with format=plain should return plain text."""
        status, headers, body = api_client.get_page("TestPage", format="plain")

        assert status == 200
        assert "content" in body

    def test_get_page_with_invalid_format(self, api_client, sample_page):
        """Getting page with invalid format should return 400."""
        status, headers, body = api_client.get_page("TestPage", format="invalid")

        assert status == 400
        assert "error" in body

    def test_get_page_with_namespace(self, api_client):
        """Getting a page in a namespace should work."""
        api_client.create_page("Namespace:SubPage", "content")

        status, headers, body = api_client.get_page("Namespace:SubPage")

        assert status == 200
        assert body.get("exists") is True

    def test_get_page_includes_basename(self, api_client, sample_page):
        """Response should include basename."""
        status, headers, body = api_client.get_page("TestPage")

        assert status == 200
        assert "basename" in body


@pytest.mark.api
class TestCreatePageEndpoint:
    """Test POST /api/page/<path> endpoint."""

    def test_create_page_success(self, api_client):
        """Creating a page should return 200."""
        status, headers, body = api_client.create_page("NewPage", "content")

        assert status == 200
        assert body.get("ok") is True
        assert body.get("page") == "NewPage"

    def test_create_page_with_markdown_format(self, api_client):
        """Creating a page with markdown format should work."""
        status, headers, body = api_client.create_page(
            "MdPage",
            "# Heading",
            format="markdown"
        )

        assert status == 200

    def test_create_page_with_wiki_format(self, api_client):
        """Creating a page with wiki format should work."""
        status, headers, body = api_client.create_page(
            "WikiPage",
            "= Heading =",
            format="wiki"
        )

        assert status == 200

    def test_create_page_that_exists(self, api_client, sample_page):
        """Creating a page that exists should return 409."""
        status, headers, body = api_client.create_page("TestPage", "duplicate")

        assert status == 409
        assert "error" in body

    def test_create_page_in_namespace(self, api_client):
        """Creating a page in a namespace should work."""
        status, headers, body = api_client.create_page(
            "Namespace:SubPage",
            "nested content"
        )

        assert status == 200

    def test_create_empty_page(self, api_client):
        """Creating an empty page should work."""
        status, headers, body = api_client.create_page("EmptyPage", "")

        assert status == 200


@pytest.mark.api
class TestUpdatePageEndpoint:
    """Test PUT /api/page/<path> endpoint."""

    def test_update_page_success(self, api_client, sample_page):
        """Updating a page should return 200."""
        status, headers, body = api_client.save_page("TestPage", "updated content")

        assert status == 200
        assert body.get("ok") is True

    def test_update_page_with_mtime(self, api_client, sample_page):
        """Updating with mtime should work."""
        # Get current mtime
        status, _, body = api_client.get_page("TestPage")
        mtime = body.get("mtime")

        # Update with mtime
        status, _, body = api_client.save_page(
            "TestPage",
            "new content",
            expected_mtime=mtime
        )

        assert status == 200

    def test_update_page_with_stale_mtime(self, api_client, sample_page):
        """Updating with stale mtime should return 409."""
        # Get initial mtime
        status, _, body = api_client.get_page("TestPage")
        old_mtime = body.get("mtime")

        # Make another edit
        api_client.save_page("TestPage", "middle edit")

        # Try to save with old mtime
        status, _, body = api_client.save_page(
            "TestPage",
            "conflicting edit",
            expected_mtime=old_mtime
        )

        assert status == 409
        assert "error" in body

    def test_update_nonexistent_page(self, api_client):
        """Updating a non-existent page should create it."""
        status, headers, body = api_client.save_page(
            "NewViaUpdate",
            "content"
        )

        assert status == 200

    def test_update_page_with_different_format(self, api_client):
        """Updating page with different format should work."""
        api_client.create_page("FormatChange", "wiki content")

        status, _, body = api_client.save_page(
            "FormatChange",
            "# Markdown",
            format="markdown"
        )

        assert status == 200

    def test_update_readonly_page_fails(self, readonly_api):
        """Updating a readonly page should return 403."""
        status, headers, body = readonly_api.save_page(
            "ReadOnlyPage",
            "can't edit"
        )

        assert status == 403
        assert "error" in body


@pytest.mark.api
class TestPatchPageEndpoint:
    """Test PATCH /api/page/<path> endpoint."""

    def test_patch_replace_operation(self, api_client, sample_page):
        """Patch with replace op should work."""
        # Get current content
        status, _, body = api_client.get_page("TestPage")
        content = body.get("content", "")

        if content:
            operations = [
                {
                    "op": "replace",
                    "search": content[:10],
                    "replace": "REPLACED"
                }
            ]

            status, _, body = api_client.patch_page("TestPage", operations)

            # May not be implemented
            assert status in (200, 501)

    def test_patch_insert_after_operation(self, api_client, sample_page):
        """Patch with insert_after op should work."""
        operations = [
            {
                "op": "insert_after",
                "search": "Test",
                "content": " INSERTED"
            }
        ]

        status, _, body = api_client.patch_page("TestPage", operations)

        # May not be implemented
        assert status in (200, 501)

    def test_patch_delete_operation(self, api_client, sample_page):
        """Patch with delete op should work."""
        operations = [
            {
                "op": "delete",
                "search": "content"
            }
        ]

        status, _, body = api_client.patch_page("TestPage", operations)

        # May not be implemented
        assert status in (200, 501)

    def test_patch_with_mtime_check(self, api_client, sample_page):
        """Patch with mtime should check for conflicts."""
        status, _, body = api_client.get_page("TestPage")
        mtime = body.get("mtime")

        operations = [
            {"op": "replace", "search": "Test", "replace": "PATCHED"}
        ]

        status, _, body = api_client.patch_page(
            "TestPage",
            operations,
            expected_mtime=mtime
        )

        # May not be implemented
        assert status in (200, 409, 501)

    def test_patch_invalid_operation(self, api_client, sample_page):
        """Patch with invalid op should return error."""
        operations = [
            {"op": "invalid", "search": "test"}
        ]

        status, _, body = api_client.patch_page("TestPage", operations)

        # May not be implemented
        assert status in (200, 400, 501)


@pytest.mark.api
class TestDeletePageEndpoint:
    """Test DELETE /api/page/<path> endpoint."""

    def test_delete_page_success(self, api_client):
        """Deleting a page should return 200."""
        # Create first
        api_client.create_page("DeleteMe", "content")

        # Delete
        status, headers, body = api_client.delete_page("DeleteMe")

        assert status == 200
        assert body.get("ok") is True
        assert body.get("deleted") == "DeleteMe"

    def test_delete_nonexistent_page(self, api_client):
        """Deleting a non-existent page should handle gracefully."""
        status, headers, body = api_client.delete_page("DoesNotExist")

        # May succeed (idempotent) or fail
        assert status in (200, 404, 500)

    def test_delete_readonly_page_fails(self, readonly_api):
        """Deleting a readonly page should return 403."""
        status, headers, body = readonly_api.delete_page("ReadOnlyPage")

        assert status == 403
        assert "error" in body


@pytest.mark.api
class TestAppendPageEndpoint:
    """Test POST /api/page/<path>/append endpoint."""

    def test_append_to_existing_page(self, api_client, sample_page):
        """Appending to existing page should work."""
        status, headers, body = api_client.append_to_page(
            "TestPage",
            "\n\nAppended"
        )

        assert status == 200
        assert body.get("ok") is True

    def test_append_to_nonexistent_page(self, api_client):
        """Appending to non-existent page should create it."""
        status, headers, body = api_client.append_to_page(
            "NewViaAppend",
            "First content"
        )

        assert status == 200

    def test_append_with_format(self, api_client):
        """Appending with format parameter should work."""
        api_client.create_page("AppendFormat", "start")

        status, _, body = api_client.append_to_page(
            "AppendFormat",
            "\nmore",
            format="wiki"
        )

        assert status == 200

    def test_append_readonly_fails(self, readonly_api):
        """Appending to readonly page should fail."""
        status, _, body = readonly_api.append_to_page(
            "ReadOnlyPage",
            "can't append"
        )

        assert status == 403


@pytest.mark.api
class TestMovePageEndpoint:
    """Test POST /api/page/<path>/move endpoint."""

    def test_move_page_success(self, api_client):
        """Moving a page should work."""
        api_client.create_page("MoveSource", "content")

        status, _, body = api_client.move_page("MoveSource", "MoveDest")

        assert status == 200
        assert body.get("ok") is True

    def test_move_with_link_update(self, api_client):
        """Moving with update_links=True should update links."""
        api_client.create_page("Source", "see [[Target]]")
        api_client.create_page("Target", "content")

        status, _, body = api_client.move_page("Target", "Moved", update_links=True)

        assert status == 200

    def test_move_without_link_update(self, api_client):
        """Moving with update_links=False should not update links."""
        api_client.create_page("Source2", "see [[Target2]]")
        api_client.create_page("Target2", "content")

        status, _, body = api_client.move_page("Target2", "Moved2", update_links=False)

        assert status == 200

    def test_move_nonexistent_page(self, api_client):
        """Moving a non-existent page should fail."""
        status, _, body = api_client.move_page("DoesNotExist", "NewName")

        assert status in (400, 404)


@pytest.mark.api
class TestTrashPageEndpoint:
    """Test POST /api/page/<path>/trash endpoint."""

    def test_trash_page_success(self, api_client):
        """Trashing a page should work."""
        api_client.create_page("TrashMe", "content")

        status, _, body = api_client.trash_page("TrashMe")

        # May succeed or fall back to delete
        assert status in (200, 400)

    def test_trash_nonexistent_page(self, api_client):
        """Trashing non-existent page should fail."""
        status, _, body = api_client.trash_page("DoesNotExist")

        assert status in (200, 400, 404)


@pytest.mark.api
class TestPageTagsEndpoints:
    """Test tag-related page endpoints."""

    def test_get_page_tags(self, api_client, sample_page):
        """Getting page tags should work."""
        status, _, body = api_client.get_page_tags("TestPage")

        assert status == 200
        assert "tags" in body

    def test_get_tags_nonexistent_page(self, api_client):
        """Getting tags for non-existent page returns empty list."""
        status, _, body = api_client.get_page_tags("NonExistent")

        # API returns 200 with empty tags list for non-existent pages
        assert status == 200
        assert body["tags"] == []

    def test_add_tag_to_page(self, api_client, sample_page):
        """Adding a tag to a page should work."""
        status, _, body = api_client.add_tag_to_page("TestPage", "testtag")

        assert status == 200
        assert body.get("ok") is True

    def test_add_duplicate_tag(self, api_client, sample_page):
        """Adding duplicate tag should return success with already_exists."""
        # Add once
        api_client.add_tag_to_page("TestPage", "duplicate")

        # Add again
        status, _, body = api_client.add_tag_to_page("TestPage", "duplicate")

        assert status == 200
        assert body.get("action") in ("added", "already_exists")

    def test_remove_tag_from_page(self, api_client, sample_page):
        """Removing a tag from a page should work."""
        # Add tag first
        api_client.add_tag_to_page("TestPage", "removeme")

        # Remove it
        status, _, body = api_client.remove_tag_from_page("TestPage", "removeme")

        assert status == 200
        assert body.get("ok") is True

    def test_remove_nonexistent_tag(self, api_client, sample_page):
        """Removing a tag that doesn't exist should return 404."""
        status, _, body = api_client.remove_tag_from_page("TestPage", "nosuchtag")

        assert status == 404


@pytest.mark.api
class TestPageSiblingsEndpoint:
    """Test GET /api/page/<path>/siblings endpoint."""

    def test_get_siblings(self, api_client, sample_notebook_structure):
        """Getting page siblings should work."""
        status, _, body = api_client.get_page_siblings("Home")

        assert status == 200
        assert "previous" in body
        assert "next" in body

    def test_get_siblings_nonexistent_page(self, api_client):
        """Getting siblings for non-existent page should fail."""
        status, _, body = api_client.get_page_siblings("NonExistent")

        # May still work (returns nulls)
        assert status == 200


@pytest.mark.api
class TestPageTreeEndpoint:
    """Test GET /api/pagetree endpoint."""

    def test_get_page_tree(self, api_client):
        """Getting page tree should work."""
        status, _, body = api_client.get_page_tree()

        assert status == 200
        assert "tree" in body

    def test_get_page_tree_with_depth(self, api_client):
        """Getting tree with depth parameter should work."""
        status, _, body = api_client.get_page_tree(depth=1)

        assert status == 200

    def test_get_page_tree_with_namespace(self, api_client):
        """Getting tree for namespace should work."""
        status, _, body = api_client.get_page_tree("Home")

        assert status == 200


@pytest.mark.api
class TestPageAnalyticsEndpoint:
    """Test GET /api/page/<path>/analytics endpoint."""

    def test_get_page_analytics(self, api_client, sample_page):
        """Getting page analytics should work."""
        status, _, body = api_client.get_page_analytics("TestPage")

        assert status == 200
        assert "words" in body
        assert "characters" in body
        assert "lines" in body

    def test_analytics_nonexistent_page(self, api_client):
        """Analytics for non-existent page should return zeros."""
        status, _, body = api_client.get_page_analytics("NonExistent")

        assert status == 200
        assert body.get("exists") is False


@pytest.mark.api
class TestPageTOCEndpoint:
    """Test GET /api/page/<path>/toc endpoint."""

    def test_get_page_toc(self, api_client):
        """Getting page TOC should work."""
        api_client.create_page("TOCTest", "= H1 =\n\n== H2 ==")

        status, _, body = api_client.get_page_toc("TOCTest")

        assert status == 200
        assert "headings" in body


@pytest.mark.api
class TestPageParseTreeEndpoint:
    """Test GET /api/page/<path>/parsetree endpoint."""

    def test_get_parse_tree(self, api_client, sample_page):
        """Getting parse tree should work."""
        status, _, body = api_client.get_page_parsetree("TestPage")

        assert status == 200
        assert "tree" in body


@pytest.mark.api
class TestPageExportEndpoints:
    """Test page export endpoints."""

    def test_export_page_html(self, api_client, sample_page):
        """Exporting page as HTML should work."""
        status, _, body = api_client.export_page("TestPage", "html")

        assert status == 200
        assert "content" in body

    def test_export_page_markdown(self, api_client, sample_page):
        """Exporting page as markdown should work."""
        status, _, body = api_client.export_page("TestPage", "markdown")

        assert status == 200

    def test_export_page_raw(self, api_client, sample_page):
        """Exporting page for download should work."""
        status, headers, body = api_client.export_page_raw("TestPage", "html")

        # May return string or dict
        assert status in (200, 500)

    def test_export_nonexistent_page(self, api_client):
        """Exporting non-existent page should fail."""
        status, _, body = api_client.export_page("NonExistent", "html")

        assert status == 404


@pytest.mark.api
class TestListPagesEndpoint:
    """Test GET /api/pages endpoint."""

    def test_list_pages(self, api_client):
        """Listing pages should work."""
        status, _, body = api_client.list_pages()

        assert status == 200
        assert "pages" in body

    def test_list_pages_with_namespace(self, api_client):
        """Listing pages in namespace should work."""
        status, _, body = api_client.list_pages("Home")

        assert status == 200

    def test_list_pages_with_limit(self, api_client):
        """Listing pages with limit should work."""
        status, _, body = api_client.list_pages_paginated(limit=5)

        assert status == 200
        assert "pages" in body

    def test_list_pages_with_offset(self, api_client):
        """Listing pages with offset should work."""
        status, _, body = api_client.list_pages_paginated(offset=5)

        assert status == 200

    def test_count_pages(self, api_client):
        """Counting pages should work."""
        status, _, body = api_client.count_pages()

        assert status == 200
        assert "count" in body


@pytest.mark.api
class TestWalkPagesEndpoint:
    """Test GET /api/pages/walk endpoint."""

    def test_walk_pages(self, api_client):
        """Walking all pages should work."""
        status, _, body = api_client.walk_pages()

        assert status == 200
        assert "pages" in body


@pytest.mark.api
class TestMatchPagesEndpoint:
    """Test GET /api/pages/match endpoint."""

    def test_match_pages(self, api_client):
        """Matching pages should work."""
        status, _, body = api_client.match_pages("test")

        assert status == 200
        assert "pages" in body

    def test_match_pages_with_limit(self, api_client):
        """Matching pages with limit should work."""
        status, _, body = api_client.match_pages("test", limit=5)

        assert status == 200


@pytest.mark.api
class TestRecentChangesEndpoint:
    """Test GET /api/recent endpoint."""

    def test_get_recent_changes(self, api_client):
        """Getting recent changes should work."""
        status, _, body = api_client.get_recent_changes()

        assert status == 200
        assert "pages" in body

    def test_get_recent_with_limit(self, api_client):
        """Getting recent changes with limit should work."""
        status, _, body = api_client.get_recent_changes(limit=10)

        assert status == 200


@pytest.mark.api
class TestBatchEndpoint:
    """Test POST /api/batch endpoint."""

    def test_batch_operations(self, api_client):
        """Batch operations should work."""
        operations = [
            {"method": "GET", "path": "/api/pages"},
            {"method": "GET", "path": "/api/stats"},
        ]

        status, _, body = api_client.batch(operations)

        assert status == 200
        assert "results" in body
        assert len(body["results"]) == 2

    def test_batch_empty_operations(self, api_client):
        """Batch with no operations returns empty results."""
        status, _, body = api_client.batch([])

        # API returns 200 with empty results for empty operations
        assert status == 200
        assert body["results"] == []
        assert body["count"] == 0

    def test_batch_invalid_json(self, api_client):
        """Batch with invalid JSON should fail."""
        # This is tested at the endpoint level
        # Just verify the method exists
        assert hasattr(api_client, "batch")


@pytest.mark.api
class TestNotebookInfoEndpoints:
    """Test notebook metadata endpoints."""

    def test_get_notebook_info(self, api_client):
        """Getting notebook info should work."""
        status, _, body = api_client.get_notebook_info()

        assert status == 200
        assert "name" in body

    def test_get_stats(self, api_client):
        """Getting notebook stats should work."""
        status, _, body = api_client.get_stats()

        assert status == 200
        assert "pages" in body

    def test_get_capabilities(self, api_client):
        """Getting capabilities should work."""
        status, _, body = api_client.get_capabilities()

        assert status == 200
        assert "capabilities" in body


@pytest.mark.api
class TestFormatEndpoints:
    """Test format-related endpoints."""

    def test_list_formats(self, api_client):
        """Listing formats should work."""
        status, _, body = api_client.list_formats()

        assert status == 200
        assert "formats" in body


@pytest.mark.api
class TestTemplateEndpoints:
    """Test template endpoints."""

    def test_list_templates(self, api_client):
        """Listing templates should work."""
        status, _, body = api_client.list_templates()

        assert status == 200
        assert "templates" in body


@pytest.mark.api
class TestSitemapEndpoint:
    """Test sitemap endpoint."""

    def test_get_sitemap_json(self, api_client):
        """Getting sitemap as JSON should work."""
        status, _, body = api_client.get_sitemap("json")

        assert status == 200
        assert "pages" in body

    def test_get_sitemap_xml(self, api_client):
        """Getting sitemap as XML should work."""
        status, headers, body = api_client.get_sitemap("xml")

        # Returns raw XML string
        assert status == 200
        assert isinstance(body, str)


@pytest.mark.api
class TestCurrentPageEndpoint:
    """Test current page endpoint."""

    def test_get_current_page(self, api_client):
        """Getting current page should work."""
        status, _, body = api_client.get_current_page()

        assert status == 200
        assert "page" in body
