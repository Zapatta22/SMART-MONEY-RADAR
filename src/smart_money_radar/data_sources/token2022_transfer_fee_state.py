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

    def fee_for_epoch(self, epoch: int) -> TransferFeeRate:
        _u64(epoch, "epoch")
        return self.newer_transfer_fee if epoch >= self.newer_transfer_fee.epoch else self.older_transfer_fee


@dataclass(frozen=True)
class TransferFeeAmountState:
    withheld_amount: int


def _u64(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= U64_MAX:
        raise ValueError(f"{field} deve ser u64")
    return value


def _read_u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], "little")


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
        if not any(remaining):
            break
        if len(data) - offset < 4:
            raise ValueError("cabeçalho TLV truncado")
        extension_type = _read_u16(data, offset)
        length = _read_u16(data, offset + 2)
        if extension_type == 0:
            if any(remaining):
                raise ValueError("padding TLV não inicializado contém bytes não zero")
            break
        value_start, value_end = offset + 4, offset + 4 + length
        if value_end > len(data):
            raise ValueError("payload TLV truncado")
        if extension_type in extensions:
            raise ValueError(f"extensão TLV duplicada: {extension_type}")
        extensions[extension_type] = data[value_start:value_end]
        offset = value_end
    return extensions


def decode_transfer_fee_config(mint_data: bytes) -> TransferFeeConfigState:
    if not isinstance(mint_data, bytes):
        raise TypeError("mint_data deve ser bytes")
    if len(mint_data) < MINT_BASE_LENGTH:
        raise ValueError("dados base de mint truncados")
    if any(mint_data[MINT_BASE_LENGTH:ACCOUNT_TYPE_OFFSET]):
        raise ValueError("padding do mint deve conter somente bytes zero")
    payload = _read_extensions(mint_data, ACCOUNT_TYPE_MINT).get(EXTENSION_TRANSFER_FEE_CONFIG)
    if payload is None:
        raise ValueError("TransferFeeConfig ausente")
    if len(payload) != TRANSFER_FEE_CONFIG_LENGTH:
        raise ValueError("tamanho inválido de TransferFeeConfig")
    withheld = _read_u64(payload, 64)

    def read_rate(offset: int) -> TransferFeeRate:
        epoch, maximum_fee = _read_u64(payload, offset), _read_u64(payload, offset + 8)
        basis_points = _read_u16(payload, offset + 16)
        if basis_points > 10_000:
            raise ValueError("transfer_fee_basis_points excede 10000")
        return TransferFeeRate(epoch, maximum_fee, basis_points)

    return TransferFeeConfigState(withheld, read_rate(72), read_rate(90))


def decode_transfer_fee_amount(account_data: bytes) -> TransferFeeAmountState:
    if not isinstance(account_data, bytes):
        raise TypeError("account_data deve ser bytes")
    if len(account_data) < TOKEN_ACCOUNT_BASE_LENGTH:
        raise ValueError("dados base de token account truncados")
    payload = _read_extensions(account_data, ACCOUNT_TYPE_ACCOUNT).get(EXTENSION_TRANSFER_FEE_AMOUNT)
    if payload is None:
        raise ValueError("TransferFeeAmount ausente")
    if len(payload) != TRANSFER_FEE_AMOUNT_LENGTH:
        raise ValueError("tamanho inválido de TransferFeeAmount")
    return TransferFeeAmountState(_read_u64(payload, 0))
