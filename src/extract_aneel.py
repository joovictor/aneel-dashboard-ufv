"""Extraction helpers for the public ANEEL CKAN datastore API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests


API_URL = "https://dadosabertos.aneel.gov.br/api/3/action/datastore_search"
RESOURCE_ID = "3710b245-88f0-4aa6-8cfb-8b1426e9021d"
UFV_FILTER = {"SigTipoGeracao": "UFV"}
DEFAULT_LIMIT = 32000
DEFAULT_TIMEOUT = 60
RAW_DATA_PATH = Path("data/raw/aneel_ufv_raw.json")


class AneelAPIError(RuntimeError):
    """Raised when the ANEEL API cannot be queried or returns invalid data."""


def fetch_page(
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Fetch one CKAN datastore page filtered by photovoltaic generation."""
    params = {
        "resource_id": RESOURCE_ID,
        "limit": limit,
        "offset": offset,
        "filters": json.dumps(UFV_FILTER, ensure_ascii=False),
    }

    try:
        response = requests.get(API_URL, params=params, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise AneelAPIError(f"Falha de conexão com a API da ANEEL: {exc}") from exc
    except ValueError as exc:
        raise AneelAPIError("A API da ANEEL retornou uma resposta que não é JSON válido.") from exc

    if not payload.get("success"):
        raise AneelAPIError(f"A API da ANEEL retornou erro: {payload.get('error', payload)}")

    result = payload.get("result")
    if not isinstance(result, dict) or "records" not in result:
        raise AneelAPIError("Resposta inválida da API da ANEEL: campo 'result.records' ausente.")

    return result


def get_total_records(timeout: int = DEFAULT_TIMEOUT) -> int:
    """Return the total number of UFV records available in the API."""
    result = fetch_page(limit=1, offset=0, timeout=timeout)
    try:
        return int(result.get("total", 0))
    except (TypeError, ValueError) as exc:
        raise AneelAPIError("Resposta inválida da API da ANEEL: total de registros inválido.") from exc


def fetch_all_ufv_records(
    limit: int = DEFAULT_LIMIT,
    output_path: Path | str = RAW_DATA_PATH,
    timeout: int = DEFAULT_TIMEOUT,
    progress_callback: Any | None = None,
) -> list[dict[str, Any]]:
    """Fetch all photovoltaic records and save the raw JSON file."""
    total = get_total_records(timeout=timeout)
    records: list[dict[str, Any]] = []

    for offset in range(0, total, limit):
        result = fetch_page(limit=limit, offset=offset, timeout=timeout)
        page_records = result.get("records", [])
        if not isinstance(page_records, list):
            raise AneelAPIError("Resposta inválida da API da ANEEL: registros não estão em lista.")

        records.extend(page_records)
        if progress_callback:
            progress_callback(len(records), total)

        if not page_records:
            break

    save_raw_records(records, output_path)
    return records


def save_raw_records(records: list[dict[str, Any]], output_path: Path | str = RAW_DATA_PATH) -> Path:
    """Save raw records as UTF-8 JSON."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False, indent=2)
    return path


if __name__ == "__main__":
    fetched = fetch_all_ufv_records()
    print(f"{len(fetched)} registros UFV salvos em {RAW_DATA_PATH}")
