"""Test per netmon-report.py."""
import datetime as dt
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "netmon-report.py"
TS = "2026-11-18T09:00:00+0000"


def row(target, loss="0", avg="18.3", mx="62.4", sent="10", recv="10"):
    return f"{TS},{target},{sent},{recv},{loss},12.1,{avg},{mx},1.2\n"


def test_parse_ts_valid(report_mod):
    ts = report_mod.parse_ts(TS)
    assert ts is not None
    assert ts.utcoffset() == dt.timedelta(0)


@pytest.mark.parametrize("bad", ["", "not-a-date", "2026-11-18T09:00:00"])
def test_parse_ts_invalid(report_mod, bad):
    assert report_mod.parse_ts(bad) is None


def test_write_svg_creates_file(report_mod, tmp_path):
    by = {
        "1.1.1.1": [
            (dt.datetime(2026, 11, 18, 9, 0), {"rtt_avg": "18.3"}),
            (dt.datetime(2026, 11, 18, 10, 0), {"rtt_avg": "25.0"}),
        ],
        "192.168.1.1": [
            (dt.datetime(2026, 11, 18, 9, 0), {"rtt_avg": "1.2"}),
        ],
    }
    out = tmp_path / "graf.svg"
    report_mod.write_svg(str(out), by)
    text = out.read_text(encoding="utf-8")
    assert text.startswith("<svg")
    assert text.rstrip().endswith("</svg>")
    assert "1.1.1.1" in text and "192.168.1.1" in text
    assert "<polyline" in text


def test_write_svg_skips_rows_without_rtt(report_mod, tmp_path):
    out = tmp_path / "empty.svg"
    report_mod.write_svg(str(out), {"1.1.1.1": [(dt.datetime.now(), {"rtt_avg": ""})]})
    assert not out.exists()


def test_cli_reports_loss_and_stats(write_csv):
    csv = write_csv([row("1.1.1.1", loss="0", avg="18.3"),
                     row("192.168.1.1", loss="10", avg="1.2", sent="10", recv="9")])
    res = subprocess.run([sys.executable, str(SCRIPT), str(csv), "--hours", "24"],
                         capture_output=True, text=True, check=True)
    assert "1.1.1.1" in res.stdout
    assert "192.168.1.1" in res.stdout
    assert "10.00" in res.stdout  # loss calcolata da sent/received
    assert "Peggiori 10 campioni" in res.stdout


def test_cli_rejects_missing_file(tmp_path):
    res = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path / "nope.csv")],
                         capture_output=True, text=True)
    assert res.returncode != 0
    assert "Log non trovato" in res.stderr


def test_cli_reports_empty_window(write_csv):
    csv = write_csv([row("1.1.1.1")])
    res = subprocess.run([sys.executable, str(SCRIPT), str(csv), "--hours", "0.001"],
                         capture_output=True, text=True)
    assert res.returncode != 0
    assert "Nessun dato" in res.stderr
