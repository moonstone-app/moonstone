"""Test multi-statement transaction atomicity with auto-commit."""

import os
import tempfile
import pytest
from notebook.pool import ConnectionPool


class TestMultiStatementTransactions:
    """Test that multi-statement transactions work correctly with auto-commit."""
    
    @pytest.fixture
    def pool(self):
        """Create a connection pool for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test.db')
            pool = ConnectionPool(db_path, size=2)
            
            # Initialize schema
            with pool.get_connection() as conn:
                conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
            
            yield pool
    
    def test_multi_insert_transaction(self, pool):
        """Test multiple INSERTs in one transaction."""
        with pool.get_connection() as conn:
            conn.execute("INSERT INTO test (name) VALUES (?)", ("Alice",))
            conn.execute("INSERT INTO test (name) VALUES (?)", ("Bob",))
            conn.execute("INSERT INTO test (name) VALUES (?)", ("Charlie",))
        
        # All should be committed
        with pool.get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM test").fetchone()[0]
            assert count == 3, f"Expected 3 rows, got {count}"
    
    def test_explicit_commit_backward_compat(self, pool):
        """Test that explicit commit() still works (backward compatibility)."""
        with pool.get_connection() as conn:
            conn.execute("INSERT INTO test (name) VALUES (?)", ("David",))
            conn.execute("INSERT INTO test (name) VALUES (?)", ("Eve",))
            conn.commit()  # Explicit commit
        
        # Both should be present (double commit is safe)
        with pool.get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM test").fetchone()[0]
            assert count == 2, f"Expected 2 rows, got {count}"
    
    def test_nested_get_connection_calls(self, pool):
        """Test that nested get_connection() calls work correctly."""
        def inner_function(pool):
            with pool.get_connection() as conn:
                conn.execute("INSERT INTO test (name) VALUES (?)", ("Frank",))
        
        with pool.get_connection() as conn:
            conn.execute("INSERT INTO test (name) VALUES (?)", ("Grace",))
            inner_function(pool)  # Nested call
        
        # Both should be committed
        with pool.get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM test").fetchone()[0]
            names = [row[0] for row in conn.execute("SELECT name FROM test ORDER BY name").fetchall()]
            assert count == 2, f"Expected 2 rows, got {count}"
            assert "Frank" in names and "Grace" in names
    
    def test_transaction_atomicity(self, pool):
        """Test that operations in a transaction are atomic."""
        # Insert some initial data
        pool.execute("INSERT INTO test (name) VALUES (?)", ("Initial",))
        
        # Multi-statement transaction
        with pool.get_connection() as conn:
            conn.execute("INSERT INTO test (name) VALUES (?)", ("Test1",))
            conn.execute("INSERT INTO test (name) VALUES (?)", ("Test2",))
            conn.execute("UPDATE test SET name = ? WHERE name = ?", ("Modified", "Initial"))
        
        # All changes should be visible
        with pool.get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM test").fetchone()[0]
            modified = conn.execute("SELECT name FROM test WHERE name = ?", ("Modified",)).fetchone()
            assert count == 3, f"Expected 3 rows, got {count}"
            assert modified is not None, "Initial row should have been modified"

