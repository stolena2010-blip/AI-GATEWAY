"""
DIEngine — Azure Document Intelligence engine.
=================================================

Used by profiles: invoices, delivery.
Uses prebuilt-invoice or prebuilt-layout models for extraction,
then GPT-4o-mini for validation.

Phase 3 implementation — stub for now.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional

from src.core.cost_tracker import CostTracker
from src.utils.logger import get_logger

logger = get_logger(__name__)


class DIEngine:
    """Azure Document Intelligence — for invoices, delivery notes.

    Requires: azure-ai-documentintelligence package.
    """

    def __init__(self, ai_config: Dict[str, Any], cost_tracker: CostTracker):
        self.di_model = ai_config.get("di_model", "prebuilt-invoice")
        self.validate_model = ai_config.get("validate_model", "gpt-4o-mini")
        self.prompts_folder = ai_config.get("prompts_folder", "prompts/invoices")
        self.cost_tracker = cost_tracker
        self._di_client = None

    def _get_di_client(self):
        """Lazy-init Azure Document Intelligence client."""
        if self._di_client is None:
            try:
                from src.services.ai.document_intelligence import get_di_client
                self._di_client = get_di_client()
            except ImportError:
                raise ImportError(
                    "azure-ai-documentintelligence package not installed. "
                    "Run: pip install azure-ai-documentintelligence"
                )
        return self._di_client

    def classify(self, file_path: Path) -> str:
        """Classify a document using Azure DI."""
        client = self._get_di_client()
        from src.services.ai.document_intelligence import classify_document
        return classify_document(client, file_path, model=self.di_model)

    def extract(self, file_path: Path, doc_type: str) -> Dict[str, Any]:
        """Extract structured data using Azure DI + GPT validation."""
        client = self._get_di_client()
        from src.services.ai.document_intelligence import extract_document
        di_result = extract_document(client, file_path, model=self.di_model)

        # Validate with GPT-4o-mini
        from src.services.ai.gpt_validator import validate_extraction
        validated = validate_extraction(
            di_result,
            prompts_folder=self.prompts_folder,
            model=self.validate_model,
        )
        return validated

    def process_folder(self, folder_path: Path, **kwargs) -> List[Dict[str, Any]]:
        """Process all supported files in a folder."""
        results = []
        supported_ext = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
        for file_path in sorted(folder_path.iterdir()):
            if file_path.suffix.lower() in supported_ext:
                try:
                    doc_type = self.classify(file_path)
                    if doc_type == "SKIP":
                        continue
                    data = self.extract(file_path, doc_type)
                    results.append(data)
                except Exception as e:
                    logger.error(f"Failed to process {file_path.name}: {e}")
                    results.append({"file": file_path.name, "error": str(e)})
        return results
