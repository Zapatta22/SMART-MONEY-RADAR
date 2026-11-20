# Detecção offline de inicialização de pools Raydium CPMM

`detect_cpmm_pool_initializations(raw_transaction)` produz evidência de
criação de pool a partir de uma transação RPC arquivada. A instrução padrão
usa o discriminador Anchor derivado de `global:initialize`
(`afaf6d1f0d989bed`), três argumentos inteiros de 64 bits e as 20 contas
obrigatórias no início da lista. O detector exige sucesso explícito, assinatura
e slot estruturais e inventário completo. Também valida ordem dos mints,
autoridade CPMM e IDs dos programas fixos, e exige caminho demonstrável em CPI.
A inicialização com permissão possui outro discriminador e fica fora do filtro.
[Layout oficial fixado](https://github.com/raydium-io/raydium-cp-swap/blob/3d69122790e97cd6aff24e8ba95940793773f58c/programs/cp-swap/src/instructions/initialize.rs) · [Programa e destinatário da taxa de criação](https://github.com/raydium-io/raydium-cp-swap/blob/3d69122790e97cd6aff24e8ba95940793773f58c/programs/cp-swap/src/lib.rs)

A saída inclui assinatura, slot, coordenadas da instrução, pool, configuração,
criador, mints, programas SPL, vaults, mint do LP e observação. Os valores de
abertura e depósitos são os argumentos pedidos à instrução. O estado atual,
as reservas efetivas e a finalidade do provedor exigem verificação adicional.
`deduplicate_cpmm_pool_initializations` mantém um replay idêntico por pool e
omite a identidade se surgirem observações conflitantes.

A fixture preserva requisição e resposta públicas de `getTransaction`
`finalized` no endpoint oficial Solana. Foi encontrada numa consulta limitada
ao destinatário oficial da taxa de criação. O pool de referência
`BrRNVcivKs4kRqqbmksT6zXE6o7SAmWHYjrWgFn9JVNC` apareceu no slot `471578450`.
O SHA-256 da resposta é
`95498b19f9ecfec42b412bc9ac1479a15fecfa474b294e25bdc2f5e52133ebd4`.
O teste confere os hashes, a identidade e os papéis decodificados.
[Transação pública](https://explorer.solana.com/tx/DPtz88XaFsCa3SmJP2S7dE5dvAX9JDDSHTgXwvLhPubyoH5isAX2BxZu3XgNKkNczoXC6JH4Sjbc8K3YHNqHGHo)

Este componente executa offline. Ingestão contínua, persistência,
deduplicação durável e avaliação de liquidez e risco exigem integração
posterior antes de alertas de lançamento.

`smr launch-scan RESPONSE.json --journal launch.sqlite` arquiva o RAW e
a identidade detectada na mesma transação SQLite. O comando retorna pools
novos e registra identidades conflitantes sem emitir uma nova detecção
para elas. Repetir a leitura após reiniciar o comando preserva a deduplicação.
A trilha local ainda aguarda integração com ingestão contínua e alertas.
