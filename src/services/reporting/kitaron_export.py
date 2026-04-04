"""
Kitaron ERP Interface File Export.
====================================

Generates fixed-width text files for Kitaron ERP import.
Configurable field mapping per format (invoices, delivery notes).
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Field definitions: (name, width, alignment, pad_char)
KITARON_INVOICE_FIELDS = [
    ("record_type", 2, "left", " "),
    ("supplier_id", 10, "right", "0"),
    ("invoice_number", 20, "left", " "),
    ("invoice_date", 8, "left", " "),       # YYYYMMDD
    ("total_amount", 15, "right", " "),      # decimal as string
    ("vat_amount", 15, "right", " "),
    ("currency", 3, "left", " "),
    ("po_number", 20, "left", " "),
    ("description", 50, "left", " "),
    ("status", 2, "left", " "),
]

KITARON_DELIVERY_FIELDS = [
    ("record_type", 2, "left", " "),
    ("supplier_id", 10, "right", "0"),
    ("delivery_number", 20, "left", " "),
    ("delivery_date", 8, "left", " "),       # YYYYMMDD
    ("po_number", 20, "left", " "),
    ("item_code", 20, "left", " "),
    ("quantity", 10, "right", " "),
    ("description", 50, "left", " "),
    ("status", 2, "left", " "),
]

FORMAT_REGISTRY = {
    "kitaron_invoice": KITARON_INVOICE_FIELDS,
    "kitaron_delivery": KITARON_DELIVERY_FIELDS,
}


def _format_field(value: str, width: int, alignment: str, pad_char: str) -> str:
    """Format a single field to fixed width."""
    value = str(value or "")[:width]
    if alignment == "right":
        return value.rjust(width, pad_char)
    return value.ljust(width, pad_char)


def generate_interface_file(
    results: List[Dict[str, Any]],
    output_path: Path,
    format_name: str = "kitaron_invoice",
) -> Path:
    """Generate a fixed-width interface file for Kitaron ERP.

    Args:
        results: List of extracted/validated document dicts
        output_path: Path for the output file
        format_name: One of the registered formats

    Returns:
        Path to the generated file
    """
    fields = FORMAT_REGISTRY.get(format_name)
    if not fields:
        raise ValueError(f"Unknown interface format: {format_name}. "
                         f"Available: {list(FORMAT_REGISTRY.keys())}")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    for record in results:
        # Build a flat dict from the record's fields
        flat = {}
        if "validated_fields" in record:
            flat.update(record["validated_fields"])
        if "fields" in record:
            for k, v in record["fields"].items():
                if k not in flat:
                    flat[k] = v.get("value", "") if isinstance(v, dict) else str(v)
        flat.update({k: v for k, v in record.items() if k not in ("fields", "validated_fields", "tables", "raw_text")})

        line_parts = []
        for field_name, width, alignment, pad_char in fields:
            value = flat.get(field_name, "")
            line_parts.append(_format_field(value, width, alignment, pad_char))

        lines.append("".join(line_parts))

    with open(output_path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")

    logger.info(f"Interface file generated: {output_path} ({len(lines)} records)")
    return output_path
