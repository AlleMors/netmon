#!/usr/bin/env bash
# install.sh — installa netmon come servizio systemd su Ubuntu.
# Eseguire con sudo dalla directory che contiene questi file.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Errore: esegui con sudo." >&2
  exit 1
fi

SRC="$(cd "$(dirname "$0")" && pwd)"
PORT="${1:-8080}"

install -m 755 "$SRC/netmon.sh"          /usr/local/bin/netmon.sh
install -m 755 "$SRC/netmon-report.py"   /usr/local/bin/netmon-report.py
install -m 755 "$SRC/netmon-web.py"      /usr/local/bin/netmon-web.py
install -m 644 "$SRC/netmon.service"     /etc/systemd/system/netmon.service
install -m 644 "$SRC/netmon.timer"       /etc/systemd/system/netmon.timer
install -m 644 "$SRC/netmon-web.service" /etc/systemd/system/netmon-web.service
install -m 644 "$SRC/netmon.logrotate"   /etc/logrotate.d/netmon

# Porta della dashboard (default 8080). Es.: sudo ./install.sh 8082
sed -i "s/^Environment=NETMON_WEB_PORT=.*/Environment=NETMON_WEB_PORT=$PORT/" \
  /etc/systemd/system/netmon-web.service

mkdir -p /var/log/netmon
chmod 755 /var/log/netmon

systemctl daemon-reload
systemctl enable --now netmon.timer

# Ferma la dashboard per verificare che la porta scelta sia libera.
# Se è occupata da un altro servizio, esce con errore invece di lasciare
# netmon-web in crash-loop.
systemctl stop netmon-web.service 2>/dev/null || true
if command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | grep -q ":$PORT\b"; then
  echo "ERRORE: la porta $PORT è già in uso da un altro servizio." >&2
  echo "Scegli un'altra porta, es.: sudo ./install.sh 8099" >&2
  exit 1
fi

systemctl enable --now netmon-web.service
# Riavvia sempre la dashboard: 'enable --now' non riavvia un processo già attivo
systemctl restart netmon-web.service

echo
echo "Installato. Verifica con:"
echo "  systemctl status netmon.timer netmon-web.service"
echo "  systemctl list-timers netmon.timer"
echo "  tail -f /var/log/netmon/netmon.csv"
echo
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo "Dashboard web:  http://${IP:-localhost}:$PORT/"
echo "Riepilogo:      netmon-report.py --hours 24"
echo "Grafico:        netmon-report.py --hours 24 --svg /tmp/netmon.svg"
