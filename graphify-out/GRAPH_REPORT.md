# Graph Report - polymarket-kalshi-weather-bot  (2026-11-07)

## Corpus Check
- 71 files · ~75,022 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 10 file(s) not represented in the graph (top: (none) 3, .example 2, .jsonl 2)

## Summary
- 868 nodes · 1725 edges · 69 communities (40 shown, 29 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 90 edges (avg confidence: 0.93)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `d8ce6961`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- KalshiClient
- btc_markets.py
- typing
- package.json
- hourly_signals.py
- signals.py
- BotState
- api/main.py
- database.py
- settlement.py
- App.tsx
- AILog
- dependencies
- api.ts
- compilerOptions
- WeatherSignal
- ClaudeAnalyzer
- GroqClassifier
- FilterBar.tsx
- EnsembleForecast
- crypto.py
- Prediction Market Trading Bot
- base.py
- utils.ts
- ConnectionManager
- EquityChart.tsx
- BaseAIClient
- compilerOptions
- deploy
- AIAnalysis
- claude.py
- WeatherMarket
- SettlementCalibrationHarness
- MicrostructurePanel.tsx
- vercel.json
- frontend/vercel.json
- test_c137_quant.py
- weather_signals.py
- vite-env.d.ts
- Platform and API Research
- Layer 2B: Econ Pipeline
- get_recent_events
- 🌐 24/7 Free GCP Deployment Guide ($0.00 / month forever)
- Backend Dependencies
- main.tsx
- weather_markets.py
- SignalsTable.tsx
- .test_simulate_trade_is_paper_and_stats_live_purity
- EdgeDistribution.tsx
- TestC137QuantitativeCore
- startup
- TradesTable.tsx
- deploy_gcp.sh
- Settings
- devDependencies
- .test_kalshi_houston_series_negative_and_inclusive_strikes_and_empty_book
- scheduler.py
- scripts
- Signal
- vite.config.ts

## God Nodes (most connected - your core abstractions)
1. `KalshiClient` - 31 edges
2. `Trade` - 31 edges
3. `TestC137QuantitativeCore` - 30 edges
4. `BotState` - 26 edges
5. `App()` - 23 edges
6. `Signal` - 22 edges
7. `get_dashboard()` - 21 edges
8. `EnsembleForecast` - 19 edges
9. `WeatherMarket` - 19 edges
10. `log_event()` - 17 edges

## Surprising Connections (you probably didn't know these)
- `Frontend Web Entry Point` --semantically_similar_to--> `Trading Dashboard UI Screenshot`  [INFERRED] [semantically similar]
  frontend/index.html → docs/dashboard.png
- `TestC137QuantitativeCore` --uses--> `SettlementCalibrationHarness`  [INFERRED]
  test_c137_quant.py → backend/analytics/calibration.py
- `TestC137QuantitativeCore` --uses--> `MicrostructureEngine`  [INFERRED]
  test_c137_quant.py → backend/analytics/microstructure.py
- `TestC137QuantitativeCore` --uses--> `WeatherTradingSignal`  [INFERRED]
  test_c137_quant.py → backend/core/weather_signals.py
- `TestC137QuantitativeCore` --uses--> `KalshiClient`  [INFERRED]
  test_c137_quant.py → backend/data/kalshi_client.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Weather Trading Subsystem** — architecture_layer2a_weather_pipeline, readme_strategy_weather_temperature, validated_research_kalshi_weather_tickers [INFERRED 0.85]

## Communities (69 total, 29 thin omitted)

### Community 0 - "KalshiClient"
Cohesion: 0.06
Nodes (14): get_kalshi_status(), generate_weather_signal(), get_base_url(), kalshi_credentials_present(), KalshiClient, _extract_price(), fetch_kalshi_weather_markets(), _parse_kalshi_market() (+6 more)

### Community 1 - "btc_markets.py"
Cohesion: 0.09
Nodes (12): BtcMarket, _compute_window_slugs(), fetch_active_btc_markets(), fetch_btc_market_by_slug(), fetch_btc_market_for_settlement(), is_valid_btc_slug(), _parse_event_to_btc_market(), _round_to_5min() (+4 more)

### Community 2 - "typing"
Cohesion: 0.18
Nodes (3): ArbitrageOpportunity, MonotonicityScanner, GateResult

### Community 3 - "package.json"
Cohesion: 0.10
Nodes (19): name, private, type, version, autoprefixer, clsx, d3-geo, leaflet (+11 more)

### Community 4 - "hourly_signals.py"
Cohesion: 0.06
Nodes (21): get_city_for_ticker(), hourly_settlement_job(), parse_expiry_from_ticker(), compute_coastal_drift_and_sigma(), evaluate_hourly_market(), HourlySignal, _normal_cdf(), scan_for_hourly_signals() (+13 more)

### Community 5 - "signals.py"
Cohesion: 0.15
Nodes (8): calculate_edge(), calculate_kelly_size(), generate_btc_signal(), get_actionable_signals(), _persist_signals(), scan_for_signals(), test(), TradingSignal

### Community 6 - "BotState"
Cohesion: 0.24
Nodes (11): get_equity_curve(), reset_bot(), run_scan(), settle_trades_endpoint(), simulate_trade(), start_bot(), stop_bot(), log_event() (+3 more)

### Community 7 - "api/main.py"
Cohesion: 0.08
Nodes (28): BotStats, BtcPriceResponse, BtcWindowResponse, DashboardData, get_actionable_signals(), get_btc_price(), get_btc_windows(), get_c137_calibration() (+20 more)

### Community 8 - "database.py"
Cohesion: 0.14
Nodes (3): BtcPriceSnapshot, ensure_schema(), get_paper_db()

### Community 9 - "settlement.py"
Cohesion: 0.15
Nodes (8): calculate_pnl(), check_market_settlement(), check_weather_settlement(), _fetch_kalshi_resolution(), _fetch_nws_resolution(), fetch_polymarket_resolution(), _parse_market_resolution(), _search_market_in_events()

### Community 10 - "App.tsx"
Cohesion: 0.22
Nodes (17): fetchDashboard(), fetchHourlySignals(), fetchMetar(), runScan(), simulateTrade(), startBot(), stopBot(), App() (+9 more)

### Community 11 - "AILog"
Cohesion: 0.14
Nodes (3): AICallLogger, AICallRecord, AILog

### Community 12 - "dependencies"
Cohesion: 0.11
Nodes (19): dependencies, axios, clsx, d3-geo, date-fns, framer-motion, leaflet, lucide-react (+11 more)

### Community 13 - "api.ts"
Cohesion: 0.13
Nodes (9): api, Props, BtcPrice, BtcWindow, CalibrationSummary, DashboardData, MetarObservation, Signal (+1 more)

### Community 14 - "compilerOptions"
Cohesion: 0.11
Nodes (18): compilerOptions, allowImportingTsExtensions, isolatedModules, jsx, lib, module, moduleResolution, noEmit (+10 more)

### Community 15 - "WeatherSignal"
Cohesion: 0.36
Nodes (7): CITIES, CityMarker, Props, Props, WeatherForecast, WeatherSignal, react-globe.gl

### Community 18 - "FilterBar.tsx"
Cohesion: 0.40
Nodes (3): FilterState, Props, STATUSES

### Community 20 - "crypto.py"
Cohesion: 0.13
Nodes (9): BtcMicrostructure, compute_btc_microstructure(), _compute_rsi(), CryptoPrice, estimate_price_probability(), fetch_binance_klines(), fetch_crypto_price(), fetch_multiple_prices() (+1 more)

### Community 21 - "Prediction Market Trading Bot"
Cohesion: 0.17
Nodes (11): Layer 1: Market Scanner, Layer 2A: Weather Pipeline, Trading Bot Architecture, Trading Dashboard UI Screenshot, Frontend Web Entry Point, Fractional Kelly Criterion Sizing, Prediction Market Trading Bot, BTC 5-Minute Microstructure Strategy (+3 more)

### Community 23 - "utils.ts"
Cohesion: 0.22
Nodes (3): AgreementBar(), WeatherPanel(), platformStyles

### Community 25 - "EquityChart.tsx"
Cohesion: 0.27
Nodes (8): CustomTooltip(), EquityChart(), Props, Props, BotStats, EquityPoint, framer-motion, recharts

### Community 27 - "compilerOptions"
Cohesion: 0.25
Nodes (7): compilerOptions, allowSyntheticDefaultImports, composite, module, moduleResolution, skipLibCheck, include

### Community 28 - "deploy"
Cohesion: 0.25
Nodes (7): build, builder, deploy, healthcheckPath, restartPolicyType, startCommand, $schema

### Community 31 - "WeatherMarket"
Cohesion: 0.13
Nodes (5): WeatherTradingSignal, WeatherMarket, run_dual_track_verification(), run_test(), run_scheduler_and_settlement_checks()

### Community 34 - "MicrostructurePanel.tsx"
Cohesion: 0.53
Nodes (5): MeterBar(), MicrostructurePanel(), Props, RsiGauge(), Microstructure

### Community 35 - "vercel.json"
Cohesion: 0.33
Nodes (5): builds, name, routes, $schema, version

### Community 36 - "frontend/vercel.json"
Cohesion: 0.40
Nodes (4): buildCommand, framework, outputDirectory, rewrites

### Community 38 - "weather_signals.py"
Cohesion: 0.18
Nodes (3): _celsius_to_fahrenheit(), fetch_ensemble_forecast(), fetch_nws_observed_temperature()

### Community 44 - "get_recent_events"
Cohesion: 0.40
Nodes (4): EventResponse, get_events(), websocket_events(), get_recent_events()

### Community 48 - "🌐 24/7 Free GCP Deployment Guide ($0.00 / month forever)"
Cohesion: 0.13
Nodes (14): 🌐 24/7 Free GCP Deployment Guide ($0.00 / month forever), ⚡ 24/7 Operations & Maintenance, Accessing the Web Dashboard, Check Service Status, Deploy to Cloud Run:, 💰 How is it $0 / Month Forever?, 🚀 Option A: 1-Click Automated Deployment (`deploy_gcp.sh`), 🛠️ Option B: Manual Setup on Any GCP VM (+6 more)

### Community 52 - "main.tsx"
Cohesion: 0.18
Nodes (7): ErrorBoundary, Props, State, queryClient, react, react-dom, @tanstack/react-query

### Community 53 - "weather_markets.py"
Cohesion: 0.24
Nodes (4): _extract_date(), fetch_polymarket_weather_markets(), _parse_polymarket_weather(), _parse_weather_market_title()

### Community 54 - "SignalsTable.tsx"
Cohesion: 0.36
Nodes (7): CategoryBadge(), EdgeBar(), PlatformBadge(), SignalsTable(), SortDir, SortKey, UnifiedSignal

### Community 56 - "EdgeDistribution.tsx"
Cohesion: 0.36
Nodes (7): BUCKETS, CustomTooltip(), EdgeDistribution(), getBucket(), Props, Props, HourlySignal

### Community 58 - "startup"
Cohesion: 0.29
Nodes (4): shutdown(), startup(), stop_scheduler(), init_db()

### Community 59 - "TradesTable.tsx"
Cohesion: 0.22
Nodes (8): LogEntry, Props, Props, SortDir, SortKey, Trade, date-fns, lucide-react

### Community 63 - "devDependencies"
Cohesion: 0.22
Nodes (9): devDependencies, autoprefixer, postcss, tailwindcss, @types/react, @types/react-dom, typescript, vite (+1 more)

### Community 65 - "scheduler.py"
Cohesion: 0.12
Nodes (11): hourly_scan_and_trade_job(), heartbeat_job(), is_scheduler_running(), run_manual_scan(), run_manual_settlement(), scan_and_trade_job(), settlement_job(), start_scheduler() (+3 more)

### Community 67 - "scripts"
Cohesion: 0.50
Nodes (4): scripts, build, dev, preview

### Community 68 - "Signal"
Cohesion: 0.14
Nodes (8): CalibrationBucket, CalibrationSummary, _compute_calibration_summary(), get_calibration(), get_paper_training_summary(), _persist_weather_signals(), ScanLog, Signal

## Knowledge Gaps
- **122 isolated node(s):** `Config`, `deploy_gcp.sh script`, `name`, `private`, `version` (+117 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 432 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **29 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `TestC137QuantitativeCore` connect `TestC137QuantitativeCore` to `KalshiClient`, `SettlementCalibrationHarness`, `scheduler.py`, `.test_kalshi_houston_series_negative_and_inclusive_strikes_and_empty_book`, `test_c137_quant.py`, `BotState`, `.test_nws_observation_weather_settlement_fallback`, `.test_kalshi_v2_create_order_yes_leg_and_auth_hygiene`, `EnsembleForecast`, `.test_simulate_trade_is_paper_and_stats_live_purity`, `WeatherMarket`?**
  _High betweenness centrality (0.055) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `KalshiClient` (e.g. with `get_kalshi_status()` and `reset_bot()`) actually correct?**
  _`KalshiClient` has 4 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Config`, `deploy_gcp.sh script`, `name` to the rest of the system?**
  _122 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `KalshiClient` be split into smaller, more focused modules?**
  _Cohesion score 0.05727644652250146 - nodes in this community are weakly interconnected._
- **Why does `KalshiClient` connect `KalshiClient` to `scheduler.py`, `hourly_signals.py`, `test_c137_quant.py`, `BotState`, `api/main.py`, `weather_signals.py`, `settlement.py`, `.test_kalshi_v2_create_order_yes_leg_and_auth_hygiene`, `TestC137QuantitativeCore`, `startup`?**
  _High betweenness centrality (0.054) - this node is a cross-community bridge._
- **Are the 17 inferred relationships involving `Trade` (e.g. with `get_dashboard()` and `get_equity_curve()`) actually correct?**
  _`Trade` has 17 INFERRED edges - model-reasoned connections that need verification._
- **Should `btc_markets.py` be split into smaller, more focused modules?**
  _Cohesion score 0.08888888888888889 - nodes in this community are weakly interconnected._