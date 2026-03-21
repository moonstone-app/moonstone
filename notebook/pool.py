# -*- coding: utf-8 -*-
"""Connection pool for thread-safe SQLite access.

Replaces the fake "main thread dispatch" pattern with proper
connection pooling. Each thread gets its own database connection,
allowing true concurrent access (with WAL mode).
"""

import os
import sqlite3
import threading
import queue
import logging
from contextlib import contextmanager

logger = logging.getLogger("moonstone.pool")


class ConnectionPool:
    """Thread-safe pool of SQLite connections.

    Usage:
        pool = ConnectionPool(db_path, size=4)
        with pool.get_connection() as conn:
            result = conn.execute("SELECT ...").fetchall()
    """

    def __init__(self, db_path, size=4, timeout=30):
        """Initialize the connection pool.

        Args:
            db_path: Path to SQLite database
            size: Number of connections to maintain (default: 4)
            timeout: Seconds to wait for a connection (default: 30)
        """
        self.db_path = db_path
        self.size = size
        self.timeout = timeout
        self._pool = queue.Queue(maxsize=size)
        self._local = threading.local()
        self._lock = threading.Lock()

        # Create connections
        for _ in range(size):
            conn = self._create_connection()
            self._pool.put(conn)

    def _create_connection(self):
        """Create a new SQLite connection with proper settings."""
        conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=1  # Short timeout for connection pool usage
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def get_connection(self):
        """Get a connection from the pool.

        Thread-local caching: each thread reuses its cached connection
        even for nested get_connection() calls.

        Returns:
            Context manager that yields a connection
        """
        # Track nesting depth for thread-local connection
        try:
            depth = self._local.depth
        except AttributeError:
            depth = 0
            self._local.depth = 0

        # Check if thread has a cached connection
        try:
            conn = self._local.conn
        except AttributeError:
            conn = None

        # If we have a cached connection, use it (even for nested calls)
        if conn is not None:
            self._local.depth = depth + 1
            try:
                yield conn
            finally:
                # Restore previous depth
                prev_depth = self._local.depth
                self._local.depth = depth
                # Only commit when exiting the outermost call (depth was 1, now back to 0)
                if prev_depth == 1 and depth == 0:
                    try:
                        conn.commit()
                    except Exception:
                        pass  # No transaction or commit failed
            return

        # Get connection from pool (blocks if pool exhausted)
        try:
            conn = self._pool.get(timeout=self.timeout)
        except queue.Empty:
            raise RuntimeError(
                f"Timeout waiting for database connection "
                f"(pool={self.size}, timeout={self.timeout}s)"
            )

        # Store in thread-local cache
        self._local.conn = conn
        self._local.depth = 1

        try:
            yield conn
        finally:
            self._local.depth = 0
            # Commit any pending transaction before returning to pool
            try:
                conn.commit()
            except Exception:
                pass  # No transaction or commit failed
            # Return connection to pool for other threads to use
            try:
                self._pool.put(conn, block=False)
                # Clear cache so it can be re-acquired from pool if needed
                try:
                    del self._local.conn
                except AttributeError:
                    pass
            except queue.Full:
                # Pool is full, keep it cached
                pass

    def return_connection(self):
        """Return the current thread's connection back to the pool and clear cache.

        This is useful when a thread is done and wants to release its cached connection.
        """
        try:
            conn = self._local.conn
            if conn is None:
                return
        except AttributeError:
            return

        # Only return if not currently in use
        in_use = getattr(self._local, 'in_use', False)
        if not in_use:
            try:
                self._pool.put(conn, block=False)
            except queue.Full:
                # Pool is full, just close it
                try:
                    conn.close()
                except Exception:
                    pass
            finally:
                self._local.conn = None
                if hasattr(self._local, 'in_use'):
                    del self._local.in_use

    def close_all(self):
        """Close all connections and shut down the pool.

        This method:
        1. Returns thread-local cached connection to pool
        2. Closes all pooled connections
        """
        with self._lock:
            # Return thread-local cached connection
            try:
                conn = self._local.conn
                if conn is not None:
                    try:
                        self._pool.put(conn, block=False)
                    except queue.Full:
                        conn.close()
                    self._local.conn = None
            except AttributeError:
                pass

            # Close all connections in pool
            while not self._pool.empty():
                try:
                    conn = self._pool.get_nowait()
                    conn.close()
                except queue.Empty:
                    break

    def execute(self, sql, params=None, many=False):
        """Execute SQL on any available connection.

        Convenience method for simple queries that don't need
        to hold a connection open.

        Note: This method auto-commits for convenience.

        Args:
            sql: SQL statement
            params: Parameters for the statement
            many: If True, execute executemany() instead of execute()

        Returns:
            For single query: cursor or None
            For many: None
        """
        with self.get_connection() as conn:
            if many:
                conn.executemany(sql, params or [])
                conn.commit()  # Commit the changes
                return None
            else:
                cursor = conn.execute(sql, params or [])
                conn.commit()  # Commit the changes
                return cursor


# Global pool for the notebook
_global_pool = None
_pool_lock = threading.Lock()


def get_pool(db_path=None, size=4):
    """Get or create the global connection pool.

    Args:
        db_path: Path to database (uses default if None)
        size: Pool size

    Returns:
        ConnectionPool instance
    """
    global _global_pool

    with _pool_lock:
        if _global_pool is None:
            if db_path is None:
                raise ValueError("db_path must be provided on first call")
            _global_pool = ConnectionPool(db_path, size=size)
        return _global_pool


def close_pool():
    """Close the global connection pool.

    Returns all thread-local connections and closes all pooled connections.
    """
    global _global_pool

    with _pool_lock:
        if _global_pool is not None:
            _global_pool.close_all()
            _global_pool = None
