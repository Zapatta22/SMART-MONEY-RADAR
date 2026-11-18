# Fixture mainnet — Raydium CPMM em rota multi-venue

## Proveniência e escopo

- Slot: `388739013`; versão RPC: `0`; commitment: `finalized`; `meta.err=null`.
- A transação foi obtida por `getTransaction` no RPC público Solana mainnet.
- Assinatura, hash SHA-256 do payload bruto e hash da projeção estão no manifesto adjacente à fixture.
- O arquivo de teste é uma projeção mínima anonimizada: preserva a ordem de todas as 21 instruções internas e seus `stackHeight`, as contas/bytes das transferências relevantes, o swap CPMM, a tabela de endereços carregados e os quatro snapshots pre/post necessários à reconciliação. Instruções não relevantes mantêm apenas programa e altura de pilha para não alterar os caminhos CPI.
- Vinte endereços de carteiras/contas foram pseudonimizados. Program IDs e mints foram preservados. O payload bruto e o mapa reversível não fazem parte do repositório.

## Operação CPMM

- Instrução externa que contém a rota: índice `2`.
- Raydium CPMM: CPI no índice interno `14`, `stackHeight=2`, caminho CPI `(3,)`.
- Transferência de entrada: CPI interno `15`, `stackHeight=3`; `4,484,029,903` unidades brutas, mint de entrada com 6 casas decimais.
- Transferência de saída: CPI interno `16`, `stackHeight=3`; `165,074,030` unidades brutas, mint de saída com 8 casas decimais.
- O input codificado na instrução CPMM contém `minimum_amount_out=0`; isso não é usado como output efetivo. O valor observado vem da transferência SPL decodificada.

## Reconciliação por conta

| Conta | Delta pre/post | Fluxo decodificado | Resultado |
|---|---:|---:|---|
| Token account de entrada da carteira | 0 | crédito e débito de 4,484,029,903 | reconciliado |
| Token account de saída da carteira | +74,030 | crédito de 165,074,030 e envio posterior de 165,000,000 | reconciliado |
| Vault de entrada | +4,484,029,903 | crédito de 4,484,029,903 | reconciliado |
| Vault de saída | -165,074,030 | débito de 165,074,030 | reconciliado |

O saldo líquido zero da conta de entrada não é tratado como ausência de atividade: todas as transferências que tocaram essa conta foram somadas e coincidem com o delta pre/post. A conta de saída também reconcilia mesmo após encaminhar parte do crédito a outra conta. Não há divisão arbitrária de deltas.

## Resultado esperado do SMR

- Uma operação CPMM decodificada, identificada por outer index + CPI path.
- Reconciliação `MATCHED`, com input `4484.029903` e output `1.65074030`.
- Um bundle de domínio, com classificação `UNKNOWN` quando nenhum mint de referência é configurado.
- A classificação passa a `BUY` ou `SELL` somente quando o respectivo mint de entrada ou saída é explicitamente configurado como referência. Isso não prova que qualquer um desses mints seja stablecoin.
- Esta fixture é evidência de reconciliação econômica do swap CPMM dentro de uma rota multi-venue. Não é uma avaliação de segurança/qualidade do token nem autorização para execução financeira.
