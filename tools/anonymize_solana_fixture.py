#!/usr/bin/env python3
"""Cria projeção anonimizada de fixture Solana sem alterar o payload bruto."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from smart_money_radar.data_sources.fixture_anonymizer import anonymize_fixture


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path, help="JSON bruto original")
    parser.add_argument("projection", type=Path, help="JSON anonimizado de saída")
    parser.add_argument("mapping", type=Path, help="Mapa reversível CONFIDENCIAL fora do diretório de fixtures")
    parser.add_argument("--manifest", type=Path, help="Manifesto de coleta original")
    parser.add_argument("--protect", action="append", default=[], help="Endereço público de programa/pool/vault a preservar; repetível")
    parser.add_argument("--anonymize", action="append", default=[], help="Endereço pessoal revisado a pseudonimizar; repetível (ex.: destinatário SOL)")
    parser.add_argument("--key-env", default="SMR_FIXTURE_ANONYMIZATION_KEY", help="Variável de ambiente com segredo >=16 bytes")
    args = parser.parse_args()
    key = os.environ.get(args.key_env, "")
    if not key:
        parser.error(f"Defina {args.key_env} com um segredo aleatório de pelo menos 16 bytes.")
    result = anonymize_fixture(args.raw, args.projection, args.mapping, key=key,
        protected_addresses=args.protect, sensitive_addresses=args.anonymize,
        source_manifest_path=args.manifest)
    print(json.dumps({"projection": str(result.projection_path), "manifest": str(result.manifest_path),
        "mapping": str(result.mapping_path), "raw_sha256": result.raw_sha256,
        "projection_sha256": result.projection_sha256, "replaced_addresses": result.replaced_addresses}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
