"""Interface de linha de comando do SMR."""

import argparse
import asyncio
import json
import logging
import signal
import sqlite3
from collections.abc import Sequence
from pathlib import Path

from smart_money_radar.data_sources.helius import HeliusDataSource
from smart_money_radar.domain.models import Wallet
from smart_money_radar.services.wallet_monitor import WalletMonitor
from smart_money_radar.settings import HeliusSettings, SettingsError
from smart_money_radar.storage.event_store import SQLiteEventStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smr",
        description="Monitoramento local, somente leitura, de carteiras públicas Solana.",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("check", help="verifica uma resposta do endpoint Helius RPC")
    watch_parser = subparsers.add_parser(
        "watch", help="monitora endereços públicos via WebSocket"
    )
    watch_parser.add_argument(
        "addresses",
        nargs="+",
        metavar="PUBLIC_ADDRESS",
        help="um ou mais endereços públicos Solana",
    )
    evidence = subparsers.add_parser(
        "geyser-evidence", help="inspeciona uma transação no journal Yellowstone local"
    )
    evidence.add_argument("database", type=Path)
    evidence.add_argument("--descriptor", type=Path, required=True)
    evidence.add_argument("--source", required=True)
    evidence.add_argument("--stream", required=True)
    evidence.add_argument("--domain", required=True)
    evidence.add_argument("--sequence", type=int, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Executa a ação solicitada; a execução sem comando não acessa a rede."""
    args = _parser().parse_args(argv)
    if args.command is None:
        print("SMART MONEY RADAR (SMR)")
        print("Modo somente leitura. Nenhuma conexão de rede será iniciada sem comando.")
        print("Use 'smr check' ou 'smr watch PUBLIC_ADDRESS' após habilitar o acesso.")
        return

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        if args.command == "geyser-evidence":
            _inspect_geyser_evidence(args)
            return
        settings = HeliusSettings.from_environment()
        source = HeliusDataSource(settings)
        if args.command == "check":
            result = source.get_version()
            print(f"Resposta RPC Helius confirmada: Solana {result.get('solana-core', 'versão desconhecida')}.")
            return
        if args.command == "watch":
            _run_monitor(settings, source, args.addresses)
            return
    except (OSError, SettingsError, RuntimeError, ValueError, sqlite3.Error) as exc:
        raise SystemExit(str(exc)) from None


def _inspect_geyser_evidence(args: argparse.Namespace) -> None:
    from google.protobuf.message import DecodeError

    from smart_money_radar.data_sources.yellowstone_receiver import (
        YellowstoneFrameReceiver,
        load_yellowstone_decoder,
    )
    from smart_money_radar.storage.geyser_raw_store import SQLiteGeyserRawStore

    try:
        decode = load_yellowstone_decoder(args.descriptor.read_bytes())
    except (DecodeError, TypeError) as exc:
        raise ValueError("descriptor Yellowstone inválido") from exc

    if not 0 <= args.sequence <= (1 << 63) - 1:
        raise ValueError("sequência fora do intervalo do journal Yellowstone")
    store = SQLiteGeyserRawStore(args.database, read_only=True)
    try:
        receiver = YellowstoneFrameReceiver(
            store, decode, source_id=args.source, stream_id=args.stream, ordering_domain_id=args.domain,
        )
        evidence = receiver.transaction_evidence_at(args.sequence)
        if evidence is None:
            raise ValueError("nenhuma transação na sequência informada")
        observation, bundle = evidence.observation, evidence.bundle
        print(json.dumps({
            "source": observation.source_id,
            "stream": observation.stream_id,
            "ordering_domain": observation.ordering_domain_id,
            "sequence": observation.stream_sequence,
            "slot": observation.slot,
            "signature": observation.transaction_signature,
            "bank_id": observation.bank_id,
            "wire_sha256": observation.payload_sha256,
            "projection_sha256": bundle.identity.payload_sha256,
            "structurally_complete": bundle.structurally_complete,
            "instruction_issues": bundle.instruction_inventory.issues,
            "transfer_count": len(bundle.transfers),
            "balance_delta_count": len(bundle.balance_deltas.deltas),
            "balance_issues": [issue.code for issue in bundle.balance_deltas.issues],
            "account_transitions": [
                {
                    "account": transition.pubkey,
                    "pre_sequence": transition.pre_state.stream_sequence,
                    "post_sequence": transition.post_state.stream_sequence,
                    "provenance": transition.evidence_classification,
                }
                for transition in evidence.account_transitions
            ],
        }, ensure_ascii=False))
    except DecodeError as exc:
        raise ValueError("frame incompatível com o descriptor Yellowstone") from exc
    finally:
        store.close()


def _run_monitor(
    settings: HeliusSettings,
    source: HeliusDataSource,
    addresses: list[str],
) -> None:
    wallets = [Wallet(address=address) for address in addresses]
    event_store = SQLiteEventStore(settings.database_path)
    monitor = WalletMonitor(settings, source, event_store)
    stop_event = asyncio.Event()
    loop = asyncio.new_event_loop()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_name, stop_event.set)
        except (NotImplementedError, RuntimeError):
            pass
    try:
        loop.run_until_complete(monitor.run_forever(wallets, stop_event))
    except KeyboardInterrupt:
        stop_event.set()
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
            # HeliusDataSource usa asyncio.to_thread para RPC; aguardar a
            # finalização do executor evita threads sobreviventes no shutdown.
            loop.run_until_complete(loop.shutdown_default_executor())
        finally:
            try:
                event_store.close()
            finally:
                loop.close()
