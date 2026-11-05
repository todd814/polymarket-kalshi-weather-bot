import { useMemo } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import type { WeatherSignal, HourlySignal } from '../types'

interface Props {
  dailySignals: WeatherSignal[]
  hourlySignals: HourlySignal[]
}

const BUCKETS = ['0-2%', '2-5%', '5-10%', '10-20%', '20%+']

function getBucket(edge: number): string {
  const pct = Math.abs(edge) * 100
  if (pct < 2) return '0-2%'
  if (pct < 5) return '2-5%'
  if (pct < 10) return '5-10%'
  if (pct < 20) return '10-20%'
  return '20%+'
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload || !payload.length) return null
  return (
    <div className="bg-neutral-900 border border-neutral-800 px-2 py-1.5 font-mono">
      <p className="text-[10px] text-neutral-400 mb-1">{label} Edge</p>
      {payload.map((p: any) => (
        <p key={p.name} className="text-[10px] tabular-nums" style={{ color: p.color }}>
          {p.name}: {p.value}
        </p>
      ))}
    </div>
  )
}

export function EdgeDistribution({ dailySignals, hourlySignals }: Props) {
  const data = useMemo(() => {
    const counts: Record<string, { daily: number; hourly: number }> = {}
    BUCKETS.forEach(b => { counts[b] = { daily: 0, hourly: 0 } })

    dailySignals.forEach(s => {
      const bucket = getBucket(s.edge)
      counts[bucket].daily++
    })

    hourlySignals.forEach(s => {
      const bucket = getBucket(s.edge)
      counts[bucket].hourly++
    })

    return BUCKETS.map(bucket => ({
      bucket,
      'Daily WX': counts[bucket].daily,
      'Hourly WX': counts[bucket].hourly,
    }))
  }, [dailySignals, hourlySignals])

  const total = dailySignals.length + hourlySignals.length
  if (total === 0) {
    return (
      <div className="h-full flex items-center justify-center text-neutral-600 text-[10px] font-mono">
        Scanning active weather edges...
      </div>
    )
  }

  return (
    <div className="h-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, left: -10, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1a1a1a" vertical={false} />
          <XAxis
            dataKey="bucket"
            stroke="#525252"
            fontSize={9}
            tickLine={false}
            axisLine={false}
            fontFamily="JetBrains Mono"
          />
          <YAxis
            stroke="#525252"
            fontSize={9}
            tickLine={false}
            axisLine={false}
            allowDecimals={false}
            fontFamily="JetBrains Mono"
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            iconSize={8}
            wrapperStyle={{ fontSize: '9px', fontFamily: 'JetBrains Mono' }}
          />
          <Bar dataKey="Daily WX" stackId="a" fill="#06b6d4" radius={[0, 0, 0, 0]} />
          <Bar dataKey="Hourly WX" stackId="a" fill="#f59e0b" radius={[2, 2, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
