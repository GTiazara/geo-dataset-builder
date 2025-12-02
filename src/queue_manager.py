"""
Queue manager for producer-consumer pattern.
Uses SQLite database to track unprocessed outputs between processes.
"""

import sqlite3
import time
from pathlib import Path
from typing import Optional, List, Tuple
from contextlib import contextmanager
import threading


class QueueManager:
    """
    Manages a queue of unprocessed output files using SQLite.
    Thread-safe and process-safe for inter-process communication.
    """
    
    def __init__(self, db_path: str = "output_queue.db", max_unprocessed: int = 10):
        """
        Initialize the queue manager.
        
        Args:
            db_path: Path to SQLite database file
            max_unprocessed: Maximum number of unprocessed items allowed
        """
        self.db_path = Path(db_path)
        self.max_unprocessed = max_unprocessed
        self._lock = threading.Lock()
        self._init_database()
    
    def _init_database(self):
        """Initialize the database schema."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS output_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL UNIQUE,
                    created_at REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    processed_at REAL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status ON output_queue(status)
            """)
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """Get a database connection with proper timeout for concurrent access."""
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,  # 30 second timeout for concurrent access
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def add_output(self, file_path: str) -> bool:
        """
        Add an output file to the queue.
        
        Args:
            file_path: Path to the output file
            
        Returns:
            True if added successfully, False if already exists
        """
        file_path = str(Path(file_path).resolve())
        with self._lock:
            with self._get_connection() as conn:
                try:
                    conn.execute("""
                        INSERT INTO output_queue (file_path, created_at, status)
                        VALUES (?, ?, 'pending')
                    """, (file_path, time.time()))
                    conn.commit()
                    return True
                except sqlite3.IntegrityError:
                    # File already in queue
                    return False
    
    def count_unprocessed(self) -> int:
        """Count the number of unprocessed items in the queue."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT COUNT(*) as count
                FROM output_queue
                WHERE status = 'pending'
            """)
            result = cursor.fetchone()
            return result['count'] if result else 0
    
    def can_produce(self) -> bool:
        """
        Check if producer can generate more outputs.
        
        Returns:
            True if there are less than max_unprocessed items, False otherwise
        """
        return self.count_unprocessed() < self.max_unprocessed
    
    def wait_until_can_produce(self, check_interval: float = 1.0):
        """
        Wait until producer can generate more outputs.
        
        Args:
            check_interval: Seconds to wait between checks
        """
        while not self.can_produce():
            time.sleep(check_interval)
    
    def get_next_pending(self) -> Optional[str]:
        """
        Get the next pending file path to process (FIFO order).
        
        Returns:
            File path or None if no pending items
        """
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT file_path
                FROM output_queue
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT 1
            """)
            result = cursor.fetchone()
            return result['file_path'] if result else None
    
    def mark_processing(self, file_path: str) -> bool:
        """
        Mark a file as being processed.
        
        Args:
            file_path: Path to the file
            
        Returns:
            True if marked successfully, False if not found
        """
        file_path = str(Path(file_path).resolve())
        with self._get_connection() as conn:
            cursor = conn.execute("""
                UPDATE output_queue
                SET status = 'processing'
                WHERE file_path = ? AND status = 'pending'
            """, (file_path,))
            conn.commit()
            return cursor.rowcount > 0
    
    def mark_completed(self, file_path: str):
        """
        Mark a file as completed and remove it from the queue.
        
        Args:
            file_path: Path to the file
        """
        file_path = str(Path(file_path).resolve())
        with self._get_connection() as conn:
            conn.execute("""
                DELETE FROM output_queue
                WHERE file_path = ?
            """, (file_path,))
            conn.commit()
    
    def get_all_pending(self) -> List[Tuple[str, float]]:
        """
        Get all pending file paths with their creation times.
        
        Returns:
            List of (file_path, created_at) tuples
        """
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT file_path, created_at
                FROM output_queue
                WHERE status = 'pending'
                ORDER BY created_at ASC
            """)
            return [(row['file_path'], row['created_at']) for row in cursor.fetchall()]
    
    def cleanup_missing_files(self):
        """
        Remove entries from queue for files that no longer exist.
        """
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT file_path FROM output_queue")
            for row in cursor.fetchall():
                file_path = row['file_path']
                if not Path(file_path).exists():
                    conn.execute("DELETE FROM output_queue WHERE file_path = ?", (file_path,))
            conn.commit()

