#!/usr/bin/env python3
"""Genera un CSV di esempio realistico per netmon.

I dati simulano 24 ore di campionamenti ogni 60 s su quattro target:
gateway locale stabile, primo hop ISP, due resolver pubblici con
congestione serale e perdita occasionale. Non contiene dati reali.

Uso:
  python3 tools/gen_sample.py > sample.csv
  python3 tools/gen_sample.py --hours 6 --end "2026-11-18T12:00:00+0000" > sample.csv
"""
import argparse
import datetime as dt
import random

HEADER = "timestamp,target,sent,received,loss_pct,rtt_min,rtt_avg,rtt_max,rtt_mdev"

# base: RTT medio (ms); jitter: dispersione; spike_*: picchi occasionali;
# loss: probabilità di perdita per pacchetto; evening: fattore di congestione.
TARGETS = {
    "192.168.1.1": dict(base=1.2, jitter=0.25, spike_p=0.00, spike=0.0, loss=0.000, evening=1.0),
    "203.0.113.1": dict(base=6.5, jitter=0.90, spike_p=0.03, spike=18.0, loss=0.002, evening=1.6),
    "1.1.1.1":     dict(base=18.5, jitter=2.00, spike_p=0.05, spike=90.0, loss=0.006, evening=2.2),
    "8.8.8.8":     dict(base=19.5, jitter=2.20, spike_p=0.05, spike=95.0, loss=0.007, evening=2.2),
}
SENT = 10  # pacchetti per campione, come NETMON_COUNT di default


def parse_end(s):
    if not s:
        return dt.datetime.now().astimezone()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z"):
        try:
            return dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise SystemExit(f"Formato --end non valido: {s}")


def congestion(ts, evening):
    """Fattore di congestione, più alto nelle ore serali (18-23)."""
    if 18 <= ts.hour < 23:
        return evening
    if 8 <= ts.hour < 18:
        return 1.0 + (evening - 1.0) * 0.35
    return 1.0


def sample_target(rng, cfg, ts):
    factor = congestion(ts, cfg["evening"])
    lost = sum(1 for _ in range(SENT) if rng.random() < cfg["loss"] * factor)
    recv = SENT - lost
    loss_pct = 100.0 * lost / SENT
    if recv == 0:
        return SENT, 0, f"{loss_pct:g}", "", "", "", ""

    avg = max(0.1, cfg["base"] * factor + rng.gauss(0, cfg["jitter"]))
    if rng.random() < cfg["spike_p"]:
        avg += rng.uniform(0.5, 1.0) * cfg["spike"]
    rmin = max(0.1, avg * rng.uniform(0.80, 0.95))
    rmax = avg + max(0.2, cfg["spike"] * 0.25 * rng.random() + cfg["jitter"])
    mdev = (rmax - rmin) / 4.0
    return (SENT, recv, f"{loss_pct:g}",
            f"{rmin:.3f}", f"{avg:.3f}", f"{rmax:.3f}", f"{mdev:.3f}")


def main():
    ap = argparse.ArgumentParser(description="Genera un CSV di esempio per netmon")
    ap.add_argument("--hours", type=float, default=24, help="durata simulata (default 24)")
    ap.add_argument("--step", type=int, default=60, help="secondi tra i campioni (default 60)")
    ap.add_argument("--end", help="timestamp finale (default: ora attuale)")
    ap.add_argument("--seed", type=int, default=42, help="seme per output riproducibile")
    args = ap.parse_args()

    end = parse_end(args.end)
    n = int(args.hours * 3600 / args.step)
    rng = random.Random(args.seed)

    print(HEADER)
    for i in range(n, 0, -1):
        ts = end - dt.timedelta(seconds=i * args.step)
        stamp = ts.strftime("%Y-%m-%dT%H:%M:%S%z")
        for target, cfg in TARGETS.items():
            sent, recv, loss, rmin, avg, rmax, mdev = sample_target(rng, cfg, ts)
            print(f"{stamp},{target},{sent},{recv},{loss},{rmin},{avg},{rmax},{mdev}")


if __name__ == "__main__":
    main()
