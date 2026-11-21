# CM38C — Modelo de confiança e CM39 — preflight

As dimensões abaixo permanecem independentes. Um rótulo de fonte é declarativo; hostname distinto não prova operadores independentes; TLS protege o transporte ao endpoint, não prova inclusão on-chain, finalização, integridade econômica ou cobertura. SHA-256 preserva bytes locais, não autentica o provedor. O commitment solicitado não constitui prova de resultado finalized. Verificação de assinatura da mensagem, quando aplicável, não prova execução bem-sucedida ou inclusão em bloco finalizado. Ausência de observações não comprova ausência de risco. Respostas divergentes são CONFLICTED; respostas insuficientes são UNKNOWN. Concordância entre fontes permanece UNATTESTED.

CM38B: journal de resposta getTransaction original antes dos pipelines existentes de carteira e Launch. Notificações WS são hints, não prova finalized. Geyser e snapshots de contas possuem arquivo RAW distinto; integração de links explícitos de operação/frame/captura derivada ainda pendente. Não reivindicar captura live por CI com transporte injetado.

CM39: o motor CM33/34 já possui replay, taxas, slippage, risco, reservas, posições, preenchimento parcial e estratégias imediata/confirmada. Preflight CM39 recusa todos os casos sem atestação independente e preço/liquidez/latência executáveis aprovados, até homologação específica. Não executa nenhum tick e não gera rentabilidade. Futuro contrato deverá vincular identidade, slot, pool, cutoff de disponibilidade, origem e RAW da cotação com evidência verificada; impedir lookahead e reutilização de sinais entre radares.

## Sequência mínima live (PR #113, preservada em Draft)
1. Aprovação humana da revisão da PR #113 (somente registro YAML); merge humano separado, nunca automático.
2. Operador opt-in manual READ_ONLY_BOUNDED_CM27, checkout da branch de integração explicitamente selecionada, 75 s no máximo, quatro contas CPMM, uma reconexão no máximo, sem ordens.
3. Conferir artifact RAW/SQLite/manifesto, hash, sessão, baseline finalized, novas inscrições, frames após reconexão, e lacunas UNKNOWN. Se não houver reconexão real demonstrada, repetir apenas o cenário faltante com sessão limitada; não declarar lacuna resolvida por simples reconexão.
4. Verificar RPC e identidade da transação, contraste confirmed/finalized, vinculação econômica às contas e origem; nenhuma credencial em logs ou URL registrada.
5. Validar independência operacional Launch/Smart Money, interrupção e recuperação, checkpoint e ausência de duplicação; gate próprio de soak Android 24h, nenhum trade real.
6. Aprovação humana da evidência, não apenas CI; manter cobertura UNKNOWN sem demonstração e separar autorização de Paper Trading prospectivo. Após validações necessárias, retornar repositório a privado.
