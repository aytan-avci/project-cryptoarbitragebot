# STATUS

> **Read first.** This file is the bridge across context compactions and new
> sessions. Update at the end of every meaningful work block.
> Hard ceiling: ≤ 60 lines. Older entries spill to `specs/LOG.md`.

---

**(B) Triangular strategy tamam.** `strategies/triangular.py` stub'ı
gerçek modüle dönüştü: `TriangularArbitrage` Strategy protokolüne
uyuyor, `evaluate(view, clock)` pure function, üç pair (intermediate/
quote, base/quote, base/intermediate) üzerinde forward (Q→I→B→Q)
ve reverse (Q→B→I→Q) cycle math yapar, daha karlı path'i tek
`Opportunity` (3 leg) olarak yayar. Strategy protocol'a `symbols` +
`min_venues` property'leri eklendi (Spatial=1 sym/2 venue,
Triangular=3 sym/1 venue). Pipeline `_build_strategy(settings,
exchange_ids)` helper'ı `strategy_name` env'ine göre switch ediyor,
snapshot fetch loop `strategy.symbols` üzerinde geziyor (KeyError'da
skip), single-venue short-circuit `< min_venues` koşuluna bağlandı.
WS mode subscribe artık `strategy.symbols`. Yeni 11 config alanı
(strategy_name + 9 triangular + venue switch). **361/361 pytest
yeşil** (önceki 347 + 12 triangular unit + 2 pipeline integration).
End-to-end smoke: paper Binance'a 3 pair seed → triangular cycle
ETH/BTC undervalued senaryosunda $1.61 net profit ile detect edildi.
Known limitation: risk gate'in `min_order_value_usd` check'i
USDT-denominated, ETH/BTC leg'in BTC-denominated limit_price'ında
yanlış pozitif reddediyor; operatör bu strategy için gate'i
calibrate edecek veya cross-pair currency conversion v2'de eklenecek.

## Last session ended at
**2026-05-23** — (B) Triangular strategy: `strategies/triangular.py`
TriangularArbitrage class + Strategy protokolü; `symbols` property
3 pair, `min_venues=1`. Spatial'a aynı property'ler eklendi.
`config.py` `strategy_name: Literal["spatial","triangular"]` switch +
`triangular_*` 9 param. Pipeline `_build_strategy` helper +
`strategy.symbols` üzerinde snapshot fetch + min_venues kontrolü;
single-venue short-circuit artık `len(adapters) < strategy.min_venues`
ile koşulluyor. WS subscribe `strategy.symbols` listesi ile çağırıyor.
Test count: 12 yeni triangular unit + 2 pipeline integration; mevcut
"at least two seeded exchanges" testi regex'i `at least 2 seeded
exchange` ile değiştirildi (string yerine sayı). Smoke: 1 venue × 3
seed → cycle detect, gate ETH/BTC leg'inin min_order_value'da rejct
etti (BTC vs USDT unit mismatch, MEMORY'de işaretli).

## Last session ended at
**2026-05-23** — (D) Performance + observability:
`observability/metrics.py` stub'ı tam modüle dönüştü; module-local
`CollectorRegistry` global state sızdırmıyor. Counter inc'leri
pipeline'da mevcut `counters` dict bump'larıyla yan yana
(REST + WS), `pipeline_iteration_seconds` context-manager timer,
`leg_placement_seconds` execution.engine'de `place_order` timer'ı,
`kill_switch_engaged` daily-loss kill firing'inde set, `daily_pnl_usd`
her fill sonrası `float(tracker.daily_pnl_usd)`. aiohttp
`/metrics` endpoint Prometheus `CONTENT_TYPE_LATEST` header'ı
direkt geçirir (aiohttp `content_type=` kwarg charset reddediyordu).
Test fixture'ı `metrics.clear_for_tests()` labelled metric'leri ve
gauge'ları sıfırlar. Yeni `tests/unit/observability/test_metrics.py`
(10 test) + integration test (pipeline.run → counter assertions).

## Last session ended at
**2026-05-23** — (C) Dashboard zenginleştirme: `DecisionLog.append_
hedger_result(HedgeResult)` yeni metod; pipeline `_handle_hedge` her
hedge sonrası çağırır → audit log'a `event="hedger_result"` (status,
counter_leg dict, remaining_exposure, reason). Dashboard TS tarafı:
`HedgerResultEvent` + `TestnetEvidence` types, `useTestnetEvidence`
hook (5s), `hedgerResults` filter + `summarizeTestnetEvidence`
(days/30, eligibility). Yeni iki component: `HedgeActivity.tsx`
(no_imbalance'ı eler, müdahale gerektiren olayları tablo halinde),
`SecurityStatus.tsx` (LinearProgress + eligibility chip + first/last
seen + venue list). App.tsx mount. Vite middleware zaten `/logs/*`
serve ediyor — extra config yok. `npm run build` temiz, 336/336
pytest yeşil. Smoke: pipeline 3-iter + manual hedge injection, 20
satır audit log hash-chain intact, 3 endpoint HTTP 200.

## Last session ended at
**2026-05-22** — Faz 7g-d: `risk/testnet_evidence.py` (yeni modül)
`record`/`load`/`attest_mainnet_eligibility` API; JSON evidence
`logs/testnet_evidence.json` (first_seen/last_seen/venues).
`BinanceAdapter` `_is_testnet` + `_record_testnet_evidence` hook'u
`_ensure_no_withdraw_permission` başarı yoluna gömüldü — mainnet URL
kayıt atmaz. `config.py` `_confirm_mainnet_live` validator S4
check'inden sonra `attest_mainnet_eligibility(min_days=30)` koşar;
`S7_OVERRIDE_TESTNET_PROBATION` + `S7_MIN_TESTNET_DAYS` env'leri.
Yeni testler: `tests/unit/risk/test_testnet_evidence.py` (11 unit),
`tests/unit/test_config.py::TestS7TestnetProbationGate` (6 senaryo:
no-evidence-rejects, recent-rejects, 31-days-allows, override-bypasses,
testnet-url-skipped, S7_MIN_TESTNET_DAYS-override), `test_binance_auth.
py` (2 hook test: testnet URL kaydeder, mainnet URL kaydetmez).
`test_imports.py` modül seti güncellendi. Live smoke: kanıt yokken
ValidationError, 31 gün seed → Settings OK.

## Last session ended at
**2026-05-22** — Faz 7g-c: `execution/hedger.py` baştan yazıldı —
`compute_net_exposure` + `_best_effort_cancel` + counter-leg builder
+ slippage budget gate (`_within_slippage`, VWAP fair price baseline)
+ `async hedge(opp, result, adapters, view, max_slippage_bps)` returns
`HedgeResult`. Yeni domain tipi `HedgeResult` (status ∈
no_imbalance/filled/partial/aborted_slippage/no_market_data/placement_
failed). Settings: `hedge_max_slippage_bps: int = 50`. PaperExchange.
cancel_order artık no-op. Pipeline her iki modda (REST + WS)
`_handle_hedge` helper'ı çağırır → hedge fills DecisionLog + tracker
+ counters'a thread. Yeni 13 unit hedger testi (net exposure × 3,
slippage gate × 3, hedge orchestration × 7: no_imbalance, happy path,
abort_slippage, no_market_data, cancel-error-swallow, placement-fail,
traceability) + 1 pipeline integration testi. Live smoke proved
failed-sell-leg → Bybit counter-leg fill, audit chain temiz.

## Last session ended at
**2026-05-22** — Faz 7g-b: `persistence/decision_log.py` SHA-256 hash
chain'e geçirildi (`GENESIS_HASH`, `_compute_hash` canonical JSON üzerinde,
`_restore_chain_state` tail'den son hash'i kurtarır, `_append` her satıra
`_prev_hash`+`_hash` enjekte eder). `verify_chain(path)` tek geçişte
JSON parse + alan varlığı + `_prev_hash` link + `_hash` recompute
kontrol ediyor; ilk ihlali satır numarasıyla raporluyor. CLI:
`scripts/verify_audit_chain.py` (exit 0/1/2). Yeni 12 test: chain
continuation across processes, content tamper, deleted line, missing
`_hash`, missing file + CLI exit code contract. Live smoke: 30 satırlık
log temiz geçti, 15. satıra elle yapılan mutasyon `_hash mismatch` ile
yakalandı. SECURITY.md S6 change log + LOG.md ingest + MEMORY decision
girdileri eklendi.

## Open questions
- (yok)

## Next (3–5 adım)
- [x] **Faz 1 — Bootstrap** (2026-05-20)
- [x] **Faz 2 — Domain types** (2026-05-20)
- [x] **Faz 2.5 — Domain reconciliation** (2026-05-20, spec hizalama)
- [x] **Faz 3 — Config + Logging** (2026-05-20)
- [x] **Faz 4 — Boş modül paketleri** (2026-05-20)
- [x] **Faz 5a — PaperExchange** (2026-05-20)
- [x] **Faz 5b — Risk gate + limits + kill-switch** (2026-05-20)
- [x] **Faz 5c — Spatial strategy + Clock/MarketView + synthetic chain** (2026-05-21)
- [x] **Faz 6 — Uçtan uca paper dry-run + orchestration + decision-log** (2026-05-21)
- [x] **Adım 1 (c) — Dashboard design smoke** (2026-05-21)
- [x] **Adım 2 (a) — Real bot data → dashboard (Vite + React + MUI v6)** (2026-05-21)
- [x] **Faz 7a — Binance live REST adapter (read-only)** (2026-05-21)
- [x] **Faz 7-S Adım 1 — SECURITY.md (15 controls, gates, IR)** (2026-05-21)
- [x] **Faz 7-S Adım 2 — S1+S2+S3+S4 implementation** (2026-05-21)
- [x] **Faz 7d — Bybit live adapter → multi-venue real spread arb** (2026-05-21)
- [x] **Faz 7c — WS subscription + reconnect + event-driven pipeline** (2026-05-22)
- [x] **Faz 7b — Binance TESTNET authenticated (S5 + S6 + S7 doc)** (2026-05-22)
- [x] **Faz 7e — Order lifecycle reconciler + concurrent placement** (2026-05-22)
- [x] **Faz 7f — Position + orders/min + venue freshness checks** (2026-05-22)
- [x] **Faz 7g-a — min_balance check + daily-loss auto-kill + balance polling** (2026-05-22)
- [x] **Faz 7g-b — Audit log hash chain (tampering catch)** (2026-05-22)
- [x] **Faz 7g-c — Hedger real implementation (cancel + counter-leg + slippage budget)** (2026-05-22)
- [x] **Faz 7g-d — S7 30-day testnet evidence enforcement gate** (2026-05-22)

## Blockers
(yok)

## Session checklist (oturum sonu)
- [ ] `Now` bu oturumda ne yapıldığını yansıtıyor mu?
- [ ] `Next` güncel ve öncelik sıralı mı?
- [ ] Yeni karar/öğrenilen ders varsa `MEMORY.md`'ye eklendi mi?
- [ ] Olay (decision/ingest/lint) varsa `specs/LOG.md`'ye satır eklendi mi?
- [ ] Yeni/silinen `.md` varsa `specs/INDEX.md` güncellendi mi?
