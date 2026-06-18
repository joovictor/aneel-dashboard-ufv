"""Shared helpers for the Streamlit dashboard."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def format_brazilian_number(value: float | int | None, decimals: int = 2) -> str:
    """Format a number with Brazilian thousand and decimal separators."""
    if value is None or pd.isna(value):
        return "0,00"
    text = f"{float(value):,.{decimals}f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def format_brazilian_date(value: object) -> str:
    """Format date-like values as dd/mm/yyyy."""
    if value is None or pd.isna(value):
        return "-"
    date = pd.to_datetime(value, errors="coerce")
    if pd.isna(date):
        return "-"
    return date.strftime("%d/%m/%Y")


def ensure_project_dirs() -> None:
    """Create expected data directories if they are missing."""
    for path in [Path("data/raw"), Path("data/processed")]:
        path.mkdir(parents=True, exist_ok=True)


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Encode a dataframe as UTF-8 CSV bytes for Streamlit downloads."""
    return df.to_csv(index=False).encode("utf-8-sig")
