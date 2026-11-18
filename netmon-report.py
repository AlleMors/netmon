#!/usr/bin/env python3
"""netmon-report.py — riepilogo del monitoraggio netmon.

Uso:
  netmon-report.py [log.csv] [--hours 24] [--svg grafico.svg]
"""
import argparse
import csv
import datetime as dt
import os
import sys
from collections import defaultdict


def parse_ts(s):
    try:
        return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")
    except (ValueError, TypeError):
        return None


def write_svg(path, by):
    W, H = 1000, 400
    ML, MR, MT, MB = 60, 20, 20, 40
    series = []
    for target, items in by.items():
        pts = [(ts, float(r["rtt_avg"])) for ts, r in items if r["rtt_avg"]]
        if pts:
            series.append((target, pts))
    if not series:
        return
    tmin = min(p[0] for _, pts in series for p in pts)
    tmax = max(p[0] for _, pts in series for p in pts)
    ymax = max(p[1] for _, pts in series for p in pts) * 1.1 or 1
    span = max(1, (tmax - tmin).total_seconds())

    def x(ts):
        return ML + (ts - tmin).total_seconds() / span * (W - ML - MR)

    def y(v):
        return H - MB - (v / ymax) * (H - MT - MB)

    colors = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c"]
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'font-family="sans-serif" font-size="12">',
        f'<rect width="{W}" height="{H}" fill="white"/>',
        f'<line x1="{ML}" y1="{H-MB}" x2="{W-MR}" y2="{H-MB}" stroke="#999"/>',
        f'<line x1="{ML}" y1="{MT}" x2="{ML}" y2="{H-MB}" stroke="#999"/>',
        f'<text x="{ML}" y="{H-10}" fill="#666">{tmin:%d/%m %H:%M}</text>',
        f'<text x="{W-MR-80}" y="{H-10}" fill="#666">{tmax:%d/%m %H:%M}</text>',
        f'<text x="5" y="{MT+10}" fill="#666">{ymax:.0f} ms</text>',
    ]
    for i, (target, pts) in enumerate(series):
        c = colors[i % len(colors)]
        d = " ".join(f"{x(ts):.1f},{y(v):.1f}" for ts, v in pts)
        out.append(f'<polyline fill="none" stroke="{c}" stroke-width="1.5" points="{d}"/>')
        out.append(f'<text x="{ML+10}" y="{MT+15+i*16}" fill="{c}">{target}</text>')
    out.append("</svg>")
    with open(path, "w") as f:
        f.write("\n".join(out))
    print(f"\nGrafico SVG scritto in {path}")


def main():
    ap = argparse.ArgumentParser(description="Riepilogo netmon")
    ap.add_argument("log", nargs="?", default="/var/log/netmon/netmon.csv")
    ap.add_argument("--hours", type=float, default=24, help="finestra in ore (default 24)")
    ap.add_argument("--svg", help="scrivi un grafico SVG del RTT medio")
    args = ap.parse_args()

    if not os.path.exists(args.log):
        sys.exit(f"Log non trovato: {args.log}")

    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=args.hours)
    rows = []
    with open(args.log, newline="") as f:
        for r in csv.DictReader(f):
            ts = parse_ts(r.get("timestamp", ""))
            if ts is None or ts < cutoff:
                continue
            rows.append((ts, r))

    if not rows:
        sys.exit("Nessun dato nel periodo richiesto.")

    by = defaultdict(list)
    for ts, r in rows:
        by[r["target"]].append((ts, r))

    print(f"Periodo: ultime {args.hours:g} h — {len(rows)} campioni\n")
    print(f"{'Target':<16}{'Camp.':>6}{'Loss%':>8}{'Avg':>8}{'P95':>8}{'Max':>8}")
    print("-" * 54)
    for target, items in sorted(by.items()):
        sent = sum(int(r["sent"] or 0) for _, r in items)
        recv = sum(int(r["received"] or 0) for _, r in items)
        loss = 100.0 * (1 - recv / sent) if sent else 100.0
        avgs = sorted(float(r["rtt_avg"]) for _, r in items if r["rtt_avg"])
        if avgs:
            avg = sum(avgs) / len(avgs)
            p95 = avgs[min(len(avgs) - 1, int(len(avgs) * 0.95))]
            mx = max(float(r["rtt_max"]) for _, r in items if r["rtt_max"])
        else:
            avg = p95 = mx = float("nan")
        print(f"{target:<16}{len(items):>6}{loss:>8.2f}{avg:>8.1f}{p95:>8.1f}{mx:>8.1f}")

    worst = sorted(
        rows,
        key=lambda x: (float(x[1]["loss_pct"] or 0), float(x[1]["rtt_avg"] or 0)),
        reverse=True,
    )[:10]
    print("\nPeggiori 10 campioni:")
    for ts, r in worst:
        print(f"  {ts:%Y-%m-%d %H:%M}  {r['target']:<15} "
              f"loss={r['loss_pct']:>5}%  avg={r['rtt_avg'] or '-':>6} ms")

    if args.svg:
        write_svg(args.svg, by)


if __name__ == "__main__":
    main()
