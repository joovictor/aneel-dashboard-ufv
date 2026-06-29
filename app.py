from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from pathlib import Path
from typing import Any

import duckdb
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
DETAIL_DIR = DATA_DIR / "detail_by_uf"
USER_STORE_PATH = Path("data/users.json")
TABLE_PAGE_SIZE = 100
MAX_CSV_ROWS = 100_000
PASSWORD_ITERATIONS = 200_000


def load_users() -> dict[str, dict[str, Any]]:
    if not USER_STORE_PATH.exists():
        return {}
    try:
        users = json.loads(USER_STORE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    needs_save = False
    has_admin = any(user.get("role") == "admin" for user in users.values())
    for username, user in users.items():
        if "approved" not in user:
            user["approved"] = True
            needs_save = True
        if "role" not in user:
            user["role"] = "admin" if not has_admin else "user"
            has_admin = True
            needs_save = True
    if needs_save:
        save_users(users)
    return users


def save_users(users: dict[str, dict[str, Any]]) -> None:
    USER_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    USER_STORE_PATH.write_text(
        json.dumps(users, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def normalize_username(username: str) -> str:
    return username.strip().lower()


def is_valid_username(username: str) -> bool:
    return bool(re.fullmatch(r"[a-zA-Z0-9_.@-]{3,80}", username.strip()))


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        PASSWORD_ITERATIONS,
    ).hex()
    return salt, digest


def verify_password(password: str, salt: str, stored_hash: str) -> bool:
    _, candidate_hash = hash_password(password, salt)
    return hmac.compare_digest(candidate_hash, stored_hash)


def create_user(username: str, password: str) -> tuple[bool, str]:
    username = normalize_username(username)
    if not is_valid_username(username):
        return False, "Use um usuário com pelo menos 3 caracteres, sem espaços."
    if len(password) < 6:
        return False, "Use uma senha com pelo menos 6 caracteres."

    users = load_users()
    if username in users:
        return False, "Esse usuário já existe."

    is_first_user = not users
    salt, password_hash = hash_password(password)
    users[username] = {
        "salt": salt,
        "password_hash": password_hash,
        "approved": is_first_user,
        "role": "admin" if is_first_user else "user",
    }
    save_users(users)
    if is_first_user:
        return True, "Cadastro criado como administrador. Agora entre com seu usuário e senha."
    return True, "Cadastro enviado. Aguarde aprovação do administrador."


def authenticate_user(username: str, password: str) -> tuple[bool, str]:
    username = normalize_username(username)
    user = load_users().get(username)
    if not user:
        return False, "Usuário ou senha inválidos."
    if not verify_password(password, user["salt"], user["password_hash"]):
        return False, "Usuário ou senha inválidos."
    if not user.get("approved", False):
        return False, "Cadastro aguardando aprovação do administrador."
    st.session_state["user_role"] = user.get("role", "user")
    return True, ""


def pending_users() -> list[str]:
    users = load_users()
    return sorted(username for username, user in users.items() if not user.get("approved", False))


def approve_user(username: str) -> None:
    users = load_users()
    if username in users:
        users[username]["approved"] = True
        save_users(users)


def render_admin_panel() -> None:
    if st.session_state.get("user_role") != "admin":
        return

    with st.sidebar.expander("Administração"):
        pending = pending_users()
        if not pending:
            st.caption("Nenhum cadastro pendente.")
            return
        selected_user = st.selectbox("Cadastros pendentes", pending)
        if st.button("Aprovar cadastro", width="stretch"):
            approve_user(selected_user)
            st.success(f"{selected_user} aprovado.")
            st.rerun()


def render_auth_screen() -> bool:
    if st.session_state.get("authenticated"):
        return True

    st.title("Dashboard ANEEL - Acesso")
    login_tab, register_tab = st.tabs(["Entrar", "Criar cadastro"])

    with login_tab:
        with st.form("login_form"):
            username = st.text_input("Usuário")
            password = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar", type="primary", width="stretch")
        if submitted:
            authenticated, message = authenticate_user(username, password)
            if authenticated:
                st.session_state["authenticated"] = True
                st.session_state["username"] = normalize_username(username)
                st.rerun()
            else:
                st.error(message)

    with register_tab:
        with st.form("register_form"):
            new_username = st.text_input("Novo usuário")
            new_password = st.text_input("Nova senha", type="password")
            confirm_password = st.text_input("Confirmar senha", type="password")
            submitted = st.form_submit_button("Criar cadastro", width="stretch")
        if submitted:
            if new_password != confirm_password:
                st.error("As senhas não conferem.")
            else:
                ok, message = create_user(new_username, new_password)
                if ok:
                    st.success(message)
                else:
                    st.error(message)

    return False


@st.cache_data(show_spinner=False)
def load_dataset(filename: str) -> pd.DataFrame:
    path = DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Arquivo processado não encontrado: {path}")
    return pd.read_parquet(path)


def parquet_source(path: Path) -> str:
    safe_path = str(path.resolve()).replace("\\", "/").replace("'", "''")
    return f"read_parquet('{safe_path}')"


@st.cache_data(show_spinner=False)
def available_ufs() -> list[str]:
    if not DETAIL_DIR.exists():
        return []
    return sorted(path.stem for path in DETAIL_DIR.glob("*.parquet"))


@st.cache_data(show_spinner=False)
def load_filter_options(uf: str) -> dict[str, Any]:
    path = DETAIL_DIR / f"{uf}.parquet"
    source = parquet_source(path)
    query = f"""
        SELECT
            LIST_SORT(LIST(DISTINCT municipio)) AS municipios,
            LIST_SORT(LIST(DISTINCT distribuidora)) AS distribuidoras,
            LIST_SORT(LIST(DISTINCT classe_consumo)) AS classes,
            LIST_SORT(LIST(DISTINCT modalidade)) AS modalidades,
            LIST_SORT(LIST(DISTINCT porte)) AS portes,
            LIST_SORT(LIST(DISTINCT tipo_consumidor)) AS tipos_consumidor,
            MIN(data_atualizacao) AS data_minima,
            MAX(data_atualizacao) AS data_maxima,
            FLOOR(COALESCE(MIN(potencia_kw), 0)) AS potencia_minima,
            CEIL(COALESCE(MAX(potencia_kw), 0)) AS potencia_maxima
        FROM {source}
    """
    with duckdb.connect(database=":memory:") as conn:
        row = conn.execute(query).fetchone()

    return {
        "municipios": row[0] or [],
        "distribuidoras": row[1] or [],
        "classes": row[2] or [],
        "modalidades": row[3] or [],
        "portes": row[4] or [],
        "tipos_consumidor": row[5] or [],
        "data_minima": row[6],
        "data_maxima": row[7],
        "potencia_minima": float(row[8] or 0),
        "potencia_maxima": float(row[9] or 0),
    }


def add_list_filter(
    conditions: list[str], params: list[Any], column: str, values: list[str]
) -> None:
    if not values:
        return
    conditions.append(f"{column} IN ({', '.join('?' for _ in values)})")
    params.extend(values)


def build_where(filters: dict[str, Any]) -> tuple[str, list[Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    add_list_filter(conditions, params, "municipio", filters["municipios"])
    add_list_filter(conditions, params, "distribuidora", filters["distribuidoras"])
    add_list_filter(conditions, params, "classe_consumo", filters["classes"])
    add_list_filter(conditions, params, "modalidade", filters["modalidades"])
    add_list_filter(conditions, params, "porte", filters["portes"])
    add_list_filter(conditions, params, "tipo_consumidor", filters["tipos_consumidor"])

    date_range = filters.get("data_range")
    full_date_range = filters.get("full_date_range")
    if (
        isinstance(date_range, (tuple, list))
        and len(date_range) == 2
        and tuple(date_range) != tuple(full_date_range or ())
    ):
        conditions.append("data_atualizacao BETWEEN ? AND ?")
        params.extend(date_range)

    power_range = filters.get("power_range")
    full_power_range = filters.get("full_power_range")
    if (
        isinstance(power_range, (tuple, list))
        and len(power_range) == 2
        and tuple(power_range) != tuple(full_power_range or ())
    ):
        conditions.append("potencia_kw BETWEEN ? AND ?")
        params.extend(power_range)

    return (" AND ".join(conditions) if conditions else "TRUE"), params


@st.cache_data(show_spinner=False, ttl=3600)
def query_dataframe(uf: str, query: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    path = DETAIL_DIR / f"{uf}.parquet"
    sql = query.format(source=parquet_source(path))
    with duckdb.connect(database=":memory:") as conn:
        return conn.execute(sql, list(params)).df()


def render_filters(uf: str) -> dict[str, Any]:
    options = load_filter_options(uf)
    with st.sidebar.form("filtros_detalhados"):
        st.subheader("Filtros da consulta")
        municipios = st.multiselect("Município", options["municipios"])
        distribuidoras = st.multiselect("Distribuidora", options["distribuidoras"])
        classes = st.multiselect("Classe de consumo", options["classes"])
        modalidades = st.multiselect("Modalidade", options["modalidades"])
        portes = st.multiselect("Porte", options["portes"])
        tipos = st.multiselect("Tipo de consumidor", options["tipos_consumidor"])

        potencia_minima = options["potencia_minima"]
        potencia_maxima = options["potencia_maxima"]
        potencia_inicio = potencia_minima
        potencia_fim = potencia_maxima
        if potencia_maxima > potencia_minima:
            st.caption("Potência instalada (kW)")
            power_cols = st.columns(2)
            with power_cols[0]:
                potencia_inicio = st.number_input(
                    "Mínima",
                    min_value=potencia_minima,
                    max_value=potencia_maxima,
                    value=potencia_minima,
                    step=1.0,
                    format="%.2f",
                )
            with power_cols[1]:
                potencia_fim = st.number_input(
                    "Máxima",
                    min_value=potencia_minima,
                    max_value=potencia_maxima,
                    value=potencia_maxima,
                    step=1.0,
                    format="%.2f",
                )

        data_range: tuple[Any, Any] | list[Any] = []
        if options["data_minima"] and options["data_maxima"]:
            data_range = st.date_input(
                "Atualização cadastral",
                value=(options["data_minima"], options["data_maxima"]),
                min_value=options["data_minima"],
                max_value=options["data_maxima"],
                format="DD/MM/YYYY",
            )
        st.form_submit_button("Aplicar filtros", type="primary", width="stretch")

    return {
        "municipios": municipios,
        "distribuidoras": distribuidoras,
        "classes": classes,
        "modalidades": modalidades,
        "portes": portes,
        "tipos_consumidor": tipos,
        "data_range": data_range,
        "full_date_range": (options["data_minima"], options["data_maxima"]),
        "power_range": (min(potencia_inicio, potencia_fim), max(potencia_inicio, potencia_fim)),
        "full_power_range": (potencia_minima, potencia_maxima),
    }


def show_metrics(metrics: pd.Series) -> None:
    cols = st.columns(6)
    cols[0].metric("Empreendimentos", f"{int(metrics['registros']):,}".replace(",", "."))
    cols[1].metric("Potência MW", format_brazilian_number(metrics["potencia_mw"]))
    cols[2].metric("UCs com crédito", f"{int(metrics['ucs_credito'] or 0):,}".replace(",", "."))
    cols[3].metric("Municípios", f"{int(metrics['municipios']):,}".replace(",", "."))
    cols[4].metric("Distribuidoras", f"{int(metrics['distribuidoras']):,}".replace(",", "."))
    cols[5].metric("Base ANEEL", format_brazilian_date(metrics["data_base"]))


def show_bar(df: pd.DataFrame, title: str, value_col: str, y_title: str) -> None:
    if df.empty:
        st.info("Não há dados para este gráfico.")
        return
    fig = px.bar(df, x="grupo", y=value_col, title=title, text_auto=".2s")
    fig.update_layout(xaxis_title="", yaxis_title=y_title, hovermode="x unified")
    st.plotly_chart(fig, width="stretch")


def show_national_view() -> None:
    metrics = load_dataset("metrics.parquet").iloc[0]
    by_uf = load_dataset("by_uf.parquet")
    by_classe = load_dataset("by_classe.parquet")
    by_modalidade = load_dataset("by_modalidade.parquet")
    by_tempo = load_dataset("by_tempo.parquet")

    show_metrics(metrics)
    st.info("Selecione uma UF para consultar todos os empreendimentos e aplicar filtros exatos.")

    left, right = st.columns(2)
    with left:
        show_bar(by_uf, "Potência instalada por UF", "potencia_mw", "MW")
    with right:
        show_bar(by_uf, "Empreendimentos por UF", "quantidade", "Empreendimentos")

    left, right = st.columns(2)
    with left:
        show_bar(by_classe, "Empreendimentos por classe", "quantidade", "Empreendimentos")
    with right:
        show_bar(by_modalidade, "Empreendimentos por modalidade", "quantidade", "Empreendimentos")

    fig = px.line(
        by_tempo,
        x="ano_mes",
        y="potencia_mw",
        markers=True,
        title="Evolução da potência por atualização cadastral",
    )
    fig.update_layout(xaxis_title="", yaxis_title="MW", hovermode="x unified")
    st.plotly_chart(fig, width="stretch")


def query_metrics(uf: str, where: str, params: list[Any]) -> pd.Series:
    df = query_dataframe(
        uf,
        f"""
        SELECT
            COUNT(*) AS registros,
            COALESCE(SUM(potencia_kw), 0) / 1000.0 AS potencia_mw,
            COALESCE(SUM(ucs_recebem_credito), 0) AS ucs_credito,
            COUNT(DISTINCT municipio) AS municipios,
            COUNT(DISTINCT distribuidora) AS distribuidoras,
            MAX(data_base) AS data_base
        FROM {{source}}
        WHERE {where}
        """,
        tuple(params),
    )
    return df.iloc[0]


def query_group(uf: str, where: str, params: list[Any], column: str, limit: int = 20) -> pd.DataFrame:
    allowed = {"municipio", "distribuidora", "classe_consumo", "modalidade", "porte"}
    if column not in allowed:
        raise ValueError("Agrupamento não permitido")
    return query_dataframe(
        uf,
        f"""
        SELECT
            {column} AS grupo,
            COUNT(*) AS quantidade,
            SUM(potencia_kw) / 1000.0 AS potencia_mw
        FROM {{source}}
        WHERE {where}
        GROUP BY 1
        ORDER BY potencia_mw DESC
        LIMIT {int(limit)}
        """,
        tuple(params),
    )


def show_filtered_charts(uf: str, where: str, params: list[Any]) -> None:
    municipality = query_group(uf, where, params, "municipio")
    distributor = query_group(uf, where, params, "distribuidora")
    classes = query_group(uf, where, params, "classe_consumo", 50)
    modalities = query_group(uf, where, params, "modalidade", 50)

    left, right = st.columns(2)
    with left:
        show_bar(municipality, "Top municípios por potência", "potencia_mw", "MW")
    with right:
        show_bar(distributor, "Top distribuidoras por potência", "potencia_mw", "MW")
    left, right = st.columns(2)
    with left:
        show_bar(classes, "Empreendimentos por classe", "quantidade", "Empreendimentos")
    with right:
        show_bar(modalities, "Empreendimentos por modalidade", "quantidade", "Empreendimentos")


def show_map(uf: str, where: str, params: list[Any]) -> None:
    max_points = st.sidebar.slider(
        "Máximo de pontos no mapa", min_value=500, max_value=20_000, value=5_000, step=500
    )
    map_df = query_dataframe(
        uf,
        f"""
        SELECT
            codigo_empreendimento,
            municipio,
            distribuidora,
            porte,
            potencia_kw,
            latitude,
            longitude
        FROM {{source}}
        WHERE {where}
          AND latitude BETWEEN -34.0 AND 6.0
          AND longitude BETWEEN -75.0 AND -30.0
        ORDER BY HASH(COALESCE(codigo_empreendimento, ''))
        LIMIT {int(max_points)}
        """,
        tuple(params),
    )
    if map_df.empty:
        st.warning("Nenhuma coordenada válida encontrada para os filtros selecionados.")
        return

    fig = px.scatter_map(
        map_df,
        lat="latitude",
        lon="longitude",
        size=map_df["potencia_kw"].clip(lower=1, upper=500),
        size_max=14,
        zoom=5,
        height=620,
        hover_name="codigo_empreendimento",
        hover_data={
            "municipio": True,
            "distribuidora": True,
            "porte": True,
            "potencia_kw": ":.2f",
            "latitude": ":.5f",
            "longitude": ":.5f",
        },
        title=f"Localização dos empreendimentos ({len(map_df):,} pontos exibidos)".replace(",", "."),
    )
    fig.update_layout(map_style="open-street-map", margin={"r": 0, "t": 45, "l": 0, "b": 0})
    st.plotly_chart(fig, width="stretch")


def detail_query(where: str, limit: int, offset: int = 0) -> str:
    return f"""
        SELECT
            codigo_empreendimento AS "Código",
            data_atualizacao AS "Atualização",
            municipio AS "Município",
            titular AS "Titular",
            distribuidora AS "Distribuidora",
            classe_consumo AS "Classe",
            modalidade AS "Modalidade",
            porte AS "Porte",
            tipo_consumidor AS "Tipo consumidor",
            ucs_recebem_credito AS "UCs com crédito",
            potencia_kw AS "Potência kW",
            latitude AS "Latitude",
            longitude AS "Longitude"
        FROM {{source}}
        WHERE {where}
        ORDER BY potencia_kw DESC NULLS LAST, codigo_empreendimento
        LIMIT {int(limit)} OFFSET {int(offset)}
    """


def show_table(uf: str, where: str, params: list[Any], total_rows: int) -> None:
    st.subheader("Tabela detalhada")
    total_pages = max(1, (total_rows + TABLE_PAGE_SIZE - 1) // TABLE_PAGE_SIZE)
    page = st.number_input("Página", min_value=1, max_value=total_pages, value=1, step=1)
    offset = (int(page) - 1) * TABLE_PAGE_SIZE
    table_df = query_dataframe(
        uf, detail_query(where, TABLE_PAGE_SIZE, offset), tuple(params)
    )
    st.caption(f"Página {int(page)} de {total_pages} · {total_rows:,} registros".replace(",", "."))
    st.dataframe(table_df, width="stretch", hide_index=True)

    if total_rows <= MAX_CSV_ROWS:
        csv_df = query_dataframe(uf, detail_query(where, total_rows), tuple(params))
        st.download_button(
            "Baixar resultado completo em CSV",
            data=dataframe_to_csv_bytes(csv_df),
            file_name=f"aneel_gd_fotovoltaica_{uf}.csv",
            mime="text/csv",
        )
    else:
        st.caption("Refine os filtros para habilitar o CSV completo (limite de 100 mil registros).")


def show_state_view(uf: str) -> None:
    filters = render_filters(uf)
    where, params = build_where(filters)
    with st.spinner("Consultando todos os registros da UF selecionada..."):
        metrics = query_metrics(uf, where, params)

    total_rows = int(metrics["registros"])
    if total_rows == 0:
        st.warning("Nenhum registro encontrado para os filtros selecionados.")
        return

    show_metrics(metrics)
    st.caption(f"Consulta exata sobre a partição completa de {uf}; nenhuma amostra foi usada nos indicadores.")
    st.divider()
    show_filtered_charts(uf, where, params)
    st.divider()
    show_map(uf, where, params)
    st.divider()
    show_table(uf, where, params, total_rows)


def main() -> None:
    if not render_auth_screen():
        st.stop()

    st.title("Dashboard ANEEL - Geração Distribuída Fotovoltaica")
    st.caption("Mini e microgeração distribuída fotovoltaica a partir da base pública da ANEEL.")

    ufs = available_ufs()
    if not ufs:
        st.error("Partições detalhadas ausentes. Execute src/precompute_dashboard_data.py.")
        st.stop()

    st.sidebar.caption(f"Usuário: {st.session_state.get('username', '')}")
    if st.sidebar.button("Sair", width="stretch"):
        st.session_state["authenticated"] = False
        st.session_state.pop("username", None)
        st.session_state.pop("user_role", None)
        st.rerun()
    render_admin_panel()

    st.sidebar.header("Consulta")
    selected_uf = st.sidebar.selectbox("UF", ["Brasil"] + ufs)

    try:
        if selected_uf == "Brasil":
            show_national_view()
        else:
            show_state_view(selected_uf)
    except (FileNotFoundError, duckdb.Error) as exc:
        st.error(f"Não foi possível consultar os dados: {exc}")


if __name__ == "__main__":
    main()
