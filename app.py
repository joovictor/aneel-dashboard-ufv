from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from src.utils import dataframe_to_csv_bytes, format_brazilian_date, format_brazilian_number


st.set_page_config(
    page_title="Dashboard ANEEL - GD Fotovoltaica",
    page_icon="☀️",
    layout="wide",
)

DATA_DIR = Path("data/processed")


@st.cache_data(show_spinner=False)
def load_dataset(filename: str) -> pd.DataFrame:
    path = DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Arquivo processado nao encontrado: {path}")
    return pd.read_parquet(path)


def load_all_data() -> dict[str, pd.DataFrame]:
    return {
        "metrics": load_dataset("metrics.parquet"),
        "uf": load_dataset("by_uf.parquet"),
        "regiao": load_dataset("by_regiao.parquet"),
        "municipio": load_dataset("by_municipio.parquet"),
        "distribuidora": load_dataset("by_distribuidora.parquet"),
        "classe": load_dataset("by_classe.parquet"),
        "modalidade": load_dataset("by_modalidade.parquet"),
        "porte": load_dataset("by_porte.parquet"),
        "tipo_consumidor": load_dataset("by_tipo_consumidor.parquet"),
        "tempo": load_dataset("by_tempo.parquet"),
        "tabela": load_dataset("top_empreendimentos.parquet"),
        "mapa": load_dataset("map_points.parquet"),
    }


def multiselect(label: str, values: pd.Series) -> list[str]:
    options = sorted(values.dropna().astype(str).unique())
    return st.sidebar.multiselect(label, options)


def apply_detail_filters(df: pd.DataFrame) -> pd.DataFrame:
    filtered = df
    st.sidebar.header("Filtros")

    selections = {
        "uf": multiselect("UF", filtered["uf"]),
        "regiao": multiselect("Região", filtered["regiao"]),
        "municipio": multiselect("Município", filtered["municipio"]),
        "distribuidora": multiselect("Distribuidora", filtered["distribuidora"]),
        "classe_consumo": multiselect("Classe de consumo", filtered["classe_consumo"]),
        "modalidade": multiselect("Modalidade", filtered["modalidade"]),
        "porte": multiselect("Porte", filtered["porte"]),
        "tipo_consumidor": multiselect("Tipo de consumidor", filtered["tipo_consumidor"]),
    }

    for column, selected in selections.items():
        if selected:
            filtered = filtered[filtered[column].astype(str).isin(selected)]

    if filtered["data_atualizacao"].notna().any():
        dates = pd.to_datetime(df["data_atualizacao"], errors="coerce")
        min_date = dates.min().date()
        max_date = dates.max().date()
        selected_range = st.sidebar.date_input(
            "Atualização cadastral",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
            format="DD/MM/YYYY",
        )
        if isinstance(selected_range, tuple) and len(selected_range) == 2:
            start, end = selected_range
            filtered_dates = pd.to_datetime(filtered["data_atualizacao"], errors="coerce")
            filtered = filtered[filtered_dates.dt.date.between(start, end)]

    return filtered


def filter_aggregate(df: pd.DataFrame, selected_groups: set[str] | None = None) -> pd.DataFrame:
    if not selected_groups:
        return df
    return df[df["grupo"].astype(str).isin(selected_groups)]


def metric_cards(metrics: pd.Series, detail_df: pd.DataFrame) -> None:
    if len(detail_df) < int(metrics["registros"]):
        registros = len(detail_df)
        potencia_mw = detail_df["potencia_mw"].sum()
        ucs = detail_df["ucs_recebem_credito"].sum()
        municipios = detail_df["municipio"].nunique()
        distribuidoras = detail_df["distribuidora"].nunique()
    else:
        registros = int(metrics["registros"])
        potencia_mw = metrics["potencia_mw"]
        ucs = metrics["ucs_credito"]
        municipios = int(metrics["municipios"])
        distribuidoras = int(metrics["distribuidoras"])

    cols = st.columns(6)
    cols[0].metric("Empreendimentos", f"{int(registros):,}".replace(",", "."))
    cols[1].metric("Potência MW", format_brazilian_number(potencia_mw))
    cols[2].metric("UCs com crédito", f"{int(ucs or 0):,}".replace(",", "."))
    cols[3].metric("Municípios", f"{int(municipios):,}".replace(",", "."))
    cols[4].metric("Distribuidoras", f"{int(distribuidoras):,}".replace(",", "."))
    cols[5].metric("Base ANEEL", format_brazilian_date(metrics["data_base"]))


def show_bar(df: pd.DataFrame, title: str, value_col: str, y_title: str = "") -> None:
    fig = px.bar(df, x="grupo", y=value_col, title=title, text_auto=".2s")
    fig.update_layout(xaxis_title="", yaxis_title=y_title, hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)


def show_charts(data: dict[str, pd.DataFrame], detail_df: pd.DataFrame) -> None:
    selected_ufs = set(detail_df["uf"].dropna().astype(str).unique()) if not detail_df.empty else set()

    left, right = st.columns(2)
    with left:
        show_bar(filter_aggregate(data["uf"], selected_ufs), "Potência instalada por UF", "potencia_mw", "MW")
    with right:
        show_bar(filter_aggregate(data["uf"], selected_ufs), "Empreendimentos por UF", "quantidade", "Empreendimentos")

    left, right = st.columns(2)
    with left:
        show_bar(
            detail_df.groupby("municipio", dropna=False, as_index=False)["potencia_mw"]
            .sum()
            .rename(columns={"municipio": "grupo"})
            .sort_values("potencia_mw", ascending=False)
            .head(20),
            "Top 20 municípios por potência",
            "potencia_mw",
            "MW",
        )
    with right:
        show_bar(
            detail_df.groupby("distribuidora", dropna=False, as_index=False)["potencia_mw"]
            .sum()
            .rename(columns={"distribuidora": "grupo"})
            .sort_values("potencia_mw", ascending=False)
            .head(20),
            "Top 20 distribuidoras por potência",
            "potencia_mw",
            "MW",
        )

    left, right = st.columns(2)
    with left:
        show_bar(data["classe"], "Empreendimentos por classe de consumo", "quantidade", "Empreendimentos")
    with right:
        show_bar(data["modalidade"], "Empreendimentos por modalidade", "quantidade", "Empreendimentos")

    fig = px.line(
        data["tempo"],
        x="ano_mes",
        y="potencia_mw",
        markers=True,
        title="Evolução da potência por atualização cadastral",
    )
    fig.update_layout(xaxis_title="", yaxis_title="MW", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)


def show_map(map_df: pd.DataFrame, detail_df: pd.DataFrame) -> None:
    selected_codes = set(detail_df["codigo_empreendimento"].dropna().astype(str))
    if selected_codes:
        filtered_map = map_df[map_df["codigo_empreendimento"].astype(str).isin(selected_codes)]
    else:
        filtered_map = map_df

    max_points = st.sidebar.slider("Pontos no mapa", min_value=500, max_value=20000, value=5000, step=500)
    if len(filtered_map) > max_points:
        filtered_map = filtered_map.sample(max_points, random_state=42)

    if filtered_map.empty:
        st.warning("Nenhum ponto de mapa encontrado para os filtros selecionados.")
        return

    fig = px.scatter_mapbox(
        filtered_map,
        lat="latitude",
        lon="longitude",
        color="uf",
        size=filtered_map["potencia_kw"].clip(lower=1, upper=500),
        size_max=14,
        zoom=3,
        height=620,
        hover_name="codigo_empreendimento",
        hover_data={
            "municipio": True,
            "uf": True,
            "distribuidora": True,
            "porte": True,
            "potencia_kw": ":.2f",
            "latitude": ":.5f",
            "longitude": ":.5f",
        },
        title=f"Localização dos empreendimentos fotovoltaicos ({len(filtered_map):,} pontos exibidos)".replace(",", "."),
    )
    fig.update_layout(mapbox_style="open-street-map", margin={"r": 0, "t": 45, "l": 0, "b": 0})
    st.plotly_chart(fig, use_container_width=True)


def show_table(detail_df: pd.DataFrame) -> None:
    st.subheader("Tabela detalhada")
    st.dataframe(detail_df, use_container_width=True, hide_index=True)

    st.download_button(
        "Baixar tabela exibida em CSV",
        data=dataframe_to_csv_bytes(detail_df),
        file_name="aneel_gd_fotovoltaica_tabela.csv",
        mime="text/csv",
    )


def main() -> None:
    st.title("Dashboard ANEEL - Geração Distribuída Fotovoltaica")
    st.caption("Mini e microgeração distribuída fotovoltaica a partir da base pública da ANEEL.")

    try:
        data = load_all_data()
    except FileNotFoundError as exc:
        st.error(f"Arquivo processado ausente: {exc}")
        st.stop()

    detail_df = apply_detail_filters(data["tabela"])
    metrics = data["metrics"].iloc[0]

    if detail_df.empty:
        st.warning("Nenhum registro encontrado para os filtros selecionados.")
        st.stop()

    metric_cards(metrics, detail_df)
    st.divider()
    show_charts(data, detail_df)
    st.divider()
    show_map(data["mapa"], detail_df)
    st.divider()
    show_table(detail_df)


if __name__ == "__main__":
    main()
