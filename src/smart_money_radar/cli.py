"""Interface de linha de comando do SMR."""

import argparse
import asyncio
import logging
import signal
from collections.abc import Sequence

from smart_money_radar.data_sources.helius import HeliusDataSource
from smart_money_radar.domain.models import Wallet
from smart_money_radar.services.wallet_monitor import WalletMonitor
from smart_money_radar.data_sources.token2022_fee_proof_resolver import (
    resolve_token2022_no_fee_proofs,
)
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
        settings = HeliusSettings.from_environment()
        source = HeliusDataSource(settings)
        if args.command == "check":
            result = source.get_version()
            print(f"Resposta RPC Helius confirmada: Solana {result.get('solana-core', 'versão desconhecida')}.")
            return
        if args.command == "watch":
            _run_monitor(settings, source, args.addresses)
            return
    except (SettingsError, RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from None


def _run_monitor(
    settings: HeliusSettings,
    source: HeliusDataSource,
    addresses: list[str],
) -> None:
    wallets = [Wallet(address=address) for address in addresses]
    event_store = SQLiteEventStore(settings.database_path)
    monitor = WalletMonitor(
        settings, source, event_store,
        token2022_fee_proof_resolver=resolve_token2022_no_fee_proofs,
    )
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
