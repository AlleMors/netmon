"""Test per netmon-web.py."""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest


def _rows(n=5, target="1.1.1.1"):
    return "".join(
        f"2026-11-18T09:{i:02d}:00+0000,{target},10,10,0.0,10.0,{15 + i}.0,{30 + i}.0,0.5\n"
        for i in range(n)
    )


def test_downsample_keeps_short_series_intact(web_mod):
    pts = [{"t": "x", "_ts": 1, "avg": 1.0, "max": 2.0, "loss": 0.0}]
    out = web_mod.downsample(pts, maxpts=10)
    assert out == [{"t": "x", "avg": 1.0, "max": 2.0, "loss": 0.0}]
    assert "_ts" not in out[0]


def test_downsample_preserves_peaks(web_mod):
    import datetime as dt
    pts = []
    base = dt.datetime(2026, 11, 18, 9, 0)
    for i in range(100):
        ts = base + dt.timedelta(minutes=i)
        pts.append({"t": ts.isoformat(), "_ts": ts,
                    "avg": float(i), "max": float(i),
                    "loss": 50.0 if i == 37 else 0.0})
    out = web_mod.downsample(pts, maxpts=10)
    assert len(out) <= 10
    assert max(p["loss"] for p in out) == 50.0
    assert max(p["max"] for p in out) == 99.0


def test_load_missing_log_returns_empty(web_mod, tmp_path, monkeypatch):
    monkeypatch.setattr(web_mod, "LOG", str(tmp_path / "missing.csv"))
    data = web_mod.load(24)
    assert data["series"] == {}
    assert data["summary"] == {}


def test_load_summary_stats(web_mod, write_csv, monkeypatch):
    csv = write_csv([_rows(5)])
    monkeypatch.setattr(web_mod, "LOG", str(csv))
    data = web_mod.load(24 * 365 * 200)  # finestra ampia per evitare cutoff
    s = data["summary"]["1.1.1.1"]
    assert s["samples"] == 5
    assert s["loss"] == 0.0
    assert s["avg"] == pytest.approx(17.0)
    assert s["max"] == 34.0
    assert s["last"] == 19.0


def test_http_endpoints(web_mod, write_csv, monkeypatch):
    csv = write_csv([_rows(2)])
    monkeypatch.setattr(web_mod, "LOG", str(csv))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), web_mod.Handler)
    port = srv.server_address[1]
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{port}"
        assert urllib.request.urlopen(base + "/health").read() == b"ok"
        page = urllib.request.urlopen(base + "/").read().decode()
        assert "<title>netmon</title>" in page
        data = json.load(urllib.request.urlopen(base + "/api/data?hours=999999"))
        assert "1.1.1.1" in data["series"]
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(base + "/nope")
        assert exc.value.code == 404
    finally:
        srv.shutdown()
        srv.server_close()
