# 01 - Política de Governança e Risco Imutável

## 1. Princípio Fundamental de Preservação de Capital
* **Regra Número Um:** A sobrevivência da banca é prioritária a qualquer retorno potencial. Devido à assimetria do Drawdown, perder 50% exige +100% apenas para recuperar o capital original.
* **Capital Inicial da Fase Semente:** R$ 100,00.
* **Meta da Fase:** R$ 250,00 (+150% líquido).

## 2. Limites Numéricos Imutáveis
1. **Risco Máximo por Operação:** Nunca exceder 2,0% do patrimônio líquido atual da conta (na banca de R$ 100,00, a perda máxima tolerada em um único stop é R$ 2,00).
2. **Stop Diário Máximo (Daily Stop Loss):** 4,0% do patrimônio líquido total do dia. Ao atingir essa perda, todas as novas entradas são bloqueadas até o dia útil seguinte.
3. **Trava de Perdas Consecutivas:** Ocorrência de 2 perdas consecutivas no mesmo dia suspende as operações intradiárias para auditoria.
4. **Alavancagem Máxima:** Zero. Operação exclusivamente spot ou com cobertura total de caixa.
5. **Spread Máximo Permitido:** Se o spread *bid-ask* for maior que 0,15% da cotação do ativo, a ordem é rejeitada para evitar fricção corrosiva.
6. **Dimensionamento por Kelly:** Uso obrigatório de Quarter-Kelly ($0,25 \times f^*$), respeitando sempre o teto rígido de 2% do patrimônio.

## 3. Janelas Temporais de Bloqueio Operacional
* Fica terminantemente proibido o envio de novas intenções de ordem nos **15 minutos que antecedem e nos 15 minutos que sucedem** divulgações de alta volatilidade:
  - Decisões de taxas de juros (FOMC, COPOM).
  - Relatórios de emprego dos EUA (Non-Farm Payroll).
  - Indicadores de inflação chave (CPI nos EUA, IPCA no Brasil).

## 4. Critérios de Desligamento Automático (Circuit Breaker Técnico)
O sistema deve entrar em modo de suspensão de emergência caso:
* A divergência entre o saldo reconciliado e a carteira interna for superior a 0,5%.
* Acontecer perda de conexão ou ausência de cotações por mais de 5 minutos durante o pregão.
* Qualquer chamada gere respostas inconsistentes ou violações de integridade temporal.
