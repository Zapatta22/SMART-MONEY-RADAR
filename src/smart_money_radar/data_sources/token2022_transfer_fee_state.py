"""Strict offline decoder for Token-2022 TransferFee extensions."""
from dataclasses import dataclass

MINT_BASE_LENGTH = 82
TOKEN_ACCOUNT_BASE_LENGTH = 165
ACCOUNT_TYPE_OFFSET = 165
TLV_START = 166
ACCOUNT_TYPE_MINT = 1
ACCOUNT_TYPE_ACCOUNT = 2
EXTENSION_TRANSFER_FEE_CONFIG = 1
EXTENSION_TRANSFER_FEE_AMOUNT = 2
TRANSFER_FEE_CONFIG_LENGTH = 108
TRANSFER_FEE_AMOUNT_LENGTH = 8
MULTISIG_LENGTH = 355
MINT_INITIALIZED_OFFSET = 45
TOKEN_ACCOUNT_STATE_OFFSET = 108
KNOWN_EXTENSION_TYPES = frozenset(range(29))
U64_MAX = (1 << 64) - 1


@dataclass(frozen=True)
class TransferFeeRate:
    epoch: int
    maximum_fee: int
    basis_points: int


@dataclass(frozen=True)
class TransferFeeConfigState:
    withheld_amount: int
    older_transfer_fee: TransferFeeRate
    newer_transfer_fee: TransferFeeRate
    extension_types: tuple[int, ...]

    def fee_for_epoch(self, epoch: int) -> TransferFeeRate:
        _u64(epoch, "epoch")
        return self.newer_transfer_fee if epoch >= self.newer_transfer_fee.epoch else self.older_transfer_fee


@dataclass(frozen=True)
class TransferFeeConfigMutationInstruction:
    kind: str
    transfer_fee_basis_points: int
    maximum_fee: int


@dataclass(frozen=True)
class TransferFeeAmountState:
    withheld_amount: int
    extension_types: tuple[int, ...]


@dataclass(frozen=True)
class TransferFeeAmountDelta:
    pre_withheld_amount: int
    post_withheld_amount: int
    delta: int
    extension_types: tuple[int, ...]


def _u64(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= U64_MAX:
        raise ValueError(f"{field} deve ser u64")
    return value


def _read_u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], "little")


def _validate_coption_tag(data: bytes, offset: int, field: str) -> None:
    tag = data[offset:offset + 4]
    if tag not in (bytes(4), (1).to_bytes(4, "little")):
        raise ValueError(f"tag COption inválida em {field}")


def _validate_mint_base(data: bytes) -> None:
    if len(data) < MINT_BASE_LENGTH or len(data) == MULTISIG_LENGTH:
        raise ValueError("tamanho de base Mint inválido")
    _validate_coption_tag(data, 0, "mint_authority")
    if data[MINT_INITIALIZED_OFFSET] != 1:
        raise ValueError("Mint não inicializado ou estado inválido")
    _validate_coption_tag(data, 46, "freeze_authority")
    if any(data[MINT_BASE_LENGTH:ACCOUNT_TYPE_OFFSET]):
        raise ValueError("padding do mint deve conter somente bytes zero")


def _validate_token_account_base(data: bytes) -> None:
    if len(data) < TOKEN_ACCOUNT_BASE_LENGTH or len(data) == MULTISIG_LENGTH:
        raise ValueError("tamanho de base token account inválido")
    _validate_coption_tag(data, 72, "delegate")
    state = data[TOKEN_ACCOUNT_STATE_OFFSET]
    if state not in (1, 2):
        raise ValueError("token account não inicializada ou estado inválido")
    _validate_coption_tag(data, 109, "is_native")
    _validate_coption_tag(data, 129, "close_authority")


def _read_u64(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 8], "little")


def _read_extensions(data: bytes, expected_account_type: int) -> dict[int, bytes]:
    if len(data) < TLV_START:
        raise ValueError("account data truncado antes do cabeçalho de extensões")
    if data[ACCOUNT_TYPE_OFFSET] != expected_account_type:
        raise ValueError("AccountType incompatível com o tipo esperado")
    extensions: dict[int, bytes] = {}
    offset = TLV_START
    while offset < len(data):
        remaining = data[offset:]
        # Match Token-2022's TLV iterator: a final single byte may be left
        # unused during reallocation, and Uninitialized terminates the list.
        if len(remaining) < 2:
            break
        extension_type = _read_u16(data, offset)
        if extension_type == 0:
            break
        if extension_type not in KNOWN_EXTENSION_TYPES:
            raise ValueError(f"tipo de extensão TLV desconhecido: {extension_type}")
        if len(remaining) < 4:
            raise ValueError("cabeçalho TLV truncado")
        length = _read_u16(data, offset + 2)
        value_start, value_end = offset + 4, offset + 4 + length
        if value_end > len(data):
            raise ValueError("payload TLV truncado")
        if extension_type in extensions:
            raise ValueError(f"extensão TLV duplicada: {extension_type}")
        extensions[extension_type] = data[value_start:value_end]
        offset = value_end
    return extensions


def decode_transfer_fee_config_optional(mint_data: bytes) -> TransferFeeConfigState | None:
    """Decodes a pre-state mint and returns None when TransferFeeConfig is absent."""
    if not isinstance(mint_data, bytes):
        raise TypeError("mint_data deve ser bytes")
    _validate_mint_base(mint_data)
    extensions = _read_extensions(mint_data, ACCOUNT_TYPE_MINT)
    payload = extensions.get(EXTENSION_TRANSFER_FEE_CONFIG)
    if payload is None:
        return None
    if len(payload) != TRANSFER_FEE_CONFIG_LENGTH:
        raise ValueError("tamanho inválido de TransferFeeConfig")
    withheld = _read_u64(payload, 64)

    def read_rate(offset: int) -> TransferFeeRate:
        epoch, maximum_fee = _read_u64(payload, offset), _read_u64(payload, offset + 8)
        basis_points = _read_u16(payload, offset + 16)
        if basis_points > 10_000:
            raise ValueError("transfer_fee_basis_points excede 10000")
        return TransferFeeRate(epoch, maximum_fee, basis_points)

    return TransferFeeConfigState(
        withheld, read_rate(72), read_rate(90), tuple(sorted(extensions))
    )


def decode_transfer_fee_config(mint_data: bytes) -> TransferFeeConfigState:
    state = decode_transfer_fee_config_optional(mint_data)
    if state is None:
        raise ValueError("TransferFeeConfig ausente")
    return state


def decode_transfer_fee_amount(account_data: bytes) -> TransferFeeAmountState:
    if not isinstance(account_data, bytes):
        raise TypeError("account_data deve ser bytes")
    _validate_token_account_base(account_data)
    extensions = _read_extensions(account_data, ACCOUNT_TYPE_ACCOUNT)
    payload = extensions.get(EXTENSION_TRANSFER_FEE_AMOUNT)
    if payload is None:
        raise ValueError("TransferFeeAmount ausente")
    if len(payload) != TRANSFER_FEE_AMOUNT_LENGTH:
        raise ValueError("tamanho inválido de TransferFeeAmount")
    return TransferFeeAmountState(_read_u64(payload, 0), tuple(sorted(extensions)))


def decode_transfer_fee_amount_delta(
    pre_account_data: bytes,
    post_account_data: bytes,
) -> TransferFeeAmountDelta:
    """Decodes the signed pre/post delta of a token account's withheld fee TLV.

    The caller must supply account-data snapshots from the exact transaction
    boundary being audited. This function validates TLV structure, not snapshot
    provenance, slot ordering, or transaction identity.
    """
    before = decode_transfer_fee_amount(pre_account_data)
    after = decode_transfer_fee_amount(post_account_data)
    if before.extension_types != after.extension_types:
        raise ValueError("conjunto de extensões mudou entre snapshots pre/post")
    return TransferFeeAmountDelta(
        pre_withheld_amount=before.withheld_amount,
        post_withheld_amount=after.withheld_amount,
        delta=after.withheld_amount - before.withheld_amount,
        extension_types=before.extension_types,
    )


def decode_transfer_fee_config_mutation_instruction(
    instruction_data: bytes,
) -> TransferFeeConfigMutationInstruction | None:
    """Decodes Token-2022 TransferFeeExtension init/set mutation instructions.

    The outer TokenInstruction discriminator is 26; the extension sub-tags are
    0 (InitializeTransferFeeConfig) and 5 (SetTransferFee). Other sub-tags do
    not mutate the mint's transfer-fee rate configuration.
    """
    if not isinstance(instruction_data, bytes):
        raise TypeError("instruction_data deve ser bytes")
    if not instruction_data or instruction_data[0] != 26:
        return None
    if len(instruction_data) < 2:
        raise ValueError("TransferFeeExtension instruction truncada")
    subtag = instruction_data[1]
    if subtag not in (0, 5):
        return None

    if subtag == 5:
        if len(instruction_data) != 12:
            raise ValueError("SetTransferFee instruction com tamanho inválido")
        basis_points = int.from_bytes(instruction_data[2:4], "little")
        maximum_fee = int.from_bytes(instruction_data[4:12], "little")
    else:
        offset = 2
        for field in ("transfer_fee_config_authority", "withdraw_withheld_authority"):
            if offset + 4 > len(instruction_data):
                raise ValueError(f"COption truncada em {field}")
            tag = int.from_bytes(instruction_data[offset:offset + 4], "little")
            if tag == 0:
                offset += 4
            elif tag == 1:
                if offset + 36 > len(instruction_data):
                    raise ValueError(f"pubkey COption truncada em {field}")
                offset += 36
            else:
                raise ValueError(f"tag COption inválida em {field}")
        if offset + 10 != len(instruction_data):
            raise ValueError("InitializeTransferFeeConfig com tamanho inválido")
        basis_points = int.from_bytes(instruction_data[offset:offset + 2], "little")
        maximum_fee = int.from_bytes(instruction_data[offset + 2:offset + 10], "little")

    if basis_points > 10_000:
        raise ValueError("transfer_fee_basis_points excede 10000")
    return TransferFeeConfigMutationInstruction(
        kind="INITIALIZE_TRANSFER_FEE_CONFIG" if subtag == 0 else "SET_TRANSFER_FEE",
        transfer_fee_basis_points=basis_points,
        maximum_fee=maximum_fee,
    )
