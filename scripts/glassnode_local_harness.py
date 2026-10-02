"""Offline Glassnode golden harness.

Runs against saved response copies. It does not call the Glassnode HTTP API
and it does not read an API key. Live refreshes of those copies stay on a
machine outside CI.

  python scripts/glassnode_local_harness.py --suite
  python scripts/glassnode_local_harness.py --suite --json
  python scripts/glassnode_local_harness.py --compare earlier_dir later_dir

``--suite`` reads ``tests/fixtures/glassnode``. A missing manifest or a missing
file listed by a case is a failure. ``--compare`` walks the immediate
subdirectories of ``earlier_dir`` and requires the same directory name under
``later_dir``. Exit status is 1 when a file is missing, the request identity
differs, the HTTP status or content type differs, or any timestamp or value
differs. Rate-limit remaining and reset may differ; those lines are printed
and do not fail the compare.

The committed fixtures are a shape contract. Middles of the price and SOPR
series, and every value of the other four metrics, are synthetic fillers.
They are not the 2026-10-03 bodies. Point ``--compare`` at the copies kept
outside the repo when a later fetch of the same window should be checked.
No revision has been observed. This script does not invent one.

Sleeve factor note. The research room named the child before any result. The
three series are not the same backtest. Only point-in-time BTC exchange
netflow covers 2021 to mid-2024. The child below is what the application will
store and read. It is not a number for a person to apply by hand.

- The raw point-in-time BTC exchange netflow series (transactions/transfers_volume_exchanges_net_pit) has no exact zeros in the saved copy from 11 Dec 2019 through 1 Oct 2026 (2487 days, 0 nulls, smallest absolute value about 2.56). The 2021-07-01 to 2024-06-30 window is 1096 days and also has no exact zero. A non-zero gate on the raw series never turns the sleeve off, so it is not the child.
- The named series, chosen before a result: 1 when that point-in-time value is below zero, and 0 otherwise. No other cut. The 0 must be stored. Dropping zero days is not allowed.
- That 0/1 column is factor one. BTC 60/2.25 stays factor two. On a two-factor FILTER the first factor is the gate and the second is the direction. The 0/1 column has to be first if it is meant to turn the sleeve on and off. Put second, the sleeve's direction is thrown away. The gate indicator is an SMA with window 1, so a stored 0 stays off and a 1 stays on. A wider window or a Bollinger is not this series.
- In the saved copy the 0/1 column is 0 on 702 days and 1 on 1785 days. That is a count of the named rule, not a backtest result.
- The signal threshold on the SMA (window 1) of the 0/1 outflow column has to sit strictly between 0 and 1. Any value in that open range leaves a stored 0 off and a stored 1 on, so the threshold is not a search and do not pick or recommend a specific number inside the range. The sleeve's 2.25 is not the gate's threshold. A threshold of 2.25 would leave the gate off every day, because a 1 is never above 2.25.
- SOPR and MVRV z-score stay a from-July-2025 check only.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quant.data.glassnode_response import (
    RevisionReport,
    SavedCopy,
    compare_copies,
    load_saved_copy,
)

logger = logging.getLogger(__name__)

DEFAULT_FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "glassnode"

# Chosen before any run. The suite fails if the contract file drifts from this.
SLEEVE_FACTOR_RULE = (
    (
        "The raw point-in-time BTC exchange netflow series "
        "(transactions/transfers_volume_exchanges_net_pit) has no exact zeros in the saved copy "
        "from 11 Dec 2019 through 1 Oct 2026 (2487 days, 0 nulls, smallest absolute value about 2.56). "
        "The 2021-07-01 to 2024-06-30 window is 1096 days and also has no exact zero. "
        "A non-zero gate on the raw series never turns the sleeve off, so it is not the child."
    ),
    (
        "The named series, chosen before a result: 1 when that point-in-time value is below zero, "
        "and 0 otherwise. No other cut. The 0 must be stored. Dropping zero days is not allowed."
    ),
    (
        "That 0/1 column is factor one. BTC 60/2.25 stays factor two. "
        "On a two-factor FILTER the first factor is the gate and the second is the direction. "
        "The 0/1 column has to be first if it is meant to turn the sleeve on and off. "
        "Put second, the sleeve's direction is thrown away. "
        "The gate indicator is an SMA with window 1, so a stored 0 stays off and a 1 stays on. "
        "A wider window or a Bollinger is not this series."
    ),
    (
        "In the saved copy the 0/1 column is 0 on 702 days and 1 on 1785 days. "
        "That is a count of the named rule, not a backtest result."
    ),
    (
        "The signal threshold on the SMA (window 1) of the 0/1 outflow column has to sit "
        "strictly between 0 and 1. Any value in that open range leaves a stored 0 off and a stored 1 on, "
        "so the threshold is not a search and do not pick or recommend a specific number inside the range. "
        "The sleeve's 2.25 is not the gate's threshold. A threshold of 2.25 would leave the gate off "
        "every day, because a 1 is never above 2.25."
    ),
    "SOPR and MVRV z-score stay a from-July-2025 check only.",
)
StepStatus = Literal["PASS", "FAIL"]


@dataclass
class StepResult:
    step: str
    status: StepStatus
    detail: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class SuiteReport:
    results: list[StepResult] = field(default_factory=list)

    def add(self, result: StepResult) -> StepResult:
        self.results.append(result)
        return result

    @property
    def failed(self) -> bool:
        return any(r.status == "FAIL" for r in self.results)

    def summary_line(self) -> str:
        passed = sum(1 for r in self.results if r.status == "PASS")
        failed = sum(1 for r in self.results if r.status == "FAIL")
        if failed:
            return f"[suite] {passed} passed, {failed} failed"
        return f"[suite] OK — {passed} passed"


def run_suite(fixture_root: Path | None = None) -> SuiteReport:
    """Run every case in ``manifest.json``. Missing files fail the case."""
    root = Path(fixture_root) if fixture_root is not None else DEFAULT_FIXTURE_ROOT
    report = SuiteReport()
    if (root / "later").exists():
        report.add(StepResult(
            "revision",
            "FAIL",
            f"{root / 'later'} is present. The corpus must not contain an invented "
            "second copy. Compare external directories with --compare.",
        ))
        return report

    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        report.add(StepResult("manifest", "FAIL", f"missing {manifest_path}"))
        return report

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.add(StepResult("manifest", "FAIL", f"manifest is not JSON: {exc}"))
        return report

    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        report.add(StepResult("manifest", "FAIL", "manifest has no cases"))
        return report

    for case in cases:
        case_id = str(case.get("id", "?"))
        try:
            detail = _run_case(root, case)
        except (AssertionError, OSError, ValueError, KeyError, TypeError) as exc:
            report.add(StepResult(case_id, "FAIL", f"{type(exc).__name__}: {exc}"))
            continue
        report.add(StepResult(case_id, "PASS", detail))

    report.add(StepResult(
        "revision",
        "PASS",
        "one copy of each response case; no later copy in the fixture root; "
        "no Glassnode revision is recorded here",
    ))
    return report


def compare_saved_dirs(earlier_dir: Path, later_dir: Path) -> SuiteReport:
    """Compare two directories of saved copies. Missing sides fail closed."""
    report = SuiteReport()
    earlier_dir = Path(earlier_dir)
    later_dir = Path(later_dir)
    if not earlier_dir.is_dir():
        report.add(StepResult("earlier", "FAIL", f"missing directory {earlier_dir}"))
        return report
    if not later_dir.is_dir():
        report.add(StepResult("later", "FAIL", f"missing directory {later_dir}"))
        return report

    names = sorted(p.name for p in earlier_dir.iterdir() if p.is_dir())
    if not names:
        report.add(StepResult("earlier", "FAIL", f"no copy directories in {earlier_dir}"))
        return report

    for name in names:
        later_path = later_dir / name
        if not later_path.is_dir():
            report.add(StepResult(name, "FAIL", f"missing {later_path}"))
            continue
        try:
            earlier = load_saved_copy(earlier_dir / name)
            later = load_saved_copy(later_path)
            diff = compare_copies(earlier, later)
        except (AssertionError, OSError, ValueError, KeyError, TypeError) as exc:
            report.add(StepResult(name, "FAIL", f"{type(exc).__name__}: {exc}"))
            continue
        status: StepStatus = "FAIL" if _compare_failed(diff) else "PASS"
        report.add(StepResult(name, status, _format_revision(diff)))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline Glassnode golden harness")
    parser.add_argument("--suite", action="store_true", help="Run the committed fixture matrix")
    parser.add_argument("--json", action="store_true", help="Print machine-readable results")
    parser.add_argument(
        "--fixture-root",
        type=Path,
        default=None,
        help="Directory that contains manifest.json (default: tests/fixtures/glassnode)",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("EARLIER", "LATER"),
        help="Compare two directories of saved copies. Does not fetch.",
    )
    args = parser.parse_args(argv)
    if not args.suite and not args.compare:
        parser.error("pass --suite, --compare, or both")

    reports: list[tuple[str, SuiteReport]] = []
    if args.suite:
        reports.append(("suite", run_suite(args.fixture_root)))
    if args.compare:
        reports.append(("compare", compare_saved_dirs(Path(args.compare[0]), Path(args.compare[1]))))

    failed = any(report.failed for _, report in reports)
    if args.json:
        payload = {
            name: {
                "summary": report.summary_line(),
                "results": [step.as_dict() for step in report.results],
            }
            for name, report in reports
        }
        print(json.dumps(payload, indent=2))
    else:
        for name, report in reports:
            print(f"[{name}]")
            for step in report.results:
                line = f"[{step.status:4}] {step.step}"
                if step.detail:
                    line += f" — {step.detail}"
                print(line)
            print(report.summary_line())
    logger.info("glassnode harness %s", "FAILED" if failed else "OK")
    return 1 if failed else 0


def _run_case(root: Path, case: dict) -> str:
    kind = case.get("type")
    if kind == "response":
        return _check_response(root, case)
    if kind == "pagination":
        return _check_pagination(root, case)
    if kind == "rate_limit":
        return _check_rate_limit(root, case)
    if kind == "interval":
        return _check_interval(root, case)
    if kind == "sleeve_factors":
        return _check_sleeve_factors(root, case)
    raise ValueError(f"unknown case type {kind!r}")


def _check_response(root: Path, case: dict) -> str:
    path = _require_path(root, case["path"])
    copy = load_saved_copy(path)
    expect = case["expect"]
    _eq(copy.parsed.status, expect["status"], "status")
    _eq(copy.request.metric_path, expect["metric_path"], "metric_path")
    _eq(copy.request.asset, expect["asset"], "asset")
    _eq(copy.request.interval, expect["interval"], "interval")
    _eq(copy.request.since, expect["since"], "since")
    _eq(copy.request.until, expect["until"], "until")

    if "content_type" in expect:
        _eq(copy.parsed.content_type, expect["content_type"], "content_type")
    if expect.get("json_array"):
        if not copy.parsed.is_json_array:
            raise AssertionError("body is not a JSON list")
        if copy.parsed.object_keys:
            raise AssertionError(f"body has object keys {copy.parsed.object_keys}")
    if "point_count" in expect:
        if copy.parsed.points is None:
            raise AssertionError("response has no point list")
        _eq(len(copy.parsed.points), expect["point_count"], "point_count")
        _check_points(copy, expect)
    if "body_prefix" in expect:
        text = copy.parsed.error_text or ""
        if not text.startswith(expect["body_prefix"]):
            raise AssertionError(f"body does not start with {expect['body_prefix']!r}")
        if copy.parsed.points is not None:
            raise AssertionError("plain-text body was parsed as points")
        if expect.get("body_complete") is False and text.rstrip().endswith("]"):
            raise AssertionError("fixture closed the allowed-values list; only a prefix was retained")
    if "rate_limit_limit" in expect:
        _eq(copy.parsed.rate_limit.limit, expect["rate_limit_limit"], "x-rate-limit-limit")
    if copy.parsed.unexpected_point_keys:
        raise AssertionError(f"unexpected point keys {copy.parsed.unexpected_point_keys}")
    return _response_detail(copy, expect)


def _check_points(copy: SavedCopy, expect: dict) -> None:
    points = copy.parsed.points or ()
    if "first_t" in expect:
        _eq(points[0].t, expect["first_t"], "first_t")
        _eq(points[-1].t, expect["last_t"], "last_t")
    if "step_seconds" in expect:
        steps = {b.t - a.t for a, b in pairwise(points)}
        _eq(steps, {expect["step_seconds"]}, "step_seconds")
    if "first_v" in expect:
        _eq(points[0].v, expect["first_v"], "first_v")
        _eq(points[-1].v, expect["last_v"], "last_v")
        middles = points[1:-1]
    else:
        middles = points
    if "fill_v" in expect:
        bad = [p.t for p in middles if p.v != expect["fill_v"]]
        if bad:
            raise AssertionError(f"synthetic fill_v mismatch at t={bad[:3]}")


def _check_pagination(root: Path, case: dict) -> str:
    doc = _load_json(_require_path(root, case["contract"]))
    if doc.get("client_paginates") is not False:
        raise AssertionError("client_paginates must be false")
    if doc.get("cursor") is not None:
        raise AssertionError("cursor must be null")
    if doc.get("observed_body_shape") != "json_list":
        raise AssertionError("observed_body_shape must be json_list")
    sample = load_saved_copy(_require_path(root, case["sample"]))
    if not sample.parsed.is_json_array:
        raise AssertionError("sample body is not a single JSON list")
    if sample.parsed.object_keys:
        raise AssertionError("sample body carries a page object")
    return "single JSON list, no cursor, client issues one GET"


def _check_rate_limit(root: Path, case: dict) -> str:
    doc = _load_json(_require_path(root, case["contract"]))
    window = doc["short_window"]
    if window["limit"] != "600":
        raise AssertionError("short-window limit must be 600")
    if doc.get("exhausted_body_saved") is not False:
        raise AssertionError("a 429 body was not captured; exhausted_body_saved must be false")
    monthly = doc["monthly_cap"]
    if monthly.get("calls") != 160000:
        raise AssertionError("monthly cap must stay the operator figure 160000")
    if monthly.get("in_response_headers") is not False:
        raise AssertionError("the monthly cap is not a response header")
    manifest = _load_json(root / "manifest.json")
    checked = 0
    for item in manifest["cases"]:
        if item.get("type") != "response":
            continue
        if "rate_limit_limit" not in item.get("expect", {}):
            continue
        copy = load_saved_copy(_require_path(root, item["path"]))
        _eq(copy.parsed.rate_limit.limit, "600", item["id"])
        checked += 1
    if checked < 1:
        raise AssertionError("no successful response carries x-rate-limit-limit")
    return f"limit 600 on {checked} responses; remaining and reset are described, not stored as absolutes"


def _check_sleeve_factors(root: Path, case: dict) -> str:
    """Lock the 3 Oct coverage facts. The three series are not one backtest."""
    doc = _load_json(_require_path(root, case["contract"]))
    rule = tuple(doc.get("rule") or ())
    if rule != SLEEVE_FACTOR_RULE:
        raise AssertionError("sleeve factor note does not match the chosen rule")

    series = doc.get("series")
    if not isinstance(series, list) or len(series) != 3:
        raise AssertionError("expected three series, each with its own window")
    covers = [item.get("covers_2021_to_mid_2024") for item in series]
    if len(set(covers)) < 2:
        raise AssertionError("the three series must not be equally backtestable")
    if covers != [True, False, False]:
        raise AssertionError(
            "only point-in-time BTC exchange netflow covers 2021 to mid-2024"
        )

    netflow, pit_indicators, bnb = series
    _eq(netflow["metric_path"], "transactions/transfers_volume_exchanges_net_pit", "netflow path")
    btc = netflow["assets"]["BTC"]
    eth = netflow["assets"]["ETH"]
    bnb_asset = netflow["assets"]["BNB"]
    _eq(btc["starts"], "2019-12-11", "BTC netflow start")
    _eq(btc["covers_2021_to_mid_2024"], True, "BTC netflow window")
    _eq(eth["starts"], "2022-02-15", "ETH netflow start")
    _eq(eth["covers_2021_to_mid_2024"], False, "ETH netflow window")
    _eq(bnb_asset["valid_asset"], False, "BNB on netflow")

    _eq(pit_indicators["starts"], "2025-06-27", "SOPR and MVRV z-score PIT start")
    _eq(pit_indicators["check"], "from July 2025 only", "SOPR and MVRV z-score check")
    _eq(
        pit_indicators["metrics"],
        ["indicators/sopr_pit", "market/mvrv_z_score_pit"],
        "PIT indicator paths",
    )
    _eq(pit_indicators["restated"]["full_window_sharpe"], "look-ahead", "restated Sharpe")
    _eq(
        pit_indicators["restated"]["metrics"],
        ["indicators/sopr", "market/mvrv_z_score"],
        "restated indicator paths",
    )

    _eq(bnb["restated"]["starts"], "2020-08-29", "BNB restated start")
    _eq(bnb["restated"]["backtestable_2021_to_mid_2024"], False, "BNB restated window")
    _eq(bnb["pit"]["starts"], "2025-06-23", "BNB PIT start")
    _eq(bnb["pit"]["covers_2021_to_mid_2024"], False, "BNB PIT window")
    _eq(
        bnb["restated"]["metric_path"],
        "distribution/exchange_net_position_change",
        "BNB restated path",
    )
    _eq(
        bnb["pit"]["metric_path"],
        "distribution/exchange_net_position_change_pit",
        "BNB PIT path",
    )
    _check_named_child(doc.get("child"))
    return "BTC netflow PIT covers 2021 to mid-2024; the child is the stored 0/1 column"


def _check_named_child(child: object) -> None:
    """Lock the named 0/1 child. Counts are only the ones already checked."""
    if not isinstance(child, dict):
        raise TypeError("the named child is missing")
    _eq(child.get("named_before_result"), True, "child named before a result")
    _eq(child.get("raw_metric_path"), "transactions/transfers_volume_exchanges_net_pit", "child raw path")
    saved = child.get("saved_copy")
    if not isinstance(saved, dict):
        raise TypeError("saved copy counts are missing")
    _eq(saved.get("from"), "2019-12-11", "saved copy start")
    _eq(saved.get("through"), "2026-10-01", "saved copy end")
    _eq(saved.get("days"), 2487, "saved copy days")
    _eq(saved.get("nulls"), 0, "saved copy nulls")
    _eq(saved.get("exact_zeros"), False, "saved copy exact zeros")
    _eq(saved.get("smallest_absolute_value"), "about 2.56", "smallest absolute value")
    window = child.get("window")
    if not isinstance(window, dict):
        raise TypeError("child window counts are missing")
    _eq(window.get("from"), "2021-07-01", "child window start")
    _eq(window.get("to"), "2024-06-30", "child window end")
    _eq(window.get("days"), 1096, "child window days")
    _eq(window.get("exact_zeros"), False, "child window exact zeros")
    _eq(child.get("below_zero"), 1, "below zero")
    _eq(child.get("otherwise"), 0, "otherwise")
    _eq(child.get("store_zero"), True, "store zero")
    _eq(child.get("drop_zero_days"), False, "drop zero days")
    _eq(child.get("days_at_0"), 702, "days at 0")
    _eq(child.get("days_at_1"), 1785, "days at 1")
    _eq(child.get("factor_one"), "0/1 column", "factor one")
    _eq(child.get("factor_two"), "BTC 60/2.25", "factor two")
    _eq(child.get("gate_indicator"), "SMA", "gate indicator")
    _eq(child.get("gate_window"), 1, "gate window")
    _eq(child.get("signal_threshold_open_range"), "(0, 1)", "signal threshold range")
    _eq(child.get("signal_threshold_is_a_search"), False, "signal threshold search")


def _check_interval(root: Path, case: dict) -> str:
    doc = _load_json(_require_path(root, case["contract"]))
    if doc.get("captured_interval") != "24h":
        raise AssertionError("only the 24h interval was captured")
    if doc.get("sub_daily_body_saved") is not False:
        raise AssertionError("no sub-daily body was saved")
    manifest = _load_json(root / "manifest.json")
    series = 0
    for item in manifest["cases"]:
        expect = item.get("expect") or {}
        if item.get("type") != "response" or "point_count" not in expect:
            continue
        if expect.get("point_count", 0) == 0:
            continue
        if expect.get("interval") != "24h":
            raise AssertionError(f"{item['id']} is not 24h")
        series += 1
    if series < 1:
        raise AssertionError("no 24h series cases")
    return f"{series} series cases are 24h; no other interval body is in the corpus"


def _require_path(root: Path, relative: str) -> Path:
    path = root / relative
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def _load_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise TypeError(f"{path} must be a JSON object")
    return doc


def _eq(actual, expected, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: {actual!r} != {expected!r}")


def _response_detail(copy: SavedCopy, expect: dict) -> str:
    if copy.parsed.points is None:
        return f"HTTP {copy.parsed.status} {copy.parsed.content_type}"
    values = expect.get("values", "")
    return (
        f"HTTP {copy.parsed.status} {len(copy.parsed.points)} points "
        f"{copy.request.metric_path} {copy.request.asset} {values}".rstrip()
    )


def _compare_failed(diff: RevisionReport) -> bool:
    return bool(
        diff.request_mismatch
        or diff.value_revision
        or diff.status_changed
        or diff.content_type_changed
        or diff.other_header_changes
    )


def _format_revision(diff: RevisionReport) -> str:
    if diff.request_mismatch:
        return diff.request_mismatch
    parts: list[str] = []
    if diff.error_text_earlier != diff.error_text_later:
        parts.append("error body text differs")
    if diff.value_changes:
        shown = ", ".join(
            f"t={c.t} {c.earlier_v} -> {c.later_v}" for c in diff.value_changes[:5]
        )
        extra = len(diff.value_changes) - 5
        if extra > 0:
            shown += f" (+{extra} more)"
        parts.append(f"value revisions: {shown}")
    if diff.timestamps_only_earlier:
        parts.append(f"timestamps removed: {diff.timestamps_only_earlier[:5]}")
    if diff.timestamps_only_later:
        parts.append(f"timestamps added: {diff.timestamps_only_later[:5]}")
    if diff.status_changed:
        parts.append(f"status {diff.status_earlier} -> {diff.status_later}")
    if diff.content_type_changed:
        parts.append(f"content-type {diff.content_type_earlier} -> {diff.content_type_later}")
    if diff.quota_changes:
        parts.append(f"quota headers changed: {diff.quota_changes}")
    if diff.transport_changes:
        parts.append(f"transport headers changed: {[name for name, _, _ in diff.transport_changes]}")
    if diff.other_header_changes:
        parts.append(f"other headers changed: {diff.other_header_changes}")
    if diff.body_sha256_earlier != diff.body_sha256_later and not diff.value_revision:
        parts.append("body bytes differ with the same points")
    if not parts:
        return "no difference in points, status, or content type"
    return "; ".join(parts)


if __name__ == "__main__":
    sys.exit(main())
