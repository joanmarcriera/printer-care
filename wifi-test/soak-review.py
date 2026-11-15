#!/usr/bin/env python3
"""soak-review.py - one-page go/no-go summary for the F2 Wi-Fi soak (stdlib only).

Usage:
  wifi-test/soak-review.py --days 28 --save wifi-test/soak-bundles/2026-11-18.json   # live, whole soak
  wifi-test/soak-review.py                       # live: last 7 d (a weekly look; can never say GO)
  wifi-test/soak-review.py --from A.json --from B.json    # offline, several saved bundles merged
  wifi-test/soak-review.py --md > docs/soak-week3-2026-11-18.md

Options: --prom URL (default http://192.168.0.5:30090, or $SOAK_PROM), --days N (1-28, default 7),
  --soak-start YYYY-MM-DD (default 2026-10-21), --min-days N (default 28),
  --target NAME=HOST (repeatable; exact host of the Prometheus instance label, default
  black=192.168.0.10 colour=192.168.0.11 pi=192.168.0.179; use the hostname if the label is a hostname).

Reads only: GET /api/v1/query_range for probe_success and probe_icmp_duration_seconds{phase="rtt"}
on jobs blackbox-printers-icmp (15 s) and blackbox-printers-ipp (60 s). ICMP and RTT are fetched at
15 s in chunks under Prometheus' 11000-point cap, :631 at 60 s. Starts no monitor, touches no printer.

Exit code: 0 GO | 1 KEEP SOAKING (nothing failing, just early or data missing) | 2 NO-GO |
  3 input error | 4 KEEP SOAKING but a check is already failing (soak not yet 28 days).

Thresholds: success >= 99.9 %, longest outage <= 300 s, ICMP RTT p95 <= 50 ms come from the "go
criteria" in docs/soak-week1-2026-10-28.md and docs/soak-week2-2026-10-31.md. The 28-day minimum is
the task wording "4+ weeks" (https://familia.riera.co.uk/tasks/3711), start 2026-10-21 = week-1 window.
Edit THRESHOLDS to recalibrate, deliberately. GO needs every check PASS, soak age >= min-days AND the
data window itself covering >= min-days (so a 7-day look can never say GO, and an early bad week
cannot be forgotten: use --days 28 or merge the saved weekly bundles).
The wired Pi is a control: shown, never judged. The weekly F4 test print is a manual line.
"""
import argparse
import datetime as dt
import json
import math
import os
import sys
import urllib.parse
import urllib.request

THRESHOLDS = {"success_pct": 99.9, "outage_s": 300, "rtt_p95_ms": 50}
JOBS = {"icmp": "blackbox-printers-icmp", "ipp": "blackbox-printers-ipp"}
DEFAULT_TARGETS = {"black": "192.168.0.10", "colour": "192.168.0.11", "pi": "192.168.0.179"}
CONTROL = "pi"
STEPS = {"icmp": 15, "rtt": 15, "ipp": 60}
MAX_POINTS = 10000


def percentile(values, q):
    """Nearest-rank percentile; None for an empty list."""
    if not values:
        return None
    s = sorted(values)
    return s[max(0, math.ceil(q / 100 * len(s)) - 1)]


def success_stats(points, nominal_step=None):
    """points: [(ts, 0|1)] -> (success_pct, fails, samples, longest_outage_s) or None.
    An outage run is consecutive failed samples at most 2 steps apart; each counts one step."""
    pts = sorted(points)
    if not pts:
        return None
    step = nominal_step or _median_step(pts) or 60
    fails = sum(1 for _, v in pts if v < 0.5)
    longest = run = 0
    prev = None   # ts of previous sample if it failed
    for ts, v in pts:
        if v < 0.5:
            run = run + (ts - prev) if prev is not None and ts - prev <= 2 * step else step
            longest = max(longest, run)
            prev = ts
        else:
            prev = None
    return (100.0 * (len(pts) - fails) / len(pts), fails, len(pts), longest)


def _median_step(pts):
    gaps = sorted(b[0] - a[0] for a, b in zip(pts, pts[1:]) if b[0] > a[0])
    return gaps[len(gaps) // 2] if gaps else 0


def rtt_p95_ms(points):
    p = percentile([v for _, v in points], 95)
    return None if p is None else p * 1000.0


def merge_bundles(bundles):
    """Concatenate series of several bundles, dedupe by timestamp, end = latest end."""
    series = {}
    for b in bundles:
        for kind, per in b["series"].items():
            for name, pts in per.items():
                d = series.setdefault(kind, {}).setdefault(name, {})
                for t, v in pts:
                    d[float(t)] = float(v)
    out = {k: {n: [[t, d[t]] for t in sorted(d)] for n, d in per.items()} for k, per in series.items()}
    return {"end": max(b["end"] for b in bundles), "series": out}


def coverage_days(bundle):
    firsts = [p[0][0] for per in bundle["series"].values() for p in per.values() if p]
    return (bundle["end"] - min(firsts)) / 86400 if firsts else 0.0


def target_data_ok(bundle, name, min_days, tolerance=0.95):
    """True if THIS target's icmp and :631 series span the minimum window with >= 95 % of the expected
    samples (a Prometheus outage or a late-added target must not read as 100 % success)."""
    end = bundle["end"]
    for kind in ("icmp", "ipp"):
        pts = bundle["series"].get(kind, {}).get(name, [])
        if not pts or pts[0][0] > end - (min_days - 0.5) * 86400:
            return False
        if len(pts) < tolerance * (end - pts[0][0]) / STEPS[kind]:
            return False
    return True


def evaluate(bundle, targets, soak_start, min_days, now=None):
    """bundle = {"end": ts, "series": {kind: {name: [[ts,v],..]}}}."""
    end = bundle["end"]
    now = now if now is not None else end
    soak_days = max(0.0, (now - soak_start.timestamp()) / 86400)
    cover = coverage_days(bundle)
    rows = {}
    for name in targets:
        s = bundle["series"]
        icmp = success_stats(s.get("icmp", {}).get(name, []), STEPS["icmp"])
        ipp = success_stats(s.get("ipp", {}).get(name, []), STEPS["ipp"])
        rtt = rtt_p95_ms(s.get("rtt", {}).get(name, []))
        checks = []

        def chk(label, val, ok, fmt):
            checks.append({"label": label, "value": None if val is None else fmt(val),
                           "ok": None if val is None else bool(ok)})
        sp = THRESHOLDS["success_pct"]
        chk("ICMP success >= %.1f %%" % sp, icmp and icmp[0], icmp and icmp[0] >= sp, lambda v: "%.3f %%" % v)
        chk(":631 success >= %.1f %%" % sp, ipp and ipp[0], ipp and ipp[0] >= sp, lambda v: "%.3f %%" % v)
        o = THRESHOLDS["outage_s"]
        chk("longest ICMP outage <= %d s" % o, icmp and icmp[3], icmp and icmp[3] <= o, lambda v: "%d s" % v)
        chk("longest :631 outage <= %d s" % o, ipp and ipp[3], ipp and ipp[3] <= o, lambda v: "%d s" % v)
        r = THRESHOLDS["rtt_p95_ms"]
        chk("ICMP RTT p95 <= %d ms" % r, rtt, rtt is not None and rtt <= r, lambda v: "%.0f ms" % v)
        rows[name] = {"checks": checks}
    mature = soak_days >= min_days and cover >= min_days - 0.5
    for name, r in rows.items():
        failed = [c["label"] for c in r["checks"] if c["ok"] is False]
        missing = [c for c in r["checks"] if c["ok"] is None]
        r["failed"] = failed
        r["data_ok"] = target_data_ok(bundle, name, min_days)
        if name == CONTROL:
            r["verdict"] = "CONTROL"
        elif failed:
            r["verdict"] = "NO-GO" if mature else "KEEP SOAKING"
        elif missing or not mature or not r["data_ok"]:
            r["verdict"] = "KEEP SOAKING"
        else:
            r["verdict"] = "GO"
    judged = {n: r for n, r in rows.items() if n != CONTROL}
    verdicts = [r["verdict"] for r in judged.values()]
    overall = ("NO-GO" if "NO-GO" in verdicts else
               "KEEP SOAKING" if (not verdicts or "KEEP SOAKING" in verdicts) else "GO")
    return {"rows": rows, "overall": overall, "soak_days": soak_days, "min_days": min_days,
            "coverage": cover, "end": end, "mature": mature,
            "failing": any(r["failed"] for r in judged.values())}


def exit_code(res):
    if res["overall"] == "GO":
        return 0
    if res["overall"] == "NO-GO":
        return 2
    return 4 if res["failing"] else 1


def render(res, md=False):
    end = dt.datetime.fromtimestamp(res["end"], dt.timezone.utc).strftime("%Y-%m-%d %H:%MZ")
    out = [("# " if md else "") + f"F2 Wi-Fi soak review - data window {res['coverage']:.1f} d to {end}",
           f"Soak age {res['soak_days']:.1f} d, data window {res['coverage']:.1f} d, minimum {res['min_days']} d. "
           f"OVERALL: {res['overall']}"]
    if not res["mature"]:
        out.append("NOTE: not a final verdict - a GO/NO-GO needs a data window of the full minimum "
                   "(run with --days 28, or --from several weekly bundles).")
    out.append("")
    for name, r in res["rows"].items():
        out.append(f"{name}: {r['verdict']}" + (f"  (failed: {'; '.join(r['failed'])})" if r["failed"] else ""))
        if not r["data_ok"] and name != CONTROL and res["mature"]:
            out.append("  NOTE  this target's series is shorter or has gaps (<95 % of expected samples): no GO")
        for c in r["checks"]:
            mark = {True: "PASS", False: "FAIL", None: "n/a "}[c["ok"]]
            out.append(f"  {mark}  {c['label']:<34} {c['value'] if c['value'] else 'no data'}")
        out.append("")
    out += ["Manual (not auto-judged): weekly F4 test print over black-wifi and colour-wifi (needs the Pi; see",
            "docs/wifi-test-plan.md). Go/no-go is Marc's: this script only recommends."]
    return "\n".join(out) + "\n"


# --- Prometheus (read-only GET) ---------------------------------------------------------------
def _query_range(prom, query, start, end, step):
    qs = urllib.parse.urlencode({"query": query, "start": start, "end": end, "step": step})
    with urllib.request.urlopen(f"{prom}/api/v1/query_range?{qs}", timeout=30) as r:
        data = json.load(r)
    if data.get("status") != "success":
        raise RuntimeError(f"prometheus: {data}")
    return data["data"]["result"]


def _host(instance):
    """Host part of a blackbox instance label: '192.168.0.10', '192.168.0.10:631', 'http://h:631'."""
    inst = instance.split("://")[-1].split("/")[0]
    return inst.rsplit(":", 1)[0] if inst.count(":") == 1 else inst


def pick(results, targets, kind, warn):
    """Map instance label -> target by exact host; warn on a target with 0 or >1 series."""
    found = {}
    for res in results:
        host = _host(res["metric"].get("instance", ""))
        for name, want in targets.items():
            if host == want:
                found.setdefault(name, []).append(res)
    for name in targets:
        n = len(found.get(name, []))
        if n != 1:
            warn(f"warning: target {name} matched {n} {kind} series (want exactly 1)")
    return {n: [[float(t), float(v)] for t, v in r[0]["values"]] for n, r in found.items() if len(r) == 1}


def fetch_series(prom, query, start, end, step):
    """query_range in chunks under the point cap; returns the merged result list per label set."""
    merged = {}
    span = MAX_POINTS * step
    t = start
    while t < end:
        stop = min(end, t + span)
        for res in _query_range(prom, query, t, stop, step):
            key = json.dumps(res["metric"], sort_keys=True)
            merged.setdefault(key, {"metric": res["metric"], "values": {}})["values"].update(
                {float(a): b for a, b in res["values"]})
        t = stop + step
    return [{"metric": m["metric"], "values": sorted(m["values"].items())} for m in merged.values()]


def fetch_bundle(prom, days, targets, now=None, warn=lambda m: print(m, file=sys.stderr)):
    end = int(now if now is not None else dt.datetime.now(dt.timezone.utc).timestamp())
    start = end - days * 86400
    series = {}
    for kind, job in JOBS.items():
        q = f'probe_success{{job="{job}"}}'
        series[kind] = pick(fetch_series(prom, q, start, end, STEPS[kind]), targets, kind, warn)
    q = f'probe_icmp_duration_seconds{{job="{JOBS["icmp"]}",phase="rtt"}}'
    series["rtt"] = pick(fetch_series(prom, q, start, end, STEPS["rtt"]), targets, "rtt", warn)
    return {"end": end, "days": days, "series": series}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--prom", default=os.environ.get("SOAK_PROM", "http://192.168.0.5:30090"))
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--from", dest="src", action="append")
    ap.add_argument("--save")
    ap.add_argument("--md", action="store_true")
    ap.add_argument("--soak-start", default="2026-10-21")
    ap.add_argument("--min-days", type=int, default=28)
    ap.add_argument("--target", action="append", default=[])
    a = ap.parse_args(argv)
    targets = dict(DEFAULT_TARGETS)
    try:
        for t in a.target:
            k, sep, v = t.partition("=")
            if not sep or not k or not v:
                raise ValueError(f"--target wants NAME=HOST, got {t!r}")
            targets[k] = v
        if a.src:
            bundles = []
            for p in a.src:
                with open(p) as f:
                    bundles.append(json.load(f))
            bundle = merge_bundles(bundles) if len(bundles) > 1 else bundles[0]
            if not isinstance(bundle.get("series"), dict) or not isinstance(bundle.get("end"), (int, float)):
                raise ValueError("bundle needs numeric 'end' and a 'series' object")
        else:
            if not 1 <= a.days <= 28:
                raise ValueError("--days must be 1-28")
            bundle = fetch_bundle(a.prom, a.days, targets)
        if a.save:
            with open(a.save, "w") as f:
                json.dump(bundle, f)
        start = dt.datetime.strptime(a.soak_start, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
        res = evaluate(bundle, targets, start, a.min_days, bundle["end"] if a.src else None)
    except (OSError, ValueError, KeyError, RuntimeError, TypeError, AttributeError, IndexError) as e:
        print(f"soak-review: {type(e).__name__}: {e}", file=sys.stderr)
        return 3
    sys.stdout.write(render(res, a.md))
    return exit_code(res)


if __name__ == "__main__":
    sys.exit(main())
