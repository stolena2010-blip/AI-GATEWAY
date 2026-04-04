from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd


SUMMARY_GLOB = "SUMMARY_all_results_*.xlsx"
DEFAULT_SOURCE = Path(r"c:/dev DrawingAI/NEW FILES")
DEFAULT_OUTPUT = Path(r"c:/dev DrawingAI/reports/hardware_history_report.xlsx")


@dataclass
class ParsedHardware:
    hardware_code: str
    hardware_qty: float | None
    price_value: float | None
    price_currency: str | None
    is_substitute: bool
    raw_token: str


def _safe_str(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _parse_run_timestamp(file_path: Path) -> datetime | None:
    match = re.search(r"SUMMARY_all_results_(\d{14})", file_path.name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def _extract_hardware_section(merged_bom: str) -> str:
    match = re.search(r"קשיחים\s*\[\d+\]\s*:\s*(.*)", merged_bom, flags=re.DOTALL)
    if not match:
        return ""
    return match.group(1).strip()


def _normalize_token(token: str) -> str:
    token = token.replace("\t", " ").replace("\n", " ")
    token = re.sub(r"\s+", " ", token)
    return token.strip(" |")


def _is_substitute_token(token: str) -> bool:
    token_lower = token.lower()
    markers = [
        "חלופי",
        "חליפי",
        "חלופה",
        "substitute",
        "alternate",
        "alternative",
        "equivalent",
    ]
    return any(marker in token_lower for marker in markers)


def _parse_hardware_token(token: str) -> ParsedHardware | None:
    token = _normalize_token(token)
    if not token:
        return None

    core = token
    if ":" in core:
        core = core.split(":", 1)[1].strip()

    code = core.split("×", 1)[0].strip()
    if not code:
        return None

    qty_match = re.search(r"×\s*([0-9]+(?:\.[0-9]+)?)", core)
    hardware_qty = float(qty_match.group(1)) if qty_match else None

    price_match = re.search(r"×\s*([0-9]+(?:\.[0-9]+)?)\s*([₪$])", core)
    price_value = float(price_match.group(1)) if price_match else None
    price_currency = price_match.group(2) if price_match else None

    return ParsedHardware(
        hardware_code=code,
        hardware_qty=hardware_qty,
        price_value=price_value,
        price_currency=price_currency,
        is_substitute=_is_substitute_token(token),
        raw_token=token,
    )


def _split_hardware_tokens(hardware_section: str) -> Iterable[str]:
    parts = re.split(r"\s*\|\s*|\n+|\s*,\s*", hardware_section)
    for part in parts:
        part = _normalize_token(part)
        if part:
            yield part


def _load_history_rows(source_root: Path) -> pd.DataFrame:
    files = sorted(source_root.rglob(SUMMARY_GLOB))
    if not files:
        return pd.DataFrame()

    all_rows: list[dict] = []
    seen = set()

    for file_path in files:
        try:
            df = pd.read_excel(file_path)
        except Exception:
            continue

        expected_cols = ["part_number", "quantity", "merged_bom", "file_name"]
        if not all(c in df.columns for c in expected_cols):
            continue

        run_ts = _parse_run_timestamp(file_path)

        for row in df.itertuples(index=False):
            row_dict = row._asdict()
            part_number = _safe_str(row_dict.get("part_number"))
            quantity = _safe_str(row_dict.get("quantity"))
            merged_bom = _safe_str(row_dict.get("merged_bom"))
            file_name = _safe_str(row_dict.get("file_name"))
            if not part_number or not merged_bom:
                continue

            hardware_section = _extract_hardware_section(merged_bom)
            if not hardware_section:
                continue

            for token in _split_hardware_tokens(hardware_section):
                parsed = _parse_hardware_token(token)
                if not parsed:
                    continue

                # Dedupe by logical event identity, not by physical workbook path.
                dedupe_key = (
                    part_number,
                    quantity,
                    parsed.hardware_code,
                    parsed.hardware_qty,
                    parsed.price_value,
                    parsed.price_currency,
                    parsed.is_substitute,
                    file_name,
                    run_ts,
                )
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)

                all_rows.append(
                    {
                        "part_number": part_number,
                        "item_quantity": quantity,
                        "hardware_code": parsed.hardware_code,
                        "hardware_quantity": parsed.hardware_qty,
                        "hardware_price": parsed.price_value,
                        "currency": parsed.price_currency,
                        "is_substitute": "yes" if parsed.is_substitute else "no",
                        "run_timestamp": run_ts,
                        "source_file": str(file_path),
                        "drawing_file": file_name,
                        "raw_hardware_text": parsed.raw_token,
                    }
                )

    return pd.DataFrame(all_rows)


def _build_summary(detail_df: pd.DataFrame) -> pd.DataFrame:
    grouped_rows: list[dict] = []

    for (part_number, hardware_code), group in detail_df.groupby(["part_number", "hardware_code"], dropna=False):
        group_sorted = group.sort_values(by="run_timestamp", ascending=True, na_position="first")

        quantities = [v for v in group_sorted["hardware_quantity"].tolist() if pd.notna(v)]
        prices = [v for v in group_sorted["hardware_price"].tolist() if pd.notna(v)]
        currencies = [v for v in group_sorted["currency"].tolist() if _safe_str(v)]
        item_quantities = [v for v in group_sorted["item_quantity"].tolist() if _safe_str(v)]
        substitute_flags = [v for v in group_sorted["is_substitute"].tolist() if _safe_str(v)]
        substitute_yes_count = sum(1 for v in substitute_flags if str(v).strip().lower() == "yes")

        qty_mode = Counter(quantities).most_common(1)[0][0] if quantities else None
        price_mode = Counter(prices).most_common(1)[0][0] if prices else None
        currency_mode = Counter(currencies).most_common(1)[0][0] if currencies else ""

        last_row = group_sorted.iloc[-1]
        grouped_rows.append(
            {
                "part_number": part_number,
                "hardware_code": hardware_code,
                "appearance_count": len(group_sorted),
                "history_rows": len(group_sorted),
                "latest_item_quantity": _safe_str(last_row.get("item_quantity")),
                "latest_hardware_quantity": last_row.get("hardware_quantity"),
                "latest_price": last_row.get("hardware_price"),
                "latest_currency": _safe_str(last_row.get("currency")),
                "is_substitute": "yes" if substitute_yes_count > 0 else "no",
                "substitute_appearance_count": substitute_yes_count,
                "common_item_quantity": Counter(item_quantities).most_common(1)[0][0] if item_quantities else "",
                "common_hardware_quantity": qty_mode,
                "common_price": price_mode,
                "common_currency": currency_mode,
                "last_seen": last_row.get("run_timestamp"),
            }
        )

    summary_df = pd.DataFrame(grouped_rows)
    if not summary_df.empty:
        summary_df = summary_df.sort_values(by=["part_number", "hardware_code"], ascending=[True, True])
    return summary_df


def _build_hardware_only_summary(detail_df: pd.DataFrame) -> pd.DataFrame:
    grouped_rows: list[dict] = []

    for hardware_code, group in detail_df.groupby("hardware_code", dropna=False):
        group_sorted = group.sort_values(by="run_timestamp", ascending=True, na_position="first")

        quantities = [v for v in group_sorted["hardware_quantity"].tolist() if pd.notna(v)]
        prices = [v for v in group_sorted["hardware_price"].tolist() if pd.notna(v)]
        currencies = [v for v in group_sorted["currency"].tolist() if _safe_str(v)]
        item_quantities = [v for v in group_sorted["item_quantity"].tolist() if _safe_str(v)]
        substitute_flags = [v for v in group_sorted["is_substitute"].tolist() if _safe_str(v)]
        substitute_yes_count = sum(1 for v in substitute_flags if str(v).strip().lower() == "yes")

        # Count unique appearances per hardware by (part_number + run_timestamp),
        # so the same part repeated in the same run is counted once.
        unique_part_run_count = len(
            group_sorted[["part_number", "run_timestamp"]]
            .drop_duplicates()
        )

        qty_mode = Counter(quantities).most_common(1)[0][0] if quantities else None
        price_mode = Counter(prices).most_common(1)[0][0] if prices else None
        currency_mode = Counter(currencies).most_common(1)[0][0] if currencies else ""

        last_row = group_sorted.iloc[-1]
        grouped_rows.append(
            {
                "hardware_code": hardware_code,
                "appearance_count": unique_part_run_count,
                "appearance_count_raw": len(group_sorted),
                "unique_part_numbers": group_sorted["part_number"].nunique(dropna=True),
                "is_substitute": "yes" if substitute_yes_count > 0 else "no",
                "substitute_appearance_count": substitute_yes_count,
                "latest_item_quantity": _safe_str(last_row.get("item_quantity")),
                "latest_hardware_quantity": last_row.get("hardware_quantity"),
                "latest_price": last_row.get("hardware_price"),
                "latest_currency": _safe_str(last_row.get("currency")),
                "common_item_quantity": Counter(item_quantities).most_common(1)[0][0] if item_quantities else "",
                "common_hardware_quantity": qty_mode,
                "common_price": price_mode,
                "common_currency": currency_mode,
                "last_seen": last_row.get("run_timestamp"),
            }
        )

    summary_df = pd.DataFrame(grouped_rows)
    if not summary_df.empty:
        summary_df = summary_df.sort_values(by=["hardware_code"], ascending=[True])
    return summary_df


def build_hardware_history_report(source_root: Path = DEFAULT_SOURCE, output_file: Path = DEFAULT_OUTPUT) -> Path:
    detail_df = _load_history_rows(source_root)

    if detail_df.empty:
        raise RuntimeError("No historical hardware rows found in summary files.")

    detail_df = detail_df.sort_values(by=["run_timestamp", "part_number", "hardware_code"], ascending=[False, True, True])
    summary_df = _build_summary(detail_df)
    hardware_only_df = _build_hardware_only_summary(detail_df)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        summary_df.to_excel(writer, index=False, sheet_name="summary")
        hardware_only_df.to_excel(writer, index=False, sheet_name="hardware_only")
        detail_df.to_excel(writer, index=False, sheet_name="detail")

    return output_file


if __name__ == "__main__":
    out_path = build_hardware_history_report()
    print(f"Saved: {out_path}")
