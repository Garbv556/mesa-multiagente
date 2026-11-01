# Arquitetura e Decisões Técnicas

## 1. Visão Geral das Camadas
A arquitetura separa estritamente o ambiente de desenvolvimento, a governança de tarefas, o motor matemático/financeiro e o gatilho de execução:

1. **Desenvolvimento (Antigravity):** Construção, testes unitários, laboratórios numéricos e empacotamento.
2. **Coordenação (Paperclip):** Orquestração de tarefas, fluxo entre Analista e Revisor, controle de orçamento de tokens.
3. **Serviço Financeiro (Python Determinístico):**
   - Normalização estatística (Z-Score)
   - Volatilidade e Stop Loss (ATR)
   - Dimensionamento de Posição (Quarter-Kelly com trava de 2% de risco de perda máxima do patrimônio)
   - Gestão de Drawdown e Risco de Cauda (VaR paramétrico e Sortino)
4. **Order Gate (Validador e Portão de Execução):**
   - Verifica se os dados estão atualizados.
   - Confere se o viés macro está alinhado.
   - Checa se o spread bid-ask está abaixo de 0,15%.
   - Garante a integridade e idempotência dos registros.
5. **Persistência e Histórico:**
   - Base relacional / arquivos estruturados em Parquet, CSV e JSON para auditoria completa e *walk-forward*.

## 2. Decisões Arquiteturais Registradas (ADRs)
* **ADR-001 (01/11/2026): Início com Cesta Multimercado (Opção C) e R$ 100,00:**
  - *Contexto:* Testar o comportamento com ativos descorrelacionados (BOVA11, GOLD11, IVVB11, USDBRL) sem risco financeiro real.
  - *Decisão:* Rodar inicialmente em modo simulador local (*paper trading*) com capital semente de R$ 100,00.
* **ADR-002 (01/11/2026): Núcleo Mínimo de Agentes:**
  - *Contexto:* Evitar custos desnecessários de API e complexidade prematura.
  - *Decisão:* Operar com Analista e Revisor. Adaptadores de Jev, GrokBot e Qwen permanecem como módulos configuráveis para ativação futura após validação da base.
* **ADR-003 (01/11/2026): Isolamento Absoluto de Outros Projetos:**
  - *Contexto:* Workspace dedicado e isolado.
  - *Decisão:* Nenhuma dependência cruzada com pastas externas. Toda configuração reside dentro de `hopeful-bell/`.
