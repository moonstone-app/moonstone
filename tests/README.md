# Moonstone Test Suite

This directory contains the test suite for Moonstone.

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=moonstone --cov-report=html

# Run specific test file
pytest tests/test_search.py

# Run only unit tests (fast)
pytest -m unit

# Run only integration tests
pytest -m integration

# Run with verbose output
pytest -v

# Run and stop on first failure
pytest -x

# Run with specific marker
pytest -m "not slow"
```

## Test Organization

```
tests/
├── conftest.py              # Pytest fixtures and configuration
├── test_unit/               # Unit tests (fast, isolated)
│   ├── test_search.py       # Search module tests
│   ├── test_config.py       # Configuration tests
│   └── test_parse_*.py      # Parser tests
├── test_integration/        # Integration tests
│   ├── test_pages.py        # Page CRUD tests
│   ├── test_search.py       # Search integration tests
│   └── test_links.py        # Link resolution tests
├── test_api/                # API endpoint tests
│   ├── test_api_pages.py    # Page API endpoints
│   ├── test_api_tags.py     # Tag API endpoints
│   └── test_api_links.py    # Link API endpoints
├── test_concurrency/        # Concurrency tests
│   ├── test_threading.py    # Thread safety tests
│   └── test_conflicts.py    # Concurrent write conflicts
└── fixtures/                # Test data
    └── notebooks/           # Sample notebooks
```

## Fixtures

Key fixtures available in tests:

- `temp_notebook` - Empty notebook in temp directory
- `api_client` - API client with full access
- `readonly_api` - Read-only API client
- `sample_page` - Pre-populated test page
- `sample_notebook_structure` - Notebook with multiple pages
- `mock_event_manager` - Mock SSE event manager
- `mock_applet_manager` - Mock applet manager
- `large_notebook` - 1000+ page notebook (performance tests)

## Coverage Goals

| Module Type | Target |
|-------------|--------|
| Core business logic | 90% |
| API endpoints | 80% |
| Utilities | 70% |
| Threading code | 60% |

## Writing Tests

### Unit Test Example

```python
# tests/test_unit/test_search.py
import pytest
from moonstone.search import Query, SearchSelection

@pytest.mark.unit
class TestQuery:
    def test_empty_query(self):
        q = Query("")
        assert not q

    def test_simple_query(self):
        q = Query("test query")
        assert str(q) == "test query"
```

### Integration Test Example

```python
# tests/test_integration/test_pages.py
import pytest
from moonstone.notebook.page import Path

@pytest.mark.integration
class TestPageCRUD:
    def test_create_read_update_delete(self, temp_notebook):
        # Create
        page = temp_notebook.get_page(Path("TestPage"))
        page.parse("wiki", "content")
        temp_notebook.store_page(page)

        # Read
        page = temp_notebook.get_page(Path("TestPage"))
        assert page.hascontent

        # Delete
        temp_notebook.delete_page(Path("TestPage"))
```

### API Test Example

```python
# tests/test_api/test_api_pages.py
import pytest

@pytest.mark.api
class TestPagesAPI:
    def test_get_page_exists(self, api_client, sample_page):
        status, headers, body = api_client.get_page("TestPage")
        assert status == 200
        assert "content" in body

    def test_get_page_not_found(self, api_client):
        status, headers, body = api_client.get_page("NonExistent")
        assert status == 404
```

## Continuous Integration

The test suite is configured to:
- Fail on any test error
- Generate coverage reports
- Run tests in parallel when possible
- Clean up temporary files automatically

## Debugging Tests

```bash
# Run with pdb on failure
pytest --pdb

# Show print statements
pytest -s

# Run specific test with output
pytest tests/test_search.py::TestQuery::test_simple_query -v -s
```
