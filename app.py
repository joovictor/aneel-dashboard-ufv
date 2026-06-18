from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

from src.extract_aneel import RAW_DATA_PATH, AneelDownloadError, download_gd_parquet
from src.utils import dataframe_to_csv_bytes, ensure_project_dirs, format_brazilian_date, format_brazilian_number


st.set_page_config(
    page_title="Dashboard ANEEL - GD Fotovoltaica",
    page_icon="☀️",
    layout="wide",
)

TABLE_COLUMNS_SQL = """
    CodEmpreendimento AS "Codigo Empreendimento",
    CAST(DthAtualizaCadastralEmpreend AS DATE) AS "Data Atualizacao Cadastral",
    SigUF AS "UF",
    NomMunicipio AS "Municipio",
    NomRegiao AS "Regiao",
    NomAgente AS "Distribuidora",
    DscClasseConsumo AS "Classe Consumo",
    DscModalidadeHabilitado AS "Modalidade",
    DscPorte AS "Porte",
    SigTipoConsumidor AS "Tipo Consumidor",
    QtdUCRecebeCredito AS "UCs Recebem Credito",
    MdaPotenciaInstaladaKW AS "Potencia Instalada kW",
    MdaPotenciaInstaladaKW / 1000.0 AS "Potencia Instalada MW",
    NumCoordNEmpreendimento AS "Latitude",
    NumCoordEEmpreendimento AS "Longitude"
"""

FILTER_COLUMNS = {
    "UF": ("SigUF", "UF"),
    "Regiao": ("NomRegiao", "Região"),
    "Municipio": ("NomMunicipio", "Município"),
    "Distribuidora": ("NomAgente", "Distribuidora"),
    "Classe Consumo": ("DscClasseConsumo", "Classe de consumo"),
    "Modalidade": ("DscModalidadeHabilitado", "Modalidade"),
    "Porte": ("DscPorte", "Porte"),
    "Tipo Consumidor": ("SigTipoConsumidor", "Tipo de consumidor"),
}


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def parquet_ref(path: str) -> str:
    return sql_literal(path.replace("\\", "/"))


def run_query(path: str, query: str) -> pd.DataFrame:
    with duckdb.connect(database=":memory:") as conn:
        return conn.execute(query).fetchdf()


def base_where(filters: dict[str, list[str]] | None = None, date_range: tuple[date, date] | None = None) -> str:
    clauses = ["SigTipoGeracao = 'UFV'"]

    if filters:
        for label, selected in filters.items():
            column = FILTER_COLUMNS[label][0]
            if selected:
                values = ", ".join(sql_literal(str(value)) for value in selected)
                clauses.append(f"{column} IN ({values})")

    if date_range:
        start_date, end_date = date_range
        clauses.append(
            "CAST(DthAtualizaCadastralEmpreend AS DATE) "
            f"BETWEEN DATE '{start_date.isoformat()}' AND DATE '{end_date.isoformat()}'"
        )

    return " AND ".join(clauses)


def update_data() -> Path:
    ensure_project_dirs()
    status = st.status("Atualizando base de geração distribuída da ANEEL...", expanded=True)

    def progress(downloaded: int, total: int | None) -> None:
        downloaded_mb = downloaded / (1024 * 1024)
        if total:
            total_mb = total / (1024 * 1024)
            status.write(f"Baixados {downloaded_mb:.1f} MB de {total_mb:.1f} MB.")
        else:
            status.write(f"Baixados {downloaded_mb:.1f} MB.")

    try:
        status.write("Baixando arquivo Parquet público da ANEEL.")
        path = download_gd_parquet(output_path=RAW_DATA_PATH, progress_callback=progress)
        clear_query_cache()
        status.update(label="Base atualizada com sucesso.", state="complete", expanded=False)
        return path
    except (AneelDownloadError, OSError) as exc:
        status.update(label="Não foi possível atualizar os dados.", state="error", expanded=True)
        raise RuntimeError(str(exc)) from exc


def get_or_download_data() -> Path:
    ensure_project_dirs()
    if Path(RAW_DATA_PATH).exists():
        return Path(RAW_DATA_PATH)

    st.info("Base local não encontrada. Baixando o Parquet público de geração distribuída da ANEEL.")
    return update_data()


def clear_query_cache() -> None:
    get_distinct_values.clear()
    get_date_bounds.clear()
    get_metrics.clear()
    get_group_sum.clear()
    get_group_count.clear()
    get_temporal_series.clear()
    get_map_points.clear()
    get_table_data.clear()
    count_filtered_rows.clear()


@st.cache_data(show_spinner=False)
def get_distinct_values(path: str, column: str) -> list[str]:
    query = f"""
        SELECT DISTINCT {column} AS value
        FROM read_parquet({parquet_ref(path)})
        WHERE SigTipoGeracao = 'UFV' AND {column} IS NOT NULL
        ORDER BY value
    """
    df = run_query(path, query)
    return df["value"].astype(str).tolist()


@st.cache_data(show_spinner=False)
def get_date_bounds(path: str) -> tuple[date, date]:
    query = f"""
        SELECT
            MIN(CAST(DthAtualizaCadastralEmpreend AS DATE)) AS min_date,
            MAX(CAST(DthAtualizaCadastralEmpreend AS DATE)) AS max_date
        FROM read_parquet({parquet_ref(path)})
        WHERE SigTipoGeracao = 'UFV'
    """
    df = run_query(path, query)
    return df.loc[0, "min_date"], df.loc[0, "max_date"]


@st.cache_data(show_spinner=False)
def get_metrics(path: str, where_sql: str) -> pd.DataFrame:
    query = f"""
        SELECT
            COUNT(*) AS registros,
            SUM(MdaPotenciaInstaladaKW) / 1000.0 AS potencia_mw,
            SUM(QtdUCRecebeCredito) AS ucs_credito,
            COUNT(DISTINCT NomMunicipio) AS municipios,
            COUNT(DISTINCT NomAgente) AS distribuidoras,
            MAX(CAST(DatGeracaoConjuntoDados AS DATE)) AS data_base
        FROM read_parquet({parquet_ref(path)})
        WHERE {where_sql}
    """
    return run_query(path, query)


@st.cache_data(show_spinner=False)
def count_filtered_rows(path: str, where_sql: str) -> int:
    query = f"SELECT COUNT(*) AS total FROM read_parquet({parquet_ref(path)}) WHERE {where_sql}"
    return int(run_query(path, query).loc[0, "total"])


@st.cache_data(show_spinner=False)
def get_group_sum(path: str, where_sql: str, group_col: str, limit: int | None = None) -> pd.DataFrame:
    limit_sql = f"LIMIT {limit}" if limit else ""
    query = f"""
        SELECT
            COALESCE(CAST({group_col} AS VARCHAR), 'Não informado') AS grupo,
            SUM(MdaPotenciaInstaladaKW) / 1000.0 AS "Potencia Instalada MW"
        FROM read_parquet({parquet_ref(path)})
        WHERE {where_sql}
        GROUP BY 1
        ORDER BY 2 DESC
        {limit_sql}
    """
    return run_query(path, query)


@st.cache_data(show_spinner=False)
def get_group_count(path: str, where_sql: str, group_col: str, limit: int | None = None) -> pd.DataFrame:
    limit_sql = f"LIMIT {limit}" if limit else ""
    query = f"""
        SELECT
            COALESCE(CAST({group_col} AS VARCHAR), 'Não informado') AS grupo,
            COUNT(*) AS Quantidade
        FROM read_parquet({parquet_ref(path)})
        WHERE {where_sql}
        GROUP BY 1
        ORDER BY 2 DESC
        {limit_sql}
    """
    return run_query(path, query)


@st.cache_data(show_spinner=False)
def get_temporal_series(path: str, where_sql: str) -> pd.DataFrame:
    query = f"""
        SELECT
            STRFTIME(CAST(DthAtualizaCadastralEmpreend AS DATE), '%Y-%m') AS "AnoMes Atualizacao",
            SUM(MdaPotenciaInstaladaKW) / 1000.0 AS "Potencia Instalada MW"
        FROM read_parquet({parquet_ref(path)})
        WHERE {where_sql} AND DthAtualizaCadastralEmpreend IS NOT NULL
        GROUP BY 1
        ORDER BY 1
    """
    return run_query(path, query)


@st.cache_data(show_spinner=False)
def get_map_points(path: str, where_sql: str, limit: int) -> pd.DataFrame:
    query = f"""
        SELECT
            CodEmpreendimento AS "Codigo Empreendimento",
            SigUF AS UF,
            NomMunicipio AS Municipio,
            NomAgente AS Distribuidora,
            DscPorte AS Porte,
            MdaPotenciaInstaladaKW AS "Potencia Instalada kW",
            NumCoordNEmpreendimento AS Latitude,
            NumCoordEEmpreendimento AS Longitude
        FROM read_parquet({parquet_ref(path)})
        WHERE {where_sql}
          AND NumCoordNEmpreendimento BETWEEN -34.0 AND 6.0
          AND NumCoordEEmpreendimento BETWEEN -75.0 AND -30.0
        ORDER BY HASH(COALESCE(CodEmpreendimento, ''))
        LIMIT {limit}
    """
    return run_query(path, query)


@st.cache_data(show_spinner=False)
def get_table_data(path: str, where_sql: str, limit: int = 10000) -> pd.DataFrame:
    query = f"""
        SELECT {TABLE_COLUMNS_SQL}
        FROM read_parquet({parquet_ref(path)})
        WHERE {where_sql}
        ORDER BY MdaPotenciaInstaladaKW DESC NULLS LAST
        LIMIT {limit}
    """
    return run_query(path, query)


def sidebar_filters(path: str) -> tuple[dict[str, list[str]], tuple[date, date] | None]:
    st.sidebar.header("Filtros")
    selected_filters: dict[str, list[str]] = {}

    for label, (column, display_label) in FILTER_COLUMNS.items():
        values = get_distinct_values(path, column)
        selected_filters[label] = st.sidebar.multiselect(display_label, values)

    min_date, max_date = get_date_bounds(path)
    selected_range = st.sidebar.date_input(
        "Atualização cadastral",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
        format="DD/MM/YYYY",
    )
    if isinstance(selected_range, tuple) and len(selected_range) == 2:
        return selected_filters, selected_range
    return selected_filters, None


def show_metrics(path: str, where_sql: str) -> None:
    metrics = get_metrics(path, where_sql).loc[0]
    cols = st.columns(6)
    cols[0].metric("Empreendimentos", f"{int(metrics['registros']):,}".replace(",", "."))
    cols[1].metric("Potência MW", format_brazilian_number(metrics["potencia_mw"]))
    cols[2].metric("UCs com crédito", f"{int(metrics['ucs_credito'] or 0):,}".replace(",", "."))
    cols[3].metric("Municípios", f"{int(metrics['municipios']):,}".replace(",", "."))
    cols[4].metric("Distribuidoras", f"{int(metrics['distribuidoras']):,}".replace(",", "."))
    cols[5].metric("Base ANEEL", format_brazilian_date(metrics["data_base"]))


def show_bar(df: pd.DataFrame, x_label: str, y_col: str, title: str) -> None:
    fig = px.bar(df, x="grupo", y=y_col, title=title, text_auto=".2s")
    fig.update_layout(xaxis_title=x_label, yaxis_title="", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)


def show_charts(path: str, where_sql: str) -> None:
    left, right = st.columns(2)
    with left:
        show_bar(get_group_sum(path, where_sql, "SigUF"), "UF", "Potencia Instalada MW", "Potência instalada por UF")
    with right:
        show_bar(get_group_count(path, where_sql, "SigUF"), "UF", "Quantidade", "Empreendimentos por UF")

    left, right = st.columns(2)
    with left:
        show_bar(
            get_group_sum(path, where_sql, "NomMunicipio", 20),
            "Município",
            "Potencia Instalada MW",
            "Top 20 municípios por potência",
        )
    with right:
        show_bar(
            get_group_sum(path, where_sql, "NomAgente", 20),
            "Distribuidora",
            "Potencia Instalada MW",
            "Top 20 distribuidoras por potência",
        )

    left, right = st.columns(2)
    with left:
        show_bar(get_group_count(path, where_sql, "DscClasseConsumo"), "Classe", "Quantidade", "Classe de consumo")
    with right:
        show_bar(get_group_count(path, where_sql, "DscModalidadeHabilitado"), "Modalidade", "Quantidade", "Modalidade")

    temporal_df = get_temporal_series(path, where_sql)
    fig = px.line(
        temporal_df,
        x="AnoMes Atualizacao",
        y="Potencia Instalada MW",
        markers=True,
        title="Evolução da potência por atualização cadastral",
    )
    fig.update_layout(xaxis_title="", yaxis_title="MW", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)


def show_map(path: str, where_sql: str) -> None:
    max_points = st.sidebar.slider("Pontos no mapa", min_value=500, max_value=20000, value=5000, step=500)
    map_df = get_map_points(path, where_sql, max_points)
    if map_df.empty:
        st.warning("Nenhum registro com coordenada válida para exibir no mapa.")
        return

    fig = px.scatter_mapbox(
        map_df,
        lat="Latitude",
        lon="Longitude",
        color="UF",
        size=map_df["Potencia Instalada kW"].clip(lower=1, upper=500),
        size_max=14,
        zoom=3,
        height=620,
        hover_name="Codigo Empreendimento",
        hover_data={
            "Municipio": True,
            "UF": True,
            "Distribuidora": True,
            "Porte": True,
            "Potencia Instalada kW": ":.2f",
            "Latitude": ":.5f",
            "Longitude": ":.5f",
        },
        title=f"Localização dos empreendimentos fotovoltaicos ({len(map_df):,} pontos exibidos)".replace(",", "."),
    )
    fig.update_layout(mapbox_style="open-street-map", margin={"r": 0, "t": 45, "l": 0, "b": 0})
    st.plotly_chart(fig, use_container_width=True)


def show_table_and_download(path: str, where_sql: str) -> None:
    st.subheader("Tabela detalhada")
    table_df = get_table_data(path, where_sql)
    st.dataframe(table_df, use_container_width=True, hide_index=True)

    total_rows = count_filtered_rows(path, where_sql)
    if total_rows <= 250000:
        csv_df = get_table_data(path, where_sql, limit=250000)
        st.download_button(
            "Baixar dados filtrados em CSV",
            data=dataframe_to_csv_bytes(csv_df),
            file_name="aneel_gd_fotovoltaica_filtrado.csv",
            mime="text/csv",
        )
    else:
        st.caption("Refine os filtros para baixar CSV com até 250.000 linhas.")


def main() -> None:
    st.title("Dashboard ANEEL - Geração Distribuída Fotovoltaica")
    st.caption("Mini e microgeração distribuída fotovoltaica a partir da base pública da ANEEL.")

    if st.button("Atualizar dados da ANEEL", type="primary"):
        try:
            data_path = update_data()
            st.success("Base Parquet atualizada com sucesso.")
        except RuntimeError as exc:
            st.error(f"Erro ao atualizar dados: {exc}")
            st.stop()
    else:
        try:
            data_path = get_or_download_data()
        except RuntimeError as exc:
            st.error(f"Erro ao carregar dados: {exc}")
            st.stop()

    path = str(data_path)
    filters, selected_date_range = sidebar_filters(path)
    where_sql = base_where(filters, selected_date_range)

    total_rows = count_filtered_rows(path, where_sql)
    if total_rows == 0:
        st.warning("Nenhum registro encontrado para os filtros selecionados.")
        st.stop()

    show_metrics(path, where_sql)
    st.divider()
    show_charts(path, where_sql)
    st.divider()
    show_map(path, where_sql)
    st.divider()
    show_table_and_download(path, where_sql)


if __name__ == "__main__":
    main()
