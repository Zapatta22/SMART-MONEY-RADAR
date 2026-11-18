#!/usr/bin/env python3
"""Coleta candidatos Solana com retomada segura e auditoria imediata."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from smart_money_radar.data_sources.fixture_audit import audit_fixture
from smart_money_radar.data_sources.rpc_fixture_collector import RpcFixtureCollector, endpoint_from_environment


def run(candidate_file: Path, output_dir: Path, *, collector: RpcFixtureCollector) -> tuple[int, int]:
    candidates = json.loads(candidate_file.read_text(encoding="utf-8"))
    if not isinstance(candidates, list):
        raise ValueError("O arquivo de candidatos deve conter uma lista JSON.")
    signatures: list[str] = []
    for item in candidates:
        if not isinstance(item, dict) or not isinstance(item.get("signature"), str):
            raise ValueError("Cada candidato deve ser um objeto com campo signature.")
        if item["signature"] not in signatures:
            signatures.append(item["signature"])
    if not signatures:
        raise ValueError("Nenhuma assinatura candidata encontrada.")

    output_dir.mkdir(parents=True, exist_ok=True)
    collected = skipped = 0
    for signature in signatures:
        raw_path = output_dir / f"{signature}.raw.json"
        manifest_path = output_dir / f"{signature}.manifest.json"
        if raw_path.exists() or manifest_path.exists():
            if not raw_path.is_file() or not manifest_path.is_file():
                raise RuntimeError(f"Evidência parcial para {signature}; preservada para inspeção, sem sobrescrita.")
            audit = audit_fixture(manifest_path)
            if not audit.valid or audit.signature != signature:
                raise RuntimeError(f"Evidência existente inválida para {signature}: {'; '.join(audit.errors)}")
            print(f"SKIP {signature} slot={audit.slot} sha256={audit.sha256} (já coletada e auditada)")
            skipped += 1
            continue
        result = collector.collect(signature)
        audit = audit_fixture(output_dir / f"{signature}.manifest.json")
        if not audit.valid:
            raise RuntimeError(f"Auditoria falhou para {signature}: {'; '.join(audit.errors)}")
        print(f"OK {signature} slot={result.slot} sha256={result.sha256} (coletada e auditada)")
        collected += 1
    return collected, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-file", type=Path, default=Path("data/fixtures/candidates/solana_mainnet_candidates.json"))
    parser.add_argument("--output", type=Path, default=Path("data/fixtures/raw"))
    args = parser.parse_args()
    try:
        collector = RpcFixtureCollector(endpoint_from_environment(), args.output)
        collected, skipped = run(args.candidate_file, args.output, collector=collector)
    except Exception as exc:
        print(f"FALHA: {type(exc).__name__}: {exc}")
        return 1
    print(f"CONCLUÍDO: {collected} novas; {skipped} já existentes e auditadas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
