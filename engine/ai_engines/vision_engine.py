"""
VisionEngine — Wraps existing Azure OpenAI Vision pipeline.
=============================================================

Used by profiles: quotes, orders, complaints.
Delegates to existing customer_extractor_v3_dual.scan_folder()
and the drawing_pipeline stages.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional

from src.core.cost_tracker import CostTracker
from src.utils.logger import get_logger

logger = get_logger(__name__)


class VisionEngine:
    """Azure OpenAI Vision — for quotes, orders, complaints.

    Wraps the existing extraction pipeline. Does NOT rewrite it.
    """

    def __init__(self, ai_config: Dict[str, Any], cost_tracker: CostTracker):
        self.stages = ai_config.get("stages", [0, 1, 2, 3, 4, 5, 9])
        self.prompts_folder = ai_config.get("prompts_folder", "prompts")
        self.classify_model = ai_config.get("classify_model", "gpt-4o-vision")
        self.extract_model = ai_config.get("extract_model", "gpt-5.4")
        self.stage_models = ai_config.get("stage_models", {})
        self.enable_ocr = ai_config.get("enable_ocr", True)
        self.enable_image_retry = ai_config.get("enable_image_retry", False)
        self.customer_variants = ai_config.get("customer_variants", ["generic"])
        self.max_image_dimension = ai_config.get("max_image_dimension", 4096)
        self.cost_tracker = cost_tracker

    def classify(self, file_path: Path) -> str:
        """Classify a file using Vision API. Returns doc type string."""
        from src.services.file.classifier import classify_file_type
        return classify_file_type(str(file_path))

    def extract(self, file_path: Path, doc_type: str) -> Dict[str, Any]:
        """Extract data from a file using the staged Vision pipeline."""
        from src.services.extraction.drawing_pipeline import run_drawing_pipeline
        result = run_drawing_pipeline(
            str(file_path),
            stages=self.stages,
            stage_models=self.stage_models,
            enable_ocr=self.enable_ocr,
        )
        return result or {}

    def process_folder(self, folder_path: Path, **kwargs) -> List[Dict[str, Any]]:
        """Process an entire folder using the existing scan_folder function.

        This is the primary entry point — it delegates to the battle-tested
        customer_extractor_v3_dual.scan_folder() which handles:
        - File classification
        - Image extraction & preprocessing
        - Multi-stage Vision API calls
        - OCR fallback
        - P.N. voting & sanity checks
        - B2B export
        """
        from customer_extractor_v3_dual import scan_folder
        return scan_folder(str(folder_path), **kwargs)
