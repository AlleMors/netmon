#!/usr/bin/env bash
# netmon.sh — campiona latenza e perdita verso più target e scrive un CSV.
# Pensato per girare sul Mac mini cablato al router (punto di misura senza powerline).
set -u

LOG_DIR="${NETMON_LOG_DIR:-/var/log/netmon}"
LOG_FILE="$LOG_DIR/netmon.csv"
# Gateway | Internet (Cloudflare) | Internet (Google)
# Aggiungi il primo hop del tuo ISP con NETMON_TARGETS, es.:
#   NETMON_TARGETS="192.168.1.1 203.0.113.1 1.1.1.1 8.8.8.8"
TARGETS="${NETMON_TARGETS:-192.168.1.1 1.1.1.1 8.8.8.8}"
COUNT="${NETMON_COUNT:-10}"
INTERVAL="${NETMON_INTERVAL:-1}"
TIMEOUT="${NETMON_TIMEOUT:-1}"

mkdir -p "$LOG_DIR" 2>/dev/null || true
if [ ! -f "$LOG_FILE" ]; then
  echo "timestamp,target,sent,received,loss_pct,rtt_min,rtt_avg,rtt_max,rtt_mdev" > "$LOG_FILE"
fi

ts=$(date '+%Y-%m-%dT%H:%M:%S%z')

# Word splitting voluto: NETMON_TARGETS è una lista separata da spazi.
# shellcheck disable=SC2086
for t in $TARGETS; do
  out=$(ping -c "$COUNT" -i "$INTERVAL" -W "$TIMEOUT" "$t" 2>/dev/null || true)
  stats=$(printf '%s\n' "$out" | tail -2)

  sent=$(printf '%s\n'  "$stats" | grep -oP '\d+(?= packets transmitted)' | head -1)
  recv=$(printf '%s\n'  "$stats" | grep -oP '\d+(?= received)'           | head -1)
  loss=$(printf '%s\n'  "$stats" | grep -oP '[\d.]+(?=% packet loss)'     | head -1)
  rtt=$(printf '%s\n'   "$stats" | grep -oP 'min/avg/max/mdev = [\d.]+/[\d.]+/[\d.]+/[\d.]+' | sed 's/.*= //')

  sent=${sent:-0}; recv=${recv:-0}; loss=${loss:-100}
  if [ -n "$rtt" ]; then
    IFS='/' read -r rmin ravg rmax rmdev <<< "$rtt"
  else
    rmin=""; ravg=""; rmax=""; rmdev=""
  fi

  printf '%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
    "$ts" "$t" "$sent" "$recv" "$loss" "$rmin" "$ravg" "$rmax" "$rmdev" >> "$LOG_FILE"
done
