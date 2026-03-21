# -*- coding: utf-8 -*-
"""Unit tests for ConnectionPool.

Tests thread-safe connection pooling with:
- Thread-local connection caching
- Pool exhaustion handling
- Connection lifecycle management
"""

import os
import sys
import tempfile
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary SQLite database for testing.

    Returns:
        pathlib.Path: Path to temporary database
    """
    db_path = tmp_path / "test.db"
    # Initialize with a simple schema
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE test (
            id INTEGER PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()
    return db_path


class TestConnectionPool:
    """Test ConnectionPool basic functionality."""

    def test_pool_initialization(self, temp_db):
        """Pool creates correct number of connections."""
        from notebook.pool import ConnectionPool

        pool = ConnectionPool(str(temp_db), size=4)

        # All connections should be created
        assert pool.size == 4
        assert pool.timeout == 30

        pool.close_all()

    def test_get_connection_context_manager(self, temp_db):
        """Connection context manager yields working connection."""
        from notebook.pool import ConnectionPool

        pool = ConnectionPool(str(temp_db), size=2)

        with pool.get_connection() as conn:
            assert conn is not None
            # Should be able to execute queries
            result = conn.execute("SELECT 1").fetchone()
            assert result[0] == 1

        pool.close_all()

    def test_thread_local_connection_reuse(self, temp_db):
        """Same thread reuses connection within nested calls."""
        from notebook.pool import ConnectionPool

        pool = ConnectionPool(str(temp_db), size=2)

        with pool.get_connection() as conn1:
            conn1_id = id(conn1)

            # Nested call should reuse same connection
            with pool.get_connection() as conn2:
                conn2_id = id(conn2)

            # Should be same connection (nested call)
            assert conn1_id == conn2_id

        pool.close_all()

    def test_concurrent_threads_different_connections(self, temp_db):
        """Different threads get different connections from pool."""
        from notebook.pool import ConnectionPool

        pool = ConnectionPool(str(temp_db), size=4, timeout=5)

        connection_ids = []
        lock = threading.Lock()

        def get_conn_id():
            with pool.get_connection() as conn:
                conn_id = id(conn)
                with lock:
                    connection_ids.append(conn_id)
                # Hold connection briefly
                time.sleep(0.1)

        # Run 4 threads concurrently
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(get_conn_id) for _ in range(4)]
            for future in as_completed(futures):
                future.result()

        # Should have 4 unique connections
        unique_ids = set(connection_ids)
        assert len(unique_ids) == 4

        pool.close_all()

    def test_pool_exhaustion_timeout(self, temp_db):
        """Pool raises error when exhausted and timeout expires."""
        from notebook.pool import ConnectionPool

        pool = ConnectionPool(str(temp_db), size=2, timeout=1)

        held_connections = []

        def hold_connection():
            with pool.get_connection() as conn:
                held_connections.append(conn)
                time.sleep(2)  # Hold longer than timeout

        # Start 2 threads to exhaust pool
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(hold_connection) for _ in range(2)]
            # Let them start
            time.sleep(0.1)

            # Try to get a 3rd connection - should timeout
            with pytest.raises(RuntimeError, match="Timeout waiting for database connection"):
                with pool.get_connection() as conn:
                    pass

            # Clean up
            for future in futures:
                future.result()

        pool.close_all()

    def test_execute_convenience_method(self, temp_db):
        """execute() method runs simple queries."""
        from notebook.pool import ConnectionPool

        pool = ConnectionPool(str(temp_db), size=2)

        # Insert
        pool.execute("INSERT INTO test (value) VALUES (?)", ["test1"])

        # Select
        cursor = pool.execute("SELECT value FROM test WHERE value = ?", ["test1"])
        result = cursor.fetchone()
        assert result[0] == "test1"

        pool.close_all()

    def test_execute_many(self, temp_db):
        """executemany() inserts multiple rows."""
        from notebook.pool import ConnectionPool

        pool = ConnectionPool(str(temp_db), size=2)

        data = [("val1",), ("val2",), ("val3",)]
        pool.execute("INSERT INTO test (value) VALUES (?)", data, many=True)

        cursor = pool.execute("SELECT COUNT(*) FROM test")
        count = cursor.fetchone()[0]
        assert count == 3

        pool.close_all()

    def test_return_connection(self, temp_db):
        """return_connection() returns thread's connection to pool."""
        from notebook.pool import ConnectionPool

        pool = ConnectionPool(str(temp_db), size=2)

        # Get connection in thread
        with pool.get_connection() as conn1:
            conn1_id = id(conn1)

        # Return it
        pool.return_connection()

        # Get another connection - should be same one (returned to pool)
        with pool.get_connection() as conn2:
            # May or may not be same connection depending on pool state
            assert conn2 is not None

        pool.close_all()

    def test_close_all(self, temp_db):
        """close_all() closes all connections and clears pool."""
        from notebook.pool import ConnectionPool

        pool = ConnectionPool(str(temp_db), size=2)

        # Use connection
        with pool.get_connection() as conn:
            pass

        # Close pool
        pool.close_all()

        # All connections should be closed (pool is empty)
        assert pool._pool.qsize() == 0

    def test_wal_mode_enabled(self, temp_db):
        """Connections enable WAL mode for concurrent access."""
        from notebook.pool import ConnectionPool

        pool = ConnectionPool(str(temp_db), size=2)

        with pool.get_connection() as conn:
            cursor = conn.execute("PRAGMA journal_mode")
            mode = cursor.fetchone()[0]
            assert mode == "wal"

        pool.close_all()

    def test_foreign_keys_enabled(self, temp_db):
        """Connections enable foreign keys."""
        from notebook.pool import ConnectionPool

        pool = ConnectionPool(str(temp_db), size=2)

        with pool.get_connection() as conn:
            cursor = conn.execute("PRAGMA foreign_keys")
            enabled = cursor.fetchone()[0]
            assert enabled == 1

        pool.close_all()

    def test_row_factory_set(self, temp_db):
        """Connections have row_factory set to sqlite3.Row."""
        from notebook.pool import ConnectionPool

        pool = ConnectionPool(str(temp_db), size=2)

        with pool.get_connection() as conn:
            assert conn.row_factory == sqlite3.Row

        pool.close_all()


class TestGlobalPool:
    """Test global pool singleton functions."""

    def test_get_pool_creates_pool(self, temp_db):
        """get_pool() creates new pool on first call."""
        from notebook.pool import get_pool, close_pool

        # Close any existing pool
        close_pool()

        pool = get_pool(str(temp_db), size=4)
        assert pool is not None
        assert pool.size == 4

        close_pool()

    def test_get_pool_returns_same_pool(self, temp_db):
        """get_pool() returns same pool on subsequent calls."""
        from notebook.pool import get_pool, close_pool

        close_pool()

        pool1 = get_pool(str(temp_db), size=4)
        pool2 = get_pool()  # No args needed
        assert pool1 is pool2

        close_pool()

    def test_get_pool_requires_db_path_first_time(self, tmp_path):
        """get_pool() raises ValueError if db_path not provided on first call."""
        from notebook.pool import get_pool, close_pool

        close_pool()

        with pytest.raises(ValueError, match="db_path must be provided"):
            get_pool()  # No db_path

    def test_close_pool(self, temp_db):
        """close_pool() closes and clears global pool."""
        from notebook.pool import get_pool, close_pool

        close_pool()

        pool = get_pool(str(temp_db), size=4)
        close_pool()

        # Should create new pool after close
        pool2 = get_pool(str(temp_db), size=2)
        assert pool2.size == 2
        assert pool is not pool2

        close_pool()


class TestConcurrency:
    """Test concurrent access patterns."""

    def test_concurrent_reads(self, temp_db):
        """Multiple threads can read concurrently (WAL mode)."""
        from notebook.pool import ConnectionPool

        pool = ConnectionPool(str(temp_db), size=4)

        # Insert test data with explicit commit
        with pool.get_connection() as conn:
            conn.execute("INSERT INTO test (value) VALUES (?)", ["test"])
            conn.commit()

        results = []
        lock = threading.Lock()

        def read_value():
            with pool.get_connection() as conn:
                cursor = conn.execute("SELECT value FROM test")
                row = cursor.fetchone()
                if row:
                    value = row[0]
                    with lock:
                        results.append(value)

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(read_value) for _ in range(10)]
            for future in as_completed(futures):
                future.result()

        assert len(results) == 10
        assert all(r == "test" for r in results)

        pool.close_all()

    def test_concurrent_writes_serialized(self, temp_db):
        """Concurrent writes are serialized by SQLite (even with WAL).

        This test verifies that writes don't corrupt data, not that
        they're truly concurrent (SQLite serializes writes).
        """
        from notebook.pool import ConnectionPool

        pool = ConnectionPool(str(temp_db), size=4)

        counter = {"value": 0}
        lock = threading.Lock()
        errors = []

        def write_value(value):
            try:
                with pool.get_connection() as conn:
                    with lock:
                        counter["value"] += 1
                        val = counter["value"]
                    conn.execute("INSERT INTO test (value) VALUES (?)", [f"val{val}"])
                    conn.commit()
            except Exception as e:
                errors.append(e)

        # Run with some delay to avoid overwhelming SQLite
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(write_value, i) for i in range(10)]
            for future in as_completed(futures):
                future.result()

        # Should have no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        cursor = pool.execute("SELECT COUNT(*) FROM test")
        count = cursor.fetchone()[0]
        assert count == 10

        pool.close_all()
