#!/usr/bin/env python3
"""Tests for wifi-test/soak-review.py over synthetic sample logs (no network).
Usage: python3 -I tests/test_soak_review.py   (exit 0 = pass)"""
import contextlib
import datetime as dt
import importlib.util
import io
import json
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("soak", os.path.join(HERE, "..", "wifi-test", "soak-review.py"))
soak = importlib.util.module_from_spec(spec)
spec.loader.exec_module(soak)

START = dt.datetime(2026, 10, 21, tzinfo=dt.timezone.utc)
END = int(dt.datetime(2026, 11, 18, 12, tzinfo=dt.timezone.utc).timestamp())  # soak day 28.5
TARGETS = dict(soak.DEFAULT_TARGETS)


def series(days, step, bad=(), value=1.0, end=END):
    """Regular series ending at `end`; indexes in `bad` fail (value ignored for those)."""
    n = days * 86400 // step
    t0 = end - days * 86400
    return [[t0 + i * step, 0.0 if i in bad else value] for i in range(n)]


def bundle(days=28, black_icmp_bad=(), colour_icmp_bad=(), rtt_black=0.03, rtt_colour=0.03,
           black_ipp_bad=(), pi_icmp_bad=(), end=END):
    return {"end": end, "series": {
        "icmp": {"black": series(days, 15, black_icmp_bad, end=end), "colour": series(days, 15, colour_icmp_bad, end=end),
                 "pi": series(days, 15, pi_icmp_bad, end=end)},
        "ipp": {"black": series(days, 60, black_ipp_bad, end=end), "colour": series(days, 60, end=end), "pi": series(days, 60, end=end)},
        "rtt": {"black": series(days, 15, value=rtt_black, end=end), "colour": series(days, 15, value=rtt_colour, end=end),
                "pi": series(days, 15, value=0.0003, end=end)}}}


def ev(b, now=None):
    return soak.evaluate(b, TARGETS, START, 28, now)


class Stats(unittest.TestCase):
    def test_success_and_longest_outage(self):
        pts = [[i * 15, 0.0 if i in (10, 11, 12, 500) else 1.0] for i in range(1000)]
        pct, fails, n, longest = soak.success_stats(pts, 15)
        self.assertEqual((fails, n), (4, 1000))
        self.assertAlmostEqual(pct, 99.6)
        self.assertEqual(longest, 45)

    def test_outage_boundary_300_passes_360_fails(self):
        self.assertEqual(soak.success_stats(series(1, 60, set(range(100, 105))), 60)[3], 300)
        self.assertEqual(soak.success_stats(series(1, 60, set(range(100, 106))), 60)[3], 360)
        r = ev(bundle(black_ipp_bad=set(range(100, 105))))
        self.assertNotIn("longest :631 outage <= 300 s", r["rows"]["black"]["failed"])
        r = ev(bundle(black_ipp_bad=set(range(100, 106))))
        self.assertIn("longest :631 outage <= 300 s", r["rows"]["black"]["failed"])

    def test_success_boundary_99_9(self):
        n = 28 * 86400 // 60      # 40320 samples; 40 fails (not adjacent) = 99.9008 %, 41 = 99.898 %
        ok = ev(bundle(black_ipp_bad=set(range(0, 40 * 100, 100))))
        self.assertNotIn(":631 success >= 99.9 %", ok["rows"]["black"]["failed"])
        bad = ev(bundle(black_ipp_bad=set(range(0, 41 * 100, 100))))
        self.assertIn(":631 success >= 99.9 %", bad["rows"]["black"]["failed"])
        self.assertGreater(n, 40000)

    def test_gap_does_not_join_outages(self):
        pts = [[0, 0.0], [15, 0.0], [100000, 0.0], [100015, 0.0]]
        self.assertEqual(soak.success_stats(pts, 15)[3], 30)

    def test_single_failed_sample_counts_one_step(self):
        self.assertEqual(soak.success_stats([[0, 0.0]], 15)[3], 15)
        self.assertEqual(soak.success_stats([[0, 0.0], [15, 1.0]], 15)[3], 15)

    def test_empty_and_percentile(self):
        self.assertIsNone(soak.success_stats([]))
        self.assertEqual(soak.percentile(list(range(1, 101)), 95), 95)
        self.assertIsNone(soak.percentile([], 95))


class Verdicts(unittest.TestCase):
    def test_28_day_clean_window_is_go_and_pi_is_control(self):
        r = ev(bundle())
        self.assertEqual(r["overall"], "GO")
        self.assertEqual(r["rows"]["pi"]["verdict"], "CONTROL")
        self.assertEqual(soak.exit_code(r), 0)

    def test_seven_day_window_can_never_say_go(self):
        r = ev(bundle(days=7))
        self.assertEqual(r["overall"], "KEEP SOAKING")
        self.assertEqual(soak.exit_code(r), 1)

    def test_seven_day_window_with_failures_is_keep_soaking_exit_4(self):
        r = ev(bundle(days=7, rtt_black=1.4))
        self.assertEqual(r["overall"], "KEEP SOAKING")
        self.assertEqual(soak.exit_code(r), 4)

    def test_early_soak_good_data_keeps_soaking(self):
        early = int(dt.datetime(2026, 11, 4, tzinfo=dt.timezone.utc).timestamp())
        r = ev(bundle(days=14, end=early), now=early)
        self.assertEqual(r["overall"], "KEEP SOAKING")

    def test_old_bad_week_in_a_28_day_window_blocks_go(self):
        r = ev(bundle(black_ipp_bad=set(range(0, 3000))))      # refusal run in the first days
        self.assertEqual(r["rows"]["black"]["verdict"], "NO-GO")
        self.assertEqual(r["rows"]["colour"]["verdict"], "GO")
        self.assertEqual(soak.exit_code(r), 2)

    def test_high_rtt_blocks_go(self):
        r = ev(bundle(rtt_black=1.4))
        self.assertEqual(r["overall"], "NO-GO")
        self.assertIn("ICMP RTT p95 <= 50 ms", r["rows"]["black"]["failed"])

    def test_failing_pi_control_is_not_judged(self):
        r = ev(bundle(pi_icmp_bad=set(range(0, 5000))))
        self.assertEqual(r["rows"]["pi"]["verdict"], "CONTROL")
        self.assertEqual(r["overall"], "GO")

    def test_target_with_short_history_cannot_ride_on_the_control_window(self):
        # colour has only 3 days of data while the Pi control covers 28: window coverage alone said GO
        b = bundle()
        for kind, step in (("icmp", 15), ("ipp", 60), ("rtt", 15)):
            b["series"][kind]["colour"] = series(3, step, value=0.03 if kind == "rtt" else 1.0, end=END)
        r = ev(b)
        self.assertEqual(r["rows"]["colour"]["verdict"], "KEEP SOAKING")
        self.assertNotEqual(r["overall"], "GO")

    def test_prometheus_hole_inside_the_window_is_not_a_clean_run(self):
        # 28 d span but a 10 d hole (Prometheus down): the missing days must not count as 100 % success
        b = bundle()
        hole_from, hole_to = END - 20 * 86400, END - 10 * 86400
        for kind in ("icmp", "ipp", "rtt"):
            b["series"][kind]["black"] = [p for p in b["series"][kind]["black"] if not hole_from <= p[0] < hole_to]
        r = ev(b)
        self.assertEqual(r["rows"]["black"]["verdict"], "KEEP SOAKING")
        self.assertNotEqual(r["overall"], "GO")

    def test_missing_data_never_go(self):
        b = bundle()
        b["series"]["rtt"].pop("colour")
        r = ev(b)
        self.assertEqual(r["rows"]["colour"]["verdict"], "KEEP SOAKING")

    def test_merge_of_weekly_bundles_equals_a_full_window(self):
        b = bundle()
        cut = END - 14 * 86400
        halves = []
        for lo, hi in ((0, cut), (cut, END + 1)):
            halves.append({"end": END if hi > END else cut, "series": {
                k: {n: [p for p in pts if lo <= p[0] < hi] for n, pts in per.items()}
                for k, per in b["series"].items()}})
        m = soak.merge_bundles(halves)
        self.assertEqual(ev(m)["overall"], "GO")
        self.assertAlmostEqual(soak.coverage_days(m), 28, delta=0.01)


class Prometheus(unittest.TestCase):
    def test_host_parsing_and_exact_match(self):
        self.assertEqual(soak._host("192.168.0.10"), "192.168.0.10")
        self.assertEqual(soak._host("192.168.0.10:631"), "192.168.0.10")
        self.assertEqual(soak._host("http://black.lab:631/x"), "black.lab")
        warns = []
        res = [{"metric": {"instance": i}, "values": [[1, "1"]]} for i in ("192.168.0.10:631", "192.168.0.11:631", "192.168.0.100:631")]
        got = soak.pick(res, {"black": "192.168.0.10", "x": "192.168.0.1"}, "ipp", warns.append)
        self.assertEqual(list(got), ["black"])          # .100 and .11 must not match .1 or .10
        self.assertTrue(any("target x matched 0" in w for w in warns))

    def test_fetch_bundle_chunks_and_stays_under_point_cap(self):
        calls = []

        def fake(prom, query, start, end, step):
            calls.append((query, start, end, step))
            assert (end - start) / step <= 11000
            inst = {"192.168.0.10": 0, "192.168.0.11": 0, "192.168.0.179": 0}
            return [{"metric": {"instance": h}, "values": [[start, "1"], [end, "1"]]} for h in inst]
        orig = soak._query_range
        soak._query_range = fake
        try:
            b = soak.fetch_bundle("http://x", 28, TARGETS, now=END, warn=lambda m: None)
        finally:
            soak._query_range = orig
        icmp_calls = [c for c in calls if "icmp" in c[0] and c[0].startswith("probe_success")]
        self.assertGreaterEqual(len(icmp_calls), 14)    # 28 d at 15 s = 161k points
        self.assertEqual(set(b["series"]), {"icmp", "ipp", "rtt"})
        self.assertEqual(set(b["series"]["icmp"]), {"black", "colour", "pi"})
        self.assertEqual({c[3] for c in icmp_calls}, {15})


class Cli(unittest.TestCase):
    def run_main(self, bundles, *extra):
        paths = []
        for b in bundles:
            f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
            json.dump(b, f)
            f.close()
            paths.append(f.name)
        args = [x for p in paths for x in ("--from", p)] + list(extra)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = soak.main(args)
        for p in paths:
            os.unlink(p)
        return rc, out.getvalue(), err.getvalue()

    def test_exit_codes_and_one_page(self):
        rc, out, _ = self.run_main([bundle()])
        self.assertEqual(rc, 0)
        self.assertIn("OVERALL: GO", out)
        self.assertLess(len(out.splitlines()), 40)
        rc, out, _ = self.run_main([bundle(rtt_colour=0.2)])
        self.assertEqual(rc, 2)
        self.assertIn("FAIL  ICMP RTT p95 <= 50 ms", out)
        self.assertIn("Manual (not auto-judged)", out)

    def test_seven_day_note(self):
        rc, out, _ = self.run_main([bundle(days=7)])
        self.assertEqual(rc, 1)
        self.assertIn("not a final verdict", out)

    def test_markdown_header(self):
        _, out, _ = self.run_main([bundle()], "--md")
        self.assertTrue(out.startswith("# F2 Wi-Fi soak review"))

    def test_bad_input_is_rc3_never_1(self):
        for bad in ([], {"end": 1, "series": []}, {"end": "x"}, {"end": 1, "series": {"icmp": 5}}):
            rc, _, err = self.run_main([bad])
            self.assertEqual(rc, 3, bad)
            self.assertIn("soak-review:", err)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(soak.main(["--from", "/nonexistent.json"]), 3)
            self.assertEqual(soak.main(["--days", "40"]), 3)
            self.assertEqual(soak.main(["--target", "x", "--from", "/nonexistent.json"]), 3)

    def test_save_roundtrip(self):
        out = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        out.close()
        rc, _, _ = self.run_main([bundle()], "--save", out.name)
        with open(out.name) as f:
            self.assertEqual(json.load(f)["end"], END)
        os.unlink(out.name)
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
