"""Transform ANEEL distributed generation data for the dashboard."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


RAW_DATA_PATH = Path("data/raw/empreendimento-geracao-distribuida.parquet")
PROCESSED_PARQUET_PATH = Path("data/processed/aneel_gd_fotovoltaica.parquet")

SOURCE_COLUMNS = [
    "DatGeracaoConjuntoDados",
    "AnmPeriodoReferencia",
    "SigAgente",
    "NomAgente",
    "DscClasseConsumo",
    "DscSubGrupoTarifario",
    "SigUF",
    "NomRegiao",
    "NomMunicipio",
    "SigTipoConsumidor",
    "CodEmpreendimento",
    "DthAtualizaCadastralEmpreend",
    "DscModalidadeHabilitado",
    "QtdUCRecebeCredito",
    "SigTipoGeracao",
    "DscFonteGeracao",
    "DscPorte",
    "NumCoordNEmpreendimento",
    "NumCoordEEmpreendimento",
    "MdaPotenciaInstaladaKW",
]

COLUMN_RENAMES = {
    "DatGeracaoConjuntoDados": "Data Geracao Conjunto Dados",
    "AnmPeriodoReferencia": "Periodo Referencia",
    "SigAgente": "Sigla Distribuidora",
    "NomAgente": "Distribuidora",
    "DscClasseConsumo": "Classe Consumo",
    "DscSubGrupoTarifario": "Subgrupo Tarifario",
    "SigUF": "UF",
    "NomRegiao": "Regiao",
    "NomMunicipio": "Municipio",
    "SigTipoConsumidor": "Tipo Consumidor",
    "CodEmpreendimento": "Codigo Empreendimento",
    "DthAtualizaCadastralEmpreend": "Data Atualizacao Cadastral",
    "DscModalidadeHabilitado": "Modalidade",
    "QtdUCRecebeCredito": "UCs Recebem Credito",
    "SigTipoGeracao": "Tipo Geracao",
    "DscFonteGeracao": "Fonte Geracao",
    "DscPorte": "Porte",
    "NumCoordNEmpreendimento": "Latitude",
    "NumCoordEEmpreendimento": "Longitude",
    "MdaPotenciaInstaladaKW": "Potencia Instalada kW",
}

CATEGORY_COLUMNS = [
    "Periodo Referencia",
    "Sigla Distribuidora",
    "Distribuidora",
    "Classe Consumo",
    "Subgrupo Tarifario",
    "UF",
    "Regiao",
    "Municipio",
    "Tipo Consumidor",
    "Modalidade",
    "Tipo Geracao",
    "Fonte Geracao",
    "Porte",
]


def transform_raw_file(
    raw_path: Path | str = RAW_DATA_PATH,
    parquet_path: Path | str = PROCESSED_PARQUET_PATH,
) -> pd.DataFrame:
    """Load the ANEEL GD Parquet, filter UFV records and save a treated Parquet."""
    path = Path(raw_path)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo bruto nao encontrado: {path}")

    df = pd.read_parquet(path, columns=SOURCE_COLUMNS)
    df = df[df["SigTipoGeracao"].astype("string").str.upper().eq("UFV")].copy()
    df = df.rename(columns=COLUMN_RENAMES)

    df["Data Geracao Conjunto Dados"] = pd.to_datetime(
        df["Data Geracao Conjunto Dados"], errors="coerce"
    )
    df["Data Atualizacao Cadastral"] = pd.to_datetime(
        df["Data Atualizacao Cadastral"], errors="coerce"
    )

    numeric_columns = [
        "UCs Recebem Credito",
        "Latitude",
        "Longitude",
        "Potencia Instalada kW",
    ]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df["Potencia Instalada MW"] = df["Potencia Instalada kW"] / 1000
    df["Ano Atualizacao"] = df["Data Atualizacao Cadastral"].dt.year.astype("Int64")
    df["Mes Atualizacao"] = df["Data Atualizacao Cadastral"].dt.month.astype("Int64")
    df["AnoMes Atualizacao"] = df["Data Atualizacao Cadastral"].dt.to_period("M").astype("string")
    df["Fonte Tecnologia"] = "Fotovoltaica"

    valid_latitude = df["Latitude"].between(-34.0, 6.0)
    valid_longitude = df["Longitude"].between(-75.0, -30.0)
    df["Coordenada Valida"] = valid_latitude & valid_longitude

    for column in CATEGORY_COLUMNS:
        if column in df.columns:
            df[column] = df[column].astype("category")

    output_path = Path(parquet_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False)
    return df


if __name__ == "__main__":
    dataframe = transform_raw_file()
    print(f"{len(dataframe)} registros tratados salvos em {PROCESSED_PARQUET_PATH}")
