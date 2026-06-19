"""Precompute lightweight dashboard datasets from ANEEL GD Parquet."""

from __future__ import annotations

from pathlib import Path

import duckdb


RAW_PARQUET_PATH = Path("data/raw/empreendimento-geracao-distribuida.parquet")
PROCESSED_DIR = Path("data/processed")


def q(path: Path) -> str:
    return "'" + str(path).replace("\\", "/").replace("'", "''") + "'"


def precompute_dashboard_data(
    raw_path: Path | str = RAW_PARQUET_PATH,
    processed_dir: Path | str = PROCESSED_DIR,
) -> None:
    raw = Path(raw_path)
    out = Path(processed_dir)
    out.mkdir(parents=True, exist_ok=True)

    if not raw.exists():
        raise FileNotFoundError(f"Arquivo bruto nao encontrado: {raw}")

    source = f"read_parquet({q(raw)})"
    where = "SigTipoGeracao = 'UFV'"

    with duckdb.connect(database=":memory:") as conn:
        conn.execute(
            f"""
            COPY (
                SELECT
                    COUNT(*) AS registros,
                    SUM(MdaPotenciaInstaladaKW) / 1000.0 AS potencia_mw,
                    SUM(QtdUCRecebeCredito) AS ucs_credito,
                    COUNT(DISTINCT NomMunicipio) AS municipios,
                    COUNT(DISTINCT NomAgente) AS distribuidoras,
                    MAX(CAST(DatGeracaoConjuntoDados AS DATE)) AS data_base,
                    MIN(CAST(DthAtualizaCadastralEmpreend AS DATE)) AS min_data_atualizacao,
                    MAX(CAST(DthAtualizaCadastralEmpreend AS DATE)) AS max_data_atualizacao
                FROM {source}
                WHERE {where}
            )
            TO {q(out / "metrics.parquet")} (FORMAT PARQUET)
            """
        )

        aggregate_specs = {
            "by_uf.parquet": "SigUF",
            "by_regiao.parquet": "NomRegiao",
            "by_municipio.parquet": "NomMunicipio",
            "by_distribuidora.parquet": "NomAgente",
            "by_classe.parquet": "DscClasseConsumo",
            "by_modalidade.parquet": "DscModalidadeHabilitado",
            "by_porte.parquet": "DscPorte",
            "by_tipo_consumidor.parquet": "SigTipoConsumidor",
        }

        for filename, column in aggregate_specs.items():
            conn.execute(
                f"""
                COPY (
                    SELECT
                        COALESCE(CAST({column} AS VARCHAR), 'Nao informado') AS grupo,
                        COUNT(*) AS quantidade,
                        SUM(MdaPotenciaInstaladaKW) / 1000.0 AS potencia_mw,
                        SUM(QtdUCRecebeCredito) AS ucs_credito
                    FROM {source}
                    WHERE {where}
                    GROUP BY 1
                    ORDER BY potencia_mw DESC
                )
                TO {q(out / filename)} (FORMAT PARQUET)
                """
            )

        conn.execute(
            f"""
            COPY (
                SELECT
                    STRFTIME(CAST(DthAtualizaCadastralEmpreend AS DATE), '%Y-%m') AS ano_mes,
                    COUNT(*) AS quantidade,
                    SUM(MdaPotenciaInstaladaKW) / 1000.0 AS potencia_mw
                FROM {source}
                WHERE {where} AND DthAtualizaCadastralEmpreend IS NOT NULL
                GROUP BY 1
                ORDER BY 1
            )
            TO {q(out / "by_tempo.parquet")} (FORMAT PARQUET)
            """
        )

        conn.execute(
            f"""
            COPY (
                SELECT
                    CodEmpreendimento AS codigo_empreendimento,
                    CAST(DthAtualizaCadastralEmpreend AS DATE) AS data_atualizacao,
                    SigUF AS uf,
                    NomMunicipio AS municipio,
                    NomRegiao AS regiao,
                    NomAgente AS distribuidora,
                    DscClasseConsumo AS classe_consumo,
                    DscModalidadeHabilitado AS modalidade,
                    DscPorte AS porte,
                    SigTipoConsumidor AS tipo_consumidor,
                    QtdUCRecebeCredito AS ucs_recebem_credito,
                    MdaPotenciaInstaladaKW AS potencia_kw,
                    MdaPotenciaInstaladaKW / 1000.0 AS potencia_mw,
                    NumCoordNEmpreendimento AS latitude,
                    NumCoordEEmpreendimento AS longitude
                FROM {source}
                WHERE {where}
                ORDER BY MdaPotenciaInstaladaKW DESC NULLS LAST
                LIMIT 50000
            )
            TO {q(out / "top_empreendimentos.parquet")} (FORMAT PARQUET)
            """
        )

        conn.execute(
            f"""
            COPY (
                SELECT
                    CodEmpreendimento AS codigo_empreendimento,
                    SigUF AS uf,
                    NomMunicipio AS municipio,
                    NomAgente AS distribuidora,
                    DscPorte AS porte,
                    MdaPotenciaInstaladaKW AS potencia_kw,
                    NumCoordNEmpreendimento AS latitude,
                    NumCoordEEmpreendimento AS longitude
                FROM {source}
                WHERE {where}
                  AND NumCoordNEmpreendimento BETWEEN -34.0 AND 6.0
                  AND NumCoordEEmpreendimento BETWEEN -75.0 AND -30.0
                ORDER BY HASH(COALESCE(CodEmpreendimento, ''))
                LIMIT 100000
            )
            TO {q(out / "map_points.parquet")} (FORMAT PARQUET)
            """
        )


if __name__ == "__main__":
    precompute_dashboard_data()
