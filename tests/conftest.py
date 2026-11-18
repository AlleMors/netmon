"""Carica i moduli con trattino nel nome (netmon-report.py, netmon-web.py)."""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def report_mod():
    return _load("netmon_report", "netmon-report.py")


@pytest.fixture(scope="session")
def web_mod():
    return _load("netmon_web", "netmon-web.py")


@pytest.fixture
def write_csv(tmp_path):
    """Scrive un CSV netmon e restituisce il path."""
    def _write(rows, name="netmon.csv"):
        path = tmp_path / name
        path.write_text(
            "timestamp,target,sent,received,loss_pct,rtt_min,rtt_avg,rtt_max,rtt_mdev\n"
            + "".join(rows),
            encoding="utf-8",
        )
        return path
    return _write
