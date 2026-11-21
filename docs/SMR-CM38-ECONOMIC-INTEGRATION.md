# CM38 — Vínculo econômico e qualificação / CM39 — pré-flight

Os dados RAW RPC originais permanecem em cm38_rpc_observations. Os vínculos cm38_economic_evidence_links são criados na mesma transação do checkpoint quando a evidência existe, abrangendo transação, swap, classificação, reconciliação e oportunidade de replay; no Launch, o cursor finalized e os vínculos RAW são atômicos. As respostas JSON reserializadas nos arquivos legados não são atribuídas como bytes originais da rede. Legados sem captura podem existir mas são UNKNOWN.

Os frames Geyser podem ser associados à RPC exclusivamente como TEMPORAL_CONTEXT_ONLY em cm38_geyser_rpc_context, com SHA-256, timestamps UTC e identidades verificadas localmente. Uma notificação de conta isolada não traz a assinatura da transação e não demonstra causalidade, inclusão ou finalização; nenhum link contextual libera CM39.

CM38E reutiliza a segurança de token, liquidez, volume e classificador; preserva razões de mint/freeze, Token-2022, concentração e manipulação, não promove status de proveniência por declaração do chamador e bloqueia estratégias imediata e confirmada quando houver lacunas.

CM38F reutiliza a descoberta CM35 e seus recibos por carteira, conferindo por operação os vínculos com RAW RPC. Somente links válidos são contados como vínculos locais: rentabilidade realizada, taxa de acerto, fees, drawdown e independência de proprietários requerem prova econômica adicional e continuam não calculados. Nenhuma carteira não qualificada influencia consenso acionável.

CM39A usa o gate de proveniência CM38C e a conta sintética CM34 de maneira estritamente somente leitura. Sem evidência autenticada, zero ticks elegíveis, zero entradas, saídas ou reservas, nenhuma alteração no ledger. Os motores CM33/34 de replay sintético offline não autorizam paper prospectivo nem trades reais.

**Aprovação humana live**: PR113 permanece Draft, exige revisão/merge humano e acionamento separado do workflow READ_ONLY_BOUNDED_CM27, no máximo 75 segundos, quatro contas CPMM e até uma reconexão. Analisar artefatos e UNKNOWN; não tratar evento não observado como teste aprovado. Após validações, restaurar repositório como privado. Ver Registro Mestre para commits e CIs.
