"""Conservative same-slot account checks for CPMM evidence.

This verifies the supplied RPC envelope and parsed vault identity, not the
Raydium pool-state binary layout or RPC authenticity. Never treat as complete
on-chain pool verification.
"""
from hashlib import sha256
import json

TOKEN_PROGRAMS = frozenset({
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
})


def validate_same_slot_vault_accounts(*, raw_payload: bytes, expected_slot: int,
                                      input_vault: str, output_vault: str,
                                      input_mint: str, output_mint: str,
                                      expected_authority: str,
                                      input_token_program: str,
                                      output_token_program: str):
    """Check getMultipleAccounts(jsonParsed) vaults against expected metadata.

    Caller must independently establish vault addresses and authority from
    authenticated CPMM pool state. RPC result alone is not proof of this.
    """
    if not isinstance(raw_payload, bytes) or not raw_payload:
        raise ValueError("payload RAW inválido")
    if type(expected_slot) is not int or expected_slot < 0:
        raise ValueError("slot esperado inválido")
    addresses = (input_vault, output_vault, input_mint, output_mint, expected_authority)
    if any(not isinstance(x, str) or not x.strip() for x in addresses):
        raise ValueError("identidade de conta ou mint inválida")
    if input_vault == output_vault or input_mint == output_mint:
        raise ValueError("vaults ou mints idênticos")
    if input_token_program not in TOKEN_PROGRAMS or output_token_program not in TOKEN_PROGRAMS:
        raise ValueError("programa SPL não suportado")
    try:
        payload = json.loads(raw_payload)
        result = payload["result"]
        slot = result["context"]["slot"]
        accounts = result["value"]
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError("resposta RPC incompleta") from exc
    if type(slot) is not int or slot != expected_slot:
        raise ValueError("slot RPC divergente")
    if not isinstance(accounts, list) or len(accounts) != 2:
        raise ValueError("esperadas duas contas vault")
    amounts = []
    for account, mint, program in zip(
        accounts, (input_mint, output_mint),
        (input_token_program, output_token_program),
    ):
        if not isinstance(account, dict) or account.get("owner") != program or account.get("executable") is not False:
            raise ValueError("proprietário do programa SPL inválido")
        try:
            data = account["data"]
            parsed = data["parsed"]
            info = parsed["info"]
            if parsed["type"] != "account" or info["mint"] != mint or info["owner"] != expected_authority:
                raise ValueError("identidade mint/authority divergente")
            token_amount = info["tokenAmount"]
            raw = token_amount["amount"]
            decimals = token_amount["decimals"]
        except (KeyError, TypeError) as exc:
            raise ValueError("layout jsonParsed inválido") from exc
        if (not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal()
                or type(decimals) is not int or not 0 <= decimals <= 18):
            raise ValueError("quantidade ou decimals inválidos")
        amounts.append((int(raw), decimals))
    return {
        "slot": slot, "raw_sha256": sha256(raw_payload).hexdigest(),
        "input_reserve_raw": amounts[0][0], "input_decimals": amounts[0][1],
        "output_reserve_raw": amounts[1][0], "output_decimals": amounts[1][1],
        "verification": "VAULT_METADATA_ONLY_POOL_STATE_NOT_VERIFIED",
    }
