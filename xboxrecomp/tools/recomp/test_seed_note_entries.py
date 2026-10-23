"""
Seed files may hold note-only entries (no "start"): a new port keeps the
donor's XPP/thread seeds as {"fo2_start": ..., "note": ...} until their
address in its own XBE is found. tools.disasm must not seed them and
tools.seed_from_log must not crash merging into such a file.

    python3 tools/recomp/test_seed_note_entries.py
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tools.disasm.__main__ import _load_seed_functions  # noqa: E402
from tools.seed_from_log.__main__ import seeded_starts  # noqa: E402

SEEDS = [
    {"note": "header"},
    {"fo2_start": "0x001320F9", "note": "donor thread seed, not yet matched"},
    {"start": "0x00012340", "note": "a real seed"},
    {"start": "0x00056780", "observed": True, "note": "observed"},
    0x9ABC0,
]


class SeedNoteEntries(unittest.TestCase):
    def test_disasm_skips_note_entries(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "seeds.json")
            with open(path, "w") as f:
                json.dump(SEEDS, f)
            observed = set()
            self.assertEqual(_load_seed_functions(path, observed),
                             [0x12340, 0x56780, 0x9ABC0])
            self.assertEqual(observed, {0x56780})

    def test_seed_from_log_skips_note_entries(self):
        self.assertEqual(seeded_starts(SEEDS), {"0x00012340", "0x00056780"})


if __name__ == "__main__":
    unittest.main()
