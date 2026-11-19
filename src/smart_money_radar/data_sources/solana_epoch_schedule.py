"""Derive a Solana epoch from an archived getEpochSchedule response."""


def epoch_for_slot(response: dict, slot: int) -> int:
    if not isinstance(response, dict) or type(slot) is not int or not 0 <= slot < 2**64:
        raise ValueError("resposta de epoch ou slot inválido")
    schedule = response.get("result", response)
    if not isinstance(schedule, dict):
        raise ValueError("getEpochSchedule sem resultado")
    slots, first_epoch, first_slot = (
        schedule.get(key) for key in ("slotsPerEpoch", "firstNormalEpoch", "firstNormalSlot")
    )
    warmup = schedule.get("warmup")
    if (any(type(value) is not int or not 0 <= value < 2**64
            for value in (slots, first_epoch, first_slot))
            or slots < 32 or type(warmup) is not bool):
        raise ValueError("parâmetros de getEpochSchedule inválidos")
    expected_epoch = (slots - 1).bit_length() - 5 if warmup else 0
    expected_slot = 32 * ((1 << expected_epoch) - 1)
    if (first_epoch, first_slot) != (expected_epoch, expected_slot):
        raise ValueError("limites de warmup do epoch são inconsistentes")
    if slot < first_slot:
        return (slot + 32).bit_length() - 6
    return first_epoch + (slot - first_slot) // slots
