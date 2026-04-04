"""
Kitaron ERP Queries — READ-ONLY lookup functions.
===================================================

Supplier lookup and PO matching against Kitaron ERP.
"""

from typing import Dict, Any, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


def lookup_supplier(db, supplier_id: str = "", supplier_name: str = "") -> Optional[Dict[str, Any]]:
    """Look up a supplier in Kitaron ERP by ID or name.

    Returns supplier record dict or None if not found.
    """
    if supplier_id:
        results = db.execute_query(
            "SELECT TOP 1 * FROM Suppliers WHERE SupplierID = ?",
            (supplier_id,),
        )
        if results:
            return results[0]

    if supplier_name:
        # Fuzzy name match using LIKE
        results = db.execute_query(
            "SELECT TOP 5 * FROM Suppliers WHERE SupplierName LIKE ?",
            (f"%{supplier_name}%",),
        )
        if results:
            return results[0]

    return None


def lookup_po(db, po_number: str) -> Optional[Dict[str, Any]]:
    """Look up a purchase order in Kitaron ERP.

    Returns PO record dict or None if not found.
    """
    if not po_number:
        return None

    results = db.execute_query(
        "SELECT TOP 1 * FROM PurchaseOrders WHERE PONumber = ?",
        (po_number,),
    )
    return results[0] if results else None


def get_supplier_pos(db, supplier_id: str, limit: int = 50) -> list:
    """Get recent purchase orders for a supplier."""
    return db.execute_query(
        "SELECT TOP (?) * FROM PurchaseOrders WHERE SupplierID = ? ORDER BY PODate DESC",
        (limit, supplier_id),
    )
