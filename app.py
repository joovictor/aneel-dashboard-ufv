from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from src.extract_aneel import RAW_DATA_PATH, AneelDownloadError, download_gd_parquet
from src.transform_aneel import PROCESSED_PARQUET_PATH, transform_raw_file
from src.utils import dataframe_to_csv_bytes, ensure_project_dirs, format_brazilian_date, format_brazilian_number


st.set_page_config(
    page_title="Dashboard ANEEL - GD Fotovoltaica",
    page_icon="☀️",
    layout="wide",
)

TABLE_COLUMNS = [
    "Codigo Empreendimento",
    "Data Atualizacao Cadastral",
    "UF",
    "Municipio",
    "Regiao",
    "Distribuidora",
    "Classe Consumo",
    "Modalidade",
    "Porte",
    "Tipo Consumidor",
    "UCs Recebem Credito",
    "Potencia Instalada kW",
    "Potencia Instalada MW",
    "Latitude",
    "Longitude",
]


@st.cache_data(show_spinner=False)
def load_processed_data(parquet_path: str) -> pd.DataFrame:
    df = pd.read_parquet(parquet_path)
    for column in ["Data Geracao Conjunto Dados", "Data Atualizacao Cadastral"]:
        if column in df.columns:
            df[column] = pd.to_datetime(df[column], errors="coerce")
    return df


def update_data() -> pd.DataFrame:
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
        download_gd_parquet(output_path=RAW_DATA_PATH, progress_callback=progress)
        status.write("Filtrando geração fotovoltaica e preparando colunas analíticas.")
        df = transform_raw_file(raw_path=RAW_DATA_PATH)
        load_processed_data.clear()
        status.update(label="Dados atualizados com sucesso.", state="complete", expanded=False)
        return df
    except (AneelDownloadError, OSError, ValueError, ImportError) as exc:
        status.update(label="Não foi possível atualizar os dados.", state="error", expanded=True)
        raise RuntimeError(str(exc)) from exc


def get_or_create_data() -> pd.DataFrame:
    ensure_project_dirs()
    if Path(PROCESSED_PARQUET_PATH).exists():
        return load_processed_data(str(PROCESSED_PARQUET_PATH))

    st.info("Base local não encontrada. Baixando a base pública de geração distribuída da ANEEL.")
    return update_data()


def multiselect_filter(df: pd.DataFrame, column: str, label: str) -> list[str]:
    if column not in df.columns:
        return []
    values = sorted(df[column].dropna().astype(str).unique())
    return st.sidebar.multiselect(label, values)


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    filtered = df

    selections = {
        "UF": multiselect_filter(df, "UF", "UF"),
        "Regiao": multiselect_filter(df, "Regiao", "Região"),
        "Municipio": multiselect_filter(df, "Municipio", "Município"),
        "Distribuidora": multiselect_filter(df, "Distribuidora", "Distribuidora"),
        "Classe Consumo": multiselect_filter(df, "Classe Consumo", "Classe de consumo"),
        "Modalidade": multiselect_filter(df, "Modalidade", "Modalidade"),
        "Porte": multiselect_filter(df, "Porte", "Porte"),
        "Tipo Consumidor": multiselect_filter(df, "Tipo Consumidor", "Tipo de consumidor"),
    }

    for column, selected in selections.items():
        if selected:
            filtered = filtered[filtered[column].astype(str).isin(selected)]

    if "Data Atualizacao Cadastral" in filtered.columns and df["Data Atualizacao Cadastral"].notna().any():
        min_date = df["Data Atualizacao Cadastral"].min().date()
        max_date = df["Data Atualizacao Cadastral"].max().date()
        selected_range = st.sidebar.date_input(
            "Atualização cadastral",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
            format="DD/MM/YYYY",
        )
        if isinstance(selected_range, tuple) and len(selected_range) == 2:
            start_date, end_date = selected_range
            filtered = filtered[
                filtered["Data Atualizacao Cadastral"].dt.date.between(start_date, end_date)
            ]

    return filtered


def metric_cards(df: pd.DataFrame) -> None:
    total_power_mw = df["Potencia Instalada MW"].sum(skipna=True)
    total_ucs = df["UCs Recebem Credito"].sum(skipna=True)
    latest_date = df["Data Geracao Conjunto Dados"].max()

    cols = st.columns(6)
    cols[0].metric("Empreendimentos", f"{len(df):,}".replace(",", "."))
    cols[1].metric("Potência MW", format_brazilian_number(total_power_mw))
    cols[2].metric("UCs com crédito", f"{int(total_ucs):,}".replace(",", "."))
    cols[3].metric("Municípios", df["Municipio"].nunique())
    cols[4].metric("Distribuidoras", df["Distribuidora"].nunique())
    cols[5].metric("Base ANEEL", format_brazilian_date(latest_date))


def show_bar_sum(df: pd.DataFrame, group_col: str, title: str, top_n: int | None = None) -> None:
    chart_df = (
        df.groupby(group_col, observed=True, dropna=False, as_index=False)["Potencia Instalada MW"]
        .sum()
        .sort_values("Potencia Instalada MW", ascending=False)
    )
    if top_n:
        chart_df = chart_df.head(top_n)
    fig = px.bar(chart_df, x=group_col, y="Potencia Instalada MW", title=title, text_auto=".2s")
    fig.update_layout(xaxis_title="", yaxis_title="MW", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)


def show_count_chart(df: pd.DataFrame, group_col: str, title: str, top_n: int | None = None) -> None:
    chart_df = df[group_col].astype("string").fillna("Não informado").value_counts().reset_index()
    chart_df.columns = [group_col, "Quantidade"]
    if top_n:
        chart_df = chart_df.head(top_n)
    fig = px.bar(chart_df, x=group_col, y="Quantidade", title=title, text_auto=".2s")
    fig.update_layout(xaxis_title="", yaxis_title="Empreendimentos", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)


def show_charts(df: pd.DataFrame) -> None:
    if df.empty:
        st.warning("Nenhum registro encontrado para os filtros selecionados.")
        return

    left, right = st.columns(2)
    with left:
        show_bar_sum(df, "UF", "Potência instalada por UF")
    with right:
        show_count_chart(df, "UF", "Empreendimentos por UF")

    left, right = st.columns(2)
    with left:
        show_bar_sum(df, "Municipio", "Top 20 municípios por potência", top_n=20)
    with right:
        show_bar_sum(df, "Distribuidora", "Top 20 distribuidoras por potência", top_n=20)

    left, right = st.columns(2)
    with left:
        show_count_chart(df, "Classe Consumo", "Empreendimentos por classe de consumo")
    with right:
        show_count_chart(df, "Modalidade", "Empreendimentos por modalidade")

    temporal_df = (
        df.dropna(subset=["AnoMes Atualizacao"])
        .groupby("AnoMes Atualizacao", observed=True, as_index=False)["Potencia Instalada MW"]
        .sum()
        .sort_values("AnoMes Atualizacao")
    )
    fig = px.line(
        temporal_df,
        x="AnoMes Atualizacao",
        y="Potencia Instalada MW",
        markers=True,
        title="Evolução da potência por atualização cadastral",
    )
    fig.update_layout(xaxis_title="", yaxis_title="MW", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)


def show_map(df: pd.DataFrame) -> None:
    map_df = df[df["Coordenada Valida"]].copy()
    if map_df.empty:
        st.warning("Nenhum registro com coordenada válida para exibir no mapa.")
        return

    max_points = st.sidebar.slider("Pontos no mapa", min_value=500, max_value=20000, value=5000, step=500)
    if len(map_df) > max_points:
        map_df = map_df.sample(max_points, random_state=42)

    size_values = map_df["Potencia Instalada kW"].clip(lower=1, upper=500)
    fig = px.scatter_mapbox(
        map_df,
        lat="Latitude",
        lon="Longitude",
        color="UF",
        size=size_values,
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


def show_table_and_download(df: pd.DataFrame) -> None:
    available_columns = [column for column in TABLE_COLUMNS if column in df.columns]

    st.subheader("Tabela detalhada")
    max_table_rows = 10000
    table_df = df[available_columns].head(max_table_rows)
    st.dataframe(table_df, use_container_width=True, hide_index=True)

    if len(df) <= 250000:
        st.download_button(
            "Baixar dados filtrados em CSV",
            data=dataframe_to_csv_bytes(df[available_columns]),
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
            df = update_data()
            st.success("Base Parquet baixada e tratada com sucesso.")
        except RuntimeError as exc:
            st.error(f"Erro ao atualizar dados: {exc}")
            st.stop()
    else:
        try:
            df = get_or_create_data()
        except RuntimeError as exc:
            st.error(f"Erro ao carregar dados: {exc}")
            st.stop()

    st.sidebar.header("Filtros")
    filtered_df = apply_filters(df)

    metric_cards(filtered_df)
    st.divider()
    show_charts(filtered_df)
    st.divider()
    show_map(filtered_df)
    st.divider()
    show_table_and_download(filtered_df)


if __name__ == "__main__":
    main()
