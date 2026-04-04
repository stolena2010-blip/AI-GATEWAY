"""
archive_extractor — Extract ZIP and RAR archives in-place.
Extracted from customer_extractor_v3_dual.scan_folder() Phase 0.5.
"""
import os
import subprocess
import zipfile
from pathlib import Path
from typing import List

from src.utils.logger import get_logger

logger = get_logger(__name__)


def extract_archives_in_folders(folders: List[Path]) -> None:
    """Extract all ZIP and RAR files found in the given folders (in-place)."""
    for folder in folders:
        _extract_zips(folder)
        _extract_rars(folder)


def _extract_zips(folder: Path) -> None:
    """Extract ZIP files in *folder*, flatten contents, then delete the ZIP."""
    for zip_path in folder.glob("*.zip"):
        try:
            if not zipfile.is_zipfile(zip_path):
                continue
            logger.info(f"Extracting ZIP: {zip_path.name} -> {folder}")
            with zipfile.ZipFile(zip_path, "r") as zf:
                for member in zf.namelist():
                    if member.endswith('/'):
                        continue
                    filename = Path(member).name
                    if not filename:
                        continue
                    source = zf.open(member)
                    target_path = folder / filename
                    with open(target_path, 'wb') as target:
                        target.write(source.read())
                    source.close()
                logger.info(f"Extracted {len([m for m in zf.namelist() if not m.endswith('/')])} files (flattened)")
            try:
                zip_path.unlink()
                logger.info(f"Deleted ZIP after extract: {zip_path.name}")
            except Exception as e:
                logger.error(f"** Failed to delete ZIP {zip_path.name}: {e}")
        except Exception as e:
            logger.error(f"** Failed to extract {zip_path.name}: {e}")


def _extract_rars(folder: Path) -> None:
    """Extract RAR files in *folder* using UnRAR or 7z, then delete the RAR."""
    for rar_path in folder.glob("*.rar"):
        try:
            logger.info(f"Extracting RAR: {rar_path.name} -> {folder}")
            extracted = False

            # Locate UnRAR.exe
            unrar_exe = None
            for _p in (
                Path(r"C:\Program Files\WinRAR\UnRAR.exe"),
                Path(r"C:\Program Files (x86)\WinRAR\UnRAR.exe"),
            ):
                if _p.exists():
                    unrar_exe = str(_p)
                    break
            if not unrar_exe:
                import shutil as _sh
                unrar_exe = _sh.which("UnRAR")

            if unrar_exe:
                result = subprocess.run(
                    [unrar_exe, 'e', '-o+', '-y', str(rar_path), str(folder) + os.sep],
                    capture_output=True, text=True, timeout=60,
                    encoding='utf-8', errors='replace',
                )
                if result.returncode == 0:
                    logger.info("Extracted RAR via UnRAR")
                    extracted = True
                else:
                    logger.warning(f"UnRAR failed (rc={result.returncode}): {result.stderr[:200]}")

            # Fallback: 7z
            if not extracted:
                _7z_exe = None
                for _p in (
                    Path(r"C:\Program Files\7-Zip\7z.exe"),
                    Path(r"C:\Program Files (x86)\7-Zip\7z.exe"),
                ):
                    if _p.exists():
                        _7z_exe = str(_p)
                        break
                if not _7z_exe:
                    import shutil as _sh
                    _7z_exe = _sh.which("7z")

                if _7z_exe:
                    result = subprocess.run(
                        [_7z_exe, 'e', str(rar_path), f'-o{folder}', '-aoa'],
                        capture_output=True, text=True, timeout=60,
                        encoding='utf-8', errors='replace',
                    )
                    if result.returncode == 0:
                        logger.info("Extracted RAR via 7z")
                        extracted = True
                    else:
                        logger.warning(f"7z failed (rc={result.returncode}): {result.stderr[:200]}")

            if extracted:
                try:
                    rar_path.unlink()
                    logger.info(f"Deleted RAR after extract: {rar_path.name}")
                except Exception as e:
                    logger.error(f"** Failed to delete RAR {rar_path.name}: {e}")
            else:
                logger.warning(f"⚠️ Cannot extract {rar_path.name}: UnRAR and 7z not found")
                logger.info("→ Install WinRAR or 7-Zip for RAR support")

        except Exception as e:
            logger.error(f"** Failed to extract {rar_path.name}: {e}")
