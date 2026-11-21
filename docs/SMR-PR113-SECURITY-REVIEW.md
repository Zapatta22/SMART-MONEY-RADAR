# CM38H — Parecer técnico de segurança da PR #113

Data: 2026-11-21. Base auditada: PR #111 HEAD 02b1631af03a634d6e255dfec5572df62b3d20b2, PR #113 Draft HEAD 58958fa3113130b2cf78ad2430300f5b7c97e02c. Fonte da PR #113: .github/workflows/smr-cm27-live-gate.yml. Fonte operacional existente SOMENTE na branch de desenvolvimento: tools/capture_live_cpmm_ws_baseline.py. Parecer limitado à inspeção estática dos arquivos; nenhum teste Solana live foi executado.

## Verificações satisfeitas nos arquivos

- Gatilho único workflow_dispatch; exigência textual READ_ONLY_BOUNDED_CM27; condição `if` no job; não existem gatilhos de push ou pull_request no workflow analisado.
- Token automático GitHub Actions restrito por `permissions: contents: read`; não há declaração de secrets, chaves privadas ou ações de compra no YAML.
- Script opt-in exige SMR_LIVE_CAPTURE_OPT_IN; endpoints públicos mainnet Solana com WebSocket e RPC JSON-RPC getMultipleAccounts (RPC usa método HTTP POST de consulta, NÃO de transação).
- Código fixa MAX_SECONDS=75, MAX_FRAMES=80 e quatro endereços de contas CPMM comparados à fixture inicial, com hash SHA-256 do RAW original.
- Runtime previsto arquivo SQLite local /tmp/smr-cpmm-baseline-live/geyser-raw.sqlite, manifesto JSON, RAW e relatórios de sessão; upload-artifact@v4 usa if: always, retenção 7 dias. Categorização de evidência retém cobertura UNKNOWN e financial_execution_authorized=False. O trabalho do runner dura no máximo o limite configurado quando seus cancelamentos assíncronos são respeitados.

## Limitações e riscos que exigem conferência humana

1. **Branch/ref no workflow:** actions/checkout@v4 não especifica ref. A instalação da PR #113 na main só disponibiliza o workflow; não instala o script correspondente. Em workflow_dispatch, o operador deve selecionar explicitamente a branch de desenvolvimento tanto na caixa de branches quanto no disparo. Sem verificação do checkout SHA no script/manifest, selecionar main ou outra branch pode executar um código diferente ou falhar. RECOMENDAÇÃO: adicionar uma verificação estática de commit/ref e assinatura do script ao pipeline antes de autorizar a captura.
2. **Permissões indiretas:** as ações checkout@v4, setup-python@v5 e upload-artifact@v4 usam tags, não SHAs imutáveis. Dependências são instaladas com `pip install -e .` sem lock de hashes; há risco residual de supply-chain. Não há segredos solicitados no YAML, mas o token padrão de conteúdos ainda existe. RECOMENDAÇÃO: fixar actions por commit imutável, dependências e revisão de permissões; apenas depois decidir merge.
3. **Limites distintos:** 75 segundos são do coletor; timeout-minutes:3 é duração total do job com instalação e artifact. Critério de interrupção de 75 s deve ser comprovado em execuções, não inferido do job YAML. Reconnect máximo configurado na política do controller e deve ser conferido explicitamente com teste.
4. **Falhas parciais:** manifest.json é gerado após runner.run(); se falhar antes, upload-artifact sempre tenta preservar o SQLite/frames mas manifesto pode não existir. RECOMENDAÇÃO: publicar manifesto de falha parcial e evitar ausência silenciosa de evidência.
5. **Limites de exposição:** artefatos de sessão podem conter endereços públicos, respostas RPC e metadados operacionais; o repositório está público no momento. Avaliar retenção, minimização e verificação manual antes de divulgação.
6. **Sem prova de autenticidade:** duas fontes RPC, hash local ou confirmação solicitada não provam inclusão ou finalização independentes. A captura não habilita CM39 nem negociação real.

## Gate de decisão em duas etapas

Etapa A: revisar o diff exclusivo da PR #113, as permissões e controles; aprovar e fazer merge MANUAL do YAML **somente após sanar o ref/pinning e o manifesto parcial**. Não remover Draft sem ordem humana.

Etapa B, separada: selecionar a branch onde o coletor validado existe, conferir o SHA, habilitar o workflow manual e escrever READ_ONLY_BOUNDED_CM27. Validar saída: RAW íntegro, SQLite integrity_check OK, manifesto de sessão, contas limitadas a quatro, duração <=75 s para o coletor, MAX_FRAMES<=80, reconexão <=1, cobertura UNKNOWN e sem qualquer envio financeiro. Em erro, suspender nova captura até analisar os artefatos. Aprovação de A NÃO autoriza B.

Conclusão: workflow estaticamente limitado e com privilégios reduzidos, porém **PENDENTE DE REFORÇO**, sem aprovação para merge/execução por esta análise. PR #113 e main preservadas.

## CM42 — Revisão complementar após correções na branch isolada da PR113 (2026-11-21 UTC)

**HEAD corrigido PR113:** 00f6a6a9225524501e8a6bb1fd4d784a2d902ef6, sem merge, ainda Draft. Esta revisão substitui apenas as recomendações de correção dos itens 1, 2 e 4 anteriores; não homologa live.

1. **Checkout/revisão executada**: agora fixa o código de captura em 49bb5e7763926d28e540ca13d9557056b9d87833, com inspeção do HEAD; checkout dos controles vinculado a github.workflow_sha. Ações checkout 11d5960a326750d5838078e36cf38b85af677262, setup-python a26af69be951a213d495a4c3e4e4022e16d87065 e upload-artifact ea165f8d65b6e75b540449e92b4886f43607fa02 fixadas por commits. Nenhum ramo mutável é usado para executar o script Solana.
2. **Dependências runtime**: requisitos Linux CPython 3.12 fixos por versões + SHA256 do wheel de python-dotenv 1.1.1, websockets 15.0.1 e protobuf 6.32.1, validados por pip --require-hashes e --only-binary em GitHub Actions. Dependências fora desse ambiente falham fechadas; atualizar exige novo lock e revisão. Sem pip install -e . e sem ferramenta de build dinâmica durante a captura.
3. **Interrupções**: timeout externo de 90 segundos é adicional à duração interna de 75 segundos; o workflow em if:always tenta registrar manifest.json FAILED_OR_INCOMPLETE e termination.json com checksum e sqlite_integrity, inclusive se o processo for interrompido ou o SQLite estiver danificado. O upload de artefato em if:always tenta preservá-los por 7 dias. Uma destruição abrupta do runner/serviço fora de controle impede garantias absolutas.
4. **Ações exclusivamente manuais e segurança**: workflow_dispatch exige READ_ONLY_BOUNDED_CM27; permissions contents:read; persist-credentials false; fonte com quatro contas CPMM, até uma reconexão (WsResiliencePolicy.max_reconnects == 1), no máximo 80 frames, nenhum envio financeiro. A CI da branch PR113 **44892867802 SUCCESS** validou os seis cenários offline e os hashes reais de wheels; testes do fluxo live (cotas Solana reais/latência/exceções do runner) **não foram executados**.

**Parecer atualizado:** os três bloqueadores de preparação (ref do código, pins e falha/encerramento) têm correção publicada e tests offline aprovados. Riscos residuais: aprovação humana do diff e do código pinado, dependência do GitHub Actions e rede pública, indisponibilidade do runner na falha catastrófica, eventual revisão de conteúdo/retencao dos artefatos, nenhuma atestação independente. Não retirar Draft automaticamente, não fazer merge, não acionar captura. Aprovação humana do workflow e autorização manual da captura continuam duas ações separadas. Não afirmar autenticação, cobertura, paper prospectivo nem trading reais.
