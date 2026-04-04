"""
InternalValidator — Wraps existing P.N. voting + sanity checks.
================================================================

Used by profiles: quotes, orders, complaints (validation.type == "internal").
"""

from typing import Dict, Any, List

from src.utils.logger import get_logger

logger = get_logger(__name__)


class InternalValidator:
    """Internal validation using existing P.N. voting and sanity checks."""

    def __init__(self, validation_config: Dict[str, Any]):
        self.pn_voting = validation_config.get("pn_voting", True)
        self.sanity_checks = validation_config.get("sanity_checks", True)

    def validate(self, data: Dict[str, Any], filename: str = "") -> Dict[str, Any]:
        """Run internal validation on extracted data.

        Wraps existing:
        - pn_voting.vote_best_pn()
        - sanity_checks.run_pn_sanity_checks()
        - sanity_checks.calculate_confidence()
        """
        if self.pn_voting:
            try:
                from src.services.extraction.pn_voting import vote_best_pn
                data = vote_best_pn(data)
            except Exception as e:
                logger.warning(f"P.N. voting failed: {e}")

        if self.sanity_checks:
            try:
                from src.services.extraction.sanity_checks import (
                    run_pn_sanity_checks,
                    calculate_confidence,
                )
                data = run_pn_sanity_checks(data, filename)
                data["confidence"] = calculate_confidence(data, filename)
            except Exception as e:
                logger.warning(f"Sanity checks failed: {e}")

        return data

    def validate_batch(self, results: List[Dict[str, Any]], filenames: List[str] = None) -> List[Dict[str, Any]]:
        """Validate a batch of extraction results."""
        filenames = filenames or [""] * len(results)
        return [
            self.validate(data, fname)
            for data, fname in zip(results, filenames)
        ]
