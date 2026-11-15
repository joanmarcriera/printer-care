#!/usr/bin/env python3
"""soak-review.py - one-page go/no-go summary for the F2 Wi-Fi soak (stdlib only).

Usage:
  wifi-test/soak-review.py                      # live: last 7 d from Prometheus (read-only GET)
  wifi-test/soak-review.py --days 7 --save wifi-test/soak-bundles/2026-11-18.json
  wifi-test/soak-review.py --from BUNDLE.json   # offline review of a saved bundle (no network)
  wifi-test/soak-review.py --md > docs/soak-week3-2026-11-18.md

Options: --prom URL (default http://192.168.0.5:30090, or $SOAK_PROM), --days N,
  --soak-start YYYY-MM-DD (default 2026-10-21), --min-days N (default 28),
  --target NAME=SUBSTRING (repeatable; default black=192.168.0.10 colour=192.168.0.11 pi=192.168.0.179).

Reads only: GET /api/v1/query_range for probe_success and probe_icmp_duration_seconds{phase="rtt"}
on jobs blackbox-printers-icmp (15 s) and blackbox-printers-ipp (60 s). Starts no monitor and
touches no printer, Pi or network. Exit code: 0 = GO, 1 = KEEP SOAKING, 2 = NO-GO, 3 = input error.

Thresholds (docs/wifi-test-plan.md / soak notes; edit THRESHOLDS below to recalibrate):
  success >= 99.9 % (ICMP and :631), longest outage <= 300 s, ICMP RTT p95 <= 50 ms.
A printer is GO only when every threshold passes AND the soak has run >= min-days (28).
The wired Pi is a control: it is shown, never judged. The weekly F4 test print needs the Pi and
is a manual line in the output, never auto-passed.
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
VERDICT_EXIT = {"GO": 0, "KEEP SOAKING": 1, "NO-GO": 2}


def percentile(values, q):
    """Nearest-rank percentile; None for an empty list."""
    if not values:
        return None
    s = sorted(values)
    return s[max(0, math.ceil(q / 100 * len(s)) - 1)]


def success_stats(points):
    """points: [(ts, 0|1)] -> (success_pct, fails, samples, longest_outage_s)."""
    pts = sorted(points)
    if not pts:
        return None
    fails = sum(1 for _, v in pts if v < 0.5)
    step = _median_step(pts)
    longest, run_start = 0, None
    for ts, v in pts:
        if v < 0.5:
            if run_start is None:
                run_start = ts
            longest = max(longest, ts - run_start + step)
        else:
            run_start = None
    return (100.0 * (len(pts) - fails) / len(pts), fails, len(pts), longest)


def _median_step(pts):
    gaps = sorted(b[0] - a[0] for a, b in zip(pts, pts[1:]) if b[0] > a[0])
    return gaps[len(gaps) // 2] if gaps else 0


def rtt_p95_ms(points):
    p = percentile([v for _, v in points], 95)
    return None if p is None else p * 1000.0


def evaluate(bundle, targets, soak_start, min_days, now=None):
    """Return a result dict. bundle = {"end": ts, "days": n, "series": {kind: {name: [[ts,v],..]}}}."""
    end = bundle["end"]
    now = now if now is not None else end
    soak_days = max(0.0, (now - soak_start.timestamp()) / 86400)
    rows = {}
    for name in targets:
        icmp = success_stats(bundle["series"].get("icmp", {}).get(name, []))
        ipp = success_stats(bundle["series"].get("ipp", {}).get(name, []))
        rtt = rtt_p95_ms(bundle["series"].get("rtt", {}).get(name, []))
        checks = []
        def chk(label, val, ok, fmt):
            checks.append({"label": label, "value": None if val is None else fmt(val),
                           "ok": None if val is None else bool(ok)})
        chk("ICMP success >= %.1f %%" % THRESHOLDS["success_pct"], icmp and icmp[0],
            icmp and icmp[0] >= THRESHOLDS["success_pct"], lambda v: "%.3f %%" % v)
        chk(":631 success >= %.1f %%" % THRESHOLDS["success_pct"], ipp and ipp[0],
            ipp and ipp[0] >= THRESHOLDS["success_pct"], lambda v: "%.3f %%" % v)
        chk("longest ICMP outage <= %d s" % THRESHOLDS["outage_s"], icmp and icmp[3],
            icmp and icmp[3] <= THRESHOLDS["outage_s"], lambda v: "%d s" % v)
        chk("longest :631 outage <= %d s" % THRESHOLDS["outage_s"], ipp and ipp[3],
            ipp and ipp[3] <= THRESHOLDS["outage_s"], lambda v: "%d s" % v)
        chk("ICMP RTT p95 <= %d ms" % THRESHOLDS["rtt_p95_ms"], rtt,
            rtt is not None and rtt <= THRESHOLDS["rtt_p95_ms"], lambda v: "%.0f ms" % v)
        rows[name] = {"checks": checks, "icmp": icmp, "ipp": ipp, "rtt": rtt}
    for name, r in rows.items():
        if name == CONTROL:
            r["verdict"] = "CONTROL"
            continue
        failed = [c for c in r["checks"] if c["ok"] is False]
        missing = [c for c in r["checks"] if c["ok"] is None]
        if failed:
            r["verdict"] = "NO-GO" if soak_days >= min_days else "KEEP SOAKING"
        elif missing:
            r["verdict"] = "KEEP SOAKING"
        elif soak_days < min_days:
            r["verdict"] = "KEEP SOAKING"
        else:
            r["verdict"] = "GO"
        r["failed"] = [c["label"] for c in failed]
    judged = [r["verdict"] for n, r in rows.items() if n != CONTROL]
    overall = ("NO-GO" if "NO-GO" in judged else
               "KEEP SOAKING" if (not judged or "KEEP SOAKING" in judged) else "GO")
    return {"rows": rows, "overall": overall, "soak_days": soak_days, "min_days": min_days,
            "days": bundle.get("days"), "end": end}


def render(res, md=False):
    h = "#" if md else ""
    end = dt.datetime.fromtimestamp(res["end"], dt.timezone.utc).strftime("%Y-%m-%d %H:%MZ")
    out = [f"{h} F2 Wi-Fi soak review - window {res['days']} d to {end}".strip(),
           f"Soak day {res['soak_days']:.1f} of {res['min_days']} minimum. OVERALL: {res['overall']}", ""]
    for name, r in res["rows"].items():
        out.append(f"{name}: {r['verdict']}" + (f"  (failed: {'; '.join(r['failed'])})" if r.get("failed") else ""))
        for c in r["checks"]:
            mark = {True: "PASS", False: "FAIL", None: "n/a "}[c["ok"]]
            out.append(f"  {mark}  {c['label']:<34} {c['value'] if c['value'] else 'no data'}")
        out.append("")
    out += ["Manual (not auto-judged): weekly F4 test print over black-wifi and colour-wifi (needs the Pi; see",
            "docs/wifi-test-plan.md). Go/no-go is Marc's: this script only recommends.",
            "Rule: GO needs every check PASS and >= %d soak days; any FAIL before that = KEEP SOAKING." % res["min_days"]]
    return "\n".join(out) + "\n"


# --- Prometheus (read-only GET) ---------------------------------------------------------------
def _query_range(prom, query, start, end, step):
    qs = urllib.parse.urlencode({"query": query, "start": start, "end": end, "step": step})
    with urllib.request.urlopen(f"{prom}/api/v1/query_range?{qs}", timeout=30) as r:
        data = json.load(r)
    if data.get("status") != "success":
        raise RuntimeError(f"prometheus: {data}")
    return data["data"]["result"]


def fetch_bundle(prom, days, targets, now=None):
    end = int(now if now is not None else dt.datetime.now(dt.timezone.utc).timestamp())
    start = end - days * 86400
    series = {"icmp": {}, "ipp": {}, "rtt": {}}
    # Prometheus caps 11000 points per query; step 60 s for 7 d = 10080. Fine for --days <= 7.
    for kind, job in JOBS.items():
        for res in _query_range(prom, f'probe_success{{job="{job}"}}', start, end, 60):
            inst = res["metric"].get("instance", "")
            for name, sub in targets.items():
                if sub in inst:
                    series[kind][name] = [[float(t), float(v)] for t, v in res["values"]]
    for res in _query_range(prom, f'probe_icmp_duration_seconds{{job="{JOBS["icmp"]}",phase="rtt"}}', start, end, 60):
        inst = res["metric"].get("instance", "")
        for name, sub in targets.items():
            if sub in inst:
                series["rtt"][name] = [[float(t), float(v)] for t, v in res["values"]]
    return {"end": end, "days": days, "series": series}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--prom", default=os.environ.get("SOAK_PROM", "http://192.168.0.5:30090"))
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--from", dest="src")
    ap.add_argument("--save")
    ap.add_argument("--md", action="store_true")
    ap.add_argument("--soak-start", default="2026-10-21")
    ap.add_argument("--min-days", type=int, default=28)
    ap.add_argument("--target", action="append", default=[])
    a = ap.parse_args(argv)
    targets = dict(DEFAULT_TARGETS)
    for t in a.target:
        k, _, v = t.partition("=")
        targets[k] = v
    try:
        if a.src:
            with open(a.src) as f:
                bundle = json.load(f)
        else:
            if a.days > 7:
                print("--days > 7 exceeds Prometheus' 11000-point cap at 60 s step", file=sys.stderr)
                return 3
            bundle = fetch_bundle(a.prom, a.days, targets)
        if a.save:
            with open(a.save, "w") as f:
                json.dump(bundle, f)
        start = dt.datetime.strptime(a.soak_start, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
        now = bundle["end"] if a.src else None
        res = evaluate(bundle, targets, start, a.min_days, now)
    except (OSError, ValueError, KeyError, RuntimeError) as e:
        print(f"soak-review: {e}", file=sys.stderr)
        return 3
    sys.stdout.write(render(res, a.md))
    return VERDICT_EXIT[res["overall"]]


if __name__ == "__main__":
    sys.exit(main())
