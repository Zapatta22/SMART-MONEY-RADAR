# SMART MONEY RADAR — motor de classificação de oportunidades (v0)

Marco 2026-11-20. **Implementado e validado apenas em testes determinísticos**.
Código em `src/smart_money_radar/services/opportunity_classifier.py`. O sistema
não opera capital, não executa swaps e não valida autonomamente a autenticidade
de dados do provedor. Dependência da PR #80 (`WalletConsensusReport`) e,
indiretamente, da PR #66 (recibos point-in-time).

## Critérios de entrada

`OpportunityEvidence`: mint, blockchain `solana`, pool, `as_of` com fuso,
identificador da origem, procedência `VERIFIED/UNKNOWN/CONFLICTED`, cobertura
`COMPLETE/PARTIAL/UNKNOWN/GAP`, segurança de token, liquidez e volume opcionais
com flags de verificação, confirmações separadas de preço e volume, bloqueios
obrigatórios e flags de manipulação. Esses campos são **declarações do
chamador**, não constatações de análises externas feitas pelo classificador.

`WalletConsensusReport`: consenso direcional, quantidade de carteiras, total
único de assinaturas, indicador de independência e razões da auditoria. A
versão atual de `WalletConsensusService` mantém sempre
`independence_verified=False` por falta de prova de operadores realmente
distintos (Sybil). Assim, **dados atuais são UNKNOWN para autorização**, mesmo
com score alto. Para simulações de teste, relatos de independência verificada
podem ser construídos explicitamente; não os tratar como prova operacional.

## Score, prioridade e limites de interpretação

Score heurístico explicável de 0–100:

- compra consensual: até 25 pontos;
- até quatro carteiras elegíveis: 5 pontos cada;
- até cinco assinaturas distintas: 3 pontos cada;
- liquidez positiva e declarada verificada: 15 pontos;
- volume positivo e declarado verificado: 10 pontos;
- procedência e cobertura completas declaradas: 10 pontos.

O score não é probabilidade de êxito, previsão de lucro, nem autorização para
comprar ou vender. `rank_opportunities` ordena primeiro pelo estado
`PRIORITY > WATCH > UNKNOWN > REJECTED`, depois score e identidade estável;
um token rejeitado não ultrapassa outro por pontuação.

`REJECTED`: bloqueio obrigatório, manipulação pendente, conflito de origem,
segurança, lacuna `GAP` ou sinais contrários. `UNKNOWN`: campos essenciais
não verificáveis, inclusive independência de carteiras, cobertura histórica,
liquidez/volume ou procedência. `WATCH/PRIORITY`: somente comparações
informacionais após guardas, sem efeito financeiro.

A classificação é determinística para o mesmo snapshot `as_of`.

## Dois contratos de simulação

`modes` contém `immediate` e `confirmed`.
`immediate` só apresenta `SIMULATION_CANDIDATE` se todos os campos
obrigatórios estiverem aprovados; `confirmed` também exige preço e volume
confirmados. A saída inclui sempre `operational_authorized=False`, mesmo
quando ambos os modos são candidatos à simulação.

## Lacunas ainda necessárias

- Proveniência independente de cotações e de relógio, reservas e profundidade
  de pool no mesmo instante; não promover flags do chamador a evidência;
- avaliação da segurança de tokens (mint/freeze authorities, transfer-fees,
  modificabilidade e riscos por programa) com evidência própria e timestamps;
- detecção/auditoria de controle conjunto de carteiras ou sinais Sybil;
- conexão com Launch Radar e telemetria real em uma integração end-to-end;
- calibração de score usando dados históricos sem look-ahead e comparações
  controladas de ambos os modos em paper replay;
- validação operacional Solana Live com Helius autorizada, hoje bloqueada.

## Evidência de validação

PRs #82, #83 e integração #84. GitHub Actions:
**749/749 testes aprovados** no commit
`4f55650cbdd9e116ee6a342f3edf9ba75304a700`, `compileall` aprovado,
https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44773372107.
Nenhuma PR mesclada à `main`. Não há percentual global fundamentado sem
pesos e gates de aceitação acordados.
