"""Collector-side bridge: archive true transport bytes before deriving events.

Legacy adapters without capture support retain their existing behavior, but do
not fabricate CM38 observations. Only the caller holding the current collector
authority can publish, after the async transport has returned.
"""
from smart_money_radar.storage.collector_authority import await_authorized,check_collector
from smart_money_radar.services.rpc_observation_journal import RpcObservationJournal

async def collect_transaction_with_evidence(store,adapter,*,radar,signature,source_id,commitment,legacy,expected_slot=None):
    method=getattr(adapter,"capture_transaction_async",None)
    if not callable(method):
        return await await_authorized(store,radar,legacy)
    capture=await await_authorized(store,radar,lambda:method(signature,commitment=commitment))
    check_collector(store,radar)
    if capture.commitment!=commitment: raise ValueError("RPC commitment mismatch")
    RpcObservationJournal(store).append(radar=radar,signature=signature,source_id=source_id,
        endpoint_host=capture.endpoint_host,raw_payload=capture.raw,observed_at=capture.observed_at,
        available_at=capture.available_at,expected_slot=expected_slot,commitment_requested=commitment)
    return capture.result
