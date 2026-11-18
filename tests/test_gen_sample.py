"""Test per tools/gen_sample.py."""
import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "gen_sample.py"


def run(*args):
    res = subprocess.run([sys.executable, str(SCRIPT), *args],
                         capture_output=True, text=True, check=True)
    return list(csv.DictReader(res.stdout.splitlines()))


def test_generates_expected_columns_and_rows():
    rows = run("--hours", "1", "--step", "60", "--seed", "1")
    assert len(rows) == 60 * 4  # 60 campioni x 4 target
    assert set(rows[0]) == {"timestamp", "target", "sent", "received",
                            "loss_pct", "rtt_min", "rtt_avg", "rtt_max", "rtt_mdev"}


def test_output_is_deterministic():
    args = ("--hours", "1", "--seed", "7", "--end", "2026-11-18T12:00:00+0000")
    a = run(*args)
    b = run(*args)
    assert a == b
    assert a[-1]["timestamp"] == "2026-11-18T11:59:00+0000"


def test_loss_consistent_with_received():
    for r in run("--hours", "2", "--seed", "3"):
        sent, recv = int(r["sent"]), int(r["received"])
        assert 0 <= recv <= sent
        if sent:
            expected = 100.0 * (sent - recv) / sent
            assert abs(float(r["loss_pct"]) - expected) < 1e-6
