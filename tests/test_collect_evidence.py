import json
import socket
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pandas as pd
import requests


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

try:
    import collect_evidence
except ImportError:
    collect_evidence = None


NOW = datetime(2026, 9, 28, 16, 20, tzinfo=timezone(timedelta(hours=8)))


def fragment(source, status):
    return {"source_results": [{"source": source, "status": status,
                                "method": "fixture", "source_url": "https://example.org/"}],
            "observations": [], "announcements": [], "issues": []}


class CollectEvidenceTests(unittest.TestCase):
    def test_network_defaults_bound_provider_requests_and_are_restored(self):
        self.assertIsNotNone(collect_evidence, "collect_evidence is missing")
        self.assertTrue(hasattr(collect_evidence, "_network_defaults"))
        calls = []

        def fake_request(self, method, url, **kwargs):
            calls.append(kwargs.get("timeout"))
            return SimpleNamespace()

        original_socket_timeout = socket.getdefaulttimeout()
        with mock.patch.object(requests.sessions.Session, "request", fake_request):
            with collect_evidence._network_defaults(requests):
                requests.Session().get("https://example.org/")
                requests.Session().get("https://example.org/", timeout=3)
                self.assertEqual(socket.getdefaulttimeout(), 15)
            self.assertIs(requests.sessions.Session.request, fake_request)
        self.assertEqual(socket.getdefaulttimeout(), original_socket_timeout)
        self.assertEqual(calls, [15, 3])

    def test_collect_saves_partial_packet_with_distinct_failures(self):
        self.assertIsNotNone(collect_evidence, "collect_evidence is missing")
        with tempfile.TemporaryDirectory() as temp, \
             mock.patch.object(collect_evidence, "collect_market", return_value=fragment("quote", "ok")), \
             mock.patch.object(collect_evidence, "collect_financial", return_value=fragment("finance", "source_failure")), \
             mock.patch.object(collect_evidence, "collect_disclosures", return_value=fragment("cninfo", "no_record")):
            path, success = collect_evidence.collect("600519", Path(temp), now=NOW,
                http_get=None, http_post=None, ak_api=None, baostock_api=None)
            packet = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(success)
            self.assertEqual(path.parent, Path(temp).resolve() / "research" / "evidence")
            self.assertEqual(packet["target"], {"code": "600519", "market": "sh"})
            self.assertEqual([x["status"] for x in packet["source_results"]],
                             ["ok", "source_failure", "no_record"])
            self.assertTrue(all(x.get("market") == "sh" and x.get("query_range")
                                for x in packet["source_results"]))

    def test_collect_all_failure_saves_diagnostics_and_returns_failure(self):
        self.assertIsNotNone(collect_evidence, "collect_evidence is missing")
        with tempfile.TemporaryDirectory() as temp, \
             mock.patch.object(collect_evidence, "collect_market", side_effect=RuntimeError("market down")), \
             mock.patch.object(collect_evidence, "collect_financial", return_value=fragment("finance", "source_failure")), \
             mock.patch.object(collect_evidence, "collect_disclosures", return_value=fragment("cninfo", "source_failure")):
            path, success = collect_evidence.collect("000001", Path(temp), now=NOW,
                http_get=None, http_post=None, ak_api=None, baostock_api=None)
            packet = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(success)
            self.assertTrue(path.exists())
            self.assertEqual(len(packet["source_results"]), 3)
            self.assertIn("market down", " ".join(packet["issues"]))

    def test_bse_must_exist_in_current_list(self):
        self.assertIsNotNone(collect_evidence, "collect_evidence is missing")
        directory = SimpleNamespace(stock_info_bj_name_code=lambda: pd.DataFrame(
            {"证券代码": ["920982", "430017"]}))
        with tempfile.TemporaryDirectory() as temp, \
             mock.patch.object(collect_evidence, "collect_market", return_value=fragment("quote", "ok")), \
             mock.patch.object(collect_evidence, "collect_financial", return_value=fragment("finance", "no_record")), \
             mock.patch.object(collect_evidence, "collect_disclosures", return_value=fragment("cninfo", "no_record")):
            with self.assertRaises(ValueError):
                collect_evidence.collect("832982", Path(temp), now=NOW,
                    http_get=None, http_post=None, ak_api=directory, baostock_api=None)
            path, success = collect_evidence.collect("920982", Path(temp), now=NOW,
                http_get=None, http_post=None, ak_api=directory, baostock_api=None)
            self.assertTrue(success)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["target"]["market"], "bj")

    def test_main_versions_same_day_packet(self):
        self.assertIsNotNone(collect_evidence, "collect_evidence is missing")
        fake_modules = {"akshare": SimpleNamespace(), "baostock": SimpleNamespace(),
                        "requests": requests}
        with tempfile.TemporaryDirectory() as temp, \
             mock.patch.dict(sys.modules, fake_modules), \
             mock.patch.object(collect_evidence, "collect_market", return_value=fragment("quote", "ok")), \
             mock.patch.object(collect_evidence, "collect_financial", return_value=fragment("finance", "no_record")), \
             mock.patch.object(collect_evidence, "collect_disclosures", return_value=fragment("cninfo", "no_record")):
            arguments = ["--code", "600519", "--output-dir", temp]
            self.assertEqual(collect_evidence.main(arguments), 0)
            self.assertEqual(collect_evidence.main(arguments), 0)
            files = list((Path(temp) / "research" / "evidence").glob("*.json"))
            self.assertEqual(len(files), 2)
            self.assertEqual(len({file.name for file in files}), 2)


if __name__ == "__main__":
    unittest.main()
