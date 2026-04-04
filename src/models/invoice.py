"""
Invoice data model.
====================

Data model for supplier invoices extracted by Azure Document Intelligence.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional, List


@dataclass
class InvoiceLineItem:
    """A single line item on an invoice."""
    line_number: int = 0
    item_code: str = ""
    description: str = ""
    quantity: float = 0.0
    unit_price: float = 0.0
    total: float = 0.0
    po_number: str = ""
    po_line: str = ""


@dataclass
class Invoice:
    """Extracted invoice data."""
    file_name: str = ""
    supplier_id: str = ""
    supplier_name: str = ""
    invoice_number: str = ""
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    total_amount: float = 0.0
    vat_amount: float = 0.0
    net_amount: float = 0.0
    currency: str = "ILS"
    po_number: str = ""
    items: List[InvoiceLineItem] = field(default_factory=list)
    confidence: float = 0.0
    validation_status: str = ""  # "ok", "warning", "error"
    validation_notes: List[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "file_name": self.file_name,
            "supplier_id": self.supplier_id,
            "supplier_name": self.supplier_name,
            "invoice_number": self.invoice_number,
            "invoice_date": self.invoice_date.isoformat() if self.invoice_date else "",
            "due_date": self.due_date.isoformat() if self.due_date else "",
            "total_amount": self.total_amount,
            "vat_amount": self.vat_amount,
            "net_amount": self.net_amount,
            "currency": self.currency,
            "po_number": self.po_number,
            "items": [
                {
                    "line_number": item.line_number,
                    "item_code": item.item_code,
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "total": item.total,
                    "po_number": item.po_number,
                }
                for item in self.items
            ],
            "confidence": self.confidence,
            "validation_status": self.validation_status,
            "validation_notes": self.validation_notes,
        }
