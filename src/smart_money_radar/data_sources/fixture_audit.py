"""Auditoria offline de pares de evidência getTransaction + manifesto."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class FixtureAudit:
    manifest_path: Path
    raw_path: Path
    signature: str
    slot: int
    sha256: str
    valid: bool
    errors: tuple[str, ...]


def audit_fixture(manifest_path: str | Path) -> FixtureAudit:
    """Valida integridade/proveniência sem alterar os arquivos de evidência."""
    manifest_path = Path(manifest_path)
    errors: list[str] = []
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest: Any = json.loads(manifest_bytes)
    except OSError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Manifesto não contém JSON válido.") from exc
    if not isinstance(manifest, dict):
        raise ValueError("Manifesto deve ser um objeto JSON.")

    required = ("signature", "slot", "commitment", "encoding", "raw_file", "sha256", "anonymized")
    missing = [key for key in required if key not in manifest]
    if missing:
        raise ValueError("Manifesto incompleto: " + ", ".join(missing))

    signature = manifest["signature"]
    slot = manifest["slot"]
    raw_name = manifest["raw_file"]
    digest_expected = manifest["sha256"]
    if not isinstance(signature, str) or not signature or any(c.isspace() for c in signature):
        errors.append("assinatura inválida no manifesto")
    if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
        errors.append("slot inválido no manifesto")
    if manifest["commitment"] != "finalized":
        errors.append("commitment não é finalized")
    if manifest["encoding"] != "json":
        errors.append("encoding não é json")
    if manifest["anonymized"] is not False:
        errors.append("arquivo bruto deve ser marcado como não anonimizado")
    if not isinstance(raw_name, str) or Path(raw_name).name != raw_name or raw_name in ("", ".", ".."):
        raise ValueError("raw_file deve ser um nome de arquivo local, sem diretórios")
    raw_path = manifest_path.parent / raw_name
    try:
        raw_bytes = raw_path.read_bytes()
    except OSError:
        errors.append("arquivo bruto ausente ou ilegível")
        raw_bytes = b""

    digest_actual = hashlib.sha256(raw_bytes).hexdigest()
    if not isinstance(digest_expected, str) or digest_actual != digest_expected:
        errors.append("SHA-256 do arquivo bruto não confere")
    if raw_bytes:
        try:
            payload: Any = json.loads(raw_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError):
            errors.append("arquivo bruto não contém JSON válido")
            payload = None
        if isinstance(payload, dict):
            result = payload.get("result")
            if not isinstance(result, dict):
                errors.append("resposta RPC não contém result objeto")
            else:
                if result.get("slot") != slot or isinstance(result.get("slot"), bool):
                    errors.append("slot do payload difere do manifesto")
                tx = result.get("transaction")
                signatures = tx.get("signatures") if isinstance(tx, dict) else None
                if not isinstance(signatures, list) or signature not in signatures:
                    errors.append("assinatura do payload difere do manifesto")
        else:
            errors.append("resposta RPC deve ser um objeto JSON")

    return FixtureAudit(
        manifest_path=manifest_path,
        raw_path=raw_path,
        signature=signature if isinstance(signature, str) else "",
        slot=slot if isinstance(slot, int) and not isinstance(slot, bool) else -1,
        sha256=digest_actual,
        valid=not errors,
        errors=tuple(errors),
    )
