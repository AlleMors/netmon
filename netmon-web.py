#!/usr/bin/env python3
"""netmon-web.py — dashboard web minimale per i dati di netmon.

Legge /var/log/netmon/netmon.csv e serve:
  GET /                → pagina HTML (Chart.js da CDN, lato browser)
  GET /api/data?hours= → JSON con serie e riepilogo
  GET /health          → "ok"

Nessuna dipendenza esterna lato server (solo stdlib).
"""
import csv
import datetime as dt
import json
import os
import sys
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

LOG = os.environ.get("NETMON_LOG", "/var/log/netmon/netmon.csv")
PORT = int(os.environ.get("NETMON_WEB_PORT", "8080"))
BIND = os.environ.get("NETMON_WEB_BIND", "0.0.0.0")
MAX_POINTS = 700


def parse_ts(s):
    try:
        return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")
    except (ValueError, TypeError):
        return None


def downsample(points, maxpts=MAX_POINTS):
    """Riduce i punti mantenendo i picchi (max RTT / max loss per bucket)."""
    if len(points) <= maxpts:
        # Rimuove sempre il campo interno _ts (datetime non serializzabile in JSON)
        return [{"t": p["t"], "avg": p["avg"], "max": p["max"], "loss": p["loss"]}
                for p in points]
    t0, t1 = points[0]["_ts"], points[-1]["_ts"]
    span = max(1.0, (t1 - t0).total_seconds())
    # maxpts-1 intervalli → al più maxpts bucket (l'ultimo punto cade nel bordo)
    bw = span / max(1, maxpts - 1)
    buckets = OrderedDict()
    for p in points:
        k = min(maxpts - 1, int((p["_ts"] - t0).total_seconds() / bw))
        b = buckets.get(k)
        if b is None:
            b = buckets[k] = {"t": p["t"], "avg_sum": 0.0, "avg_n": 0,
                              "max": None, "loss": 0.0}
        if p["avg"] is not None:
            b["avg_sum"] += p["avg"]
            b["avg_n"] += 1
        if p["max"] is not None and (b["max"] is None or p["max"] > b["max"]):
            b["max"] = p["max"]
        if p["loss"] is not None and p["loss"] > b["loss"]:
            b["loss"] = p["loss"]
    out = []
    for b in buckets.values():
        out.append({
            "t": b["t"],
            "avg": (b["avg_sum"] / b["avg_n"]) if b["avg_n"] else None,
            "max": b["max"],
            "loss": b["loss"],
        })
    return out


def load(hours):
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
    series = OrderedDict()
    sent, recv = {}, {}
    if not os.path.exists(LOG):
        return {"series": {}, "summary": {}, "generated": dt.datetime.now().isoformat()}
    with open(LOG, newline="") as f:
        for r in csv.DictReader(f):
            ts = parse_ts(r.get("timestamp", ""))
            if ts is None or ts < cutoff:
                continue
            tgt = r["target"]
            series.setdefault(tgt, []).append({
                "t": r["timestamp"],
                "_ts": ts,
                "avg": float(r["rtt_avg"]) if r["rtt_avg"] else None,
                "max": float(r["rtt_max"]) if r["rtt_max"] else None,
                "loss": float(r["loss_pct"]) if r["loss_pct"] else None,
            })
            sent[tgt] = sent.get(tgt, 0) + int(r["sent"] or 0)
            recv[tgt] = recv.get(tgt, 0) + int(r["received"] or 0)

    summary = OrderedDict()
    for tgt, pts in series.items():
        avgs = sorted(p["avg"] for p in pts if p["avg"] is not None)
        summary[tgt] = {
            "samples": len(pts),
            "loss": (100.0 * (1 - recv[tgt] / sent[tgt])) if sent.get(tgt) else 100.0,
            "avg": (sum(avgs) / len(avgs)) if avgs else None,
            "p95": avgs[min(len(avgs) - 1, int(len(avgs) * 0.95))] if avgs else None,
            "max": max((p["max"] for p in pts if p["max"] is not None), default=None),
            "last": pts[-1]["avg"] if pts else None,
            "last_ts": pts[-1]["t"] if pts else None,
        }
        series[tgt] = downsample(series[tgt])

    return {"series": series, "summary": summary,
            "generated": dt.datetime.now().isoformat()}


PAGE = r"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>netmon</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root { --bg:#0f172a; --card:#1e293b; --fg:#e2e8f0; --muted:#94a3b8; --line:#334155; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
         background:var(--bg); color:var(--fg); padding:24px; }
  h1 { font-size:20px; margin:0; }
  header { display:flex; align-items:center; gap:16px; flex-wrap:wrap; margin-bottom:20px; }
  .spacer { flex:1; }
  #window button { background:var(--card); color:var(--muted); border:1px solid var(--line);
         padding:6px 12px; border-radius:8px; cursor:pointer; margin-right:6px; }
  #window button.active { background:#2563eb; color:#fff; border-color:#2563eb; }
  #status { color:var(--muted); font-size:13px; }
  #cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
           gap:14px; margin-bottom:20px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }
  .card .name { color:var(--muted); font-size:13px; margin-bottom:8px; word-break:break-all; }
  .card .big { font-size:26px; font-weight:600; }
  .card .sub { color:var(--muted); font-size:12px; margin-top:6px; line-height:1.5; }
  .bad { color:#f87171; } .warn { color:#fbbf24; } .good { color:#4ade80; }
  .panel { background:var(--card); border:1px solid var(--line); border-radius:12px;
           padding:16px; margin-bottom:20px; }
  .panel h2 { font-size:14px; color:var(--muted); font-weight:600; margin:0 0 12px; }
  canvas { width:100% !important; height:280px !important; }
</style>
</head>
<body>
<header>
  <h1>netmon</h1>
  <div id="window">
    <button data-h="1">1h</button>
    <button data-h="6">6h</button>
    <button data-h="24" class="active">24h</button>
    <button data-h="168">7g</button>
  </div>
  <div class="spacer"></div>
  <span id="status">caricamento…</span>
</header>
<section id="cards"></section>
<div class="panel"><h2>Latenza media (ms) — picchi per bucket</h2><canvas id="rtt"></canvas></div>
<div class="panel"><h2>Perdita pacchetti (%)</h2><canvas id="loss"></canvas></div>

<script>
const COLORS = ['#60a5fa','#f87171','#4ade80','#c084fc','#fb923c','#22d3ee'];
const state = { hours: 24, rtt: null, loss: null };
let colorMap = {};

function colorFor(t, i) {
  if (!(t in colorMap)) colorMap[t] = COLORS[Object.keys(colorMap).length % COLORS.length];
  return colorMap[t];
}
function fmt(v, d=1) { return (v === null || v === undefined || isNaN(v)) ? '—' : v.toFixed(d); }
function cls(loss) { return loss > 5 ? 'bad' : loss > 0.5 ? 'warn' : 'good'; }

function renderCards(summary) {
  const el = document.getElementById('cards');
  const keys = Object.keys(summary);
  if (!keys.length) { el.innerHTML = '<div class="card">Nessun dato ancora.</div>'; return; }
  el.innerHTML = keys.map(t => {
    const s = summary[t];
    return `<div class="card">
      <div class="name">${t}</div>
      <div class="big ${cls(s.loss)}">${fmt(s.last)} ms</div>
      <div class="sub">
        loss <span class="${cls(s.loss)}">${fmt(s.loss,2)}%</span> ·
        avg ${fmt(s.avg)} · p95 ${fmt(s.p95)} · max ${fmt(s.max)}<br>
        ${s.samples} campioni
      </div></div>`;
  }).join('');
}

function buildSeries(series, key) {
  return Object.keys(series).map((t, i) => ({
    label: t,
    data: series[t].map(p => ({ x: Date.parse(p.t), y: p[key] })),
    borderColor: colorFor(t, i),
    backgroundColor: colorFor(t, i),
    borderWidth: 1.6, pointRadius: 0, tension: 0.2, spanGaps: true,
  }));
}

function renderCharts(series) {
  const labels = Object.keys(series);
  const rttData = buildSeries(series, 'avg');
  const lossData = buildSeries(series, 'loss');

  if (!state.rtt) {
    state.rtt = new Chart(document.getElementById('rtt'), {
      type: 'line', data: { datasets: rttData },
      options: {
        responsive: true, maintainAspectRatio: false, parsing: false,
        interaction: { mode: 'nearest', intersect: false },
        plugins: { legend: { labels: { color: '#94a3b8', boxWidth: 12 } } },
        scales: {
          x: { type: 'linear', ticks: { color: '#64748b',
               callback: v => new Date(v).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) },
               grid: { color: 'rgba(51,65,85,.5)' } },
          y: { beginAtZero: true, ticks: { color: '#64748b' }, grid: { color: 'rgba(51,65,85,.5)' } }
        }
      }
    });
  } else { state.rtt.data.datasets = rttData; state.rtt.update('none'); }

  if (!state.loss) {
    state.loss = new Chart(document.getElementById('loss'), {
      type: 'line', data: { datasets: lossData },
      options: {
        responsive: true, maintainAspectRatio: false, parsing: false,
        interaction: { mode: 'nearest', intersect: false },
        plugins: { legend: { labels: { color: '#94a3b8', boxWidth: 12 } } },
        scales: {
          x: { type: 'linear', ticks: { color: '#64748b',
               callback: v => new Date(v).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) },
               grid: { color: 'rgba(51,65,85,.5)' } },
          y: { beginAtZero: true, max: 100, ticks: { color: '#64748b' },
               grid: { color: 'rgba(51,65,85,.5)' } }
        }
      }
    });
  } else { state.loss.data.datasets = lossData; state.loss.update('none'); }
}

async function refresh() {
  try {
    const r = await fetch(`/api/data?hours=${state.hours}`);
    const d = await r.json();
    renderCards(d.summary);
    renderCharts(d.series);
    document.getElementById('status').textContent =
      'aggiornato ' + new Date().toLocaleTimeString() + ' · ultime ' + state.hours + 'h';
  } catch (e) {
    document.getElementById('status').textContent = 'errore: ' + e;
  }
}

document.querySelectorAll('#window button').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('#window button').forEach(x => x.classList.remove('active'));
  b.classList.add('active');
  state.hours = parseInt(b.dataset.h, 10);
  refresh();
}));

refresh();
setInterval(refresh, 60000);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="text/plain; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if u.path == "/health":
            return self._send(200, "ok")
        if u.path == "/api/data":
            q = parse_qs(u.query)
            try:
                hours = float(q.get("hours", ["24"])[0])
            except ValueError:
                hours = 24.0
            hours = min(max(hours, 0.05), 24 * 90)
            return self._send(200, json.dumps(load(hours), default=str),
                              "application/json; charset=utf-8")
        return self._send(404, "not found")

    def log_message(self, fmt, *args):
        pass  # niente spam nei log di sistema


def main():
    server = ThreadingHTTPServer((BIND, PORT), Handler)
    print(f"netmon-web in ascolto su http://{BIND}:{PORT}/ (log: {LOG})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
