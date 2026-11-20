"""Interface de linha de comando do SMR."""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import signal
import sqlite3
from collections.abc import Sequence
from dataclasses import asdict
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
    watch_parser.add_argument(
        "--reference-mint", action="append", default=[],
        help="mint de cotação para classificar swaps arquivados; repetível",
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
    evidence.add_argument("--block-sequence", type=int, help="comprova o índice usando o frame do bloco")
    evidence.add_argument("--epoch-schedule", type=Path, help="resposta getEpochSchedule da rede do journal")
    evidence.add_argument("--damm-wallet", help="reconcilia DAMM v2 para esta carteira Solana")
    capture = subparsers.add_parser(
        "geyser-capture", help="captura um fluxo Yellowstone TLS com limites de duração e frames"
    )
    capture.add_argument("database", type=Path)
    capture.add_argument("--target", required=True)
    capture.add_argument("--source", required=True)
    capture.add_argument("--descriptor", type=Path, required=True)
    capture.add_argument("--subscription", type=Path, required=True)
    capture.add_argument("--max-frames", type=int, default=1000)
    capture.add_argument("--timeout", type=int, default=60)
    capture.add_argument("--max-attempts", type=int, default=1)
    sessions = subparsers.add_parser(
        "geyser-sessions", help="lista cobertura e desfecho das sessões Yellowstone arquivadas"
    )
    sessions.add_argument("database", type=Path)
    sessions.add_argument("--source")
    sessions.add_argument("--limit", type=int, default=100)
    verify = subparsers.add_parser(
        "geyser-verify", help="confere os frames arquivados e calcula o SHA-256 da sessão"
    )
    verify.add_argument("database", type=Path)
    verify.add_argument("--source", required=True)
    verify.add_argument("--stream", required=True)
    verify.add_argument("--domain", required=True)
    verify.add_argument("--expected-sha256")
    paper = subparsers.add_parser("paper-replay", help="simula entradas em observações locais")
    paper.add_argument("scenario", type=Path)
    paper.add_argument("--as-of", help="limita o replay de arquivo à disponibilidade até este instante")
    paper.add_argument("--quotes", type=Path, help="arquivo de cotações bid/ask independente")
    paper.add_argument("--archive", type=Path, help="lê swaps concluídos de um banco SQLite local")
    paper.add_argument("--mode", choices=("immediate", "confirmed", "both"), default="both")
    paper.add_argument("--strict-evidence", type=Path, help="JSON de evidências e risco para replay protegido local")
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
        if args.command == "geyser-capture":
            _capture_geyser(args)
            return
        if args.command == "geyser-sessions":
            _list_geyser_sessions(args)
            return
        if args.command == "geyser-verify":
            _verify_geyser_session(args)
            return
        if args.command == "paper-replay":
            _paper_replay(args)
            return
        settings = HeliusSettings.from_environment()
        source = HeliusDataSource(settings)
        if args.command == "check":
            result = source.get_version()
            print(f"Resposta RPC Helius confirmada: Solana {result.get('solana-core', 'versão desconhecida')}.")
            return
        if args.command == "watch":
            _run_monitor(settings, source, args.addresses, reference_mints=args.reference_mint)
            return
    except (OSError, SettingsError, RuntimeError, ValueError, sqlite3.Error) as exc:
        raise SystemExit(str(exc)) from None


def _paper_replay(args: argparse.Namespace) -> None:
    from datetime import datetime, timezone
    from decimal import Decimal, InvalidOperation

    from smart_money_radar.domain.paper_replay import PaperConfig, ReplayTick, compare_paper_reports, replay_paper

    scenario_bytes = args.scenario.read_bytes()
    scenario = json.loads(scenario_bytes, parse_float=Decimal)
    if args.strict_evidence is not None and args.archive is not None:
        raise ValueError("--strict-evidence ainda não suporta --archive")
    if args.archive is None and (args.as_of is not None or args.quotes is not None):
        raise ValueError("--as-of e --quotes exigem --archive")
    as_of = datetime.fromisoformat(args.as_of) if args.as_of is not None else None
    if as_of is not None:
        if as_of.utcoffset() is None:
            raise ValueError("--as-of exige horário com fuso")
        as_of = as_of.astimezone(timezone.utc)

    def decimal(value):
        if isinstance(value, bool):
            raise ValueError("valor decimal não pode ser booleano")
        return Decimal(value)

    try:
        config = PaperConfig(**{key: decimal(value) for key, value in scenario["config"].items()})
        if args.archive is None:
            ticks = [
                ReplayTick(
                    datetime.fromisoformat(row["at"]), decimal(row["price"]), decimal(row["volume"]),
                    row.get("signal", "NONE"), row.get("entry_allowed", False), row.get("halted", False),
                )
                for row in scenario["ticks"]
            ]
            archive_report = None
        else:
            from smart_money_radar.domain.paper_swap_archive import ticks_from_swap_archive

            market = scenario["market"]
            scope = {key: market[key] for key in ("wallet", "program", "base_mint", "quote_mint")}
            if "pool" in market:
                scope["pool"] = market["pool"]
            if (any(not isinstance(value, str) or not value.strip() for value in scope.values())
                    or scope["base_mint"] == scope["quote_mint"]):
                raise ValueError("mercado do replay inválido")
            store = SQLiteEventStore(args.archive, read_only=True)
            try:
                rows = store.list_swap_replay_archive(**scope)
            finally:
                store.close()
            if as_of is not None:
                rows = [row for row in rows if datetime.fromisoformat(row["available_at"]) <= as_of]
            ticks, skipped = ticks_from_swap_archive(
                rows, quote_mint=scope["quote_mint"], min_confidence=decimal(market["min_confidence"]),
            )
            quote_report = None
            if args.quotes is not None:
                from smart_money_radar.domain.paper_quote_archive import ticks_from_quote_archive

                quote_archive = json.loads(args.quotes.read_text(encoding="utf-8"), parse_float=Decimal)
                source = quote_archive["source"]
                if (not isinstance(source, str) or not source.strip()
                        or quote_archive.get("pool") != scope.get("pool")
                        or any(quote_archive[key] != scope[key]
                               for key in ("program", "base_mint", "quote_mint"))):
                    raise ValueError("fonte ou mercado das cotações não corresponde ao cenário")
                ticks, selected_quotes = ticks_from_quote_archive(
                    quote_archive["quotes"], ticks, signal_ttl_seconds=market["signal_ttl_seconds"],
                    as_of=as_of, pool=scope.get("pool"),
                )
                canonical_quotes = json.dumps(
                    selected_quotes, sort_keys=True, separators=(",", ":"), default=str,
                ).encode()
                quote_report = {
                    "source": source, "quotes": len(selected_quotes),
                    "pool_scope": scope.get("pool"),
                    "sha256": hashlib.sha256(canonical_quotes).hexdigest(),
                    "signal_ttl_seconds": market["signal_ttl_seconds"],
                }
            canonical_rows = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
            archive_report = {
                **scope, "ticks": len(ticks), "skipped_operation_ids": skipped,
                "as_of": as_of.isoformat() if as_of is not None else None,
                "receipts_sha256": hashlib.sha256(canonical_rows).hexdigest(),
            }
            if quote_report is not None:
                archive_report["quote_archive"] = quote_report
    except (AttributeError, KeyError, TypeError, InvalidOperation) as exc:
        raise ValueError("arquivo de cenário ou dados do paper-replay inválidos") from exc
    modes = ("immediate", "confirmed") if args.mode == "both" else (args.mode,)
    strict_metadata = None
    if args.strict_evidence is not None:
        from smart_money_radar.domain.paper_entry_risk_policy import EntryRiskLimits, EntryRiskSnapshot
        from smart_money_radar.domain.paper_evidence_replay import replay_with_required_risk
        raw = json.loads(args.strict_evidence.read_text(encoding="utf-8"), parse_float=Decimal)
        limits = EntryRiskLimits(**{k: decimal(v) for k, v in raw["risk_limits"].items()})
        snapshots = {qid: EntryRiskSnapshot(**{
            k: v if k in ("emergency_halt", "evidence_verified") else decimal(v)
            for k, v in values.items()
        }) for qid, values in raw["risk_by_quote"].items()}
        ticks = [ReplayTick(
            datetime.fromisoformat(row["at"]), decimal(row["price"]), decimal(row["volume"]),
            row.get("signal", "NONE"), row.get("entry_allowed", False),
            row.get("halted", False), quote_id=row.get("quote_id"),
        ) for row in scenario["ticks"]]
        strict = replay_with_required_risk(
            ticks, raw["evidence_by_quote"], config=config, expected_pool=raw["pool"],
            risk_limits=limits, risk_by_quote=snapshots,
        )
        results = {mode: strict[mode] for mode in modes}
        strict_metadata = {k: v for k, v in strict.items()
                           if k not in ("immediate", "confirmed", "comparison")}
    else:
        results = {mode: replay_paper(ticks, config=config, mode=mode) for mode in modes}
    report = {mode: asdict(result) for mode, result in results.items()}
    if args.mode == "both":
        report["comparison"] = compare_paper_reports(results["immediate"], results["confirmed"])
        report["comparison"]["scenario_sha256"] = hashlib.sha256(scenario_bytes).hexdigest()
    if strict_metadata is not None:
        report["strict_evidence"] = strict_metadata
    if archive_report is not None:
        report["archive"] = archive_report
    print(json.dumps(report, default=str, ensure_ascii=False))


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

    if args.epoch_schedule is not None and (args.damm_wallet is None or args.block_sequence is None):
        raise ValueError("--epoch-schedule exige --damm-wallet e --block-sequence")
    for sequence in (args.sequence, args.block_sequence):
        if sequence is not None and not 0 <= sequence <= (1 << 63) - 1:
            raise ValueError("sequência fora do intervalo do journal Yellowstone")
    store = SQLiteGeyserRawStore(args.database, read_only=True)
    try:
        receiver = YellowstoneFrameReceiver(
            store, decode, source_id=args.source, stream_id=args.stream, ordering_domain_id=args.domain,
        )
        evidence = receiver.transaction_evidence_at(args.sequence, block_sequence=args.block_sequence)
        if evidence is None:
            raise ValueError("nenhuma transação na sequência informada")
        observation, bundle = evidence.observation, evidence.bundle
        report = {
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
            "provider_reported_finalized": evidence.provider_reported_finalized,
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
        }
        session = store.get_capture_session(observation.source_id, observation.stream_id)
        if session is not None:
            report["capture_session"] = session
        if evidence.block_order is not None:
            report["block_order"] = asdict(evidence.block_order)
        if args.damm_wallet is not None:
            epoch = None
            if args.epoch_schedule is not None:
                from smart_money_radar.data_sources.solana_epoch_schedule import epoch_for_slot

                schedule = args.epoch_schedule.read_bytes()
                epoch = epoch_for_slot(json.loads(schedule), observation.slot)
                report["epoch_schedule"] = {
                    "epoch": epoch, "sha256": hashlib.sha256(schedule).hexdigest(),
                    "provenance": "operator_supplied",
                }
            result = evidence.reconcile_damm_v2(
                monitored_wallet=args.damm_wallet, transaction_epoch=epoch,
            )
            report["damm_v2"] = {
                "status": result.status,
                "operation_count": result.operation_count,
                "reason": result.reason,
                "withheld_fee_status": result.withheld_fee_status,
                "mint_fee_config_status": result.mint_fee_config_status,
            }
        print(json.dumps(report, ensure_ascii=False))
    except DecodeError as exc:
        raise ValueError("frame incompatível com o descriptor Yellowstone") from exc
    finally:
        store.close()


def _list_geyser_sessions(args: argparse.Namespace) -> None:
    from smart_money_radar.storage.geyser_raw_store import SQLiteGeyserRawStore

    store = SQLiteGeyserRawStore(args.database, read_only=True)
    try:
        report = store.list_wire_sessions(source_id=args.source, limit=args.limit)
        print(json.dumps({"sessions": report}, ensure_ascii=False))
    finally:
        store.close()


def _verify_geyser_session(args: argparse.Namespace) -> None:
    from smart_money_radar.storage.geyser_raw_store import SQLiteGeyserRawStore

    expected = args.expected_sha256
    if expected is not None and (len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected)):
        raise ValueError("SHA-256 esperado inválido")
    store = SQLiteGeyserRawStore(args.database, read_only=True)
    try:
        report = store.verify_wire_session(args.source, args.stream, args.domain)
        if expected is not None and report["sha256"] != expected:
            raise ValueError("SHA-256 da sessão Yellowstone diverge do esperado")
        print(json.dumps(report, ensure_ascii=False))
    finally:
        store.close()


def _capture_geyser(args: argparse.Namespace) -> None:
    from google.protobuf.json_format import ParseError
    from google.protobuf.message import DecodeError

    from smart_money_radar.data_sources.yellowstone_grpc import capture_yellowstone_sessions
    from smart_money_radar.storage.geyser_raw_store import SQLiteGeyserRawStore

    subscription = json.loads(args.subscription.read_text(encoding="utf-8"))
    if not isinstance(subscription, dict):
        raise ValueError("a assinatura Yellowstone precisa ser um objeto JSON")
    store = SQLiteGeyserRawStore(args.database)
    try:
        attempts = capture_yellowstone_sessions(
            store, target=args.target, source_id=args.source, descriptor=args.descriptor.read_bytes(),
            subscription=subscription, token=os.environ.get("YELLOWSTONE_TOKEN"),
            max_frames=args.max_frames, timeout=args.timeout, max_attempts=args.max_attempts,
        )
        print(json.dumps({"sessions": [asdict(capture) for capture in attempts]}))
        if not attempts:
            raise ValueError("orçamento de tempo Yellowstone esgotado antes da conexão")
        outcome = attempts[-1].outcome
        if outcome not in {"eof", "frame_limit", "deadline_exceeded"}:
            raise ValueError(f"captura Yellowstone interrompida: {outcome}")
    except ModuleNotFoundError as exc:
        if exc.name != "grpc":
            raise
        raise ValueError("instale o extra smart-money-radar[yellowstone]") from exc
    except (DecodeError, ParseError, TypeError) as exc:
        raise ValueError("descriptor ou assinatura Yellowstone inválidos") from exc
    finally:
        store.close()


def _run_monitor(
    settings: HeliusSettings,
    source: HeliusDataSource,
    addresses: list[str],
    *,
    reference_mints: Sequence[str] = (),
) -> None:
    from smart_money_radar.data_sources.solana_token_transfer_decoder import _decode_base58

    if any(len(mint) > 44 or len(_decode_base58(mint)) != 32 for mint in reference_mints):
        raise ValueError("mint de cotação inválido: esperado endereço Solana em Base58")
    wallets = [Wallet(address=address) for address in addresses]
    event_store = SQLiteEventStore(settings.database_path)
    monitor = WalletMonitor(settings, source, event_store, reference_mints=tuple(dict.fromkeys(reference_mints)))
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
