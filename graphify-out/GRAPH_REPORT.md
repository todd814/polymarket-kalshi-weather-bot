# Graph Report - polymarket-kalshi-weather-bot  (2026-10-31)

## Corpus Check
- 66 files · ~68,461 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 9 file(s) not represented in the graph (top: (none) 3, .example 2, .jsonl 2)

## Summary
- 795 nodes · 1540 edges · 62 communities (35 shown, 27 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 75 edges (avg confidence: 0.93)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `80844b86`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- test_kalshi_demo.py
- btc_markets.py
- typing
- package.json
- KalshiClient
- signals.py
- BotState
- get_dashboard
- database.py
- Trade
- App.tsx
- AILog
- dependencies
- api.ts
- compilerOptions
- EdgeDistribution.tsx
- ClaudeAnalyzer
- GroqClassifier
- Terminal.tsx
- EnsembleForecast
- get
- Prediction Market Trading Bot
- base.py
- TradesTable.tsx
- ConnectionManager
- EquityChart.tsx
- BaseAIClient
- compilerOptions
- deploy
- AIAnalysis
- claude.py
- TestC137QuantitativeCore
- _signal_to_response
- WeatherSignal
- MicrostructurePanel.tsx
- vercel.json
- frontend/vercel.json
- WeatherMarket
- crypto.py
- vite-env.d.ts
- Platform and API Research
- Layer 2B: Econ Pipeline
- api/main.py
- scheduler.py
- 🌐 24/7 Free GCP Deployment Guide ($0.00 / month forever)
- Backend Dependencies
- main.tsx
- scan_for_weather_signals
- SignalsTable.tsx
- weather_signals.py
- .test_simulate_trade_is_paper_and_stats_live_purity
- .test_kalshi_houston_series_negative_and_inclusive_strikes_and_empty_book
- deploy_gcp.sh

## God Nodes (most connected - your core abstractions)
1. `TestC137QuantitativeCore` - 30 edges
2. `KalshiClient` - 29 edges
3. `Trade` - 27 edges
4. `BotState` - 25 edges
5. `App()` - 22 edges
6. `get_dashboard()` - 21 edges
7. `EnsembleForecast` - 19 edges
8. `WeatherMarket` - 19 edges
9. `log_event()` - 18 edges
10. `scan_for_signals()` - 17 edges

## Surprising Connections (you probably didn't know these)
- `Frontend Web Entry Point` --semantically_similar_to--> `Trading Dashboard UI Screenshot`  [INFERRED] [semantically similar]
  frontend/index.html → docs/dashboard.png
- `TestC137QuantitativeCore` --uses--> `SettlementCalibrationHarness`  [INFERRED]
  test_c137_quant.py → backend/analytics/calibration.py
- `TestC137QuantitativeCore` --uses--> `MicrostructureEngine`  [INFERRED]
  test_c137_quant.py → backend/analytics/microstructure.py
- `TestC137QuantitativeCore` --uses--> `OmniRiskGovernor`  [INFERRED]
  test_c137_quant.py → backend/analytics/risk_governor.py
- `TestC137QuantitativeCore` --uses--> `WeatherTradingSignal`  [INFERRED]
  test_c137_quant.py → backend/core/weather_signals.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Weather Trading Subsystem** — architecture_layer2a_weather_pipeline, readme_strategy_weather_temperature, validated_research_kalshi_weather_tickers [INFERRED 0.85]

## Communities (62 total, 27 thin omitted)

### Community 0 - "test_kalshi_demo.py"
Cohesion: 0.07
Nodes (16): Config, Settings, get_base_url(), _extract_price(), fetch_kalshi_weather_markets(), _parse_kalshi_market(), fetch_ensemble_forecast(), _extract_date() (+8 more)

### Community 1 - "btc_markets.py"
Cohesion: 0.07
Nodes (15): BtcMarket, _compute_window_slugs(), fetch_active_btc_markets(), fetch_btc_market_by_slug(), fetch_btc_market_for_settlement(), is_valid_btc_slug(), _parse_event_to_btc_market(), _round_to_5min() (+7 more)

### Community 2 - "typing"
Cohesion: 0.05
Nodes (7): SettlementCalibrationHarness, SettlementRecord, MicrostructureEngine, ArbitrageOpportunity, MonotonicityScanner, GateResult, OmniRiskGovernor

### Community 3 - "package.json"
Cohesion: 0.05
Nodes (36): devDependencies, autoprefixer, postcss, tailwindcss, @types/react, @types/react-dom, typescript, vite (+28 more)

### Community 5 - "signals.py"
Cohesion: 0.15
Nodes (8): calculate_edge(), generate_btc_signal(), get_actionable_signals(), _persist_signals(), scan_for_signals(), test(), TradingSignal, Signal

### Community 6 - "BotState"
Cohesion: 0.14
Nodes (15): reset_bot(), settle_trades_endpoint(), shutdown(), simulate_trade(), start_bot(), startup(), stop_bot(), heartbeat_job() (+7 more)

### Community 7 - "get_dashboard"
Cohesion: 0.16
Nodes (15): BotStats, BtcPriceResponse, BtcWindowResponse, CalibrationBucket, CalibrationSummary, _compute_calibration_summary(), DashboardData, get_calibration() (+7 more)

### Community 8 - "database.py"
Cohesion: 0.13
Nodes (4): BtcPriceSnapshot, ensure_schema(), init_db(), ScanLog

### Community 9 - "Trade"
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
Nodes (9): api, Props, Props, BotStats, BtcPrice, BtcWindow, CalibrationSummary, DashboardData (+1 more)

### Community 14 - "compilerOptions"
Cohesion: 0.11
Nodes (18): compilerOptions, allowImportingTsExtensions, isolatedModules, jsx, lib, module, moduleResolution, noEmit (+10 more)

### Community 15 - "EdgeDistribution.tsx"
Cohesion: 0.36
Nodes (7): BUCKETS, CustomTooltip(), EdgeDistribution(), getBucket(), Props, Props, Signal

### Community 18 - "Terminal.tsx"
Cohesion: 0.22
Nodes (6): FilterState, Props, STATUSES, LogEntry, Props, lucide-react

### Community 20 - "get"
Cohesion: 0.13
Nodes (8): get_btc_price(), get_btc_windows(), get_c137_calibration(), get_kalshi_status(), get_weather_forecasts(), health(), root(), serve_frontend()

### Community 21 - "Prediction Market Trading Bot"
Cohesion: 0.17
Nodes (11): Layer 1: Market Scanner, Layer 2A: Weather Pipeline, Trading Bot Architecture, Trading Dashboard UI Screenshot, Frontend Web Entry Point, Fractional Kelly Criterion Sizing, Prediction Market Trading Bot, BTC 5-Minute Microstructure Strategy (+3 more)

### Community 23 - "TradesTable.tsx"
Cohesion: 0.18
Nodes (6): Props, SortDir, SortKey, Trade, platformStyles, date-fns

### Community 25 - "EquityChart.tsx"
Cohesion: 0.47
Nodes (5): CustomTooltip(), EquityChart(), Props, EquityPoint, recharts

### Community 27 - "compilerOptions"
Cohesion: 0.25
Nodes (7): compilerOptions, allowSyntheticDefaultImports, composite, module, moduleResolution, skipLibCheck, include

### Community 28 - "deploy"
Cohesion: 0.25
Nodes (7): build, builder, deploy, healthcheckPath, restartPolicyType, startCommand, $schema

### Community 32 - "_signal_to_response"
Cohesion: 0.33
Nodes (4): get_actionable_signals(), get_signals(), _signal_to_response(), SignalResponse

### Community 33 - "WeatherSignal"
Cohesion: 0.33
Nodes (8): CITIES, CityMarker, Props, AgreementBar(), Props, WeatherPanel(), WeatherForecast, WeatherSignal

### Community 34 - "MicrostructurePanel.tsx"
Cohesion: 0.53
Nodes (5): MeterBar(), MicrostructurePanel(), Props, RsiGauge(), Microstructure

### Community 35 - "vercel.json"
Cohesion: 0.33
Nodes (5): builds, name, routes, $schema, version

### Community 36 - "frontend/vercel.json"
Cohesion: 0.40
Nodes (4): buildCommand, framework, outputDirectory, rewrites

### Community 37 - "WeatherMarket"
Cohesion: 0.15
Nodes (4): WeatherTradingSignal, WeatherMarket, run_test(), run_scheduler_and_settlement_checks()

### Community 38 - "crypto.py"
Cohesion: 0.15
Nodes (8): BtcMicrostructure, compute_btc_microstructure(), _compute_rsi(), CryptoPrice, estimate_price_probability(), fetch_crypto_price(), fetch_multiple_prices(), test()

### Community 44 - "api/main.py"
Cohesion: 0.15
Nodes (7): EventResponse, get_events(), get_weather_signals(), _weather_signal_to_response(), WeatherSignalResponse, websocket_events(), get_recent_events()

### Community 46 - "scheduler.py"
Cohesion: 0.15
Nodes (6): is_scheduler_running(), run_manual_scan(), run_manual_settlement(), scan_and_trade_job(), settlement_job(), update_bot_state_with_settlements()

### Community 48 - "🌐 24/7 Free GCP Deployment Guide ($0.00 / month forever)"
Cohesion: 0.13
Nodes (14): 🌐 24/7 Free GCP Deployment Guide ($0.00 / month forever), ⚡ 24/7 Operations & Maintenance, Accessing the Web Dashboard, Check Service Status, Deploy to Cloud Run:, 💰 How is it $0 / Month Forever?, 🚀 Option A: 1-Click Automated Deployment (`deploy_gcp.sh`), 🛠️ Option B: Manual Setup on Any GCP VM (+6 more)

### Community 52 - "main.tsx"
Cohesion: 0.18
Nodes (7): ErrorBoundary, Props, State, queryClient, react, react-dom, @tanstack/react-query

### Community 53 - "scan_for_weather_signals"
Cohesion: 0.20
Nodes (6): get_weather_markets(), run_scan(), WeatherMarketResponse, _persist_weather_signals(), scan_for_weather_signals(), fetch_polymarket_weather_markets()

### Community 54 - "SignalsTable.tsx"
Cohesion: 0.36
Nodes (7): CategoryBadge(), EdgeBar(), PlatformBadge(), SignalsTable(), SortDir, SortKey, UnifiedSignal

## Knowledge Gaps
- **122 isolated node(s):** `Config`, `deploy_gcp.sh script`, `name`, `private`, `version` (+117 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 397 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **27 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `TestC137QuantitativeCore` connect `TestC137QuantitativeCore` to `typing`, `KalshiClient`, `WeatherMarket`, `BotState`, `Trade`, `EnsembleForecast`, `.test_simulate_trade_is_paper_and_stats_live_purity`, `.test_nws_observation_weather_settlement_fallback`, `.test_weather_signal_ratchet_and_single_db_session`, `.test_kalshi_houston_series_negative_and_inclusive_strikes_and_empty_book`?**
  _High betweenness centrality (0.059) - this node is a cross-community bridge._
- **Are the 9 inferred relationships involving `TestC137QuantitativeCore` (e.g. with `SettlementCalibrationHarness` and `MicrostructureEngine`) actually correct?**
  _`TestC137QuantitativeCore` has 9 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Config`, `deploy_gcp.sh script`, `name` to the rest of the system?**
  _122 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `test_kalshi_demo.py` be split into smaller, more focused modules?**
  _Cohesion score 0.06802721088435375 - nodes in this community are weakly interconnected._
- **Why does `AILog` connect `AILog` to `BotState`, `database.py`, `api/main.py`, `ClaudeAnalyzer`, `GroqClassifier`, `base.py`, `claude.py`?**
  _High betweenness centrality (0.054) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `KalshiClient` (e.g. with `get_kalshi_status()` and `reset_bot()`) actually correct?**
  _`KalshiClient` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Should `btc_markets.py` be split into smaller, more focused modules?**
  _Cohesion score 0.07149758454106281 - nodes in this community are weakly interconnected._