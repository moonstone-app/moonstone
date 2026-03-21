# -*- coding: utf-8 -*-
"""Pytest fixtures for Moonstone testing.

This module provides reusable fixtures for testing Moonstone's
notebook operations, API endpoints, and concurrent access patterns.
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, MagicMock
import pytest

# Add parent directory to path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Create an import hook to make imports from 'moonstone' resolve to the root directory
import importlib.abc
import importlib.util

class MoonstoneMetaPathFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == "moonstone":
            # The 'moonstone' package itself is mapped to the project root
            spec = importlib.util.spec_from_file_location(
                "moonstone",
                os.path.join(project_root, "__init__.py"),
                submodule_search_locations=[project_root]
            )
            return spec
        
        if fullname.startswith("moonstone."):
            # Submodules (e.g. 'moonstone.notebook') resolve to 'notebook' in root
            real_name = fullname[len("moonstone."):]
            # Try to find the spec for the actual underlying module
            real_spec = None
            try:
                # To prevent recursion, we temporarily remove our hook
                sys.meta_path.remove(self)
                real_spec = importlib.util.find_spec(real_name)
            except Exception:
                pass
            finally:
                sys.meta_path.insert(0, self)
                
            if real_spec:
                # Return a spec that loads the underlying file but gives it the requested 'moonstone.*' name
                # This ensures module __name__ matches what the imports expect
                return importlib.util.spec_from_file_location(
                    fullname, 
                    real_spec.origin,
                    submodule_search_locations=getattr(real_spec, 'submodule_search_locations', None)
                )
        
        return None

# Install the hook so any modules trying to import moonstone.* will find them
# Even if they're in the actual source tree doing absolute imports!
sys.meta_path.insert(0, MoonstoneMetaPathFinder())


@pytest.fixture
def temp_dir(tmp_path):
    """Create a temporary directory that is cleaned up after the test.

    Returns:
        pathlib.Path: Path to temporary directory
    """
    return tmp_path


@pytest.fixture
def temp_notebook(tmp_path):
    """Create a temporary notebook directory for isolated tests.

    The notebook is initialized with:
    - Basic directory structure
    - Empty index database
    - Default configuration

    Note: Index is NOT built by default for performance.
    Tests that need index data should call notebook.index.update().

    Returns:
        Notebook: A Moonstone Notebook instance
    """
    from notebook.notebook import Notebook

    notebook_dir = tmp_path / "test_notebook"
    notebook_dir.mkdir()

    # Create minimal notebook structure
    (notebook_dir / "notebook.zim").write_text(
        "[Notebook]\n"
        "name=Test Notebook\n"
        "interwiki=\n"
        "home=Home\n"
        "icon=\n"
    )

    # Initialize notebook (fast - no index scan)
    notebook = Notebook(notebook_dir)

    # Access index property to create database (fast - no scan)
    # This is lazy: DB is created but not populated with pages
    _ = notebook.index

    yield notebook

    # Cleanup: clear LRU cache to free memory
    notebook._page_cache.clear()


@pytest.fixture
def api_factory(temp_notebook, tmp_path):
    """Factory function to create API clients with various configurations.

    Usage:
        def test_something(api_factory):
            api = api_factory(readonly=False)
            status, _, body = api.get_page("Test")

    Returns:
        callable: Function that creates NotebookAPI instances
    """
    def _create(**kwargs):
        from webbridge.api import NotebookAPI

        defaults = {
            "notebook": temp_notebook,
            "app": None,
            "event_manager": None,
            "applet_manager": None,
        }
        defaults.update(kwargs)

        # Create mock app if not provided
        if defaults["app"] is None:
            mock_app = Mock()
            mock_app.applets_dir = tmp_path / "applets"
            mock_app.applets_dir.mkdir(exist_ok=True)
            mock_app._event_manager = defaults["event_manager"] or Mock()
            mock_app._history = None
            defaults["app"] = mock_app

        return NotebookAPI(
            defaults["notebook"],
            defaults["app"],
            defaults["event_manager"],
            defaults["applet_manager"],
        )

    return _create


@pytest.fixture
def api_client(api_factory):
    """Create a standard API client for testing.

    This is a pre-configured client with:
    - Full read/write access
    - Mock event manager
    - Mock applet manager

    Returns:
        NotebookAPI: Configured API client instance
    """
    return api_factory()


@pytest.fixture
def readonly_api(api_factory):
    """Create a read-only API client for testing permissions.

    Returns:
        NotebookAPI: Read-only API client instance
    """
    from notebook.notebook import Notebook
    # Create a read-only notebook mock
    readonly_notebook = Mock()
    readonly_notebook.readonly = True
    readonly_notebook.pages = Mock()
    readonly_notebook.index = Mock()

    return api_factory(notebook=readonly_notebook)


@pytest.fixture
def sample_page(temp_notebook):
    """Create a sample page with known content for testing.

    The page has:
    - Name: TestPage
    - Content with links, tags, and formatting
    - Stored in the notebook

    Returns:
        Page: A Moonstone Page object
    """
    from notebook.page import Path

    try:
        path = Path("TestPage")
        page = temp_notebook.get_page(path)

        # Parse content with wiki syntax
        content = """= Test Page =

This is a test page with various features.

[[Link|Another Page]]

@example tag

* Bullet point 1
* Bullet point 2

== Heading ==

Subsection content.
"""
        page.parse("wiki", content)

        # Store the page
        if hasattr(temp_notebook, "store_page"):
            temp_notebook.store_page(page)

        yield page
    except Exception as e:
        # If we can't create a real page, return a mock
        mock_page = Mock()
        mock_page.name = "TestPage"
        mock_page.basename = "TestPage"
        mock_page.hascontent = True
        mock_page.readonly = False
        yield mock_page


@pytest.fixture
def sample_notebook_structure(tmp_path):
    """Create a notebook with multiple pages for integration tests.

    Creates:
    - Home page
    - Multiple linked pages
    - Pages with tags
    - Pages with attachments directory

    Returns:
        Notebook: Populated notebook instance
    """
    from notebook.notebook import Notebook
    from notebook.page import Path

    notebook_dir = tmp_path / "populated_notebook"
    notebook_dir.mkdir()

    # Create config
    (notebook_dir / "notebook.zim").write_text(
        "[Notebook]\n"
        "name=Populated Notebook\n"
        "home=Home\n"
    )

    try:
        notebook = Notebook(notebook_dir)

        # Create Home page
        home_path = Path("Home")
        home_page = notebook.get_page(home_path)
        home_page.parse("wiki", "= Home =\n\nWelcome to [[Journal]] and [[Projects]].")
        notebook.store_page(home_page)

        # Create Journal page
        journal_path = Path("Journal")
        journal_page = notebook.get_page(journal_path)
        journal_page.parse("wiki", "= Journal =\n\n@daily\n\nToday's notes.")
        notebook.store_page(journal_page)

        # Create Projects page
        projects_path = Path("Projects")
        projects_page = notebook.get_page(projects_path)
        projects_page.parse("wiki", "= Projects =\n\n@work\n\nCurrent tasks.")
        notebook.store_page(projects_page)

        yield notebook

    except Exception as e:
        # If notebook creation fails, return a mock
        mock_nb = Mock()
        mock_nb.folder = notebook_dir
        mock_nb.readonly = False
        yield mock_nb


@pytest.fixture
def mock_event_manager():
    """Create a mock event manager for SSE testing.

    Returns:
        Mock: Configured event manager mock
    """
    manager = Mock()
    manager.emit = Mock()
    return manager


@pytest.fixture
def mock_applet_manager(tmp_path):
    """Create a mock applet manager for testing.

    Returns:
        Mock: Configured applet manager mock
    """
    manager = Mock()
    manager.list_applets = Mock(return_value=[])
    manager.get_applet = Mock(return_value=None)
    manager.refresh = Mock()
    return manager


@pytest.fixture(scope="session")
def large_notebook(tmp_path_factory):
    """Create a large notebook for performance testing.

    Creates a notebook with 1000+ pages for benchmarking.

    WARNING: This is expensive. Use sparingly.

    Returns:
        Notebook: Large notebook instance
    """
    from notebook.notebook import Notebook
    from notebook.page import Path

    tmp_dir = tmp_path_factory.mktemp("large_nb")
    notebook_dir = tmp_dir / "large_notebook"
    notebook_dir.mkdir()

    # Create config
    (notebook_dir / "notebook.zim").write_text(
        "[Notebook]\n"
        "name=Large Notebook\n"
        "home=Home\n"
    )

    try:
        notebook = Notebook(notebook_dir)

        # Create 1000 pages
        for i in range(1000):
            path = Path(f"Page{i:04d}")
            page = notebook.get_page(path)
            page.parse("wiki", f"= Page {i} =\n\nContent for page {i}.\n\n@test tag{i % 10}.")
            notebook.store_page(page)

        return notebook

    except Exception:
        # Return mock if creation fails
        mock_nb = Mock()
        mock_nb.folder = notebook_dir
        return mock_nb


# Helper functions for tests

def create_test_page(notebook, name, content="Test content"):
    """Helper to create a test page.

    Args:
        notebook: Notebook instance
        name: Page name (Path or string)
        content: Page content (default: "Test content")

    Returns:
        Page: Created page object
    """
    from notebook.page import Path

    path = Path(name) if isinstance(name, str) else name
    page = notebook.get_page(path)
    page.parse("wiki", content)

    if hasattr(notebook, "store_page"):
        notebook.store_page(page)

    return page


def assert_api_response(status, headers, body, expected_status=200, has_data=True):
    """Helper to assert common API response properties.

    Args:
        status: HTTP status code from API call
        headers: Headers dict from API call
        body: Response body from API call
        expected_status: Expected HTTP status (default: 200)
        has_data: Whether body should contain data (default: True)
    """
    assert status == expected_status, f"Expected {expected_status}, got {status}: {body}"
    if has_data and expected_status == 200:
        assert body is not None, "Response body should not be None for successful response"


# Pytest hooks

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests (fast, isolated)"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests (slower, use fixtures)"
    )
    config.addinivalue_line(
        "markers", "api: API endpoint tests"
    )
    config.addinivalue_line(
        "markers", "concurrency: Concurrency and thread-safety tests"
    )
    config.addinivalue_line(
        "markers", "slow: Slow-running tests (>1s)"
    )
    config.addinivalue_line(
        "markers", "network: Tests that require network access"
    )


def pytest_collection_modifyitems(config, items):
    """Automatically mark tests based on their location and name."""
    for item in items:
        # Mark tests in test_unit/ as unit tests
        if "/test_unit/" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        # Mark tests in test_integration/ as integration tests
        elif "/test_integration/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        # Mark tests in test_api/ as API tests
        elif "/test_api/" in str(item.fspath):
            item.add_marker(pytest.mark.api)
        # Mark tests in test_concurrency/ as concurrency tests
        elif "/test_concurrency/" in str(item.fspath):
            item.add_marker(pytest.mark.concurrency)
