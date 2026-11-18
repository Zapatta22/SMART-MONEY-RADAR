# Etapa 11 — Coletor RPC de fixtures brutas

## Objetivo

Preparar uma coleta reproduzível de `getTransaction` em `finalized`, usando um endpoint Solana RPC HTTPS configurado externamente. O coletor é somente leitura: não assina nem transmite transações e não depende de Helius.

## Execução

Configure `SMR_SOLANA_RPC_URL` no ambiente local com um endpoint HTTPS de leitura que você esteja autorizado a usar. Não publique URLs que contenham tokens/chaves em capturas de tela, logs ou chats.

```bash
PYTHONPATH=src python tools/collect_solana_fixtures.py \
  G2GwWpKY3ssU9JsWtc8FHTX5PqLYgYqBDpANu1jFLHK45qvEHsiZYRMoi5kVHZQGRsx85v26PYgAtGFUkZJvgJa \
  26ETVS1u7jvobgdgp7pfd76AzbEY2aAmjk5h7b5qbnkuurf97BG5ErzZyF2kzwdQFQs7EaWfbxkryQHS7P8icJHc
```

Por padrão, os arquivos são gravados em `data/fixtures/raw/`. Cada assinatura gera:

- `<signature>.raw.json`: bytes JSON exatos recebidos da RPC;
- `<signature>.manifest.json`: assinatura, slot, versão, commitment, endpoint host, nome do arquivo, SHA-256, proveniência e estado `anonymized=false`.

## Salvaguardas

- Exige HTTPS e `finalized`.
- Usa `maxSupportedTransactionVersion=0`, coerente com o parser atual; transações com versões superiores não devem ser forçadas nem descartadas silenciosamente.
- Confere se a assinatura pedida está no payload retornado.
- Rejeita `result=null`, erro RPC e resposta não JSON.
- Aplica intervalo mínimo entre chamadas configurável no construtor.
- Não sobrescreve fixtures existentes.
- Não anonimiza o payload bruto. O bruto deve permanecer restrito; a projeção anonimizada será um artefato separado, com aliases consistentes e sem mapa reversível no pacote de testes.

## Limitações ainda abertas

1. O runtime de auditoria usado nesta sessão continua sem resolução DNS/RPC, então nenhuma das cinco transações candidatas foi efetivamente baixada nesta etapa.
2. O coletor ainda não trata automaticamente `maxSupportedTransactionVersion` acima de zero; ampliar suporte exige teste e revisão separados.
3. Ainda não existe fixture real aprovada nem decodificador de protocolo implementado.
4. A coleta real depende de um endpoint RPC HTTPS alcançável no ambiente que executar o script. Não inserir chave paga no código.

## Critério de aceite de fixture

Uma fixture só pode ser promovida quando houver: payload bruto íntegro; assinatura e slot conferidos; SHA-256 recalculável; proveniência identificada; projeção anonimizada revisada; e teste que prove os invariantes sem depender de rede.

## Auditoria offline de evidências (Etapa 12)

O comando `python tools/audit_solana_fixtures.py <diretorio>` valida cada par `*.raw.json`/`*.manifest.json` sem fazer chamadas de rede. Confere campos obrigatórios, `finalized`, `encoding=json`, marcador `anonymized=false`, nome de arquivo sem traversal, SHA-256, slot e assinatura dentro do payload. O comando retorna código 0 quando todos os manifestos são válidos, 1 quando há evidência inválida e 2 quando não há manifestos.

A auditoria não transforma um payload em fixture aprovada: a revisão semântica, a anonimização separada e a aprovação humana continuam obrigatórias. Os payloads sintéticos usados nos testes verificam apenas o comportamento do auditor; não são evidência mainnet.
