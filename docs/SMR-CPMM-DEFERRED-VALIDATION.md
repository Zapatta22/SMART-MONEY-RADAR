# SMR — Registro de validações adiadas (PR #64)

**Estado:** BLOQUEANTE PARA ACEITAÇÃO DO MÓDULO CPMM E PARA QUALQUER EXECUÇÃO REAL.

Este documento é a fonte rastreável das pendências deliberadamente adiadas.
Código implementado não significa código aprovado. Não alterar o status para
CONCLUÍDO sem evidências reproduzíveis e links de CI.

## Pendências obrigatórias

| ID | Status | Critério de encerramento |
| --- | --- | --- |
| CPMM-01 | PENDENTE | GitHub Actions verde no SHA final da PR #64, com suíte completa e testes novos executados. Registrar URL e SHA. |
| CPMM-02 | PENDENTE | Confirmar offsets, discriminadores, comprimentos e taxas de PoolState/AmmConfig contra código oficial versionado e contas mainnet finalizadas. Registrar hashes e fixtures. |
| CPMM-03 | PENDENTE | Provar owner/program ID, pool, config, vaults, mints, autoridade, decimais e saldo efetivo no mesmo contexto de slot; documentar limitações de RPC. |
| CPMM-04 | PENDENTE | Comparar estimativas com swaps reais finalizados no mesmo pool, com fee/rounding e eventual Token-2022 explicitados; reportar desvios. |
| CPMM-05 | PARCIAL — TESTES NÃO EXECUTADOS | O adaptador filtra ticks sem evidência e aplica cutoff as-of; falta integrar CLI, validar no pipeline completo e executar CI. |\n| CPMM-06 | PENDENTE | Vincular criptograficamente a cotação (quote_id, preço bid/ask, pool, payload e timestamps) à evidência RAW; rótulos declarados pelo arquivo não bastam para autenticar quotes. |\n| CPMM-07 | PENDENTE | Auditar paridade dos offsets/layouts binários com versão fixa do código Raydium e fixtures reais; decodificador recém-adicionado ainda não foi validado. |

## Política de retomada

- É permitido avançar para componentes independentes, sem remover os bloqueios.
- Nenhuma das pendências acima pode ser implicitamente considerada resolvida.
- Não fazer merge desta PR nem habilitar ordens reais enquanto os bloqueios
  de aceitação não estiverem encerrados e revisados.
- Ao retomar, verificar cada ID contra evidências no GitHub e atualizar o
  status somente após confirmação.
