# SMR — Matriz de programas Solana e preparação de fixtures — Etapa 10

Data: 16/11/2026  
Escopo: classificar programas Solana prioritários da V1, registrar assinaturas públicas candidatas e estabelecer requisitos de proveniência/anonimização. Sem execução financeira.

## 1. Base e validação inicial

Base utilizada: pacote `SMR-CODIGO-BASE-ETAPA9-2026-11-16.zip` e Registro Mestre da Etapa 9. Antes das alterações, a suíte foi reexecutada: 62 testes aprovados, 0 falhas.

## 2. Entregas implementadas

Novos arquivos:
- `src/smart_money_radar/domain/program_registry.py`
- `tests/test_program_registry.py`
- `docs/fixtures/ETAPA10-MATRIZ-PROGRAMAS-E-FIXTURES.md`

Arquivo atualizado:
- `README.md`

O registro contém 15 programas, com ID Base58, categoria, prioridade, escopo e fonte de referência. Categorias: core, launchpad, AMM e aggregator. Jupiter v6 é explicitamente `venue=False`, pois roteia operações através de venues e não deve ser contado como pool/DEX independente.

Validação do registro:
- unicidade dos Program IDs;
- decodificação Base58 para chave de 32 bytes;
- metadados e URLs de referência não vazios;
- comportamento explícito para programa desconhecido;
- distinção entre Pump.fun Bonding Curve e PumpSwap.

## 3. Matriz e candidatos a fixture

A matriz cobre System, SPL Token, Token-2022, Associated Token Account, Pump.fun, PumpSwap, Raydium CPMM, Raydium AMM v4, Raydium LaunchLab, Raydium CLMM, Orca Whirlpools, Meteora DLMM, Meteora DBC, Meteora DAMM v2 e Jupiter v6.

Foram registrados cinco candidatos mainnet encontrados em páginas públicas Solscan: Raydium CPMM, Raydium AMM v4, Jupiter v6, Meteora DLMM e Meteora DAMM v2. Assinatura, slot, status resumido e URL estão documentados em `docs/fixtures/ETAPA10-MATRIZ-PROGRAMAS-E-FIXTURES.md`.

**Limite de evidência:** os exploradores apresentam resumo e assinatura, mas o payload integral `getTransaction` ainda não foi obtido. Portanto, nenhum desses candidatos foi promovido a fixture executável. Não há arquivos JSON de transação inventados ou sintéticos no pacote.

## 4. Regras técnicas estabelecidas

- Preservar o JSON bruto e seu SHA-256 como evidência imutável.
- Produzir projeção anonimizada separada, substituindo signers/carteiras/token accounts pessoais por aliases locais por fixture.
- Preservar program IDs, mints, pools e contas de protocolo indispensáveis à interpretação.
- Não incluir o mapa reversível de aliases no pacote de testes.
- Resolver account keys completos, incluindo loaded addresses em transações versionadas.
- Registrar instrução top-level e caminho CPI/stack height.
- Não inferir swap apenas de dois deltas de saldo.
- Separar router e venue subjacente; evitar dupla contagem.
- Separar fees, rent, tips, wrap/unwrap e transferências auxiliares dos montantes econômicos do swap.
- Preservar instruções desconhecidas e payload bruto.

## 5. Testes e resultado

- Suíte completa: **66 testes aprovados, 0 falhas**.
- `PYTHONPATH=src python -m compileall -q src tests`: aprovado.
- Quatro testes novos para unicidade/validade dos IDs, Jupiter como agregador, separação Pump.fun/PumpSwap e programa desconhecido.
- Testes locais; sem RPC remoto e sem benchmark.

## 6. Bloqueio de coleta RPC

Tentativa de acesso ao endpoint público `https://api.mainnet-beta.solana.com` falhou por resolução DNS indisponível no runtime (`Temporary failure in name resolution`). Nenhuma chamada Helius foi feita, nenhuma chave foi usada e nenhum crédito foi consumido. A coleta de payloads brutos fica pendente até existir canal RPC de leitura autorizado e acessível.

## 7. Estado por etiqueta

- Matriz de programas: implementada e testada.
- Assinaturas públicas candidatas: localizadas e documentadas.
- Fixtures reais brutas: não coletadas.
- Projeções anonimizadas: não produzidas, pois dependem do payload bruto.
- Decodificadores específicos de DEX/launchpad: não implementados.
- Integração de decisão/risco/portfólio/execução: não implementada.

## 8. Próxima tarefa exata

Obter JSON RPC `getTransaction` finalized para as assinaturas candidatas, arquivar payload bruto, hash e proveniência; criar projeções anonimizadas revisadas; aprovar fixtures por protocolo. Em seguida começar pelo primeiro decodificador vertical Pump.fun Bonding Curve/PumpSwap ou Raydium CPMM, conforme a cobertura real das fixtures. Não ativar endpoints pagos, Helius ou execução de transações sem autorização explícita.
