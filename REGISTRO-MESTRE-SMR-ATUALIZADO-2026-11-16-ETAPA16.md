# SMART MONEY RADAR (SMR) — REGISTRO MESTRE
Última atualização: 2026-11-16 — Etapa 16

## 1. Estado executivo

Fase atual: preparar coleta de fixtures reais Solana com execução assistida por Android, mantendo somente leitura.
Estado real: base local de ingestão/normalização, coletor RPC, auditor offline, anonimizador e ferramentas de preparação implementados/testados. O SMR completo não está integrado, em produção ou operando 24/7. Nenhuma fixture mainnet foi coletada ou aprovada.

## 2. Etapas consolidadas

- Etapas 1–9: robustez de ingestão/monitor, persistência/replay, contratos de domínio, normalização e integração com EventStore.
- Etapa 10: matriz de 15 programas Solana e cinco assinaturas públicas candidatas.
- Etapa 11: coletor `getTransaction` finalized somente leitura, manifesto e SHA-256.
- Etapa 12: auditor offline de evidências.
- Etapa 13: anonimizador de projeções com mapa reversível confidencial.
- Etapa 14: preflight RPC e coleta em lote.
- Etapa 15: endurecimento de validação Base58, resposta JSON e gravação exclusiva.
- Etapa 16: execução assistida Android/Termux e coleta retomável com auditoria imediata.

## 3. Etapa 16 — alterações

Novos arquivos:
- `tools/collect_solana_candidates.py`
- `tools/run_smr_android.sh`
- `tests/test_candidate_collection_runner.py`
- `docs/fixtures/ETAPA16-EXECUCAO-ANDROID.md`
- `AUDITORIA-ETAPA16-EXECUCAO-ANDROID-2026-11-16.md`

Atualizado: `README.md`.

O fluxo Android usa por padrão `https://api.mainnet-beta.solana.com`, sem chave, apenas `getHealth` e `getTransaction`. A coleta é sequencial, deduplica assinaturas e audita cada par logo após gravação. Em retomada, pares existentes íntegros são pulados; pares parciais/inválidos interrompem o fluxo e são preservados. Nenhuma evidência existente é sobrescrita.

## 4. Validação Etapa 16

- `PYTHONPATH=src:. pytest -q`: **95 passed, 8 subtests passed**.
- `PYTHONPATH=src:. python -m compileall -q src tests tools`: aprovado.
- `bash -n tools/run_smr_android.sh`: aprovado.
- Testes locais/simulados; não houve chamada RPC nem execução em dispositivo Android.

## 5. Próxima tarefa exata

Executar no Android com Termux e internet funcional:

```bash
bash tools/run_smr_android.sh
```

O script interrompe a execução se `getHealth` não retornar `ok`. Se passar, coleta os cinco candidatos e audita estruturalmente. Depois será necessária revisão manual de instruções/CPI, signers, token accounts, pools/vaults, anonimização e aprovação da primeira fixture. Não iniciar decodificador antes dessa aprovação.

## 6. Restrições preservadas

- Solana V1; sem multichain nesta fase.
- Somente leitura; sem assinatura/envio de transações ou trades reais.
- Sem Helius, endpoint pago, créditos ou VPS sem autorização explícita.
- Não tratar payload sintético, resumo de explorer ou teste local como fixture mainnet.
- Launch Radar, Market Radar, Decision/Risk/Portfolio e execução financeira não entram nesta etapa.

## 7. Estado de implantação

Etapa 16 implementada e validada localmente. Não foi testada no Android do usuário. O SMR continua em preparação offline, sem fixture real aprovada, sem validação remota e sem operação 24/7.
