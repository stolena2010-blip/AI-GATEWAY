"""
Azure Document Intelligence client.
=====================================

Prebuilt invoice model, layout model, read model.
Multi-page PDF native. Hebrew + handwriting support.

Requires: pip install azure-ai-documentintelligence
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)

_client = None


def get_di_client():
    """Get or create a Document Intelligence client singleton."""
    global _client
    if _client is not None:
        return _client

    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential

    endpoint = os.getenv("AZURE_DI_ENDPOINT", "")
    api_key = os.getenv("AZURE_DI_API_KEY", "")

    if not endpoint or not api_key:
        raise ValueError(
            "AZURE_DI_ENDPOINT and AZURE_DI_API_KEY must be set in .env"
        )

    _client = DocumentIntelligenceClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(api_key),
    )
    logger.info("Azure Document Intelligence client initialized")
    return _client


def classify_document(client, file_path: Path, model: str = "prebuilt-invoice") -> str:
    """Classify a document type using Azure DI.

    Returns the detected document type or 'OTHER'.
    """
    file_path = Path(file_path)
    with open(file_path, "rb") as f:
        poller = client.begin_analyze_document(
            model_id=model,
            body=f,
            content_type="application/octet-stream",
        )
    result = poller.result()

    if result.documents:
        doc_type = result.documents[0].doc_type or "OTHER"
        confidence = result.documents[0].confidence or 0
        logger.info(f"Classified {file_path.name}: {doc_type} (confidence={confidence:.2f})")
        return doc_type

    return "OTHER"


def extract_document(client, file_path: Path, model: str = "prebuilt-invoice") -> Dict[str, Any]:
    """Extract structured data from a document using Azure DI.

    Returns a dict with extracted fields.
    """
    file_path = Path(file_path)
    with open(file_path, "rb") as f:
        poller = client.begin_analyze_document(
            model_id=model,
            body=f,
            content_type="application/octet-stream",
        )
    result = poller.result()

    extracted = {
        "file": file_path.name,
        "model": model,
        "pages": len(result.pages) if result.pages else 0,
        "fields": {},
        "tables": [],
        "raw_text": result.content or "",
    }

    # Extract document-level fields
    if result.documents:
        doc = result.documents[0]
        extracted["doc_type"] = doc.doc_type
        extracted["confidence"] = doc.confidence
        if doc.fields:
            for name, field in doc.fields.items():
                extracted["fields"][name] = {
                    "value": field.content if hasattr(field, "content") else str(field.value) if field.value else "",
                    "confidence": field.confidence if hasattr(field, "confidence") else None,
                    "type": field.type if hasattr(field, "type") else None,
                }

    # Extract tables
    if result.tables:
        for table in result.tables:
            table_data = {
                "row_count": table.row_count,
                "column_count": table.column_count,
                "cells": [],
            }
            for cell in table.cells:
                table_data["cells"].append({
                    "row": cell.row_index,
                    "col": cell.column_index,
                    "content": cell.content,
                })
            extracted["tables"].append(table_data)

    logger.info(
        f"Extracted {file_path.name}: {len(extracted['fields'])} fields, "
        f"{len(extracted['tables'])} tables, {extracted['pages']} pages"
    )
    return extracted
