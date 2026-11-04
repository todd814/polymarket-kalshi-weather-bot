# Graph Report - polymarket-kalshi-weather-bot  (2026-11-04)

## Corpus Check
- 70 files · ~71,004 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 9 file(s) not represented in the graph (top: (none) 3, .example 2, .jsonl 2)

## Summary
- 839 nodes · 1659 edges · 73 communities (41 shown, 32 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 83 edges (avg confidence: 0.93)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `e55f7cba`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- KalshiClient
- btc_markets.py
- test_c137_quant.py
- package.json
- hourly_signals.py
- signals.py
- scheduler.py
- BaseModel
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
- get
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
- TestC137QuantitativeCore
- get_dashboard
- SettlementCalibrationHarness
- MicrostructurePanel.tsx
- vercel.json
- frontend/vercel.json
- MicrostructureEngine
- crypto.py
- vite-env.d.ts
- Platform and API Research
- Layer 2B: Econ Pipeline
- api/main.py
- BtcMarket
- 🌐 24/7 Free GCP Deployment Guide ($0.00 / month forever)
- Backend Dependencies
- main.tsx
- typing
- SignalsTable.tsx
- weather.py
- .test_simulate_trade_is_paper_and_stats_live_purity
- TradesTable.tsx
- deploy_gcp.sh
- dataclasses
- devDependencies
- get_recent_events
- get_weather_signals
- Settings
- scripts
- get_btc_windows
- get_weather_forecasts
- get_weather_markets
- vite.config.ts

## God Nodes (most connected - your core abstractions)
1. `KalshiClient` - 31 edges
2. `Trade` - 30 edges
3. `TestC137QuantitativeCore` - 30 edges
4. `BotState` - 27 edges
5. `App()` - 22 edges
6. `get_dashboard()` - 21 edges
7. `Signal` - 20 edges
8. `EnsembleForecast` - 19 edges
9. `WeatherMarket` - 19 edges
10. `log_event()` - 18 edges

## Surprising Connections (you probably didn't know these)
- `Frontend Web Entry Point` --semantically_similar_to--> `Trading Dashboard UI Screenshot`  [INFERRED] [semantically similar]
  frontend/index.html → docs/dashboard.png
- `TestC137QuantitativeCore` --uses--> `SettlementCalibrationHarness`  [INFERRED]
  test_c137_quant.py → backend/analytics/calibration.py
- `TestC137QuantitativeCore` --uses--> `MicrostructureEngine`  [INFERRED]
  test_c137_quant.py → backend/analytics/microstructure.py
- `TestC137QuantitativeCore` --uses--> `OmniRiskGovernor`  [INFERRED]
  test_c137_quant.py → backend/analytics/risk_governor.py
- `TestC137QuantitativeCore` --uses--> `KalshiClient`  [INFERRED]
  test_c137_quant.py → backend/data/kalshi_client.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Weather Trading Subsystem** — architecture_layer2a_weather_pipeline, readme_strategy_weather_temperature, validated_research_kalshi_weather_tickers [INFERRED 0.85]

## Communities (73 total, 32 thin omitted)

### Community 0 - "KalshiClient"
Cohesion: 0.05
Nodes (13): get_base_url(), KalshiClient, _extract_price(), fetch_kalshi_weather_markets(), _parse_kalshi_market(), _extract_date(), _parse_polymarket_weather(), _parse_weather_market_title() (+5 more)

### Community 1 - "btc_markets.py"
Cohesion: 0.18
Nodes (8): _compute_window_slugs(), fetch_active_btc_markets(), fetch_btc_market_by_slug(), fetch_btc_market_for_settlement(), is_valid_btc_slug(), _parse_event_to_btc_market(), _round_to_5min(), test()

### Community 2 - "test_c137_quant.py"
Cohesion: 0.11
Nodes (4): ArbitrageOpportunity, MonotonicityScanner, GateResult, OmniRiskGovernor

### Community 3 - "package.json"
Cohesion: 0.10
Nodes (19): name, private, type, version, autoprefixer, clsx, d3-geo, leaflet (+11 more)

### Community 4 - "hourly_signals.py"
Cohesion: 0.09
Nodes (13): hourly_scan_and_trade_job(), hourly_settlement_job(), _estimate_diurnal_drift_per_hour(), evaluate_hourly_market(), HourlySignal, _normal_cdf(), scan_for_hourly_signals(), fetch_kalshi_hourly_markets() (+5 more)

### Community 5 - "signals.py"
Cohesion: 0.15
Nodes (8): calculate_edge(), calculate_kelly_size(), generate_btc_signal(), get_actionable_signals(), _persist_signals(), scan_for_signals(), test(), TradingSignal

### Community 6 - "scheduler.py"
Cohesion: 0.11
Nodes (17): run_scan(), shutdown(), start_bot(), startup(), heartbeat_job(), is_scheduler_running(), log_event(), run_manual_scan() (+9 more)

### Community 7 - "BaseModel"
Cohesion: 0.15
Nodes (10): BtcPriceResponse, CalibrationBucket, CalibrationSummary, _compute_calibration_summary(), DashboardData, get_btc_price(), get_calibration(), MicrostructureResponse (+2 more)

### Community 8 - "database.py"
Cohesion: 0.13
Nodes (4): BtcPriceSnapshot, ensure_schema(), init_db(), ScanLog

### Community 9 - "settlement.py"
Cohesion: 0.15
Nodes (10): calculate_pnl(), check_market_settlement(), check_weather_settlement(), _fetch_kalshi_resolution(), _fetch_nws_resolution(), fetch_polymarket_resolution(), _parse_market_resolution(), _search_market_in_events() (+2 more)

### Community 10 - "App.tsx"
Cohesion: 0.23
Nodes (16): fetchDashboard(), runScan(), simulateTrade(), startBot(), stopBot(), App(), CityRadarFallback(), GlobeView (+8 more)

### Community 11 - "AILog"
Cohesion: 0.14
Nodes (3): AICallLogger, AICallRecord, AILog

### Community 12 - "dependencies"
Cohesion: 0.11
Nodes (19): dependencies, axios, clsx, d3-geo, date-fns, framer-motion, leaflet, lucide-react (+11 more)

### Community 13 - "api.ts"
Cohesion: 0.13
Nodes (7): api, Props, BtcPrice, BtcWindow, CalibrationSummary, DashboardData, axios

### Community 14 - "compilerOptions"
Cohesion: 0.11
Nodes (18): compilerOptions, allowImportingTsExtensions, isolatedModules, jsx, lib, module, moduleResolution, noEmit (+10 more)

### Community 15 - "WeatherSignal"
Cohesion: 0.19
Nodes (14): BUCKETS, CustomTooltip(), EdgeDistribution(), getBucket(), Props, CITIES, CityMarker, Props (+6 more)

### Community 18 - "FilterBar.tsx"
Cohesion: 0.40
Nodes (3): FilterState, Props, STATUSES

### Community 20 - "get"
Cohesion: 0.15
Nodes (7): get_c137_calibration(), get_hourly_signals(), get_kalshi_status(), get_metar_observations(), health(), root(), serve_frontend()

### Community 21 - "Prediction Market Trading Bot"
Cohesion: 0.17
Nodes (11): Layer 1: Market Scanner, Layer 2A: Weather Pipeline, Trading Bot Architecture, Trading Dashboard UI Screenshot, Frontend Web Entry Point, Fractional Kelly Criterion Sizing, Prediction Market Trading Bot, BTC 5-Minute Microstructure Strategy (+3 more)

### Community 23 - "utils.ts"
Cohesion: 0.24
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

### Community 31 - "TestC137QuantitativeCore"
Cohesion: 0.08
Nodes (7): WeatherTradingSignal, WeatherMarket, TestC137QuantitativeCore, run_dual_track_verification(), run_empty_book_check(), run_test(), run_scheduler_and_settlement_checks()

### Community 32 - "get_dashboard"
Cohesion: 0.29
Nodes (4): get_actionable_signals(), get_dashboard(), get_signals(), _signal_to_response()

### Community 34 - "MicrostructurePanel.tsx"
Cohesion: 0.53
Nodes (5): MeterBar(), MicrostructurePanel(), Props, RsiGauge(), Microstructure

### Community 35 - "vercel.json"
Cohesion: 0.33
Nodes (5): builds, name, routes, $schema, version

### Community 36 - "frontend/vercel.json"
Cohesion: 0.40
Nodes (4): buildCommand, framework, outputDirectory, rewrites

### Community 38 - "crypto.py"
Cohesion: 0.14
Nodes (9): BtcMicrostructure, compute_btc_microstructure(), _compute_rsi(), CryptoPrice, estimate_price_probability(), fetch_binance_klines(), fetch_crypto_price(), fetch_multiple_prices() (+1 more)

### Community 44 - "api/main.py"
Cohesion: 0.16
Nodes (10): BotStats, get_equity_curve(), get_stats(), get_trades(), reset_bot(), settle_trades_endpoint(), simulate_trade(), stop_bot() (+2 more)

### Community 48 - "🌐 24/7 Free GCP Deployment Guide ($0.00 / month forever)"
Cohesion: 0.13
Nodes (14): 🌐 24/7 Free GCP Deployment Guide ($0.00 / month forever), ⚡ 24/7 Operations & Maintenance, Accessing the Web Dashboard, Check Service Status, Deploy to Cloud Run:, 💰 How is it $0 / Month Forever?, 🚀 Option A: 1-Click Automated Deployment (`deploy_gcp.sh`), 🛠️ Option B: Manual Setup on Any GCP VM (+6 more)

### Community 52 - "main.tsx"
Cohesion: 0.18
Nodes (7): ErrorBoundary, Props, State, queryClient, react, react-dom, @tanstack/react-query

### Community 53 - "typing"
Cohesion: 0.15
Nodes (3): _persist_weather_signals(), _extract_price(), fetch_polymarket_weather_markets()

### Community 54 - "SignalsTable.tsx"
Cohesion: 0.36
Nodes (7): CategoryBadge(), EdgeBar(), PlatformBadge(), SignalsTable(), SortDir, SortKey, UnifiedSignal

### Community 55 - "weather.py"
Cohesion: 0.23
Nodes (5): generate_weather_signal(), _celsius_to_fahrenheit(), fetch_ensemble_forecast(), fetch_nws_observed_temperature(), test_weather_ensemble_and_edge_calculation()

### Community 59 - "TradesTable.tsx"
Cohesion: 0.22
Nodes (8): LogEntry, Props, Props, SortDir, SortKey, Trade, date-fns, lucide-react

### Community 62 - "dataclasses"
Cohesion: 0.31
Nodes (3): btc_market_to_market_data(), fetch_all_markets(), MarketData

### Community 63 - "devDependencies"
Cohesion: 0.22
Nodes (9): devDependencies, autoprefixer, postcss, tailwindcss, @types/react, @types/react-dom, typescript, vite (+1 more)

### Community 64 - "get_recent_events"
Cohesion: 0.40
Nodes (4): EventResponse, get_events(), websocket_events(), get_recent_events()

### Community 65 - "get_weather_signals"
Cohesion: 0.50
Nodes (3): get_weather_signals(), _weather_signal_to_response(), WeatherSignalResponse

### Community 67 - "scripts"
Cohesion: 0.50
Nodes (4): scripts, build, dev, preview

## Knowledge Gaps
- **122 isolated node(s):** `Config`, `deploy_gcp.sh script`, `name`, `private`, `version` (+117 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 419 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **32 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `TestC137QuantitativeCore` connect `TestC137QuantitativeCore` to `KalshiClient`, `SettlementCalibrationHarness`, `test_c137_quant.py`, `MicrostructureEngine`, `scheduler.py`, `.test_nws_local_midnight_and_obs_cache`, `api/main.py`, `EnsembleForecast`, `.test_simulate_trade_is_paper_and_stats_live_purity`, `.test_nws_observation_weather_settlement_fallback`, `.test_weather_signal_ratchet_and_single_db_session`?**
  _High betweenness centrality (0.057) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `KalshiClient` (e.g. with `get_kalshi_status()` and `reset_bot()`) actually correct?**
  _`KalshiClient` has 4 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Config`, `deploy_gcp.sh script`, `name` to the rest of the system?**
  _122 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `KalshiClient` be split into smaller, more focused modules?**
  _Cohesion score 0.054354178842782 - nodes in this community are weakly interconnected._
- **Why does `KalshiClient` connect `KalshiClient` to `test_c137_quant.py`, `hourly_signals.py`, `scheduler.py`, `settlement.py`, `api/main.py`, `get`, `typing`, `TestC137QuantitativeCore`?**
  _High betweenness centrality (0.056) - this node is a cross-community bridge._
- **Are the 16 inferred relationships involving `Trade` (e.g. with `get_dashboard()` and `get_equity_curve()`) actually correct?**
  _`Trade` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Should `test_c137_quant.py` be split into smaller, more focused modules?**
  _Cohesion score 0.11231884057971014 - nodes in this community are weakly interconnected._