# netmon — monitoraggio stabilità rete

Servizio leggero per misurare **latenza e perdita di pacchetti** verso più
target contemporaneamente, con archivio CSV, riepilogo da terminale, grafico
SVG e dashboard web.

Nasce da un'esigenza concreta: diagnosticare in modo oggettivo un collegamento
**FWA/radio instabile** e distinguere i problemi della linea WAN da quelli
della rete locale (Wi-Fi, powerline, router), senza dipendere dalla percezione
soggettiva di "internet che va lento".

## Caratteristiche

- campionamento periodico tramite `ping`, senza dipendenze esterne;
- **un solo CSV** come fonte dati, semplice da conservare e analizzare;
- riepilogo CLI con loss, media, p95 e massimo, più grafico SVG;
- dashboard web **sola lettura** con auto-refresh e grafici Chart.js;
- integrazione completa con **systemd** (timer + servizio) e **logrotate**;
- server web in sola standard library Python.

## Come funziona

```text
systemd timer (ogni 60 s)
        │
        ▼
   netmon.sh ──► ping verso N target ──► /var/log/netmon/netmon.csv
                                                  │
                        ┌─────────────────────────┴────────────────────────┐
                        ▼                                                  ▼
              netmon-report.py                                  netmon-web.py
         (riepilogo CLI + SVG)                          (dashboard HTTP, porta 8080)
```

Ogni campione è una riga del CSV:

```text
timestamp,target,sent,received,loss_pct,rtt_min,rtt_avg,rtt_max,rtt_mdev
```

Target di esempio (configurabili):

| Target | Cosa rappresenta |
|---|---|
| `192.168.1.1` | gateway locale / router (salute della LAN) |
| `203.0.113.1` | primo hop ISP (accesso WAN) |
| `1.1.1.1` | Internet (Cloudflare) |
| `8.8.8.8` | Internet (Google) |

> `203.0.113.0/24` è un intervallo riservato alla documentazione (TEST-NET-3):
> sostituiscilo con il primo hop della tua connessione.

## Requisiti

- Linux con **systemd** (testato su Ubuntu 24.04);
- `bash`, `ping` (pacchetto `iputils-ping`), `python3` (3.8+);
- nessun pacchetto Python aggiuntivo: solo standard library.

## Installazione

```bash
git clone https://github.com/AlleMors/netmon.git
cd netmon
sudo ./install.sh          # dashboard sulla porta 8080
sudo ./install.sh 8081     # porta alternativa se la 8080 è occupata
```

In alternativa puoi copiare la cartella sull'host di misura:

```bash
scp -r netmon/ <utente>@<host>:/tmp/
ssh <utente>@<host>
cd /tmp/netmon && sudo ./install.sh
```

La porta scelta viene scritta nello unit `netmon-web.service`; lo script
avvisa ed esce se la porta è già in uso, evitando un crash-loop.

## Verifica

```bash
systemctl status netmon.timer netmon-web.service
systemctl list-timers netmon.timer
tail -f /var/log/netmon/netmon.csv
```

## Analisi da terminale

```bash
# riepilogo ultime 24 h
netmon-report.py --hours 24

# ultimi 7 giorni
netmon-report.py --hours 168

# grafico SVG del RTT medio
netmon-report.py --hours 24 --svg /tmp/netmon.svg
```

Esempio di output:

```text
Target            Camp.   Loss%     Avg     P95     Max
------------------------------------------------------
1.1.1.1             1440    0.42    18.3    27.1    62.4
8.8.8.8             1440    0.35    19.0    28.4    65.1
192.168.1.1         1440    0.00     1.2     2.0     8.7
```

## Dashboard web

Lo unit `netmon-web.service` espone una dashboard sulla porta **8080**
(configurabile con `sudo ./install.sh <porta>`):

```text
http://<host>:8080/
```

Mostra:

- **card per target** con ultimo RTT, loss%, media, p95 e massimo;
- **grafico latenza** (ms) con i picchi per bucket;
- **grafico perdita** (%);
- selettore finestra **1h / 6h / 24h / 7g**;
- auto-refresh ogni 60 s.

È **sola lettura**, non richiede login e non espone API di scrittura.

Verifica:

```bash
curl -s http://127.0.0.1:8080/health
```

## Configurazione

Variabili d'ambiente (modificabili con `systemctl edit netmon.service` o
`systemctl edit netmon-web.service`):

| Variabile | Default | Descrizione |
|---|---|---|
| `NETMON_TARGETS` | `192.168.1.1 1.1.1.1 8.8.8.8` | target separati da spazio |
| `NETMON_COUNT` | `10` | pacchetti per target a ogni campione |
| `NETMON_INTERVAL` | `1` | intervallo tra i pacchetti (s) |
| `NETMON_TIMEOUT` | `1` | timeout per pacchetto (s) |
| `NETMON_LOG_DIR` | `/var/log/netmon` | directory del CSV |
| `NETMON_LOG` | `/var/log/netmon/netmon.csv` | percorso CSV per la dashboard |
| `NETMON_WEB_PORT` | `8080` | porta della dashboard |
| `NETMON_WEB_BIND` | `0.0.0.0` | indirizzo di ascolto |

Esempio:

```ini
[Service]
Environment=NETMON_TARGETS="192.168.1.1 1.1.1.1 8.8.8.8 9.9.9.9"
Environment=NETMON_COUNT=20
```

## Come leggere i risultati

- **Perdita solo verso i target Internet, non verso il gateway** → problema
  a monte: linea WAN, ISP, radio/FWA o CPE.
- **Perdita anche verso il gateway** → problema locale: LAN, router o cavo.
- **Confronto tra due punti di misura** (ad esempio un host cablato e uno
  dietro powerline/Wi-Fi): se il secondo peggiora, l'instabilità è locale; se
  peggiorano allo stesso modo, la causa è a monte.

## Sicurezza

La dashboard **non ha autenticazione** e per default ascolta su `0.0.0.0`.
Esponila solo su una LAN fidata. Per limitarla alla macchina locale:

```bash
sudo systemctl edit netmon-web.service
# [Service]
# Environment=NETMON_WEB_BIND=127.0.0.1
```

Il CSV può contenere indirizzi IP interni: non pubblicarlo senza verificarne
il contenuto.

## Rotazione log

`logrotate` mantiene 30 giorni compressi (`/etc/logrotate.d/netmon`).

## Struttura del progetto

```text
netmon.sh           campionamento ping → CSV
netmon-report.py    riepilogo CLI + grafico SVG
netmon-web.py       dashboard HTTP (solo stdlib)
netmon.service      unit one-shot di campionamento
netmon.timer        esegue netmon.service ogni 60 s
netmon-web.service  unit del servizio dashboard
netmon.logrotate    rotazione del CSV
install.sh          installazione systemd e logrotate
```

## Sviluppi possibili

- alerting (es. loss > 1% per 5 min) via notifica;
- esportazione metriche per **Prometheus + blackbox_exporter + Grafana**;
- confronto automatico tra più punti di misura;
- test automatici e integrazione continua.

## Licenza

Distribuito sotto licenza **MIT**. Vedi [LICENSE](LICENSE).
