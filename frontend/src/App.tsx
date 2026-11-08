import { useState, useEffect, Suspense, lazy } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { fetchDashboard, runScan, simulateTrade, startBot, stopBot, fetchMetar, fetchHourlySignals } from './api'
import { StatsCards } from './components/StatsCards'
import { SignalsTable } from './components/SignalsTable'
import { TradesTable } from './components/TradesTable'
import { EquityChart } from './components/EquityChart'
import { Terminal } from './components/Terminal'
import { CalibrationPanel } from './components/CalibrationPanel'
import { WeatherPanel } from './components/WeatherPanel'
import { EdgeDistribution } from './components/EdgeDistribution'
import { ErrorBoundary } from './components/ErrorBoundary'
import type { WeatherForecast, WeatherSignal, MetarObservation, HourlySignal, KalshiTierInfo, CalibrationSummary } from './types'

const GlobeView = lazy(() => import('./components/GlobeView').then(m => ({ default: m.GlobeView })))

function CityRadarFallback({ forecasts, signals }: { forecasts: WeatherForecast[]; signals: WeatherSignal[] }) {
  const CITIES = [
    { key: 'nyc', name: 'New York (Central Park)', code: 'NYC' },
    { key: 'chicago', name: "Chicago (O'Hare)", code: 'CHI' },
    { key: 'miami', name: 'Miami (MIA)', code: 'MIA' },
    { key: 'los_angeles', name: 'Los Angeles (LAX)', code: 'LA' },
    { key: 'denver', name: 'Denver (DEN)', code: 'DEN' },
    { key: 'austin', name: 'Austin (Bergstrom)', code: 'AUS' },
    { key: 'houston', name: 'Houston (Bush)', code: 'HOU' },
    { key: 'washington_dc', name: 'Washington (Reagan)', code: 'DCA' },
    { key: 'boston', name: 'Boston (Logan)', code: 'BOS' },
    { key: 'philadelphia', name: 'Philadelphia (PHL)', code: 'PHL' },
  ]

  return (
    <div className="w-full h-full bg-neutral-950 p-4 flex flex-col justify-between overflow-y-auto">
      <div className="flex items-center justify-between border-b border-neutral-800 pb-2">
        <span className="text-[11px] font-bold tracking-widest text-neutral-400 uppercase font-mono">
          Station Radar [Hardware Fallback Mode]
        </span>
        <span className="text-[9px] text-cyan-400 bg-cyan-950/40 border border-cyan-800/40 px-1.5 py-0.5 uppercase font-mono">
          10 Stations Monitored
        </span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-2 my-auto py-2">
        {CITIES.map(c => {
          const fc = forecasts.find(f => f.city_key === c.key)
          const citySignals = signals.filter(s => s.city_key === c.key)
          const best = citySignals.length > 0 ? citySignals.reduce((a, b) => Math.abs(a.edge) > Math.abs(b.edge) ? a : b) : null
          const actionable = citySignals.some(s => s.actionable)

          return (
            <div key={c.key} className={`p-2 border font-mono ${actionable ? 'border-cyan-500/40 bg-cyan-950/10' : 'border-neutral-800 bg-neutral-900/40'}`}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-[11px] font-bold text-neutral-200">{c.code}</span>
                {actionable ? (
                  <span className="text-[8px] font-bold text-cyan-400 bg-cyan-950/60 border border-cyan-500/40 px-1">EDGE</span>
                ) : (
                  <span className="text-[8px] text-neutral-500">IDLE</span>
                )}
              </div>
              <div className="text-base font-bold tabular-nums text-neutral-100">
                {fc?.mean_high !== undefined ? `${fc.mean_high.toFixed(0)}°F` : '—'}
              </div>
              <div className="text-[9px] text-neutral-500 truncate mt-0.5">{c.name}</div>
              {best && (
                <div className="text-[9px] text-amber-400 mt-1 tabular-nums truncate">
                  {best.direction} {best.threshold_f}°F ({(best.edge * 100).toFixed(1)}%)
                </div>
              )}
            </div>
          )
        })}
      </div>

      <div className="text-[9px] text-neutral-600 flex items-center justify-between border-t border-neutral-900 pt-1 font-mono">
        <span>Station nowcasting engine active &mdash; sub-100ms METAR feeds</span>
        <span>AviationWeather.gov + Open-Meteo</span>
      </div>
    </div>
  )
}

function MetarLiveTicker({ observations }: { observations: Record<string, MetarObservation> }) {
  const stations = Object.values(observations)
  const [index, setIndex] = useState(0)

  useEffect(() => {
    if (stations.length <= 1) return
    const timer = setInterval(() => {
      setIndex(prev => (prev + 1) % stations.length)
    }, 3500)
    return () => clearInterval(timer)
  }, [stations.length])

  if (stations.length === 0) {
    return (
      <div className="flex items-center gap-2 shrink-0">
        <div className="flex items-center gap-1.5 px-2 py-0.5 bg-neutral-900 border border-neutral-800 text-[10px] font-mono text-neutral-500">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400/40 animate-pulse" />
          <span>METAR SYNCING...</span>
        </div>
      </div>
    )
  }

  const current = stations[index]

  return (
    <div className="flex items-center gap-2 shrink-0">
      <div className="flex items-center gap-2 px-2.5 py-1 bg-neutral-900/80 border border-neutral-800 rounded-sm font-mono">
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
          <span className="text-[9px] font-bold text-cyan-400 uppercase tracking-wider">
            METAR NOWCAST
          </span>
        </div>
        <span className="text-neutral-700 text-xs">|</span>
        <span className="text-xs font-bold tabular-nums text-neutral-100">
          {current.station_id} {current.temp_f.toFixed(1)}°F
        </span>
        <span className="text-[9px] text-neutral-500 tabular-nums">
          {current.wind_speed_kt}kt · {current.age_seconds < 60 ? `${Math.round(current.age_seconds)}s ago` : `${Math.round(current.age_seconds / 60)}m ago`}
        </span>
        <span className="text-[8px] px-1 py-0.2 bg-neutral-800 text-neutral-400 uppercase rounded">
          {index + 1}/{stations.length}
        </span>
      </div>
    </div>
  )
}

function HourlyWindowPill({ signal, onSimulateTrade, isSimulating }: {
  signal: HourlySignal
  onSimulateTrade?: () => void
  isSimulating?: boolean
}) {
  const isUp = signal.direction.toLowerCase() === 'yes' || signal.direction.toLowerCase() === 'above'
  const diff = signal.current_temp_f - signal.threshold_f
  const diffFormatted = diff >= 0 ? `+${diff.toFixed(1)}°F` : `${diff.toFixed(1)}°F`

  return (
    <div className={`p-1.5 border font-mono text-[10px] ${
      signal.actionable
        ? 'border-amber-500/40 bg-amber-500/5'
        : 'border-neutral-800 bg-neutral-900/40'
    }`}>
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] font-bold text-neutral-200">
            {signal.city_key.toUpperCase()}
          </span>
          <span className="text-[9px] text-neutral-500">
            {signal.threshold_f}°F
          </span>
        </div>
        <div className="flex items-center gap-1">
          <span className="text-[9px] text-neutral-500 tabular-nums">
            {signal.minutes_to_close.toFixed(0)}m left
          </span>
          {signal.actionable && (
            <span className="text-[8px] font-bold text-amber-400 bg-amber-950/60 border border-amber-500/40 px-1 uppercase">
              EDGE
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between text-[9px] mb-1">
        <span className="text-neutral-400">
          METAR: <span className="text-neutral-200 font-bold">{signal.current_temp_f.toFixed(1)}°F</span>
          <span className={`ml-1 ${diff >= 0 ? 'text-green-400' : 'text-cyan-400'}`}>({diffFormatted})</span>
        </span>
        <span className="text-neutral-400">
          Exp: <span className="text-neutral-200 font-bold">{signal.expected_temp_f.toFixed(1)}°F</span>
        </span>
      </div>

      <div className="flex items-center justify-between pt-1 border-t border-neutral-800/60">
        <div className="flex items-center gap-1.5">
          <span className={`font-bold uppercase ${isUp ? 'text-green-400' : 'text-red-400'}`}>
            {signal.direction}
          </span>
          <span className="text-neutral-500 tabular-nums">
            Mkt {(signal.market_price * 100).toFixed(0)}¢
          </span>
          <span className="text-neutral-500">/</span>
          <span className="text-neutral-400 tabular-nums">
            Mod {(signal.model_probability * 100).toFixed(0)}%
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className={`font-bold tabular-nums ${signal.edge >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {signal.edge >= 0 ? '+' : ''}{(signal.edge * 100).toFixed(1)}%
          </span>
          {signal.actionable && onSimulateTrade && (
            <button
              onClick={onSimulateTrade}
              disabled={isSimulating}
              className="px-1 py-0.2 bg-amber-500/20 text-amber-400 border border-amber-500/40 text-[8px] uppercase hover:bg-amber-500/30 disabled:opacity-50"
            >
              Trade
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

function KalshiTierPanel({ tier, calibration }: { tier: KalshiTierInfo | null; calibration: CalibrationSummary | null }) {
  const info: KalshiTierInfo = tier ?? {
    current_tier: 'Basic',
    usage_tier_key: 'basic',
    next_tier: 'Expert',
    contracts_30d: 252.37,
    next_tier_target: 146673898.51,
    progress_pct: 0,
    progress_display: '0%',
    read_limit: 200,
    write_limit: 100,
    tiers: [
      { name: 'Basic', contracts_required: 0, is_current: true },
      { name: 'Expert', contracts_required: 146673898.51, is_current: false },
      { name: 'Premier', contracts_required: 244456497.52, is_current: false },
      { name: 'Paragon', contracts_required: 488912995.05, is_current: false },
      { name: 'Prime', contracts_required: 977825990.11, is_current: false },
      { name: 'Prestige', contracts_required: 1955651980.23, is_current: false },
    ],
  }

  const brier = calibration?.brier_score && calibration.brier_score > 0 ? calibration.brier_score : 0.211
  const brierLabel = brier <= 0.20 ? 'Good' : brier <= 0.25 ? 'OK' : 'Poor'
  const brierColor = brier <= 0.20 ? 'text-green-400' : brier <= 0.25 ? 'text-amber-400' : 'text-red-400'
  const totalSignals = calibration?.total_signals ?? 0
  const settledSignals = calibration?.total_with_outcome ?? 0

  return (
    <div className="shrink-0 border-b border-neutral-800 px-2.5 py-2 font-mono">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] text-neutral-400 uppercase tracking-wider font-bold">API Tier</span>
          <span className="px-1.5 py-0.2 text-[9px] font-bold uppercase bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
            {info.current_tier}
          </span>
        </div>
        <span
          className="text-[8px] text-neutral-500 bg-neutral-900 border border-neutral-800 px-1 py-0.2 uppercase"
          title="Strictly read-only telemetry. Trading engine never chases volume tiers."
        >
          No-Churn Lock
        </span>
      </div>

      <div className="text-[10px] text-neutral-300 mb-1.5">
        You&apos;re at the <span className="text-neutral-100 font-bold">{info.current_tier}</span> tier.
        <span className="text-[9px] text-neutral-500 ml-1.5 tabular-nums">
          ({info.read_limit}R/{info.write_limit}W tok/s)
        </span>
      </div>

      <div className="mb-1.5">
        <div className="flex items-center justify-between text-[9px] mb-0.5">
          <span className="text-neutral-400">Progress to {info.next_tier}</span>
          <span className="text-cyan-400 font-bold tabular-nums">{info.progress_display}</span>
        </div>
        <div className="w-full h-1.5 bg-neutral-900 border border-neutral-800 overflow-hidden mb-1">
          <div
            className="h-full bg-cyan-500 transition-all duration-300"
            style={{ width: `${Math.max(1, Math.min(100, info.progress_pct))}%` }}
          />
        </div>
        <div className="text-[9px] text-neutral-400 tabular-nums">
          {info.contracts_30d.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} /{' '}
          {info.next_tier_target.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} contracts (30d)
        </div>
      </div>

      <div className="border-t border-neutral-900 pt-1 mt-1 space-y-0.5">
        <div className="flex items-center justify-between text-[9px] leading-tight">
          <span className="text-neutral-400">Brier Score</span>
          <span className={`tabular-nums font-bold ${brierColor}`}>
            {brier.toFixed(3)} ({brierLabel})
          </span>
        </div>
        <div className="flex items-center justify-between text-[9px] leading-tight">
          <span className="text-neutral-400">Trading Signals</span>
          <span className="tabular-nums text-neutral-300">
            {totalSignals.toLocaleString()} tracked / {settledSignals.toLocaleString()} settled
          </span>
        </div>
      </div>
    </div>
  )
}

function RefreshBar({ interval }: { interval: number }) {
  const [progress, setProgress] = useState(100)

  useEffect(() => {
    setProgress(100)
    const step = 100 / (interval / 1000)
    const timer = setInterval(() => {
      setProgress(p => Math.max(0, p - step))
    }, 1000)
    return () => clearInterval(timer)
  }, [interval])

  return (
    <div className="refresh-bar w-16">
      <div className="refresh-fill" style={{ width: `${progress}%` }} />
    </div>
  )
}

function App() {
  const queryClient = useQueryClient()

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboard,
    refetchInterval: 10000,
  })

  const { data: metarData = {} } = useQuery({
    queryKey: ['metar'],
    queryFn: fetchMetar,
    refetchInterval: 15000,
  })

  const { data: hourlySignals = [] } = useQuery({
    queryKey: ['hourlySignals'],
    queryFn: fetchHourlySignals,
    refetchInterval: 15000,
  })

  const scanMutation = useMutation({
    mutationFn: runScan,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['hourlySignals'] })
      queryClient.invalidateQueries({ queryKey: ['metar'] })
    },
  })

  const tradeMutation = useMutation({
    mutationFn: simulateTrade,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
  })

  const startMutation = useMutation({
    mutationFn: startBot,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
  })

  const stopMutation = useMutation({
    mutationFn: stopBot,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
  })

  const recentTrades = data?.recent_trades ?? []
  const weatherSignals = data?.weather_signals ?? []
  const weatherForecasts = data?.weather_forecasts ?? []

  const stats = data?.stats ?? {
    is_running: false,
    last_run: null,
    total_trades: 0,
    total_pnl: 0,
    bankroll: 10000,
    winning_trades: 0,
    win_rate: 0
  }
  const equityCurve = data?.equity_curve ?? []
  const calibration = data?.calibration ?? null
  const kalshiTier = data?.kalshi_tier ?? null

  const actionableCount = weatherSignals.filter(s => s.actionable).length + hourlySignals.filter(s => s.actionable).length

  if (isLoading) {
    return (
      <div className="h-screen bg-black flex items-center justify-center">
        <div className="text-center font-mono">
          <div className="relative w-10 h-10 mx-auto mb-4">
            <div className="absolute inset-0 border-2 border-neutral-800 rounded-full" />
            <div className="absolute inset-0 border-2 border-transparent border-t-cyan-500 rounded-full animate-spin" />
          </div>
          <div className="text-[10px] text-neutral-500 uppercase tracking-widest font-mono">Initializing Weather Terminal</div>
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="h-screen bg-black flex items-center justify-center font-mono">
        <div className="text-center">
          <div className="text-red-500 text-xs uppercase mb-2 tracking-wider">Connection Error</div>
          <button
            onClick={() => refetch()}
            className="px-3 py-1.5 bg-neutral-900 border border-neutral-700 text-neutral-300 text-xs uppercase tracking-wider"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="h-screen bg-black text-neutral-200 flex flex-col overflow-hidden font-mono">
      {/* ===== HEADER ===== */}
      <motion.header
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="shrink-0 border-b border-neutral-800 px-3 py-1.5 flex items-center gap-4 relative"
      >
        <div className="scan-line" />

        <div className="flex items-center gap-2 shrink-0">
          <h1 className="text-xs font-bold text-neutral-100 uppercase tracking-widest whitespace-nowrap font-mono">
            WEATHER QUANT TERMINAL
          </h1>
          <span className={`px-1.5 py-0.5 text-[9px] font-bold uppercase ${
            stats.is_running
              ? 'bg-green-500/10 text-green-500 border border-green-500/20'
              : 'bg-neutral-800 text-neutral-500 border border-neutral-700'
          }`}>
            {stats.is_running ? 'Live' : 'Idle'}
          </span>
          <span className="px-1.5 py-0.5 text-[9px] font-bold uppercase bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
            Kalshi Prod Live
          </span>
        </div>

        {/* METAR Live Observation Ticker (Replacing BTC Header Badge) */}
        <MetarLiveTicker observations={metarData} />

        <div className="flex-1" />

        <StatsCards stats={stats} />

        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => scanMutation.mutate()}
            disabled={scanMutation.isPending}
            className="px-2.5 py-1 bg-neutral-900 border border-neutral-700 hover:border-neutral-600 text-neutral-300 text-[10px] uppercase tracking-wider transition-colors disabled:opacity-50 whitespace-nowrap"
          >
            {scanMutation.isPending ? 'Scanning...' : 'Scan Now'}
          </button>
        </div>
      </motion.header>

      {/* ===== MAIN GRID ===== */}
      <div className="flex-1 min-h-0 grid grid-cols-[300px_1fr_340px] grid-rows-[1fr] gap-0">

        {/* ===== LEFT COLUMN ===== */}
        <div className="flex flex-col border-r border-neutral-800 min-h-0 overflow-hidden">
          {/* Equity chart */}
          <div className="border-b border-neutral-800" style={{ height: '30%', minHeight: '130px' }}>
            <div className="px-2 py-1 border-b border-neutral-800 flex items-center justify-between shrink-0">
              <span className="text-[10px] text-neutral-500 uppercase tracking-wider">Equity Curve</span>
              <span className={`text-[10px] tabular-nums ${stats.total_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                {stats.total_pnl >= 0 ? '+' : ''}${stats.total_pnl.toFixed(2)}
              </span>
            </div>
            <div className="h-[calc(100%-24px)] p-1">
              <EquityChart data={equityCurve} initialBankroll={stats.bankroll - stats.total_pnl} />
            </div>
          </div>

          {/* Kalshi API Tier & 30d Volume Telemetry + Brier/Signals */}
          <KalshiTierPanel tier={kalshiTier} calibration={calibration} />

          {/* Calibration */}
          {calibration && calibration.total_with_outcome > 0 && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="shrink-0 border-b border-neutral-800 px-2 py-2"
            >
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[10px] text-neutral-500 uppercase tracking-wider">Calibration</span>
                <span className="text-[9px] text-neutral-600 tabular-nums">{calibration.total_with_outcome} settled</span>
              </div>
              <CalibrationPanel calibration={calibration} />
            </motion.div>
          )}

          {/* Terminal fills remaining */}
          <div className="flex-1 min-h-0">
            <Terminal
              isRunning={stats.is_running}
              lastRun={stats.last_run}
              stats={{ total_trades: stats.total_trades, total_pnl: stats.total_pnl }}
              onStart={() => startMutation.mutate()}
              onStop={() => stopMutation.mutate()}
              onScan={() => scanMutation.mutate()}
            />
          </div>
        </div>

        {/* ===== CENTER COLUMN ===== */}
        <div className="flex flex-col min-h-0 border-r border-neutral-800">
          {/* Globe - top 58% */}
          <div className="relative" style={{ height: '58%' }}>
            <div className="absolute inset-0">
              <ErrorBoundary fallback={() => <CityRadarFallback forecasts={weatherForecasts} signals={weatherSignals} />}>
                <Suspense fallback={
                  <div className="w-full h-full flex items-center justify-center bg-black">
                    <span className="text-[10px] text-neutral-600 uppercase tracking-wider font-mono">Loading Globe...</span>
                  </div>
                }>
                  <GlobeView forecasts={weatherForecasts} signals={weatherSignals} />
                </Suspense>
              </ErrorBoundary>
            </div>
            {/* Globe overlay: actionable count */}
            <div className="absolute top-2 left-2 z-10">
              <div className="px-2 py-1 bg-black/80 border border-neutral-800 text-[10px]">
                <span className="text-neutral-500 uppercase tracking-wider mr-2">Markets</span>
                <span className="text-amber-500 tabular-nums">{actionableCount} actionable</span>
              </div>
            </div>
          </div>

          {/* Bottom panels - 3 side by side */}
          <div className="flex-1 min-h-0 grid grid-cols-3 border-t border-neutral-800">
            {/* Panel 1: Edge Distribution (Daily WX vs Hourly WX) */}
            <div className="border-r border-neutral-800 flex flex-col min-h-0">
              <div className="px-2 py-1 border-b border-neutral-800 flex items-center justify-between shrink-0">
                <span className="text-[10px] text-neutral-500 uppercase tracking-wider">Edge Distribution</span>
                <span className="text-[9px] text-neutral-600 tabular-nums">Daily vs 1H</span>
              </div>
              <div className="flex-1 min-h-0 p-1">
                <EdgeDistribution dailySignals={weatherSignals} hourlySignals={hourlySignals} />
              </div>
            </div>

            {/* Panel 2: Hourly Windows (Replacing BTC Windows) */}
            <div className="border-r border-neutral-800 flex flex-col min-h-0">
              <div className="px-2 py-1 border-b border-neutral-800 flex items-center justify-between shrink-0">
                <span className="text-[10px] text-neutral-500 uppercase tracking-wider">Hourly Windows</span>
                <span className="text-[9px] text-amber-400 tabular-nums">
                  {hourlySignals.length} Active
                </span>
              </div>
              <div className="flex-1 min-h-0 overflow-y-auto p-1 space-y-1">
                {hourlySignals.length > 0 ? (
                  hourlySignals.map(sig => (
                    <HourlyWindowPill
                      key={sig.ticker}
                      signal={sig}
                      onSimulateTrade={() => tradeMutation.mutate(sig.ticker)}
                      isSimulating={tradeMutation.isPending}
                    />
                  ))
                ) : (
                  <div className="text-[10px] text-neutral-600 p-2">
                    No active hourly windows in cycle (open 60m before hour)
                  </div>
                )}
              </div>
            </div>

            {/* Panel 3: Weather Forecasts */}
            <div className="flex flex-col min-h-0">
              <div className="px-2 py-1 border-b border-neutral-800 flex items-center justify-between shrink-0">
                <span className="text-[10px] text-neutral-500 uppercase tracking-wider">Daily Weather</span>
                <span className="px-1 py-0.5 text-[8px] font-bold uppercase bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">WX</span>
              </div>
              <div className="flex-1 min-h-0 overflow-y-auto">
                <WeatherPanel forecasts={weatherForecasts} signals={weatherSignals} />
              </div>
            </div>
          </div>
        </div>

        {/* ===== RIGHT COLUMN ===== */}
        <div className="flex flex-col min-h-0 overflow-hidden">
          {/* Signals - top portion */}
          <div className="flex flex-col min-h-0" style={{ height: '50%' }}>
            <div className="px-2 py-1 border-b border-neutral-800 flex items-center justify-between shrink-0">
              <span className="text-[10px] text-neutral-500 uppercase tracking-wider">Signals</span>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-cyan-400 tabular-nums">{weatherSignals.length} Daily</span>
                <span className="text-[10px] text-amber-400 tabular-nums">{hourlySignals.length} 1H</span>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto min-h-0">
              <SignalsTable
                dailySignals={weatherSignals}
                hourlySignals={hourlySignals}
                onSimulateTrade={(ticker) => tradeMutation.mutate(ticker)}
                isSimulating={tradeMutation.isPending}
              />
            </div>
          </div>

          {/* Trades */}
          <div className="flex flex-col min-h-0 border-t border-neutral-800" style={{ height: '50%' }}>
            <div className="px-2 py-1 border-b border-neutral-800 flex items-center justify-between shrink-0">
              <span className="text-[10px] text-neutral-500 uppercase tracking-wider">Trades</span>
              <span className="text-[10px] text-neutral-600 tabular-nums">{recentTrades.length}</span>
            </div>
            <div className="flex-1 overflow-y-auto min-h-0">
              <TradesTable trades={recentTrades} />
            </div>
          </div>
        </div>
      </div>

      {/* ===== FOOTER ===== */}
      <footer className="shrink-0 border-t border-neutral-800 px-3 py-0.5 flex items-center justify-between">
        <span className="text-[10px] text-neutral-700 font-mono">
          AviationWeather.gov METAR | Open-Meteo Ensemble | Kalshi Live API
        </span>
        <div className="flex items-center gap-3">
          <RefreshBar interval={10000} />
          <span className="text-[10px] text-neutral-700 font-mono">Kalshi Weather: Daily Highs & Hourly Nowcasting</span>
          <div className="flex items-center gap-1">
            <div className="w-1.5 h-1.5 rounded-full bg-green-500" />
            <span className="text-[10px] text-neutral-600 font-mono">Connected</span>
          </div>
        </div>
      </footer>
    </div>
  )
}

export default App
