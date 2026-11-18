# Auditoria — Etapa 11: coletor RPC de fixtures
Data: 2026-11-16

## Entrega implementada

- `src/smart_money_radar/data_sources/rpc_fixture_collector.py`: coletor JSON-RPC somente leitura para `getTransaction` finalized.
- `tools/collect_solana_fixtures.py`: CLI para coletar uma ou mais assinaturas.
- `tests/test_rpc_fixture_collector.py`: cinco testes automatizados.
- `docs/fixtures/ETAPA11-COLETOR-RPC-EVIDENCIAS.md`: procedimento, salvaguardas e critérios de aceite.

## Salvaguardas verificadas

HTTPS obrigatório; timeout positivo; intervalo mínimo entre requisições; resposta JSON validada; erros RPC e `result=null` rejeitados; assinatura retornada conferida; slot obrigatório; gravação dos bytes originais; SHA-256; manifest de proveniência; proteção contra sobrescrita; nenhuma assinatura ou envio de transação.

## Validação

- Suíte completa: **71 testes aprovados, 0 falhas** (66 anteriores + 5 novos).
- A coleta de rede não foi executada com sucesso nesta sessão: a indisponibilidade DNS previamente observada persiste. Portanto, não há payload real novo, hash de transação candidata, nem fixture aprovada.
- Nenhuma chave Helius, crédito pago ou endpoint pago foi utilizado.

## Conclusão

A ferramenta de coleta e o protocolo de evidência estão implementados e testados localmente. A coleta efetiva permanece bloqueada por conectividade RPC no ambiente atual. Não iniciar decodificadores de protocolo até obter pelo menos uma fixture real completa e revisada.
