"""Offline Glassnode harness. No network and no API key."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

import scripts.glassnode_local_harness as harness
from quant.data import glassnode_response
from quant.data.glassnode_response import (
    RequestIdentity,
    SavedCopy,
    compare_copies,
    load_saved_copy,
    parse_response,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "glassnode"
WINDOW = {"since": 1577836800, "until": 1579046400}


def _identity(**overrides) -> RequestIdentity:
    base = dict(metric_path="market/price_usd_close", asset="BTC", interval="24h", **WINDOW)
    base.update(overrides)
    return RequestIdentity(**base)


def _copy(body: bytes, *, headers=None, status=200, identity=None, error_ok=False) -> SavedCopy:
    parsed = parse_response(status=status, headers=headers or {"content-type": "application/json"}, body=body)
    return SavedCopy(
        request=identity or _identity(),
        parsed=parsed,
        captured_at=None,
        directory=Path("."),
    )


class TestSuite:
    def test_suite_passes_on_committed_fixtures(self):
        report = harness.run_suite(FIXTURE_ROOT)
        failed = [step for step in report.results if step.status == "FAIL"]
        assert failed == []
        ids = [step.step for step in report.results]
        assert "price_usd_close_btc_24h" in ids
        assert "sopr_btc_24h" in ids
        assert "mvrv_btc_24h" in ids
        assert "active_count_btc_24h" in ids
        assert "transfers_volume_to_exchanges_sum_btc_24h" in ids
        assert "hash_rate_mean_btc_24h" in ids
        assert "notacoin_price_usd_close" in ids
        assert "empty_json_list" in ids
        assert "pagination" in ids
        assert "rate_limit" in ids
        assert "interval" in ids
        assert "sleeve_factors" in ids
        assert "revision" in ids

    def test_sleeve_note_matches_the_chosen_rule(self):
        note = inspect.getsource(harness)
        for sentence in harness.SLEEVE_FACTOR_RULE:
            assert sentence in note
        contract = json.loads(
            (FIXTURE_ROOT / "contracts" / "sleeve_factors.json").read_text(encoding="utf-8")
        )
        assert tuple(contract["rule"]) == harness.SLEEVE_FACTOR_RULE
        covers = [item["covers_2021_to_mid_2024"] for item in contract["series"]]
        assert covers == [True, False, False]

    def test_store_proposal_is_latest_only_until_confirmed(self):
        note = inspect.getsource(harness)
        expected = (
            "A stored point keeps the latest value for now, and this is a proposal until Alfred confirms.",
            "Keeping a second stored value is not the point-in-time series. Point-in-time is a different Glassnode series.",
        )
        assert harness.STORE_VALUE_PROPOSAL == expected
        for sentence in expected:
            assert sentence in note
        assert harness.SLEEVE_FACTOR_RULE[0] == (
            "Point-in-time BTC exchange netflow is factor one. BTC 60/2.25 stays factor two."
        )

    def test_equal_coverage_fails_closed(self, tmp_path):
        src = FIXTURE_ROOT / "contracts" / "sleeve_factors.json"
        dest_dir = tmp_path / "contracts"
        dest_dir.mkdir()
        doc = json.loads(src.read_text(encoding="utf-8"))
        for item in doc["series"]:
            item["covers_2021_to_mid_2024"] = True
        (dest_dir / "sleeve_factors.json").write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(AssertionError, match="equally backtestable"):
            harness._check_sleeve_factors(
                tmp_path, {"contract": "contracts/sleeve_factors.json"}
            )

    def test_missing_manifest_fails_closed(self, tmp_path):
        report = harness.run_suite(tmp_path)
        assert report.failed
        assert report.results[0].step == "manifest"

    def test_missing_fixture_fails_closed(self, tmp_path):
        manifest = {
            "cases": [
                {
                    "id": "gone",
                    "type": "response",
                    "path": "responses/gone",
                    "expect": {
                        "status": 200,
                        "metric_path": "market/price_usd_close",
                        "asset": "BTC",
                        "interval": "24h",
                        **WINDOW,
                    },
                }
            ]
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        report = harness.run_suite(tmp_path)
        assert report.failed
        gone = next(step for step in report.results if step.step == "gone")
        assert gone.status == "FAIL"
        assert "missing" in gone.detail

    def test_invented_later_directory_fails(self, tmp_path):
        (tmp_path / "later").mkdir()
        (tmp_path / "manifest.json").write_text('{"cases": []}', encoding="utf-8")
        report = harness.run_suite(tmp_path)
        assert report.failed
        assert report.results[0].step == "revision"

    def test_suite_source_does_not_call_the_api(self):
        src = inspect.getsource(glassnode_response) + inspect.getsource(harness)
        assert "import requests" not in src
        assert "urlopen" not in src
        assert "os.getenv" not in src
        assert "os.environ" not in src


class TestParser:
    def test_keeps_observed_price_literals(self):
        copy = load_saved_copy(FIXTURE_ROOT / "responses" / "price_usd_close_btc_24h")
        assert copy.parsed.points[0].v == "7199.66110087"
        assert copy.parsed.points[-1].v == "8827.76442606"
        assert copy.parsed.points[0].t == 1577836800
        assert copy.parsed.points[-1].t == 1578960000
        assert len(copy.parsed.points) == 14

    def test_keeps_observed_sopr_literals(self):
        copy = load_saved_copy(FIXTURE_ROOT / "responses" / "sopr_btc_24h")
        assert copy.parsed.points[0].v == "0.9978004158377769"
        assert copy.parsed.points[-1].v == "1.0228497570844635"

    def test_plain_text_400_is_not_json(self):
        copy = load_saved_copy(FIXTURE_ROOT / "responses" / "notacoin_price_usd_close")
        assert copy.parsed.status == 400
        assert copy.parsed.content_type == "text/plain"
        assert copy.parsed.points is None
        assert copy.parsed.error_text.startswith("parameter a=NOTACOIN is invalid, allowed values=[")

    def test_text_plain_json_looking_body_stays_text(self):
        parsed = parse_response(
            status=400,
            headers={"Content-Type": "text/plain; charset=utf-8"},
            body=b"[]",
        )
        assert parsed.points is None
        assert parsed.content_type == "text/plain"
        assert parsed.error_text == "[]"

    def test_empty_list(self):
        copy = load_saved_copy(FIXTURE_ROOT / "responses" / "empty_json_list")
        assert copy.parsed.points == ()
        assert copy.parsed.is_json_array

    def test_rate_limit_headers(self):
        parsed = parse_response(
            status=200,
            headers={
                "content-type": "application/json",
                "X-Rate-Limit-Limit": "600",
                "X-Rate-Limit-Remaining": "10",
                "X-Rate-Limit-Reset": "20",
            },
            body=b'[{"t":1577836800,"v":1}]',
        )
        assert parsed.rate_limit.limit == "600"
        assert parsed.rate_limit.remaining == "10"
        assert parsed.rate_limit.reset == "20"

    def test_object_body_is_not_a_point_list(self):
        parsed = parse_response(
            status=200,
            headers={"content-type": "application/json"},
            body=b'{"next":"cursor","data":[]}',
        )
        assert parsed.points is None
        assert parsed.is_json_array is False
        assert "next" in parsed.object_keys


class TestRevision:
    def test_planted_value_change_is_visible(self):
        """The delta below is planted in this test. Glassnode did not return it."""
        earlier = _copy(b'[{"t":1577836800,"v":1.5},{"t":1577923200,"v":2}]')
        later = _copy(b'[{"t":1577836800,"v":1.5},{"t":1577923200,"v":2.25}]')
        diff = compare_copies(earlier, later)
        assert diff.value_revision
        assert len(diff.value_changes) == 1
        change = diff.value_changes[0]
        assert change.t == 1577923200
        assert change.earlier_v == "2"
        assert change.later_v == "2.25"

    def test_transport_headers_may_change(self):
        body = b'[{"t":1577836800,"v":1.5}]'
        earlier = _copy(body, headers={
            "content-type": "application/json",
            "x-rate-limit-limit": "600",
            "x-rate-limit-remaining": "10",
            "x-rate-limit-reset": "20",
        })
        later = _copy(body, headers={
            "content-type": "application/json",
            "x-rate-limit-limit": "600",
            "x-rate-limit-remaining": "9",
            "x-rate-limit-reset": "18",
        })
        diff = compare_copies(earlier, later)
        assert diff.value_revision is False
        assert [name for name, _, _ in diff.transport_changes] == [
            "x-rate-limit-remaining",
            "x-rate-limit-reset",
        ]
        assert diff.quota_changes == ()
        assert harness._compare_failed(diff) is False

    def test_different_request_is_not_a_revision(self):
        """ETH here is only a second identity. No ETH body was captured."""
        body = b'[{"t":1577836800,"v":1}]'
        earlier = _copy(body, identity=_identity(asset="BTC"))
        later = _copy(body, identity=_identity(asset="ETH"))
        diff = compare_copies(earlier, later)
        assert diff.request_mismatch
        assert diff.value_changes == ()
        assert harness._compare_failed(diff)

    def test_error_body_change_is_visible(self):
        earlier = _copy(b"parameter a=NOTACOIN is invalid, allowed values=[", status=400, headers={"content-type": "text/plain"})
        later = _copy(b"parameter a=OTHER is invalid, allowed values=[", status=400, headers={"content-type": "text/plain"})
        diff = compare_copies(earlier, later)
        assert diff.value_revision
        assert harness._compare_failed(diff)

    def test_missing_later_copy_fails_closed(self, tmp_path):
        earlier = tmp_path / "earlier" / "price"
        earlier.mkdir(parents=True)
        src = FIXTURE_ROOT / "responses" / "price_usd_close_btc_24h"
        for name in ("request.json", "response.meta.json", "response.body"):
            (earlier / name).write_bytes((src / name).read_bytes())
        (tmp_path / "later").mkdir()
        report = harness.compare_saved_dirs(tmp_path / "earlier", tmp_path / "later")
        assert report.failed
        assert "missing" in report.results[0].detail

    def test_corpus_does_not_record_a_revision(self):
        assert not (FIXTURE_ROOT / "later").exists()
        manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
        assert all("later" not in case for case in manifest["cases"])


def test_cli_suite_exit_code():
    assert harness.main(["--suite", "--json"]) == 0


def test_cli_requires_a_mode():
    with pytest.raises(SystemExit) as exc:
        harness.main([])
    assert exc.value.code == 2
