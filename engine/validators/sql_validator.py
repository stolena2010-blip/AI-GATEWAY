"""
SQLValidator — SQL Server based validation against Kitaron ERP.
================================================================

Used by profiles: invoices, delivery (validation.type == "sql_server").
READ-ONLY access to Kitaron ERP database.

Phase 3 implementation — stub for now.
Requires: pyodbc + ODBC Driver 17 for SQL Server.
"""

from typing import Dict, Any, List

from src.utils.logger import get_logger

logger = get_logger(__name__)


class SQLValidator:
    """SQL Server validation — supplier lookup + PO matching."""

    def __init__(self, validation_config: Dict[str, Any]):
        self.supplier_lookup = validation_config.get("supplier_lookup", True)
        self.po_matching = validation_config.get("po_matching", True)
        self.price_tolerance_percent = validation_config.get("price_tolerance_percent", 5)
        self._db = None

    def _get_db(self):
        """Lazy-init database connection."""
        if self._db is None:
            try:
                from src.services.database.connector import KitaronDB
                self._db = KitaronDB()
            except ImportError:
                raise ImportError(
                    "pyodbc package not installed. "
                    "Run: pip install pyodbc"
                )
        return self._db

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate extracted data against Kitaron ERP.

        - Supplier lookup: match supplier name/ID to ERP records
        - PO matching: match purchase order numbers
        - Price validation: check within tolerance
        """
        db = self._get_db()

        if self.supplier_lookup:
            supplier_id = data.get("supplier_id", "")
            supplier_name = data.get("supplier_name", "")
            if supplier_id or supplier_name:
                from src.services.database.queries import lookup_supplier
                match = lookup_supplier(db, supplier_id, supplier_name)
                if match:
                    data["supplier_validated"] = True
                    data["supplier_erp_id"] = match.get("id", "")
                else:
                    data["supplier_validated"] = False

        if self.po_matching:
            po_number = data.get("po_number", "")
            if po_number:
                from src.services.database.queries import lookup_po
                po_match = lookup_po(db, po_number)
                if po_match:
                    data["po_validated"] = True
                    data["po_details"] = po_match
                    # Price tolerance check
                    if self.price_tolerance_percent and "total_amount" in data:
                        expected = po_match.get("amount", 0)
                        actual = data.get("total_amount", 0)
                        if expected and actual:
                            diff_pct = abs(actual - expected) / expected * 100
                            data["price_within_tolerance"] = diff_pct <= self.price_tolerance_percent
                else:
                    data["po_validated"] = False

        return data

    def validate_batch(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validate a batch of extraction results."""
        return [self.validate(data) for data in results]
