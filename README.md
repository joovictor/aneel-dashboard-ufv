# Dashboard ANEEL - Usinas Fotovoltaicas

Portal web em Streamlit para consultar, tratar e visualizar dados públicos de usinas fotovoltaicas da ANEEL.

## Objetivo

Este projeto consulta a API pública CKAN da ANEEL, filtra empreendimentos com `SigTipoGeracao = UFV`, salva uma base bruta em JSON, gera arquivos tratados em CSV e Parquet e publica um dashboard interativo com indicadores, gráficos, filtros e tabela detalhada.

## Fonte dos dados

- Portal de dados abertos da ANEEL
- Endpoint CKAN: `https://dadosabertos.aneel.gov.br/api/3/action/datastore_search`
- Resource ID: `3710b245-88f0-4aa6-8cfb-8b1426e9021d`
- Filtro aplicado: `{"SigTipoGeracao": "UFV"}`

Não é necessário token ou API Key. A consulta é pública.

## Estrutura

```txt
aneel-dashboard-ufv/
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
├── src/
│   ├── __init__.py
│   ├── extract_aneel.py
│   ├── transform_aneel.py
│   └── utils.py
├── data/
│   ├── raw/
│   │   └── .gitkeep
│   └── processed/
│       └── .gitkeep
└── .streamlit/
    └── config.toml
```

## Como rodar localmente

Requisitos: Python 3.10 ou superior.

```bash
pip install -r requirements.txt
streamlit run app.py
```

Ao abrir pela primeira vez, se `data/processed/aneel_ufv_tratado.parquet` não existir, o app consulta automaticamente a API da ANEEL, salva o JSON bruto e cria os arquivos tratados.

## Como atualizar os dados

No dashboard, clique em **Atualizar dados da ANEEL**. O app irá:

1. Consultar a API CKAN da ANEEL com paginação usando `limit=32000` e `offset`.
2. Baixar todos os registros UFV.
3. Salvar o JSON bruto em `data/raw/aneel_ufv_raw.json`.
4. Tratar datas e campos numéricos.
5. Salvar os arquivos tratados em:
   - `data/processed/aneel_ufv_tratado.csv`
   - `data/processed/aneel_ufv_tratado.parquet`

O dashboard lê preferencialmente o Parquet tratado para evitar consultar a API a cada carregamento.

## Publicar no GitHub

```bash
git init
git add .
git commit -m "Cria dashboard ANEEL UFV"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/aneel-dashboard-ufv.git
git push -u origin main
```

## Publicar no Streamlit Community Cloud

1. Crie um repositório no GitHub.
2. Suba este projeto para o repositório.
3. Acesse `https://streamlit.io/cloud`.
4. Conecte sua conta GitHub.
5. Selecione o repositório criado.
6. Informe o arquivo principal:

```txt
app.py
```

7. Clique em **Deploy**.

O app funciona sem secrets, token ou API Key.

## Usar os dados no Power BI

Depois de atualizar os dados pelo dashboard ou executando os scripts localmente, você pode importar:

- CSV: `data/processed/aneel_ufv_tratado.csv`
- Parquet: `data/processed/aneel_ufv_tratado.parquet`

No Power BI Desktop:

1. Clique em **Obter dados**.
2. Escolha **Texto/CSV** para o arquivo CSV ou **Parquet** para o arquivo Parquet.
3. Selecione o arquivo em `data/processed/`.
4. Confira os tipos de dados, especialmente datas e potência instalada.
5. Clique em **Carregar** ou **Transformar dados**.

## Observações

- A API da ANEEL pode demorar para responder; o projeto usa timeout e tratamento de erros.
- O arquivo Parquet local melhora a performance no Streamlit Community Cloud.
- A pasta `data/` não é ignorada pelo Git, mas os arquivos de dados gerados podem ser atualizados pelo próprio app.
