# SMR — Etapa 13: anonimizador de fixtures Solana

Data: 2026-11-16  
Base: `SMR-CODIGO-BASE-ETAPA12-2026-11-16.zip` (76 testes informados como aprovados no Registro Mestre).  
Escopo: criar projeção anonimizada sem alterar payload RPC bruto; sem rede e sem execução financeira.

## Implementação

- `src/smart_money_radar/data_sources/fixture_anonymizer.py`
- `tools/anonymize_solana_fixture.py`
- `tests/test_fixture_anonymizer.py`
- README atualizado.

## Política aplicada

1. O bruto é somente lido; SHA-256 original é calculado antes da projeção.
2. Signers/fee payer são identificados pelo `header.numRequiredSignatures` ou pelo campo `signer` em `jsonParsed`.
3. `owner` de `preTokenBalances`/`postTokenBalances` e a token account no `accountIndex` correspondente são pseudonimizados.
4. Program IDs referenciados por `programId`/`programIdIndex`, mints e endereços passados explicitamente em `protected_addresses` permanecem intactos.
5. Alias é uma chave pública Base58 de 32 bytes derivada por HMAC-SHA256 com segredo local; o mesmo endereço e segredo produzem o mesmo alias.
6. Strings/logs são substituídos por igualdade exata ou token Base58 completo, evitando corrupção de mints por substituição de substring.
7. Mapa reversível é emitido separadamente, fora do diretório de fixtures, com permissão `0600`; não é incluído no pacote de testes.
8. Projeção, manifesto e mapa não sobrescrevem artefatos existentes. A operação falha em caso de entrada JSON inválida, chave curta, manifesto de origem incompatível ou colisão de caminhos.

## Limites explícitos

- A identificação de pools, vaults e contas de protocolo depende da lista `--protect` revisada para cada fixture. Endereços pessoais fora dos papéis inferíveis automaticamente (ex.: destinatário SOL) dependem de `--anonymize`. Não presumir que toda conta não-signatária seja pessoal nem anonimizar indiscriminadamente.
- A ferramenta não decodifica swaps, não declara fixture semanticamente aprovada e não faz chamadas RPC.
- O mapa contém dados reversíveis e deve permanecer privado; a chave secreta não é armazenada.
- Os testes usam payloads sintéticos exclusivamente para testar a transformação; não são transações mainnet nem fixtures de parser.
- Nenhum payload RPC real foi coletado/aprovado nesta etapa.

## Testes

- Preserva bruto byte a byte e verifica SHA-256.
- Pseudonimiza fee payer, token account e owner; preserva program ID, mint, pool e program IDs resolvidos em CPI/loaded addresses.
- Remove endereços pessoais conhecidos de logs sem substituir substrings de outros endereços.
- Mantém aliases estáveis para a mesma chave.
- Protege endereços explicitamente permitidos.
- Rejeita mapa dentro do diretório de fixtures, segredo curto, sobrescrita e manifesto de origem divergente; valida também manifesto finalized e SHA-256 de origem.

Validação: 86 testes `unittest` aprovados, 0 falhas; `compileall` aprovado. Tudo local/offline, sem RPC real, Helius ou créditos.

## Próxima tarefa

Executar o coletor em ambiente com RPC HTTPS acessível/autorizado; auditar a resposta finalized; revisar manualmente contas pessoais versus pools/vaults/protocolos; produzir a primeira projeção com o anonimizador; verificar bruto/hash/projeção/mapa; aprovar a primeira fixture somente após revisão semântica. Não iniciar decodificador sem fixture real aprovada.
