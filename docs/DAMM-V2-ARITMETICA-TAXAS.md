# DAMM v2 — aritmética de taxas isolada

## Escopo desta etapa

Este módulo contém funções aritméticas puras e testes sintéticos para os cálculos de transfer fee do Token-2022 e de taxa AMM do DAMM v2. Ele é uma base de teste para o reconciliador futuro; **não é um reconciliador econômico**.

Arquivos:
- `src/smart_money_radar/data_sources/damm_v2_fee_math.py`
- `tests/test_damm_v2_fee_math.py`

## Fontes de implementação fixadas

- Meteora DAMM v2: `MeteoraAg/damm-v2@18936b18c26708f6e9b52cacc01ea2f99868ba8e`
  - `programs/cp-amm/src/utils/token.rs`: cálculo de transfer fee excluída/incluída e uso de epoch fee.
  - `programs/cp-amm/src/state/fee.rs`: `get_excluded_fee_amount`, `get_included_fee_amount`, `split_fees` e `FeeMode::get_fee_mode`.
  - `programs/cp-amm/src/state/pool.rs`: uso dessas funções em partial fill.
  - `programs/cp-amm/src/instructions/swap/swap_partial_fill.rs`: limite bruto, cálculo do consumo e gross-up do valor efetivamente transferido.
- Token-2022: `solana-program/token-2022/interface/src/extension/transfer_fee/mod.rs`
  - `TransferFee::calculate_fee`: ceil da taxa em basis points, limitada por maximum_fee.
  - `calculate_pre_fee_amount` e `calculate_inverse_fee`: menor valor bruto que produz o líquido solicitado, com arredondamento e cap.
  - `TransferFeeConfig::get_epoch_fee`: escolha entre older/newer fee conforme epoch.

## Regras reproduzidas

1. Transfer fee Token-2022: `ceil(gross × basis_points / 10_000)`, limitada a `maximum_fee`.
2. Gross-up Token-2022: reproduz a inversão oficial, incluindo taxa de 100%, cap e verificação de retorno ao net.
3. Taxa AMM incluída/excluída: denominador `1_000_000_000` e arredondamento para cima, conforme `PoolFeesStruct`.
4. Split AMM: protocolo e referral calculados com arredondamento para baixo; referral é subtraído do protocolo emitido no evento; compounding é calculado sobre a parcela LP e claiming recebe o restante.
5. FeeMode: seis combinações `CollectFeeMode × TradeDirection` reproduzidas da matriz do programa.

## Testes sintéticos

A suíte cobre:
- Transfer fee: ceil, cap, zero, inverse com múltiplos gross válidos, 100%, overflow e entradas inválidas.
- Taxa AMM: arredondamento para cima, valor incluído/excluído, zero e denominador inválido.
- Split: referral separado do protocolo líquido e arredondamentos para baixo.
- FeeMode: as seis combinações do programa, incluindo referral ativo.

Os vetores são inteiros raw e determinísticos; não dependem de rede, banco, relógio ou fixture RAW.

## Limitações explícitas

- Não decodifica bytes de `TransferFeeConfig` ou `TransferFeeAmount`.
- Não escolhe epoch histórico; a função recebe os parâmetros já resolvidos como entrada.
- Não modela a curva de liquidez nem calcula `amount_left` de PartialFill. Apenas fornece as primitivas de taxa usadas pelo caminho parcial.
- Não associa transferências, deltas, vaults, contas de usuário, referral ou instruções.
- Não prova exclusividade de efeitos por operação e não decide `MATCHED`.
- Não cria `SwapObservation`, `SwapClassification` ou `SwapEvidence`.
- Não acessa RPC/Helius, SQLite, checkpoint ou execução on-chain.

## Próxima validação

Executar os 17 testes focais e a suíte completa em clone atualizado; revisar os casos de borda e a equivalência com as fontes fixadas. Depois, implementar decodificação explícita do estado de transfer fee e só então compor as evidências de transferências/deltas em um reconciliador puro.
