# SMR — Auditoria Etapa 14: preflight e coleta em lote

Data: 2026-11-16

## Escopo executado

- Consolidado o conjunto de cinco assinaturas mainnet previamente documentadas na Etapa 10 em `data/fixtures/candidates/solana_mainnet_candidates.json`.
- Atualizada a CLI do coletor para aceitar `--candidate-file`, validar a estrutura JSON e deduplicar assinaturas preservando a ordem.
- Criado `tools/check_solana_rpc.py`, que executa `getHealth` em endpoint HTTPS configurado por ambiente, com timeout de 8 segundos e sem imprimir URL completa, tokens ou resposta integral.
- Documentados os comandos de preflight e coleta em lote no README.

## Validação

- Suíte completa: **88 testes aprovados**, mais 5 subtests.
- A suíte anterior tinha 86 testes aprovados; dois testes novos cobrem o catálogo de cinco candidatos e o carregamento/deduplicação do arquivo de lote.
- A tentativa real de `getHealth` em `https://api.mainnet-beta.solana.com` falhou antes da resposta HTTP: `URLError` ao chamar o host público `api.mainnet-beta.solana.com`; a tentativa direta anterior identificou `Temporary failure in name resolution`. A saída do preflight omitiu corretamente URL completa e credenciais.
- Nenhuma chamada Helius, chave paga, crédito ou endpoint pago foi utilizado.
- Nenhum payload de transação foi coletado nesta etapa; não há hash de transação novo nem fixture real aprovada.

## Limites e estado

A preparação offline da coleta em lote e o preflight estão implementados. A coleta de rede permanece BLOQUEADA pela resolução DNS deste runtime. O estado dos cinco registros permanece `candidate`, nunca `fixture approved`. Não iniciar decodificadores específicos até obter pelo menos um payload bruto íntegro, auditado, anonimizado e semanticamente revisado.

## Próxima ação exata

Executar o preflight e o comando de coleta em um ambiente com RPC HTTPS gratuito/autorizado e DNS funcional, usando o arquivo de cinco candidatos. Em seguida, rodar `audit_solana_fixtures.py`, revisar programas/instruções/CPI/signers/token accounts/pools/vaults, gerar projeções anonimizadas com a Etapa 13 e aprovar uma fixture real. Só então iniciar o decodificador do protocolo correspondente.
