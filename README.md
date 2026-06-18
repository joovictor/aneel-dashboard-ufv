# Dashboard ANEEL - Geração Distribuída Fotovoltaica

Dashboard web em Streamlit para consultar e visualizar a base pública de mini e microgeração distribuída fotovoltaica da ANEEL.

## Objetivo

O projeto baixa a relação pública de empreendimentos de geração distribuída da ANEEL, filtra empreendimentos fotovoltaicos (`SigTipoGeracao = UFV`), trata os campos principais e publica um dashboard com indicadores, filtros, gráficos, mapa geográfico e tabela detalhada com coordenadas.

## Fonte dos dados

- Dataset: Relação de empreendimentos de Mini e Micro Geração Distribuída
- Portal: dados abertos da ANEEL
- Arquivo usado: `empreendimento-geracao-distribuida.parquet`
- URL pública:

```txt
https://dadosabertos.aneel.gov.br/dataset/5e0fafd2-21b9-4d5b-b622-40438d40aba2/resource/cd29f6eb-e08d-4db7-b6fb-ed6e3b682d27/download/empreendimento-geracao-distribuida.parquet
```

Não é necessário token ou API Key.

## Funcionalidades

- Download da base Parquet pública da ANEEL.
- Filtro automático para geração fotovoltaica (`UFV`).
- Indicadores de empreendimentos, potência instalada, UCs com crédito, municípios e distribuidoras.
- Filtros por UF, região, município, distribuidora, classe, modalidade, porte, tipo de consumidor e data de atualização cadastral.
- Gráficos interativos com Plotly.
- Mapa com coordenadas dos empreendimentos, usando amostragem quando há muitos pontos filtrados.
- Tabela detalhada com latitude e longitude.
- Download em CSV da base filtrada, limitado a recortes de até 250.000 linhas para evitar travamentos.

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

```bash
pip install -r requirements.txt
streamlit run app.py
```

Na primeira execução, o app baixa a base Parquet da ANEEL, salva em `data/raw/`, filtra e trata os dados, e salva o resultado em `data/processed/`. Nas próximas execuções, o dashboard lê o Parquet tratado local.

## Como atualizar os dados

No dashboard, clique em **Atualizar dados da ANEEL**. O app baixa novamente a base pública, refaz o tratamento e atualiza o arquivo Parquet processado.

## Publicar no Streamlit Community Cloud

1. Suba os arquivos do projeto para um repositório no GitHub.
2. Acesse `https://streamlit.io/cloud`.
3. Conecte sua conta GitHub.
4. Selecione o repositório.
5. Configure o arquivo principal:

```txt
app.py
```

6. Clique em **Deploy**.

## Power BI

Depois de rodar o app localmente, você pode importar o arquivo tratado:

```txt
data/processed/aneel_gd_fotovoltaica.parquet
```

No Power BI Desktop, use **Obter dados > Parquet** e selecione o arquivo. Para recortes menores, use o botão de download CSV no dashboard.
