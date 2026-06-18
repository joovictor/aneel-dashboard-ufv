"""Download helpers for ANEEL distributed generation public files."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import requests


GD_PARQUET_URL = (
    "https://dadosabertos.aneel.gov.br/dataset/5e0fafd2-21b9-4d5b-b622-40438d40aba2/"
    "resource/cd29f6eb-e08d-4db7-b6fb-ed6e3b682d27/download/"
    "empreendimento-geracao-distribuida.parquet"
)
RAW_DATA_PATH = Path("data/raw/empreendimento-geracao-distribuida.parquet")
DEFAULT_TIMEOUT = (15, 180)
CHUNK_SIZE = 1024 * 1024


class AneelDownloadError(RuntimeError):
    """Raised when the ANEEL public file cannot be downloaded."""


def download_gd_parquet(
    output_path: Path | str = RAW_DATA_PATH,
    url: str = GD_PARQUET_URL,
    progress_callback: Callable[[int, int | None], None] | None = None,
) -> Path:
    """Download the distributed generation Parquet file from ANEEL."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".download")

    try:
        with requests.get(url, stream=True, timeout=DEFAULT_TIMEOUT) as response:
            response.raise_for_status()
            total_header = response.headers.get("content-length")
            total = int(total_header) if total_header and total_header.isdigit() else None
            downloaded = 0

            with temporary_path.open("wb") as file:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if not chunk:
                        continue
                    file.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total)

        temporary_path.replace(path)
    except requests.RequestException as exc:
        temporary_path.unlink(missing_ok=True)
        raise AneelDownloadError(f"Falha ao baixar arquivo público da ANEEL: {exc}") from exc
    except OSError as exc:
        temporary_path.unlink(missing_ok=True)
        raise AneelDownloadError(f"Falha ao salvar arquivo da ANEEL: {exc}") from exc

    return path


if __name__ == "__main__":
    downloaded_path = download_gd_parquet()
    print(f"Arquivo salvo em {downloaded_path}")
