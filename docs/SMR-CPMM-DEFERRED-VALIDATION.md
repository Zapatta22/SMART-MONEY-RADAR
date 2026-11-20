# SMR — Registro de validações adiadas (PR #64)

**Estado:** BLOQUEANTE PARA ACEITAÇÃO DO MÓDULO CPMM E PARA QUALQUER EXECUÇÃO REAL.

Este documento é a fonte rastreável das pendências deliberadamente adiadas.
Código implementado não significa código aprovado. Não alterar o status para
CONCLUÍDO sem evidências reproduzíveis e links de CI.

## Pendências obrigatórias

| ID | Status | Critério de encerramento |
| --- | --- | --- |
| CPMM-01 | PENDENTE | GitHub Actions verde no SHA final da PR #64, com suíte completa e testes novos executados. Registrar URL e SHA. |
| CPMM-02 | VALIDADO LOCALMENTE NO POOL DE REFERÊNCIA | Confirmar offsets, discriminadores, comprimentos e taxas de PoolState/AmmConfig contra código oficial versionado e contas mainnet finalizadas. Registrar hashes e fixtures. |
| CPMM-03 | PENDENTE | Provar owner/program ID, pool, config, vaults, mints, autoridade, decimais e saldo efetivo no mesmo contexto de slot; documentar limitações de RPC. |
| CPMM-04 | PENDENTE | Comparar estimativas com swaps reais finalizados no mesmo pool, com fee/rounding e eventual Token-2022 explicitados; reportar desvios. |
| CPMM-05 | PARCIAL — TESTES NÃO EXECUTADOS | O adaptador filtra ticks sem evidência e aplica cutoff as-of; falta integrar CLI, validar no pipeline completo e executar CI. |
| CPMM-06 | PENDENTE | Vincular criptograficamente a cotação (quote_id, preço bid/ask, pool, payload e timestamps) à evidência RAW; rótulos declarados pelo arquivo não bastam para autenticar quotes. |
| CPMM-07 | VALIDADO LOCALMENTE NO POOL DE REFERÊNCIA | Conferir em CI a regressão com a captura finalizada e manter testes sintéticos para bytes discriminadores, prefixos Base58 e flags. |

## Evidência da auditoria binária

A captura finalizada `getMultipleAccounts` do RPC público Solana usa o slot
`471539976` e arquiva os bytes de PoolState, AmmConfig e dois vaults do pool
CPMM SOL/USDC `47hq28mcL7q5GhBg7epyGF2dnuJd4MKFt8QhT7CzYUp4`. Os arquivos estão
em `data/fixtures/mainnet/raydium-cpmm-state`. O teste verifica os SHA-256
do pedido, da resposta e dos metadados do endpoint público de chaves Raydium
antes de comparar os campos decodificados de PoolState e AmmConfig. O
SHA-256 da resposta RPC é
`7b449069fce62d5ccf96cf3cb96644e205ba19e6d71af67ad4b34648eedd71f4`.

O layout conferido tem 637 bytes para PoolState e 236 para AmmConfig, em
ambos os casos incluindo o discriminador Anchor de oito bytes. A auditoria
corrigiu a preservação de zeros binários iniciais na conversão Base58 e
expôs `open_time`, modo e flag de creator fee e taxa de participação do
criador conforme o layout fixado. [PoolState versionado](https://github.com/raydium-io/raydium-cp-swap/blob/3d69122790e97cd6aff24e8ba95940793773f58c/programs/cp-swap/src/states/pool.rs) · [AmmConfig versionado](https://github.com/raydium-io/raydium-cp-swap/blob/3d69122790e97cd6aff24e8ba95940793773f58c/programs/cp-swap/src/states/config.rs)

A captura documenta um pool específico e a ordem do pedido arquivado. Ainda
faltam a prova de autoridade dos vaults no caminho de produção, a autenticação
da origem, a captura prospectiva e a comparação com swaps do mesmo pool.

## Política de retomada

- É permitido avançar para componentes independentes, sem remover os bloqueios.
- Nenhuma das pendências acima pode ser implicitamente considerada resolvida.
- Não fazer merge desta PR nem habilitar ordens reais enquanto os bloqueios
  de aceitação não estiverem encerrados e revisados.
- Ao retomar, verificar cada ID contra evidências no GitHub e atualizar o
  status somente após confirmação.
