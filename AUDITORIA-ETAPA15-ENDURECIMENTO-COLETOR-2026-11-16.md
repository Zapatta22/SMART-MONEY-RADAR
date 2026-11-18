# SMR — Auditoria Etapa 15: endurecimento do coletor RPC

Data: 2026-11-16

## Escopo

Revisão focada na fronteira entre entrada de assinatura, chamada RPC e persistência de evidências. A coleta remota continuou indisponível por falha DNS; esta etapa foi inteiramente local/offline.

## Achados corrigidos

1. A assinatura era validada apenas quanto a vazio/espaços, embora também fosse usada no nome do arquivo. Agora é exigido alfabeto Base58 e comprimento decodificado de 64 bytes antes de qualquer chamada RPC, bloqueando valores arbitrários e tentativas de path traversal.
2. A raiz da resposta JSON agora precisa ser um objeto antes de acessar campos JSON-RPC.
3. Os arquivos bruto e manifesto agora são criados exclusivamente (`xb`/`x`), com `flush` e `fsync`; não substituem evidências existentes. Se a gravação do manifesto falhar depois de criado o bruto, o bruto daquela tentativa é removido.

## Testes

- Três testes adicionais: assinatura inválida rejeitada antes da rede; JSON com raiz não-objeto rejeitado; conflito de manifesto preserva o arquivo existente e não deixa bruto órfão.
- Suíte completa: **91 testes aprovados, 8 subtests aprovados, 0 falhas**.
- `PYTHONPATH=src:. python -m compileall -q src tests tools`: aprovado.
- As cinco assinaturas candidatas passaram na validação estrutural Base58/64 bytes. Isso não autentica a transação nem confirma sua disponibilidade.

## Limites

- O runtime não resolve `api.mainnet-beta.solana.com`: `socket.gaierror: [Errno -3] Temporary failure in name resolution`.
- Não houve `getHealth` bem-sucedido, `getTransaction`, payload real, fixture aprovada ou revisão semântica.
- Nenhum endpoint pago, Helius, crédito ou VPS foi usado.

## Próxima tarefa

Repetir preflight e coleta dos cinco candidatos em ambiente com DNS funcional e RPC HTTPS gratuito/autorizado. Não iniciar decodificador específico antes de obter e aprovar semanticamente a primeira fixture real.
