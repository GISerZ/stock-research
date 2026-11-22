import json
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

try:
    from evidence_core import empty_fragment, normalize_target, save_packet, validate_packet
except ImportError:
    empty_fragment = normalize_target = save_packet = validate_packet = None


def packet():
    return {
        "schema_version": 1,
        "target": {"code": "600519", "market": "sh"},
        "collected_at": "2026-09-28T16:20:00+08:00",
        "source_results": [{"source": "tencent_quote", "status": "ok"}],
        "observations": [{
            "field": "price", "value": 1243.88, "unit": "CNY/share",
            "period_or_market_time": "2026-09-28T16:14:51+08:00",
            "publication_time": None, "retrieved_time": "2026-09-28T16:20:00+08:00",
            "basis": "unadjusted", "source_name": "腾讯财经",
            "source_url": "https://qt.gtimg.cn/q=sh600519",
            "verification": "market_vendor",
        }],
        "announcements": [],
        "issues": [],
    }


class EvidenceCoreTests(unittest.TestCase):
    def test_normalize_target_accepts_current_codes_and_rejects_legacy_or_wrong_prefix(self):
        self.assertIsNotNone(normalize_target, "evidence_core is missing")
        self.assertEqual(normalize_target("000001"), ("000001", "sz"))
        self.assertEqual(normalize_target("SH600519"), ("600519", "sh"))
        active = {"920982", "430017"}
        self.assertEqual(normalize_target("920982", active_bse_codes=active), ("920982", "bj"))
        self.assertEqual(normalize_target("430017", active_bse_codes=active), ("430017", "bj"))
        for value, codes in [("SH000001", None), ("832982", active), ("920982", None)]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_target(value, active_bse_codes=codes)

    def test_save_packet_versions_without_overwriting_prior_snapshot(self):
        self.assertIsNotNone(save_packet, "evidence_core is missing")
        with tempfile.TemporaryDirectory() as directory:
            first = save_packet(packet(), Path(directory))
            original = first.read_bytes()
            second = save_packet(packet(), Path(directory))
            self.assertEqual(first.name, "2026-09-28-600519.json")
            self.assertEqual(second.name, "2026-09-28-600519-v2.json")
            self.assertEqual(first.read_bytes(), original)
            self.assertEqual(json.loads(second.read_text(encoding="utf-8"))["target"]["code"], "600519")

    def test_validate_packet_rejects_missing_provenance_and_time(self):
        self.assertIsNotNone(validate_packet, "evidence_core is missing")
        for missing in ("source_url", "retrieved_time"):
            bad = packet()
            del bad["observations"][0][missing]
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                validate_packet(bad)

    def test_empty_fragment_has_independent_lists(self):
        self.assertIsNotNone(empty_fragment, "evidence_core is missing")
        left, right = empty_fragment(), empty_fragment()
        left["issues"].append("timeout")
        self.assertEqual(right["issues"], [])


if __name__ == "__main__":
    unittest.main()
