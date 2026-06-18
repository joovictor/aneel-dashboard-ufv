"""Transform raw ANEEL records into analytics-ready CSV and Parquet files."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


RAW_DATA_PATH = Path("data/raw/aneel_ufv_raw.json")
PROCESSED_CSV_PATH = Path("data/processed/aneel_ufv_tratado.csv")
PROCESSED_PARQUET_PATH = Path("data/processed/aneel_ufv_tratado.parquet")

DATE_COLUMNS = ["DatGeracaoConjuntoDados", "DatPublicacao"]
NUMERIC_COLUMNS = ["MdaPotenciaInstaladaMW", "MdaAmpliacaoReducaoMW"]

COLUMN_RENAMES = {
    "DatGeracaoConjuntoDados": "Data Geracao Conjunto Dados",
    "DatPublicacao": "Data Publicacao",
    "DscNumAto": "Numero Ato",
    "DscEmpreendimento": "Empreendimento",
    "CodCEG": "Codigo CEG",
    "IdeNucleoCEG": "Nucleo CEG",
    "SigTipoGeracao": "Tipo Geracao",
    "DscAssunto": "Assunto",
    "DscObjeto": "Objeto",
    "DscAmbiente": "Ambiente",
    "DscTipoAto": "Tipo Ato",
    "DscProcesso": "Processo",
    "DscCombustivel": "Fonte",
    "MdaPotenciaInstaladaMW": "Potencia Instalada MW",
    "MdaAmpliacaoReducaoMW": "Ampliacao Reducao MW",
    "NomAgente": "Agente",
    "NomMunicipio": "Municipio",
    "SigUF": "UF",
    "SigRegimeExploracao": "Regime Exploracao",
    "DscRio": "Rio",
}

EXPECTED_COLUMNS = [
    "_id",
    "DatGeracaoConjuntoDados",
    "DatPublicacao",
    "DscNumAto",
    "DscEmpreendimento",
    "CodCEG",
    "IdeNucleoCEG",
    "SigTipoGeracao",
    "DscAssunto",
    "DscObjeto",
    "DscAmbiente",
    "DscTipoAto",
    "DscProcesso",
    "DscCombustivel",
    "MdaPotenciaInstaladaMW",
    "MdaAmpliacaoReducaoMW",
    "NomAgente",
    "NomMunicipio",
    "SigUF",
    "SigRegimeExploracao",
    "DscRio",
]


def load_raw_records(raw_path: Path | str = RAW_DATA_PATH) -> list[dict]:
    """Load raw JSON records saved by the extractor."""
    path = Path(raw_path)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo bruto não encontrado: {path}")

    with path.open("r", encoding="utf-8") as file:
        records = json.load(file)

    if not isinstance(records, list):
        raise ValueError("O JSON bruto deve conter uma lista de registros.")
    return records


def clean_numeric_series(series: pd.Series) -> pd.Series:
    """Convert Brazilian/loose numeric text into decimal values."""
    cleaned = (
        series.astype("string")
        .str.strip()
        .str.replace(",", ".", regex=False)
        .str.replace(r"[^0-9.\-]", "", regex=True)
    )
    return pd.to_numeric(cleaned, errors="coerce")


def transform_records(records: list[dict]) -> pd.DataFrame:
    """Convert raw ANEEL records into a clean dataframe with friendly columns."""
    df = pd.DataFrame(records)

    for column in EXPECTED_COLUMNS:
        if column not in df.columns:
            df[column] = pd.NA

    if "SigTipoGeracao" in df.columns:
        df = df[df["SigTipoGeracao"].astype("string").str.upper().eq("UFV")].copy()

    for column in DATE_COLUMNS:
        df[column] = pd.to_datetime(df[column], errors="coerce", dayfirst=True)

    for column in NUMERIC_COLUMNS:
        df[column] = clean_numeric_series(df[column])

    keep_columns = [column for column in EXPECTED_COLUMNS if column in df.columns]
    df = df[keep_columns].rename(columns=COLUMN_RENAMES)

    publicacao = df["Data Publicacao"]
    df["Ano Publicacao"] = publicacao.dt.year.astype("Int64")
    df["Mes Publicacao"] = publicacao.dt.month.astype("Int64")
    df["AnoMes Publicacao"] = publicacao.dt.to_period("M").astype("string")
    df["Fonte Tecnologia"] = "Fotovoltaica"

    return df


def save_processed_data(
    df: pd.DataFrame,
    csv_path: Path | str = PROCESSED_CSV_PATH,
    parquet_path: Path | str = PROCESSED_PARQUET_PATH,
) -> tuple[Path, Path]:
    """Save processed data in CSV and Parquet formats."""
    csv_output = Path(csv_path)
    parquet_output = Path(parquet_path)
    csv_output.parent.mkdir(parents=True, exist_ok=True)
    parquet_output.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(csv_output, index=False, encoding="utf-8-sig")
    df.to_parquet(parquet_output, index=False)
    return csv_output, parquet_output


def transform_raw_file(
    raw_path: Path | str = RAW_DATA_PATH,
    csv_path: Path | str = PROCESSED_CSV_PATH,
    parquet_path: Path | str = PROCESSED_PARQUET_PATH,
) -> pd.DataFrame:
    """Load, transform and persist raw ANEEL data."""
    records = load_raw_records(raw_path)
    df = transform_records(records)
    save_processed_data(df, csv_path, parquet_path)
    return df


if __name__ == "__main__":
    dataframe = transform_raw_file()
    print(f"{len(dataframe)} registros tratados salvos em {PROCESSED_PARQUET_PATH}")
