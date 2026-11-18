# SMR — Etapa 16: execução assistida pelo Android

## Objetivo

Permitir executar o preflight e a coleta somente leitura em um Android com Termux e internet funcional, sem depender do runtime de desenvolvimento que apresentou falha DNS.

## Pré-requisitos

- Termux instalado a partir de uma fonte oficial do projeto.
- Arquivo ZIP Etapa 16 extraído no armazenamento acessível pelo Termux.
- Python instalado no Termux (`pkg install python`).
- Conexão à internet.

## Execução

Na pasta extraída do projeto:

```bash
bash tools/run_smr_android.sh
```

O script usa por padrão `https://api.mainnet-beta.solana.com`, endpoint público sem chave, somente para `getHealth` e `getTransaction`. Não usa Helius, chave privada, assinatura ou envio de transações. Para outro endpoint HTTPS gratuito/autorizado, a variável `SMR_SOLANA_RPC_URL` pode ser definida antes da execução; nunca compartilhe tokens ou URLs privadas no chat.

## Retomada e proteção

`tools/collect_solana_candidates.py` coleta os candidatos em sequência e audita cada par manifesto/payload imediatamente. Se a execução for interrompida, uma nova execução valida e pula pares existentes íntegros; não sobrescreve evidências. Se encontrar somente um dos arquivos ou um par inválido, interrompe e preserva tudo para inspeção.

## Limites

A auditoria é estrutural: SHA-256, slot, assinatura, formato e manifesto. Não comprova autenticidade independente do provedor nem semântica de swap. A execução não aprova fixtures automaticamente. Revisão de instruções/CPI, signers, token accounts, pools/vaults, anonimização e aprovação continuam obrigatórias.
