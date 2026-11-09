# Cotações reais

O painel, o ciclo de análise e os relatórios do bot leem a cesta
`BOVA11.SA`, `IVVB11.SA`, `GOLD11.SA`, `USDBRL=X` e `^VIX` de fontes de
mercado. Z-Score de 20 pregões, ATR de 14, volatilidade de 20, variação do
dia e sparkline saem do OHLC diário dessa coleta. `tempo_referencia`,
`tempo_evento` e `tempo_publicacao` repetem o carimbo do negócio na fonte.
`tempo_coleta` é o horário em que o servidor concluiu a leitura.

Não há pregão sintético. Se a leitura falha e ainda existe coleta real dentro
da validade, `/api/market` devolve esse último preço com `dados_stale: true`
e um `aviso`. Fora da validade, o ativo volta com `disponivel: false` e
preços nulos.

## Ordem das fontes

1. Yahoo Finance Chart (`query1`, depois `query2`). Sem token.
2. `yfinance`, também em cima do Yahoo, com outro cliente HTTP.
3. Reservas:
   - tickers B3 (`BOVA11`, `IVVB11`, `GOLD11`): [brapi.dev](https://brapi.dev), só se `BRAPI_TOKEN` estiver definido;
   - `^VIX`: CSV diário oficial da CBOE. A data do pregão não traz horário; o carimbo fica em 00:00 UTC desse dia;
   - `USDBRL=X`: AwesomeAPI (`/json/daily/USD-BRL/90`), sujeita à cota gratuita.

O campo `fonte` de cada ativo diz qual caminho respondeu (`yahoo`, `yfinance`, `brapi`, `cboe`, `awesomeapi`).

O sparkline é a sequência dos fechamentos diários, inclusive quando um pregão abre em gap. Em 26/10/2026 o Ibovespa e o BOVA11 caem cerca de 14% no OHLC do Yahoo, no mesmo pregão em que o índice `^BVSP` sai de 205.083 para 176.608. Esse degrau fica no gráfico porque está na série; ele não é um tick sorteado.

## Variáveis de ambiente

Nenhuma é obrigatória. O deploy na Railway continua com `python main.py` e as dependências já listadas em `requirements.txt`.

| Variável | Padrão | Função |
| --- | --- | --- |
| `BRAPI_TOKEN` | vazio | Token da brapi.dev. Liga a reserva dos ETFs da B3 quando o Yahoo não responde. |
| `MARKET_CACHE_TTL_SECONDS` | `60` | Intervalo mínimo entre coletas de `/api/market`. |
| `MARKET_STALE_MAX_SECONDS` | `129600` (36 h) | Por quanto tempo a última coleta real pode aparecer marcada como desatualizada. |

O cache em `data/snapshots/ultimo_mercado.json` é local e efêmero na Railway. O arquivo só é relido se cada ativo tiver `fonte` de uma das fontes acima e `tempo_coleta` dentro da validade. Snapshot antigo, sem `fonte`, é ignorado.

## O que continua simulado

A carteira de R$ 100 e o conector BTG sem credenciais seguem em paper trading. Eles não geram cotação: o preço da posição aberta passa a ser o preço real coletado.
