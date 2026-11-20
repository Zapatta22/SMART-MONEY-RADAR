# SMR — Protocolo de validação Solana Live com rede real

Estado em 2026-11-20: **PR de preparação; nenhuma sessão externa foi executada**.
A validação automatizada é distinta da aceitação operacional.

## Origem e compromisso

O monitor assina `logsSubscribe` em `confirmed` para **um endereço por
subscrição**. A notificação é somente um *hint*. Somente
`getSignaturesForAddress` e `getTransaction` solicitados em `finalized`
podem avançar o cursor. Ver documentação pública Solana:
https://solana.com/docs/rpc/websocket/logssubscribe e
https://solana.com/docs/rpc/http/getsignaturesforaddress.

A API JSON-RPC retorna uma **afirmação do provedor**: não oferece atestado
criptográfico independente da origem, do relógio ou da completude histórica.
O código atualmente reserializa a resposta `getTransaction` em JSON antes
de arquivar evidências; seu SHA-256 não é o hash dos bytes HTTP originais.

## Pré-requisitos para execução autorizada

1. Usar um ambiente sob controle do operador e rede autorizada, com chave
   Helius válida (não colar a chave em relatórios, scripts versionados, PRs
   ou logs). **Não há credenciais Helius nesta sessão.**
2. Revisar quotas e eventual cobrança do provedor; não contratar planos
   pagos sem aprovação. Usar inicialmente um endereço público de atividade
   moderada. Monitorar o programa CPMM inteiro pode exceder limites RPC
   rapidamente se cada log produzir uma consulta.
3. Instalar a branch de integração aprovada e usar exclusivamente modo
   somente leitura. Nunca configurar chaves de carteiras ou trading.
4. Utilizar o mesmo `SMR_DB_PATH` e o mesmo identificador de origem ao
   repetir o ensaio. Trocar cluster/endpoint exige outra identidade de origem.

Exemplo de uma **única sessão controlada** no terminal do operador:

```bash
export SOLANA_CLUSTER=mainnet
export SMR_ALLOW_NETWORK=true
export SMR_DB_PATH="$HOME/smr-validation.sqlite3"
read -r -s -p "Chave Helius (não exibida): " HELIUS_API_KEY
export HELIUS_API_KEY
echo
smr launch-live PUBLIC_SOLANA_ADDRESS \
  --source-id helius-mainnet-test-v1 \
  --duration-seconds 120 \
  --page-size 100 --max-pages 10 \
  --min-reconcile-interval-seconds 1 \
  --metrics-json "$HOME/smr-live-validation.json"
unset HELIUS_API_KEY
```

`PUBLIC_SOLANA_ADDRESS` deve ser substituído por endereço **público real**
aprovado para o ensaio. O endereço oficial do programa Raydium CPMM presente
no decoder do SMR é
`CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C`.
Não começar diretamente por esse programa de alto volume sem avaliar custo.

O modo `--duration-seconds` exige 1 a 900 segundos. O argumento
`--metrics-json` exige duração limitada. Se `SMR_ALLOW_NETWORK` ou a
chave estiverem ausentes, nenhuma coleta é iniciada.

## Evidências produzidas

- SQLite conserva a assinatura RPC finalizada por origem, sequências locais,
  hashes de payload JSON reserializado e evidências CPMM;
- JSON grava horário UTC **local** de início/fim, endereço público,
  SHA-256 do identificador da fonte, cursores e `PRAGMA integrity_check`;
- JSON **não contém API key nem URL com credenciais**;
- amostras monotônicas da coleta RPC, persistência e intervalo entre
  **recepção local** de hint confirmado e arquivo da **mesma assinatura**
  consultada em finalized;
- p50/p95/p99 só aparecem com pelo menos 20 amostras locais; caso contrário
  ficam `null`, sem inventar tempos;
- erros de taxa (HTTP 429), notificações duplicadas, hints pendentes e
  recuperações incompletas são contados quando observados.

O relatório carrega sempre `coverage=UNKNOWN`. Não mede latência
de emissão do validador até chegada no cliente: a notificação padrão não
fornece instante de emissão confiável. Registro local não prova relógio
confiável nem provedor independente.

## Plano de comparação e recuperação

Repetir sessões com a mesma base e origem, separadas por interrupção
controlada; verificar que cada reconexão executa RPC finalized antes da
aceitação das notificações pendentes. Conferir que a assinatura anterior
é encontrada no histórico, que o cursor não avança em erro 429 ou página
insuficiente, e que duplicatas não geram nova identidade. Conferir
`PRAGMA integrity_check = ok` antes e depois.

Divergência, transação indisponível, páginas duplicadas/fora de ordem e
`confirmationStatus` diferente de finalized exigem parada e investigação.
Histórico perdido fora do limite de paginação não é recuperado
automaticamente. Em qualquer lacuna, **não declarar cobertura completa**.

## Portões de aceitação ainda abertos

- [ ] Captura WS + RPC real com créditos/autorização do operador;
- [ ] prova de correspondência de assinaturas e slots e observações finalizadas;
- [ ] contagem de mensagens, custo do provedor e amostras suficientes;
- [ ] teste real de desconexão/reconexão e comportamento HTTP 429;
- [ ] medição de latência p95/p99, somente quando houver amostragem suficiente;
- [ ] evidência de janela de histórico e política de lacuna, reorg e dados atrasados;
- [ ] trilha externa verificável de proveniência (não somente hash local);
- [ ] análise da taxa de tráfego e limitação de chamadas para endereço de alto volume;
- [ ] revisão humana da cadeia Draft antes de integração com o restante do SMR.

**Nunca habilitar ordens reais** com base apenas neste manifesto ou nos testes
determinísticos.


## Limite de custo RPC e deduplicação

O CLI limita a **uma tentativa de reconciliação por endereço a cada segundo**
por padrão (`--min-reconcile-interval-seconds 1`, ajustável entre 0 e 60).
Notificações intermediárias ficam marcadas como pendentes, e a reconciliação
periódica/reconexão continua obrigatória. `coalesced_notifications` mede a
quantidade de mensagens agrupadas; **não é contador de eventos recuperados**.
Aumentar o intervalo reduz requisições mas aumenta atraso e risco de o RPC
não oferecer uma janela histórica suficiente. Quando uma assinatura é perdida
por limite de páginas, o algoritmo interrompe sem mover o checkpoint.
