# Auditoria técnica — SMR Etapa 13: anonimizador Solana

Data: 16/11/2026  
Base: pacote Etapa 12  
Resultado: **aprovado em testes locais/offline**, com limites abaixo.

## Alterações

- Adicionado `fixture_anonymizer.py` para criar projeção sem modificar bruto.
- Adicionado CLI `anonymize_solana_fixture.py`.
- Adicionados 10 testes específicos.
- Adicionada documentação de política e uso.
- Alinhada a matriz Etapa 10 ao `encoding=json` efetivamente usado pelo coletor Etapa 11.

## Verificações

- Preservação byte a byte do JSON bruto e hash SHA-256.
- Pseudonimização de fee payer/signers, owners SPL e token accounts por `accountIndex`.
- Preservação de program IDs resolvidos por instruções top-level, CPI e loaded addresses.
- Preservação automática de mints; proteção manual de pools/vaults/contas de protocolo.
- Endereços pessoais adicionais aceitos por `--anonymize`; `--protect` prevalece.
- Alias Base58 de 32 bytes derivado por HMAC-SHA256; aliases estáveis sob a mesma chave.
- Substituição em logs sem corrupção por substring.
- Mapa reversível separado, modo `0600`, não armazenado no diretório de fixtures.
- Validação do manifesto de origem via auditor Etapa 12, incluindo hash, slot e assinatura.
- Proteção contra sobrescrita e caminhos inseguros.

## Resultado de validação

`PYTHONPATH=src python -m unittest discover -s tests -v`: **86/86 aprovados**.  
`PYTHONPATH=src python -m compileall -q src tests`: aprovado.  
`PYTHONPATH=src python tools/anonymize_solana_fixture.py --help`: aprovado.

Sem conexão RPC/Helius, sem uso de créditos e sem transações. Os payloads dos testes são sintéticos e servem somente para testar a transformação.

## Riscos/limites remanescentes

- Pools, vaults e outras contas de protocolo exigem revisão por transação e inclusão em `--protect`.
- Carteiras pessoais que não sejam signers nem owners/token accounts precisam ser identificadas na revisão e incluídas em `--anonymize`.
- O mapa é reversível e confidencial; permissões `0600` não equivalem a criptografia. Deve ser guardado em ambiente privado e nunca distribuído.
- Nenhuma fixture mainnet foi coletada ou aprovada; DNS/RPC permanece bloqueado neste runtime.
- O pacote ainda é uma cópia local de auditoria, não sincronizada ao Replit/VPS.

## Decisão

Etapa 13 concluída quanto à implementação e testes do anonimizador. A aprovação de uma fixture real permanece pendente da coleta RPC autorizada e revisão semântica. Próximo passo: coletar as cinco assinaturas candidatas, auditar, anonimizar e aprovar a primeira fixture antes de iniciar decodificador específico.
