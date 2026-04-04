"""
Kitaron ERP Database Connector — READ-ONLY.
=============================================

SQL Server connector for supplier lookup and PO matching.
Requires: pyodbc + ODBC Driver 17 for SQL Server.
"""

import os
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


class KitaronDB:
    """Read-only SQL Server connector to Kitaron ERP."""

    def __init__(
        self,
        server: Optional[str] = None,
        database: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        import pyodbc

        self.server = server or os.getenv("KITARON_DB_SERVER", "")
        self.database = database or os.getenv("KITARON_DB_NAME", "")
        self.username = username or os.getenv("KITARON_DB_USER", "")
        self.password = password or os.getenv("KITARON_DB_PASSWORD", "")
        self._conn = None

    def _get_connection(self):
        """Get or create a database connection."""
        import pyodbc

        if self._conn is None:
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={self.server};"
                f"DATABASE={self.database};"
                f"UID={self.username};"
                f"PWD={self.password};"
                f"ApplicationIntent=ReadOnly;"
                f"TrustServerCertificate=yes;"
            )
            self._conn = pyodbc.connect(conn_str, readonly=True)
            logger.info(f"Connected to Kitaron DB: {self.server}/{self.database}")
        return self._conn

    def execute_query(self, query: str, params: tuple = ()) -> list:
        """Execute a read-only query and return results as list of dicts."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("Kitaron DB connection closed")
