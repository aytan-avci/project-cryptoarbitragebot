# Crypto Arbitrage Agent — Kullanım Kılavuzu / User Manual

> **Bilingual** — Türkçe önce, English follows below the divider.
> Kod/komut/path'ler her iki dilde de aynıdır.

---

# 🇹🇷 Türkçe

## 1. Genel Bakış

**Arbitrage Agent**, çoklu kripto borsasında çalışan modüler bir
arbitraj botudur. Python 3.11+ ile yazıldı, `asyncio` üzerine kurulu,
[`CLAUDE.md`](CLAUDE.md) ve Karpathy'nin dört LLM-kodlama prensibi
çerçevesinde geliştirildi.

**Şu an destekli stratejiler:**
- **Spatial arbitrage** (varsayılan) — A borsasından al, B borsasından sat
- **Triangular arbitrage** — tek borsa üzerinde üç-leg cycle

**Mod hiyerarşisi:**
1. **Paper** (varsayılan): synthetic snapshot'lar, gerçek para yok
2. **Live + testnet**: gerçek API ama testnet URL'i — `binance.com` değil `testnet.binance.vision`
3. **Live + mainnet**: gerçek para. **30-day S7 testnet probation gate**
   olmadan başlatılamaz.

---

## 2. Önkoşullar

- **Python 3.11+** (`uv` ile yönetiliyor)
- **Node 18+** + npm (dashboard için)
- **gh CLI** + `gitleaks` + `pre-commit` (push'tan önce hooks koşar)
- **VPN**: `testnet.binance.vision` operatör ISP'sinde TLS-blocked
  olabilir (2026-05-22 tespit). Mainnet'e geçiş için gerekli.

```bash
# Mac (homebrew):
brew install python@3.11 node gh gitleaks pre-commit uv
```

---

## 3. Kurulum

```bash
git clone https://github.com/aytan-avci/project-cryptoarbitragebot.git
cd project-cryptoarbitragebot

# Python venv + dev deps
uv venv
.venv/bin/pip install -e ".[dev]"

# Dashboard
cd dashboard && npm install && cd ..

# Pre-commit hooks (push'tan önce gitleaks + check_env_example koşar)
pre-commit install
```

Doğrulama:
```bash
.venv/bin/python -m pytest -q     # 361+ test geçmeli
cd dashboard && npm run build      # 0 hata
```

---

## 4. İlk Paper Smoke

`.env` gerekmez — paper mod synthetic seed kullanır.

```bash
PIPELINE_ITERATIONS=5 .venv/bin/python -m arbitrage_agent
```

Beklenen çıktı:
- `pipeline.live_mode` veya synthetic-paper modu
- 5 iter × 2 snapshot = 10 snapshot
- 5 opportunity (geniş spread seed'ler kazançlı)
- 5 approved, 0 rejected
- 10 fill (her iter'da 2 leg)

`logs/decisions.jsonl` oluşur ve hash chain ile imzalanır.

---

## 5. Konfigürasyon (`.env`)

Tüm settings [`config.py`](src/arbitrage_agent/config.py) içinde.
Override için `.env` (gitignored) veya env var.

**Temel ayarlar:**

```env
EXECUTION_MODE=paper                 # paper | live
LOG_LEVEL=INFO
STRATEGY_NAME=spatial                # spatial | triangular
```

**Spatial parametreleri:**

```env
SPATIAL_SIZE_BTC=0.001
SPATIAL_TAKER_FEE_BPS=10
SPATIAL_MIN_PROFIT_THRESHOLD_USD=0.50
SPATIAL_VALID_FOR_MS=1000
```

**Triangular parametreleri:**

```env
TRIANGULAR_VENUE=binance
TRIANGULAR_QUOTE=USDT
TRIANGULAR_INTERMEDIATE=BTC
TRIANGULAR_BASE=ETH
TRIANGULAR_SIZE_QUOTE=50
TRIANGULAR_MIN_PROFIT_THRESHOLD_USD=0.50
```

**Risk gate (10 deterministik check):**

```env
RISK_MIN_PROFIT_THRESHOLD_USD=0.50
RISK_MIN_ORDER_VALUE_USD=20
RISK_MAX_ORDER_VALUE_USD=200
RISK_MAX_GROSS_EXPOSURE_USD=1500
RISK_MAX_POSITION_VALUE_USD=500
RISK_MAX_ORDERS_PER_MINUTE=30
RISK_MAX_SNAPSHOT_AGE_MS=10000
RISK_MIN_REQUIRED_BALANCE_USD=50
RISK_MAX_LOSS_PER_DAY_USD=50
```

**Live borsa anahtarları** (paper modda gereksiz):

```env
BINANCE_ENABLED=true
BINANCE_REST_BASE_URL=https://testnet.binance.vision
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
```

**Mainnet kilidi:**

```env
LIVE_TRADING_CONFIRMED=true   # SADECE 30-day probation sonrası
```

---

## 6. Dashboard

Bot çalışırken paralel olarak Vite dev server'ı başlat:

```bash
cd dashboard && npm run dev
# → http://localhost:3005
```

Panel'ler:
- **Overview** — P&L, opportunities, approval rate, exchanges, live prices, recent opportunities, recent fills
- **Hedge Activity** — sadece müdahale gerektiren hedge'ler (`no_imbalance` gizli)
- **Security Status** — S7 probation progress (X/30 days) + eligibility chip
- **Kill-Switch Banner** — engaged olduğunda kırmızı banner

Polling:
- Audit log: 500 ms (`/logs/decisions.jsonl`)
- Kill switch: 2 s (`/api/kill-switch`)
- Testnet evidence: 5 s (`/logs/testnet_evidence.json`)

---

## 7. Prometheus Metrics

Opt-in olarak aç:

```bash
METRICS_ENABLED=true METRICS_PORT=9090 .venv/bin/python -m arbitrage_agent
```

Scrape:
```bash
curl http://127.0.0.1:9090/metrics
```

Yayılan metric'ler:
- `arbitrage_opportunities_total{strategy}` (counter)
- `arbitrage_decisions_total{outcome}` (counter)
- `arbitrage_fills_total{exchange,side}` (counter)
- `arbitrage_hedge_results_total{status}` (counter)
- `arbitrage_pipeline_iteration_seconds` (histogram)
- `arbitrage_leg_placement_seconds{exchange}` (histogram)
- `arbitrage_kill_switch_engaged` (gauge)
- `arbitrage_daily_pnl_usd` (gauge)

Grafana dashboard için kullanılabilir; alertmanager rule önerileri:
- `arbitrage_kill_switch_engaged == 1` → operatör çağır
- `rate(arbitrage_decisions_total{outcome="rejected"}[5m]) > 10` → strateji/gate
  problemi
- `arbitrage_daily_pnl_usd < -40` → günlük loss budget'a yaklaşıyor

---

## 8. Audit Log Doğrulama

Her satır SHA-256 hash chain ile imzalı. Tampering yakalama:

```bash
.venv/bin/python scripts/verify_audit_chain.py logs/decisions.jsonl
# verified N line(s); chain intact   → exit 0
# line K: _hash mismatch ...         → exit 1 (TAMPER)
```

**Cron'da koş** (production önerisi):
```cron
*/15 * * * * cd /path/to/bot && .venv/bin/python scripts/verify_audit_chain.py logs/decisions.jsonl || /usr/local/bin/page-operator
```

---

## 9. Testnet Kurulumu (S7 probation başlangıcı)

1. **Binance testnet hesabı** aç: https://testnet.binance.vision/
2. **API key** üret — `canTrade=true`, **`canWithdraw=false` ZORUNLU**
   (S5 probe withdraw permission'lı key'i reddeder)
3. **`.env`** doldur:
   ```env
   EXECUTION_MODE=live
   BINANCE_ENABLED=true
   BINANCE_REST_BASE_URL=https://testnet.binance.vision
   BINANCE_API_KEY=...
   BINANCE_API_SECRET=...
   ```
4. **VPN** açık olduğundan emin ol (`curl https://testnet.binance.vision/api/v3/ping`
   → `{}` dönmeli)
5. **Bot'u uzun-ömürlü başlat**:
   ```bash
   nohup .venv/bin/python -m arbitrage_agent > logs/bot.out 2>&1 &
   # veya systemd unit
   ```
6. İlk başarılı `_ensure_no_withdraw_permission` çağrısı
   `logs/testnet_evidence.json`'a `first_seen_utc` damgalar:
   ```json
   {
     "first_seen_utc": "2026-05-23T...",
     "last_seen_utc": "...",
     "venues": ["binance-testnet"]
   }
   ```
7. **Günlük chain doğrulama cron'u** kur (§ 8)

---

## 10. Mainnet'e Geçiş Runbook (A)

[`MEMORY.md § 2026-05-23 — (A) Mainnet runbook`](MEMORY.md) tam playbook.
Özet sıra:

1. Testnet'te kesintisiz 30 gün çalıştır (§ 9)
2. Her gün audit chain'i verify et (§ 8)
3. Day-30'da Settings doğrulaması:
   ```bash
   .venv/bin/python -c "from arbitrage_agent.risk.testnet_evidence import attest_mainnet_eligibility; print(attest_mainnet_eligibility())"
   # (True, '30 testnet days observed since ...')
   ```
4. Mainnet'e flip:
   ```env
   BINANCE_REST_BASE_URL=https://api.binance.com
   LIVE_TRADING_CONFIRMED=true
   ```
5. [`MEMORY.md § Decisions & Why`](MEMORY.md) altına tarih + rationale satırı ekle
6. Bot'u **çok küçük size_btc** ile başlat (0.0001), 1 hafta gözlemle, sonra yavaşça büyüt

**Acil bypass** (yalnızca operasyonel olaylar için):
```env
S7_OVERRIDE_TESTNET_PROBATION=true
```
Override her kullanımı `MEMORY.md`'ye dokümante edilmeli. **30 günü
atlamak için kullanma.**

---

## 11. Operasyonel Kontroller

### Kill-Switch
**Manual engage** (acil dur):
```python
from pathlib import Path
from arbitrage_agent.risk import kill_switch
kill_switch.engage(Path("logs/kill_switch.json"), reason="manual operator stop")
```

**Reset**:
```python
kill_switch.reset(Path("logs/kill_switch.json"))
```

Bot bir sonraki risk_evaluate çağrısında check #1'den reddeder.

### Otomatik kill triggers
- `daily_pnl_usd < -RISK_MAX_LOSS_PER_DAY_USD` → otomatik engage
- `kill_switch.json` dosyasının varlığı engaged demek

### Hedger davranışı
- Her başarısız leg sonrası `_handle_hedge` çağrılır
- `hedge_max_slippage_bps` (varsayılan 50) budget kontrolü
- Budget aşıldıysa `aborted_slippage` durumu + open exposure
  operatöre raporlanır (dashboard'da kırmızı)

---

## 12. Sorun Giderme

| Belirti | Olası neden | Çözüm |
|---|---|---|
| `ValidationError: S7: no testnet evidence` | Mainnet+live aktif ama 30-day probation tamamlanmadı | `EXECUTION_MODE=paper` veya testnet URL'i; ya da 30 gün bekle |
| `PermanentFailure: Binance API key has withdraw permission` | Key'de withdraw açık (C1 ihlali) | Binance'ta key'i revoke et, trade-only yenisi üret |
| Dashboard "no data yet" | `logs/decisions.jsonl` boş | `python -m arbitrage_agent` koş, dashboard 500ms'de yenilenir |
| `LibreSSL WRONG_VERSION_NUMBER` | ISP testnet.binance.vision'a TLS block | VPN aç |
| `line N: _hash mismatch` | Audit log tampered/corrupted | Backup'tan restore, kim/ne değiştirdiğini araştır |
| Pipeline single-venue mode'da takılı | Tek venue seed'lendi, spatial 2 venue ister | İkinci venue ekle veya `STRATEGY_NAME=triangular` |
| Triangular leg risk gate'te reject | Cross-pair USDT/BTC unit mismatch (known) | `RISK_MIN_ORDER_VALUE_USD` widen veya v2 conversion bekle |

---

## 13. Güvenlik Notları

15 kontrol [`specs/SECURITY.md`](specs/SECURITY.md)'de tam liste.
En kritik 5:

- **C1** — Withdraw permission'lı key REDDEDİLİR (S5 lazy probe)
- **C2** — Risk Layer geçmeden hiçbir order live'a gönderilmez
- **C3** — Paper varsayılan, live için explicit `EXECUTION_MODE=live`
- **C6** — Secret'lar `.env` (gitignored), gitleaks pre-commit + CI
- **S7** — Mainnet 30-day testnet probation gate (otomatik enforce)

`.env.example` template asla gerçek credential içermez —
`check_env_example.py` pre-commit hook bunu zorlar.

---

---

# 🇬🇧 English

## 1. Overview

**Arbitrage Agent** is a modular crypto arbitrage bot for multiple
exchanges. Written in Python 3.11+, built on `asyncio`, developed
under the [`CLAUDE.md`](CLAUDE.md) constitution and Karpathy's four
LLM-coding principles.

**Currently supported strategies:**
- **Spatial arbitrage** (default) — buy on exchange A, sell on B
- **Triangular arbitrage** — single-venue three-leg cycle

**Mode hierarchy:**
1. **Paper** (default): synthetic snapshots, no real money
2. **Live + testnet**: real API but testnet URL —
   `testnet.binance.vision`, not `binance.com`
3. **Live + mainnet**: real money. Cannot start without the
   **30-day S7 testnet probation gate** being satisfied.

---

## 2. Prerequisites

- **Python 3.11+** (managed via `uv`)
- **Node 18+** + npm (for the dashboard)
- **gh CLI** + `gitleaks` + `pre-commit` (hooks run before push)
- **VPN**: `testnet.binance.vision` may be TLS-blocked by the
  operator's ISP (diagnosed 2026-05-22). Required for the mainnet
  probation flow.

```bash
# Mac (Homebrew):
brew install python@3.11 node gh gitleaks pre-commit uv
```

---

## 3. Installation

```bash
git clone https://github.com/aytan-avci/project-cryptoarbitragebot.git
cd project-cryptoarbitragebot

# Python venv + dev deps
uv venv
.venv/bin/pip install -e ".[dev]"

# Dashboard
cd dashboard && npm install && cd ..

# Pre-commit hooks (gitleaks + check_env_example run before push)
pre-commit install
```

Verify:
```bash
.venv/bin/python -m pytest -q     # 361+ tests must pass
cd dashboard && npm run build      # 0 errors
```

---

## 4. First Paper Smoke

`.env` is not required — paper mode uses synthetic seeds.

```bash
PIPELINE_ITERATIONS=5 .venv/bin/python -m arbitrage_agent
```

Expected output:
- `pipeline.live_mode` or synthetic-paper mode
- 5 iterations × 2 snapshots = 10 snapshots
- 5 opportunities (wide-spread seeds are profitable)
- 5 approved, 0 rejected
- 10 fills (2 legs per iter)

`logs/decisions.jsonl` is created and signed with the SHA-256 hash chain.

---

## 5. Configuration (`.env`)

All settings live in [`config.py`](src/arbitrage_agent/config.py).
Override via `.env` (gitignored) or environment variables.

**Core settings:**

```env
EXECUTION_MODE=paper                 # paper | live
LOG_LEVEL=INFO
STRATEGY_NAME=spatial                # spatial | triangular
```

**Spatial parameters:**

```env
SPATIAL_SIZE_BTC=0.001
SPATIAL_TAKER_FEE_BPS=10
SPATIAL_MIN_PROFIT_THRESHOLD_USD=0.50
SPATIAL_VALID_FOR_MS=1000
```

**Triangular parameters:**

```env
TRIANGULAR_VENUE=binance
TRIANGULAR_QUOTE=USDT
TRIANGULAR_INTERMEDIATE=BTC
TRIANGULAR_BASE=ETH
TRIANGULAR_SIZE_QUOTE=50
TRIANGULAR_MIN_PROFIT_THRESHOLD_USD=0.50
```

**Risk gate (10 deterministic checks):**

```env
RISK_MIN_PROFIT_THRESHOLD_USD=0.50
RISK_MIN_ORDER_VALUE_USD=20
RISK_MAX_ORDER_VALUE_USD=200
RISK_MAX_GROSS_EXPOSURE_USD=1500
RISK_MAX_POSITION_VALUE_USD=500
RISK_MAX_ORDERS_PER_MINUTE=30
RISK_MAX_SNAPSHOT_AGE_MS=10000
RISK_MIN_REQUIRED_BALANCE_USD=50
RISK_MAX_LOSS_PER_DAY_USD=50
```

**Live exchange credentials** (not needed in paper mode):

```env
BINANCE_ENABLED=true
BINANCE_REST_BASE_URL=https://testnet.binance.vision
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
```

**Mainnet unlock:**

```env
LIVE_TRADING_CONFIRMED=true   # ONLY after the 30-day probation
```

---

## 6. Dashboard

Run the Vite dev server in parallel while the bot is active:

```bash
cd dashboard && npm run dev
# → http://localhost:3005
```

Panels:
- **Overview** — P&L, opportunities, approval rate, exchanges, live prices, recent opportunities, recent fills
- **Hedge Activity** — only neutralisations (the `no_imbalance` happy path is hidden)
- **Security Status** — S7 probation progress (X/30 days) + eligibility chip
- **Kill-Switch Banner** — red banner shown when engaged

Polling cadence:
- Audit log: 500 ms (`/logs/decisions.jsonl`)
- Kill switch: 2 s (`/api/kill-switch`)
- Testnet evidence: 5 s (`/logs/testnet_evidence.json`)

---

## 7. Prometheus Metrics

Opt-in:

```bash
METRICS_ENABLED=true METRICS_PORT=9090 .venv/bin/python -m arbitrage_agent
```

Scrape:
```bash
curl http://127.0.0.1:9090/metrics
```

Exposed metrics:
- `arbitrage_opportunities_total{strategy}` (counter)
- `arbitrage_decisions_total{outcome}` (counter)
- `arbitrage_fills_total{exchange,side}` (counter)
- `arbitrage_hedge_results_total{status}` (counter)
- `arbitrage_pipeline_iteration_seconds` (histogram)
- `arbitrage_leg_placement_seconds{exchange}` (histogram)
- `arbitrage_kill_switch_engaged` (gauge)
- `arbitrage_daily_pnl_usd` (gauge)

Usable in Grafana; suggested alertmanager rules:
- `arbitrage_kill_switch_engaged == 1` → page operator
- `rate(arbitrage_decisions_total{outcome="rejected"}[5m]) > 10` →
  strategy / gate problem
- `arbitrage_daily_pnl_usd < -40` → approaching daily loss budget

---

## 8. Audit Log Verification

Every line is signed in a SHA-256 hash chain. Tamper detection:

```bash
.venv/bin/python scripts/verify_audit_chain.py logs/decisions.jsonl
# verified N line(s); chain intact   → exit 0
# line K: _hash mismatch ...         → exit 1 (TAMPER)
```

**Run in cron** (production recommendation):
```cron
*/15 * * * * cd /path/to/bot && .venv/bin/python scripts/verify_audit_chain.py logs/decisions.jsonl || /usr/local/bin/page-operator
```

---

## 9. Testnet Setup (start of S7 probation)

1. **Create a Binance testnet account**: https://testnet.binance.vision/
2. **Generate an API key** — `canTrade=true`,
   **`canWithdraw=false` REQUIRED** (the S5 probe refuses any key with
   withdraw permission)
3. **Populate `.env`**:
   ```env
   EXECUTION_MODE=live
   BINANCE_ENABLED=true
   BINANCE_REST_BASE_URL=https://testnet.binance.vision
   BINANCE_API_KEY=...
   BINANCE_API_SECRET=...
   ```
4. **Make sure VPN is up** (`curl https://testnet.binance.vision/api/v3/ping`
   should return `{}`)
5. **Start the bot long-running**:
   ```bash
   nohup .venv/bin/python -m arbitrage_agent > logs/bot.out 2>&1 &
   # or via a systemd unit
   ```
6. The first successful `_ensure_no_withdraw_permission` call stamps
   `logs/testnet_evidence.json` with `first_seen_utc`:
   ```json
   {
     "first_seen_utc": "2026-05-23T...",
     "last_seen_utc": "...",
     "venues": ["binance-testnet"]
   }
   ```
7. **Set up a daily chain-verification cron** (§ 8)

---

## 10. Mainnet Runbook (A)

Full playbook in [`MEMORY.md § 2026-05-23 — (A) Mainnet runbook`](MEMORY.md).
Summary sequence:

1. Run on testnet uninterrupted for 30 days (§ 9)
2. Verify the audit chain daily (§ 8)
3. On day 30, confirm via Settings:
   ```bash
   .venv/bin/python -c "from arbitrage_agent.risk.testnet_evidence import attest_mainnet_eligibility; print(attest_mainnet_eligibility())"
   # (True, '30 testnet days observed since ...')
   ```
4. Flip to mainnet:
   ```env
   BINANCE_REST_BASE_URL=https://api.binance.com
   LIVE_TRADING_CONFIRMED=true
   ```
5. Add a dated row + rationale to
   [`MEMORY.md § Decisions & Why`](MEMORY.md)
6. Start the bot with a **very small `size_btc`** (0.0001), observe
   for one week, then scale up slowly.

**Emergency bypass** (operational incidents only):
```env
S7_OVERRIDE_TESTNET_PROBATION=true
```
Every override use must be documented in `MEMORY.md`. **Do not use
this to skip the 30-day rule.**

---

## 11. Operational Controls

### Kill-Switch
**Manual engage** (emergency stop):
```python
from pathlib import Path
from arbitrage_agent.risk import kill_switch
kill_switch.engage(Path("logs/kill_switch.json"), reason="manual operator stop")
```

**Reset**:
```python
kill_switch.reset(Path("logs/kill_switch.json"))
```

The bot will reject at check #1 on the next risk evaluation.

### Automatic kill triggers
- `daily_pnl_usd < -RISK_MAX_LOSS_PER_DAY_USD` → auto-engages
- Presence of `kill_switch.json` = engaged

### Hedger behaviour
- `_handle_hedge` runs after every imbalanced execution
- `hedge_max_slippage_bps` (default 50) budget check
- Budget exceeded → `aborted_slippage` + open exposure surfaced to
  operator (red in dashboard)

---

## 12. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ValidationError: S7: no testnet evidence` | mainnet+live active but 30-day probation incomplete | switch to paper or testnet URL; or wait the 30 days |
| `PermanentFailure: Binance API key has withdraw permission` | key has withdraw enabled (C1 violation) | revoke on Binance, generate a trade-only key |
| Dashboard shows "no data yet" | `logs/decisions.jsonl` is empty | run `python -m arbitrage_agent`; dashboard refreshes every 500ms |
| `LibreSSL WRONG_VERSION_NUMBER` | ISP TLS-blocks testnet.binance.vision | turn on VPN |
| `line N: _hash mismatch` | audit log tampered/corrupted | restore from backup, investigate who/what changed |
| Pipeline stuck in single-venue mode | only one venue seeded, spatial needs 2 | add a second venue or `STRATEGY_NAME=triangular` |
| Triangular leg rejected by risk gate | cross-pair USDT/BTC unit mismatch (known) | widen `RISK_MIN_ORDER_VALUE_USD` or wait for v2 conversion |

---

## 13. Security Notes

The 15 controls are catalogued in [`specs/SECURITY.md`](specs/SECURITY.md).
The five most critical:

- **C1** — keys with withdraw permission are REFUSED (S5 lazy probe)
- **C2** — no order is placed live without passing the Risk Layer
- **C3** — paper is the default; live requires explicit
  `EXECUTION_MODE=live`
- **C6** — secrets live in `.env` (gitignored); gitleaks pre-commit + CI
- **S7** — mainnet is gated on 30-day testnet probation (automated)

`.env.example` never contains real credentials — the
`check_env_example.py` pre-commit hook enforces this.

---

*Last updated: 2026-05-23. Versioned in git; see commit history for changes.*
