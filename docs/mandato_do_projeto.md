# Mandato do Projeto: Operação de Investimentos com IA

## 1. Identificação e Finalidade
* **Nome do Projeto:** Sistema de Agentes Híbridos para Gestão de Investimentos
* **Fase Atual:** Fase 1 – Laboratório e Semente (Simulação / Paper Trading)
* **Capital Inicial Simulado:** R$ 100,00 (Meta: R$ 250,00 | +150% de retorno líquido acumulado)
* **Moeda-Base:** Real (BRL)
* **Modo Operacional Inicial:** Simulação estrita (*paper trading*) com registro completo de auditoria. Nenhuma ordem com dinheiro real é autorizada nesta etapa.

## 2. Universo de Ativos (Opção C - Cesta Multimercado de Estudo)
A cesta inicial foca em ativos com alta liquidez, representatividade macroeconômica e custos operacionais mínimos:
* **Ações Brasil (B3):** `BOVA11.SA` (ETF Ibovespa) / Blue chips de liquidez extrema (`PETR4.SA`, `VALE3.SA`).
* **Proteção em Ouro:** `GOLD11.SA` (ETF Ouro na B3) / Spot XAU.
* **Exposição Cambial / Internacional:** `IVVB11.SA` (ETF S&P 500 em BRL) / `USDBRL=X` (Taxa PTAX / Spot).
* **Renda Fixa / CDI:** Benchmark CDI / Taxa Selic (referência para taxa livre de risco $R_f$).

## 3. Equipe Inicial de Agentes (Núcleo Mínimo)
Antes de acoplar múltiplos serviços externos, o sistema opera com um núcleo de alta verificabilidade:
1. **Analista (System 2):** Responsável por formular diagnósticos de mercado, avaliar os dados históricos e fundamentais e propor cenários estruturados (com viés: LONG, SHORT ou NEUTRAL).
2. **Revisor Independente:** Realiza checagem cruzada das hipóteses, contesta premissas, audita se há dados vencidos ou ausentes e confere se a proposta respeita as regras.
3. **Paperclip / Antigravity (Coordenação & Dev):** Gestão das tarefas, estado do pipeline e orçamento tecnológico (teto zero / uso restrito de tiers gratuitos nesta fase semente).

## 4. Princípio de Governança e Decisão
* **LLM não envia ordens:** Os modelos geram unicamente relatórios estruturados e vetores de viés.
* **Toda matemática é determinística:** Dimensionamento, volatilidade e stop loss são processados pelo motor numérico em Python.
* **Modo Sugestão + Aprovação Humana:** Nenhuma ordem teórica é concluída sem reconciliação e validação do operador humano.

## 5. Dimensões Temporais dos Dados (Prevenção de Vazamento)
Todo dado registrado na base deve conter quatro timestamps:
1. **Período de Referência:** Mês/trimestre a que a métrica se refere.
2. **Data do Evento:** Momento em que o fato ocorreu no mercado.
3. **Data de Publicação:** Momento em que a informação se tornou pública.
4. **Data de Coleta:** Momento exato em que o sistema gravou a informação.
