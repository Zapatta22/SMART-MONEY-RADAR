# SMR — Comando Mestre 18: histórico CPMM e primeiro baseline prospectivo real

Data: **20/11/2026**. Branch `codex/smr-cpmm-prospective-account-witness`, **PR #103 Draft**, base #102. `main` inalterada.

## A. Estado histórico originalmente solicitado

| Componente no slot histórico **471039497** | Resultado |
|---|---|
| PoolState binário completo | **PENDENTE** |
| AmmConfig binário completo | **PENDENTE** |
| Vaults por snapshot independente antes da instrução | **PENDENTE** |
| Fee counters por categoria | **DESCONHECIDOS no slot antigo** |
| Taxa configurada no slot antigo | **NÃO VERIFICADA** |
| SwapEvent observado da transação original | **PRESENTE**, PR #102, comparação matemática diferença zero |
| Outra fonte de finalização/autenticidade | **PENDENTE** |
| Cotação comprovadamente disponível antes da decisão | **NÃO** |
| Execução financeira / PnL confiável | **BLOQUEADOS** |

O `SwapEvent` preservado da primeira fonte informa reservas efetivas imediatamente pré-instrução e taxas realizadas. **Não é um segundo snapshot de PoolState/AmmConfig**, não resolve a independência de fonte e só foi observado por nós dois dias depois do swap. `getAccountInfo` / `getMultipleAccounts` RPC público padrão não recuperam contas em slot passado somente com `minContextSlot`.

## B. Fontes investigadas antes das consultas

- Solana RPC padrão: `getAccountInfo` documenta `minContextSlot`, **não** leitura arbitrária de uma versão histórica.
  https://solana.com/docs/rpc/http/getaccountinfo
- Alchemy Solana Account Archive: suporte explícito a `slot` / `lastUpdateBeforeSlot` mas a própria documentação restringe consultas históricas aos **planos pagos**; descartado.
  https://www.alchemy.com/docs/solana/account-archive
- Corvus Labs Historical Accounts: divulga `getAccountInfo` e `getMultipleAccounts` no slot solicitado, porém exige acesso autenticado/plano alugado; **não foi contratado nem consultado**.
  https://docs.corvus-labs.io/solana-rpc/historical-accounts
  https://docs.corvus-labs.io/platform/pricing
- Solarchive: dataset gratuito Parquet, mas a vitrine pública de cobertura e arquivos publicada até **dezembro de 2025**, sem demonstração de disponibilidade do snapshot de **novembro de 2026**. Não baixado.
  https://solarchive.org/
- Trawl Raydium CPMM: amostra gratuita refere-se aos slots **468300000–468300999**, não ao `471039497`; arquivos do intervalo desejado aparecem como produto pago. Não adquirido.
  https://trawl.run/data/raydium-cpmm
- Rewind (Solana Vibe Station): anuncia leitura histórica por slot e assinatura, mas exige API key; trial cobre **1 dia**, Pro até **30 dias** mediante plano. **Nenhuma chave/conta/plano habilitado** neste ciclo.
  https://solanavibestation.com/rewind

**Conclusão:** nenhuma fonte histórica completa e gratuita do slot antigo foi comprovada como acessível sem contratação/credenciais. Não continuar repetindo chamadas de `getTransaction` nos nós que responderam `null` e HTTPError sem hipótese nova.

## C. Captura prospectiva efetivamente realizada e preservada

Uma **única** solicitação `getMultipleAccounts` para `https://api.mainnet-beta.solana.com`, com `commitment=finalized` **solicitado**, `encoding=base64`, buscou nesta ordem:

1. PoolState `CqvMZmWDvEufa5rzkubidyR4zMDqDPoLjAtsW6wGsPMu`.
2. AmmConfig `D4FPEruKEHrG5TenZ2mpDGEfu1iUvTiqBxvpU8HLBvC2`.
3. Vault HIGH `C5S7w9bJ81oaksCpTrBUMX5Wn4RfSxbnnkCBwMuMaPdU`.
4. Vault WSOL `8cGsmrpU5rkLszygFgaFfo8PaFBipm1zfqSLxTdytKmG`.

- **Slot da resposta:** `471856996` (posterior ao swap original de slot `471039497`).
- **Horário de observação:** `2026-11-20T19:37:10.132099+00:00`.
- **Horário de disponibilidade:** `2026-11-20T19:37:10.344983+00:00`.
- **SHA-256 request RAW:** `2ee9db161ff7928efee3e21ac4ac93d63daeec3cab22838a94c582b1a10ed718`.
- **SHA-256 response RAW:** `2645d85a94cdd728f7485929b59fbdd475a1d200cb403c8f4a893e50a8f44562`.
- **Coleta GitHub Actions:** https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44803809348
- **Cópia permanente, sem nova consulta RPC:** https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44803965437
- **Arquivos RAW originais** e manifesto em `data/evidence/mainnet/2026-11-20/prospective-slot-471856996/`.

Os validadores existentes `decode_pool_state`, `decode_amm_config`, `verify_pool_swap_identity` foram reutilizados e reunidos em `services/prospective_cpmm_account_snapshot.py`. O contrato verifica associação à própria requisição, SHA, owner declarado, layout Anchor, mints e autoridade SPL, taxas acumuladas, identidade dos vaults e disponibilidade temporal. Foi corrigido erro de prefixo zero no decodificador Base58 existente. **Sem verificação criptográfica do fornecedor.**

| Campo da observação RPC no slot **471856996** | Valor |
|---|---:|
| Vault HIGH bruto | 76.503.529.653.334 unidades RAW |
| Reserva HIGH líquida das taxas acumuladas | 76.473.066.869.631 unidades RAW |
| Vault WSOL bruto | 257.443.240.033 lamports |
| Reserva WSOL líquida das taxas acumuladas | 257.014.075.604 lamports |
| `AmmConfig.trade_fee_rate` declarada no estado **atual da captura** | 2.500 / 1.000.000 |
| `AmmConfig.creator_fee_rate` declarada no estado **atual da captura** | 500 / 1.000.000 |

Essas reservas são computadas a partir da leitura RPC das quatro contas no **mesmo context.slot** e não são valores de uma cotação comercial observada/executável. O estado atual **não verifica** a mesma configuração no slot anterior. O conjunto é rotulado `RPC_DECLARED_PROSPECTIVE_ONLY`, com `pre_swap_state_of_original_tx=False`, `provider_independently_authenticated=False`, `executable_quote_proven=False`, `operational_authorized=False`.

## D. Código, testes e próxima tarefa

- Novos: `tools/capture_prospective_cpmm.py`, `services/prospective_cpmm_account_snapshot.py`, `tests/test_prospective_cpmm_account_snapshot.py`, `tests/test_real_prospective_cpmm_accounts.py`, dois workflows isolados para coleta e persistência offline. Nenhum agendamento recorrente, captura apenas neste marco.
- **925 testes aprovados, zero falhas e compileall**, commit de código `34baa2017b5e5a2a8d6e620485da2d919445c864`, CI https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44804088637.
- Testes adversariais: hash e identidade RAW, outras contas/config, owner, mints, authority, conta faltante, JSON ruim, taxas superiores aos saldos, slot antigo, data e proveniência, determinismo e proibição de replay com dados retrospectivamente coletados.
- **Próximo módulo executável sem custo:** construir e avaliar *dois ou mais* snapshots prospectivos, de momentos futuros distintos, **somente se houver caso de uso**, com persistência RAW, cutoff e identificação de mudanças; não supor ordem de instrução intra-slot a partir de `context.slot`, nem disponibilidade antes de captura. Para o swap antigo, apenas adquirir account-write snapshots de fonte realmente histórica com atestação, slot e ordenação; sem solução comprovada gratuita neste momento.
- Sem Helius, VPS, contratação, chaves privadas, operações financeiras ou merge.
