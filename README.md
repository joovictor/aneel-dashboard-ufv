# Dashboard ANEEL - Geração Distribuída Fotovoltaica

Dashboard Streamlit para consultar a relação pública de empreendimentos de mini e microgeração distribuída da ANEEL, filtrada para geração fotovoltaica (`SigTipoGeracao = UFV`).

## Como funciona

- A visão Brasil usa agregações nacionais leves.
- A base detalhada é dividida em 27 arquivos Parquet, um para cada UF.
- Depois que uma UF é selecionada, o DuckDB consulta todos os registros daquele estado.
- Indicadores, gráficos e tabela são exatos em relação à fotografia publicada pela ANEEL.
- A tabela é paginada e o mapa limita somente a quantidade de pontos desenhados.

Os arquivos detalhados somam aproximadamente 35 MB. Nenhum recorte de 50 mil empreendimentos é usado nos cálculos.

## Fonte

Dataset: Relação de Empreendimentos de Mini e Micro Geração Distribuída.

```txt
https://dadosabertos.aneel.gov.br/dataset/5e0fafd2-21b9-4d5b-b622-40438d40aba2/resource/cd29f6eb-e08d-4db7-b6fb-ed6e3b682d27/download/empreendimento-geracao-distribuida.parquet
```

## Estrutura principal

```txt
aneel-dashboard-ufv/
├── app.py
├── requirements.txt
├── src/
│   └── precompute_dashboard_data.py
└── data/
    ├── raw/
    │   └── .gitkeep
    └── processed/
        ├── metrics.parquet
        ├── by_uf.parquet
        └── detail_by_uf/
            ├── AC.parquet
            ├── SC.parquet
            └── SP.parquet
```

## Executar localmente

```powershell
pip install -r requirements.txt
streamlit run app.py
```

## Atualizar a base

1. Baixe o Parquet da ANEEL.
2. Salve como `data/raw/empreendimento-geracao-distribuida.parquet`.
3. Execute:

```powershell
python src/precompute_dashboard_data.py
```

O script recria as agregações e todas as partições em `data/processed/detail_by_uf/`.

O arquivo bruto de `data/raw/` não deve ser enviado ao GitHub. Envie somente os arquivos processados.

## Publicação

No Streamlit Community Cloud, use:

```txt
Repositório: joovictor/aneel-dashboard-ufv
Branch: main
Main file path: app.py
```
