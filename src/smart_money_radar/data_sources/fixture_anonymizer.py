"""Anonimização determinística de endereços pessoais em projeções Solana.

O JSON bruto nunca é alterado. A projeção é um arquivo novo e o mapa reversível
é escrito em caminho separado, com permissões restritas. Program IDs, mints,
assinaturas, slots e contas explicitamente protegidas permanecem intactos.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from smart_money_radar.data_sources.fixture_audit import audit_fixture

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


@dataclass(frozen=True, slots=True)
class AnonymizationResult:
    raw_path: Path
    projection_path: Path
    mapping_path: Path
    manifest_path: Path
    raw_sha256: str
    projection_sha256: str
    replaced_addresses: int


def _is_pubkey(value: Any) -> bool:
    if not isinstance(value, str) or not _B58_RE.fullmatch(value):
        return False
    zeros = len(value) - len(value.lstrip("1"))
    number = 0
    for char in value:
        number = number * 58 + _B58.index(char)
    byte_length = (number.bit_length() + 7) // 8
    return zeros + byte_length == 32


def _b58encode(data: bytes) -> str:
    zeros = len(data) - len(data.lstrip(b"\0"))
    n = int.from_bytes(data, "big")
    out = ""
    while n:
        n, rem = divmod(n, 58)
        out = _B58[rem] + out
    return "1" * zeros + (out or ("" if zeros else "1"))


def _atomic_write(path: Path, data: bytes, *, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        if private:
            os.chmod(tmp_name, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, path)
        if private:
            os.chmod(path, 0o600)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _load_json(path: Path) -> tuple[bytes, dict[str, Any]]:
    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Payload bruto não contém JSON válido.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("result"), dict):
        raise ValueError("Payload deve ser resposta getTransaction com result objeto.")
    transaction = payload["result"].get("transaction")
    if not isinstance(transaction, dict) or not isinstance(transaction.get("message"), dict):
        raise ValueError("Payload getTransaction não contém transaction.message válido.")
    return raw, payload


def _account_key_entries(result: dict[str, Any]) -> list[tuple[dict[str, Any], int, str]]:
    tx = result.get("transaction")
    message = tx.get("message") if isinstance(tx, dict) else None
    keys = message.get("accountKeys") if isinstance(message, dict) else None
    found: list[tuple[dict[str, Any], int, str]] = []
    if isinstance(keys, list):
        for i, item in enumerate(keys):
            if isinstance(item, dict) and isinstance(item.get("pubkey"), str):
                found.append((item, i, item["pubkey"]))
            elif isinstance(item, str):
                # jsonParsed normalmente usa objetos; strings são suportadas também.
                found.append(({"__string_key__": item}, i, item))
    meta = result.get("meta")
    loaded = meta.get("loadedAddresses") if isinstance(meta, dict) else None
    if isinstance(loaded, dict):
        base = len(keys) if isinstance(keys, list) else 0
        writable_count = len(loaded.get("writable", [])) if isinstance(loaded.get("writable"), list) else 0
        for group in ("writable", "readonly"):
            values = loaded.get(group)
            if isinstance(values, list):
                group_offset = 0 if group == "writable" else writable_count
                for offset, address in enumerate(values):
                    if isinstance(address, str):
                        found.append(({"__loaded_group__": group, "__index__": offset}, base + group_offset + offset, address))
    return found


def _collect_sensitive(result: dict[str, Any], protected: set[str]) -> set[str]:
    sensitive: set[str] = set()
    entries = _account_key_entries(result)
    # Signers (incluindo fee payer) são identidades pessoais; não tocar em programas.
    tx = result.get("transaction")
    message = tx.get("message") if isinstance(tx, dict) else None
    header = message.get("header") if isinstance(message, dict) else None
    required_signers = header.get("numRequiredSignatures", 0) if isinstance(header, dict) else 0
    for item, key_index, address in entries:
        if address in protected or not _is_pubkey(address):
            continue
        if item.get("signer") is True or (isinstance(required_signers, int) and not isinstance(required_signers, bool) and key_index < required_signers):
            sensitive.add(address)
    # Donos de token accounts são carteiras pessoais. accountIndex identifica
    # a token account correspondente, que também precisa ser pseudonimizada.
    meta = result.get("meta")
    if isinstance(meta, dict):
        for field in ("preTokenBalances", "postTokenBalances"):
            balances = meta.get(field)
            if not isinstance(balances, list):
                continue
            for balance in balances:
                if not isinstance(balance, dict):
                    continue
                owner = balance.get("owner")
                if isinstance(owner, str) and owner not in protected and _is_pubkey(owner):
                    sensitive.add(owner)
                index = balance.get("accountIndex")
                if isinstance(index, int) and not isinstance(index, bool):
                    for _, key_index, address in entries:
                        if key_index == index and address not in protected and _is_pubkey(address):
                            sensitive.add(address)
    return sensitive


def _walk_replace(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: _walk_replace(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [_walk_replace(item, replacements) for item in value]
    if isinstance(value, str):
        # Campos de endereço são substituídos por igualdade exata. Em logs,
        # apenas tokens Base58 completos são candidatos; nunca substring.
        if value in replacements:
            return replacements[value]
        return re.sub(r"(?<![1-9A-HJ-NP-Za-km-z])[1-9A-HJ-NP-Za-km-z]{32,44}(?![1-9A-HJ-NP-Za-km-z])",
                      lambda match: replacements.get(match.group(0), match.group(0)), value)
    return value


def anonymize_fixture(
    raw_path: str | Path,
    projection_path: str | Path,
    mapping_path: str | Path,
    *,
    key: str | bytes,
    protected_addresses: Iterable[str] = (),
    sensitive_addresses: Iterable[str] = (),
    source_manifest_path: str | Path | None = None,
) -> AnonymizationResult:
    """Cria projeção e mapa separado; falha em colisão de caminhos/sobrescrita.

    `key` deve ser segredo aleatório persistente para manter aliases estáveis
    dentro do conjunto de fixtures. Nunca gravar a chave no pacote.
    """
    raw_path = Path(raw_path).resolve()
    projection_path = Path(projection_path).resolve()
    mapping_path = Path(mapping_path).resolve()
    manifest_path = projection_path.with_suffix(projection_path.suffix + ".manifest.json")
    source_manifest_file = Path(source_manifest_path).resolve() if source_manifest_path else None
    if not isinstance(key, (str, bytes)) or len(key) < 16:
        raise ValueError("A chave de anonimização deve ter pelo menos 16 bytes/caracteres.")
    secret = key.encode("utf-8") if isinstance(key, str) else key
    if len(secret) < 16:
        raise ValueError("A chave de anonimização deve ter pelo menos 16 bytes.")
    if projection_path in (raw_path, mapping_path) or mapping_path == raw_path or manifest_path in (raw_path, mapping_path):
        raise ValueError("Payload bruto, projeção e mapa devem usar caminhos distintos.")
    if projection_path.exists() or mapping_path.exists() or manifest_path.exists():
        raise FileExistsError("Projeção, mapa ou manifesto já existe; nada foi sobrescrito.")
    try:
        mapping_path.relative_to(projection_path.parent)
        mapping_is_inside_projection_dir = True
    except ValueError:
        mapping_is_inside_projection_dir = False
    if mapping_is_inside_projection_dir:
        raise ValueError("Mapa reversível deve ficar fora do diretório das fixtures de teste.")

    raw_bytes, payload = _load_json(raw_path)
    result = payload["result"]
    protected = set(protected_addresses)
    # IDs de programas nunca são pseudonimizados, mesmo se vierem como account keys.
    message = result.get("transaction", {}).get("message", {})
    instructions = message.get("instructions", []) if isinstance(message, dict) else []
    account_entries = _account_key_entries(result)
    index_to_address = {index: address for _, index, address in account_entries}
    all_instruction_sets = [instructions]
    inner = result.get("meta", {}).get("innerInstructions", []) if isinstance(result.get("meta"), dict) else []
    if isinstance(inner, list):
        all_instruction_sets.extend(group.get("instructions", []) for group in inner if isinstance(group, dict))
    for instruction_set in all_instruction_sets:
        for instruction in instruction_set if isinstance(instruction_set, list) else []:
            if not isinstance(instruction, dict):
                continue
            program_id = instruction.get("programId")
            if isinstance(program_id, str):
                protected.add(program_id)
            program_index = instruction.get("programIdIndex")
            if isinstance(program_index, int) and not isinstance(program_index, bool):
                if program_index in index_to_address:
                    protected.add(index_to_address[program_index])
    for group in ("preTokenBalances", "postTokenBalances"):
        balances = result.get("meta", {}).get(group, []) if isinstance(result.get("meta"), dict) else []
        if isinstance(balances, list):
            for balance in balances:
                if isinstance(balance, dict):
                    mint = balance.get("mint")
                    if isinstance(mint, str):
                        protected.add(mint)

    sensitive = _collect_sensitive(result, protected)
    # Endereços pessoais não inferíveis apenas pelo papel RPC (ex.: destinatário
    # de transferência SOL) devem ser identificados na revisão e passados aqui.
    for address in sensitive_addresses:
        if not isinstance(address, str) or not _is_pubkey(address):
            raise ValueError("Cada endereço em sensitive_addresses deve ser uma chave pública Base58 válida.")
        if address not in protected:
            sensitive.add(address)
    sensitive.difference_update(protected)
    replacements: dict[str, str] = {}
    for address in sorted(sensitive):
        digest = hmac.new(secret, address.encode("ascii"), hashlib.sha256).digest()
        replacements[address] = _b58encode(digest)
    projected = _walk_replace(payload, replacements)
    projected_bytes = (json.dumps(projected, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    raw_hash = hashlib.sha256(raw_bytes).hexdigest()
    projection_hash = hashlib.sha256(projected_bytes).hexdigest()

    source_manifest: dict[str, Any] = {}
    if source_manifest_file is not None:
        try:
            source_manifest = json.loads(source_manifest_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Manifesto de origem inválido ou ilegível.") from exc
        audited_source = audit_fixture(source_manifest_file)
        if (not audited_source.valid or source_manifest.get("sha256") != raw_hash
                or source_manifest.get("anonymized") is not False):
            raise ValueError("Manifesto de origem não corresponde ao bruto íntegro/não anonimizado.")

    mapping_doc = {
        "schema": "smr.address-alias-map.v1",
        "warning": "CONFIDENCIAL: contém associação reversível entre endereços e aliases.",
        "aliases": replacements,
    }
    projection_manifest = {
        "schema": "smr.anonymized-fixture.v1",
        "signature": source_manifest.get("signature") or result.get("transaction", {}).get("signatures", [None])[0],
        "slot": result.get("slot"),
        "commitment": source_manifest.get("commitment", "unknown"),
        "raw_sha256": raw_hash,
        "projection_file": projection_path.name,
        "projection_sha256": projection_hash,
        "anonymized": True,
        "replaced_addresses": len(replacements),
        "mapping_file": None,
        "provenance_manifest": source_manifest_file.name if source_manifest_file else None,
        "protected_address_count": len(protected),
    }
    _atomic_write(projection_path, projected_bytes)
    try:
        _atomic_write(manifest_path, (json.dumps(projection_manifest, indent=2) + "\n").encode())
        _atomic_write(mapping_path, (json.dumps(mapping_doc, indent=2) + "\n").encode(), private=True)
    except Exception:
        projection_path.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        mapping_path.unlink(missing_ok=True)
        raise
    return AnonymizationResult(raw_path, projection_path, mapping_path, manifest_path, raw_hash, projection_hash, len(replacements))
