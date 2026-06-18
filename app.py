from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from src.extract_aneel import AneelAPIError, RAW_DATA_PATH, fetch_all_ufv_records
from src.transform_aneel import PROCESSED_PARQUET_PATH, transform_raw_file
from src.utils import dataframe_to_csv_bytes, ensure_project_dirs, format_brazilian_date, format_brazilian_number


st.set_page_config(
    page_title="Dashboard ANEEL - Usinas Fotovoltaicas",
    page_icon="☀️",
    layout="wide",
)


@st.cache_data(show_spinner=False)
def load_processed_data(parquet_path: str) -> pd.DataFrame:
    df = pd.read_parquet(parquet_path)
    for column in ["Data Geracao Conjunto Dados", "Data Publicacao"]:
        if column in df.columns:
            df[column] = pd.to_datetime(df[column], errors="coerce")
    return df


def update_data() -> pd.DataFrame:
    ensure_project_dirs()
    status = st.status("Atualizando dados da ANEEL...", expanded=True)

    def progress(current: int, total: int) -> None:
        status.write(f"Baixados {current:,} de {total:,} registros UFV.".replace(",", "."))

    try:
        status.write("Consultando API pública CKAN da ANEEL.")
        fetch_all_ufv_records(output_path=RAW_DATA_PATH, progress_callback=progress)
        status.write("Tratando campos, datas e valores numéricos.")
        df = transform_raw_file(raw_path=RAW_DATA_PATH)
        load_processed_data.clear()
        status.update(label="Dados atualizados com sucesso.", state="complete", expanded=False)
        return df
    except (AneelAPIError, OSError, ValueError, pd.errors.ParserError) as exc:
        status.update(label="Não foi possível atualizar os dados.", state="error", expanded=True)
        raise RuntimeError(str(exc)) from exc


def get_or_create_data() -> pd.DataFrame:
    ensure_project_dirs()
    if Path(PROCESSED_PARQUET_PATH).exists():
        return load_processed_data(str(PROCESSED_PARQUET_PATH))

    st.info("Base local não encontrada. Consultando a API da ANEEL para criar os arquivos iniciais.")
    return update_data()


def multiselect_filter(df: pd.DataFrame, column: str, label: str) -> list[str]:
    values = sorted(df[column].dropna().astype(str).unique()) if column in df.columns else []
    return st.sidebar.multiselect(label, values)


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    filtered = df.copy()

    selections = {
        "UF": multiselect_filter(df, "UF", "UF"),
        "Municipio": multiselect_filter(df, "Municipio", "Município"),
        "Agente": multiselect_filter(df, "Agente", "Agente"),
        "Tipo Ato": multiselect_filter(df, "Tipo Ato", "Tipo de ato"),
        "Assunto": multiselect_filter(df, "Assunto", "Assunto"),
        "Ambiente": multiselect_filter(df, "Ambiente", "Ambiente"),
    }

    for column, selected in selections.items():
        if selected:
            filtered = filtered[filtered[column].astype(str).isin(selected)]

    if "Data Publicacao" in filtered.columns and filtered["Data Publicacao"].notna().any():
        min_date = df["Data Publicacao"].min().date()
        max_date = df["Data Publicacao"].max().date()
        selected_range = st.sidebar.date_input(
            "Intervalo de data de publicação",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
            format="DD/MM/YYYY",
        )
        if not isinstance(selected_range, tuple) or len(selected_range) != 2:
            return filtered
        start_date, end_date = selected_range
        filtered = filtered[
            filtered["Data Publicacao"].dt.date.between(start_date, end_date)
        ]

    return filtered


def metric_cards(df: pd.DataFrame) -> None:
    total_power = df["Potencia Instalada MW"].sum(skipna=True) if "Potencia Instalada MW" in df.columns else 0
    latest_date = df["Data Publicacao"].max() if "Data Publicacao" in df.columns else None

    cols = st.columns(6)
    cols[0].metric("Registros", f"{len(df):,}".replace(",", "."))
    cols[1].metric("Potência MW", format_brazilian_number(total_power))
    cols[2].metric("UFs", df["UF"].nunique() if "UF" in df.columns else 0)
    cols[3].metric("Municípios", df["Municipio"].nunique() if "Municipio" in df.columns else 0)
    cols[4].metric("Agentes", df["Agente"].nunique() if "Agente" in df.columns else 0)
    cols[5].metric("Última publicação", format_brazilian_date(latest_date))


def show_bar_chart(df: pd.DataFrame, group_col: str, value_col: str, title: str, top_n: int | None = None) -> None:
    chart_df = (
        df.groupby(group_col, dropna=False, as_index=False)[value_col]
        .sum()
        .sort_values(value_col, ascending=False)
    )
    if top_n:
        chart_df = chart_df.head(top_n)
    fig = px.bar(chart_df, x=group_col, y=value_col, title=title, text_auto=".2s")
    fig.update_layout(xaxis_title="", yaxis_title="MW", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)


def show_count_chart(df: pd.DataFrame, group_col: str, title: str) -> None:
    chart_df = df[group_col].fillna("Não informado").value_counts().reset_index()
    chart_df.columns = [group_col, "Quantidade"]
    fig = px.bar(chart_df, x=group_col, y="Quantidade", title=title, text_auto=True)
    fig.update_layout(xaxis_title="", yaxis_title="Registros", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)


def show_charts(df: pd.DataFrame) -> None:
    if df.empty:
        st.warning("Nenhum registro encontrado para os filtros selecionados.")
        return

    left, right = st.columns(2)
    with left:
        show_bar_chart(df, "UF", "Potencia Instalada MW", "Potência instalada total por UF")
    with right:
        show_count_chart(df, "UF", "Quantidade de registros por UF")

    left, right = st.columns(2)
    with left:
        show_bar_chart(df, "Municipio", "Potencia Instalada MW", "Top 20 municípios por potência instalada", top_n=20)
    with right:
        show_bar_chart(df, "Agente", "Potencia Instalada MW", "Top 20 agentes por potência instalada", top_n=20)

    temporal_df = (
        df.dropna(subset=["AnoMes Publicacao"])
        .groupby("AnoMes Publicacao", as_index=False)["Potencia Instalada MW"]
        .sum()
        .sort_values("AnoMes Publicacao")
    )
    fig = px.line(
        temporal_df,
        x="AnoMes Publicacao",
        y="Potencia Instalada MW",
        markers=True,
        title="Evolução temporal da potência instalada por publicação",
    )
    fig.update_layout(xaxis_title="", yaxis_title="MW", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    left, right = st.columns(2)
    with left:
        show_count_chart(df, "Tipo Ato", "Quantidade de registros por tipo de ato")
    with right:
        show_count_chart(df, "Assunto", "Quantidade de registros por assunto")


def show_table_and_download(df: pd.DataFrame) -> None:
    columns = [
        "Data Publicacao",
        "Empreendimento",
        "Codigo CEG",
        "Agente",
        "Municipio",
        "UF",
        "Fonte",
        "Tipo Geracao",
        "Potencia Instalada MW",
        "Tipo Ato",
        "Assunto",
        "Ambiente",
        "Processo",
    ]
    available_columns = [column for column in columns if column in df.columns]

    st.download_button(
        "Baixar dados filtrados em CSV",
        data=dataframe_to_csv_bytes(df[available_columns]),
        file_name="aneel_ufv_filtrado.csv",
        mime="text/csv",
    )
    st.dataframe(df[available_columns], use_container_width=True, hide_index=True)


def main() -> None:
    st.title("Dashboard ANEEL - Usinas Fotovoltaicas")
    st.caption("Dados públicos de empreendimentos fotovoltaicos consultados via API CKAN da ANEEL.")

    if st.button("Atualizar dados da ANEEL", type="primary"):
        try:
            df = update_data()
            st.success("Arquivos JSON, CSV e Parquet atualizados.")
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
    st.subheader("Tabela detalhada")
    show_table_and_download(filtered_df)


if __name__ == "__main__":
    main()
