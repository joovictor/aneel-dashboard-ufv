"""Precompute national aggregates and complete UF partitions from ANEEL GD data."""

from __future__ import annotations

from pathlib import Path

import duckdb


RAW_PARQUET_PATH = Path("data/raw/empreendimento-geracao-distribuida.parquet")
PROCESSED_DIR = Path("data/processed")


def q(path: Path) -> str:
    return "'" + str(path.resolve()).replace("\\", "/").replace("'", "''") + "'"


def remove_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()


def precompute_dashboard_data(
    raw_path: Path | str = RAW_PARQUET_PATH,
    processed_dir: Path | str = PROCESSED_DIR,
) -> None:
    raw = Path(raw_path)
    out = Path(processed_dir)
    detail_dir = out / "detail_by_uf"
    out.mkdir(parents=True, exist_ok=True)
    detail_dir.mkdir(parents=True, exist_ok=True)

    if not raw.exists():
        raise FileNotFoundError(f"Arquivo bruto não encontrado: {raw}")

    source = f"read_parquet({q(raw)})"
    where = "SigTipoGeracao = 'UFV'"
    generated_files = [
        "metrics.parquet",
        "by_uf.parquet",
        "by_regiao.parquet",
        "by_municipio.parquet",
        "by_distribuidora.parquet",
        "by_classe.parquet",
        "by_modalidade.parquet",
        "by_porte.parquet",
        "by_tipo_consumidor.parquet",
        "by_tempo.parquet",
        # Legacy samples from the first lightweight version.
        "top_empreendimentos.parquet",
        "map_points.parquet",
    ]
    for filename in generated_files:
        remove_if_exists(out / filename)

    with duckdb.connect(database=":memory:") as conn:
        conn.execute("SET preserve_insertion_order = false")
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
            TO {q(out / 'metrics.parquet')} (FORMAT PARQUET, COMPRESSION ZSTD)
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
                        COALESCE(CAST({column} AS VARCHAR), 'Não informado') AS grupo,
                        COUNT(*) AS quantidade,
                        SUM(MdaPotenciaInstaladaKW) / 1000.0 AS potencia_mw,
                        SUM(QtdUCRecebeCredito) AS ucs_credito
                    FROM {source}
                    WHERE {where}
                    GROUP BY 1
                    ORDER BY potencia_mw DESC
                )
                TO {q(out / filename)} (FORMAT PARQUET, COMPRESSION ZSTD)
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
            TO {q(out / 'by_tempo.parquet')} (FORMAT PARQUET, COMPRESSION ZSTD)
            """
        )

        ufs = [
            row[0]
            for row in conn.execute(
                f"""
                SELECT DISTINCT SigUF
                FROM {source}
                WHERE {where} AND SigUF IS NOT NULL
                ORDER BY SigUF
                """
            ).fetchall()
        ]

        for uf in ufs:
            target = detail_dir / f"{uf}.parquet"
            remove_if_exists(target)
            conn.execute(
                f"""
                COPY (
                    SELECT
                        COALESCE(CAST(CodEmpreendimento AS VARCHAR), '') AS codigo_empreendimento,
                        CAST(DthAtualizaCadastralEmpreend AS DATE) AS data_atualizacao,
                        CAST(DatGeracaoConjuntoDados AS DATE) AS data_base,
                        COALESCE(CAST(SigUF AS VARCHAR), 'Não informado') AS uf,
                        COALESCE(CAST(NomMunicipio AS VARCHAR), 'Não informado') AS municipio,
                        COALESCE(CAST(NomRegiao AS VARCHAR), 'Não informado') AS regiao,
                        COALESCE(CAST(NomAgente AS VARCHAR), 'Não informado') AS distribuidora,
                        COALESCE(CAST(DscClasseConsumo AS VARCHAR), 'Não informado') AS classe_consumo,
                        COALESCE(CAST(DscModalidadeHabilitado AS VARCHAR), 'Não informado') AS modalidade,
                        COALESCE(CAST(DscPorte AS VARCHAR), 'Não informado') AS porte,
                        COALESCE(CAST(SigTipoConsumidor AS VARCHAR), 'Não informado') AS tipo_consumidor,
                        COALESCE(TRY_CAST(QtdUCRecebeCredito AS BIGINT), 0) AS ucs_recebem_credito,
                        COALESCE(TRY_CAST(MdaPotenciaInstaladaKW AS DOUBLE), 0) AS potencia_kw,
                        TRY_CAST(NumCoordNEmpreendimento AS DOUBLE) AS latitude,
                        TRY_CAST(NumCoordEEmpreendimento AS DOUBLE) AS longitude
                    FROM {source}
                    WHERE {where} AND SigUF = ?
                )
                TO {q(target)} (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)
                """,
                [uf],
            )
            print(f"Partição {uf}: {target}")


if __name__ == "__main__":
    precompute_dashboard_data()
