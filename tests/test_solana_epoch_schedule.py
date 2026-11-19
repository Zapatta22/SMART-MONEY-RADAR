import unittest

from smart_money_radar.data_sources.solana_epoch_schedule import epoch_for_slot


class EpochScheduleTests(unittest.TestCase):
    def test_warmup_and_normal_epoch_boundaries(self):
        schedule = {"slotsPerEpoch": 432000, "firstNormalEpoch": 14,
                    "firstNormalSlot": 524256, "warmup": True}
        for slot, expected in (
            (0, 0), (31, 0), (32, 1), (95, 1), (96, 2), (524255, 13),
            (524256, 14), (956255, 14), (956256, 15),
        ):
            with self.subTest(slot=slot):
                self.assertEqual(epoch_for_slot({"result": schedule}, slot), expected)

    def test_without_warmup_and_inconsistent_schedule(self):
        schedule = {"slotsPerEpoch": 64, "firstNormalEpoch": 0, "firstNormalSlot": 0, "warmup": False}
        self.assertEqual(epoch_for_slot(schedule, 128), 2)
        with self.assertRaisesRegex(ValueError, "inconsistentes"):
            epoch_for_slot({**schedule, "firstNormalSlot": 32}, 128)
        with self.assertRaisesRegex(ValueError, "inválido"):
            epoch_for_slot(schedule, True)
