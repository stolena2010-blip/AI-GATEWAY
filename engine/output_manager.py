"""
OutputManager — Generates output based on profile config.
===========================================================

Handles B2B text export, interface file generation, email sending,
Excel reports, and file archiving.
"""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


class OutputManager:
    """Generates output based on profile config."""

    def __init__(
        self,
        output_config: Dict[str, Any],
        folders_config: Dict[str, Any],
        profile_name: str,
    ):
        self.method = output_config.get("method", "b2b")
        self.send_email = output_config.get("send_email", False)
        self.auto_send = output_config.get("auto_send", False)
        self.send_to = output_config.get("send_to", "")
        self.send_cc = output_config.get("send_cc", "")
        self.b2b_confidence_level = output_config.get("b2b_confidence_level", "HIGH")
        self.generate_excel = output_config.get("generate_excel", True)
        self.generate_interface = output_config.get("generate_interface", False)
        self.interface_format = output_config.get("interface_format")
        self.profile_name = profile_name

        self.download_dir = Path(folders_config.get("download", ""))
        self.output_dir = Path(folders_config.get("output", ""))
        self.archive_dir = Path(folders_config.get("archive", ""))
        self.to_send_dir = Path(folders_config.get("to_send", "")) if folders_config.get("to_send") else None

        # Ensure output dirs exist
        for d in (self.output_dir, self.archive_dir):
            if d and str(d):
                d.mkdir(parents=True, exist_ok=True)
        if self.to_send_dir and str(self.to_send_dir):
            self.to_send_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, results: List[Dict[str, Any]], msg_metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """Generate all configured outputs for a set of results.

        Returns dict with paths to generated files.
        """
        generated = {}

        if self.method in ("b2b", "both"):
            b2b_path = self._generate_b2b(results, msg_metadata)
            if b2b_path:
                generated["b2b"] = str(b2b_path)

        if self.method in ("interface", "both"):
            iface_path = self._generate_interface_file(results, msg_metadata)
            if iface_path:
                generated["interface"] = str(iface_path)

        if self.generate_excel:
            excel_path = self._generate_excel_report(results, msg_metadata)
            if excel_path:
                generated["excel"] = str(excel_path)

        return generated

    def _generate_b2b(self, results: List[Dict[str, Any]], msg_metadata: Optional[Dict] = None) -> Optional[Path]:
        """Generate B2B text file using existing b2b_export module."""
        try:
            from src.services.reporting.b2b_export import _save_text_summary_with_variants

            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            output_path = self.output_dir / f"B2B-0_200002-{timestamp}.txt"

            customer_email = ""
            if msg_metadata:
                customer_email = msg_metadata.get("sender", "")

            _save_text_summary_with_variants(
                results,
                output_path,
                customer_email=customer_email,
                b2b_number="200002",
                timestamp=timestamp,
            )
            logger.info(f"B2B file generated: {output_path}")

            # Copy to TO_SEND if configured
            if self.to_send_dir:
                shutil.copy2(output_path, self.to_send_dir / output_path.name)

            return output_path
        except Exception as e:
            logger.error(f"Failed to generate B2B file: {e}")
            return None

    def _generate_interface_file(self, results: List[Dict[str, Any]], msg_metadata: Optional[Dict] = None) -> Optional[Path]:
        """Generate Kitaron ERP interface file. Phase 3."""
        if not self.interface_format:
            return None
        try:
            from src.services.reporting.kitaron_export import generate_interface_file

            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            output_path = self.output_dir / f"{self.interface_format}_{timestamp}.txt"

            generate_interface_file(
                results,
                output_path,
                format_name=self.interface_format,
            )
            logger.info(f"Interface file generated: {output_path}")
            return output_path
        except ImportError:
            logger.warning("kitaron_export module not yet available (Phase 3)")
            return None
        except Exception as e:
            logger.error(f"Failed to generate interface file: {e}")
            return None

    def _generate_excel_report(self, results: List[Dict[str, Any]], msg_metadata: Optional[Dict] = None) -> Optional[Path]:
        """Generate Excel report using existing excel_export module."""
        try:
            from src.services.reporting.excel_export import _save_results_to_excel

            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            excel_path = self.output_dir / f"{self.profile_name}_report_{timestamp}.xlsx"

            _save_results_to_excel(results, str(excel_path))
            logger.info(f"Excel report generated: {excel_path}")
            return excel_path
        except Exception as e:
            logger.error(f"Failed to generate Excel report: {e}")
            return None

    def archive_originals(self, source_dir: Path) -> None:
        """Move processed originals to archive folder."""
        if not self.archive_dir or not source_dir.exists():
            return
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = self.archive_dir / f"{source_dir.name}_{timestamp}"
            shutil.move(str(source_dir), str(dest))
            logger.info(f"Archived: {source_dir} -> {dest}")
        except Exception as e:
            logger.error(f"Failed to archive {source_dir}: {e}")
