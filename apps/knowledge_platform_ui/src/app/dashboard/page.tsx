'use client'

import { useEffect, useState, useRef } from 'react'
import { FileText, Zap, BarChart3, Bot, Cpu, TrendingUp } from 'lucide-react'
import { api, StatsResponse, ActivityItem } from '@/lib/api'

function useCountUp(target: number | undefined, duration = 900): number | undefined {
  const [display, setDisplay] = useState<number | undefined>(undefined)
  const rafRef = useRef<number | null>(null)

  useEffect(() => {
    if (target === undefined) return
    const start = performance.now()
    const from = 0

    const tick = (now: number) => {
      const elapsed = now - start
      const progress = Math.min(elapsed / duration, 1)
      // ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3)
      setDisplay(Math.round(from + (target - from) * eased))
      if (progress < 1) rafRef.current = requestAnimationFrame(tick)
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current) }
  }, [target, duration])

  return display
}

const DOMAIN_COLORS: Record<string, string> = {
  Technology: 'text-blue-400',
  Competitor: 'text-orange-400',
  Regulatory: 'text-purple-400',
  rag_demo: 'text-green-400',
  private_hub: 'text-yellow-400',
}

const TYPE_LABELS: Record<string, string> = {
  document: 'Document ingested',
  radar_signal: 'Tech signal',
  competitor_signal: 'Competitor signal',
  report: 'Report generated',
}

function KpiCard({
  label,
  value,
  icon: Icon,
  color,
}: {
  label: string
  value: number | undefined
  icon: React.ElementType
  color: string
}) {
  const animated = useCountUp(value)
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm text-slate-400">{label}</span>
        <Icon size={18} className={color} />
      </div>
      <div className="text-3xl font-bold text-slate-100">
        {animated === undefined ? '—' : animated.toLocaleString()}
      </div>
    </div>
  )
}

function ActivityFeed({ items }: { items: ActivityItem[] }) {
  return (
    <div className="space-y-2">
      {items.slice(0, 15).map((item, i) => (
        <div key={i} className="flex items-start gap-3 py-2.5 border-b border-slate-800 last:border-0">
          <div className="mt-0.5 w-1.5 h-1.5 rounded-full bg-slate-600 shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm text-slate-300 truncate">{item.title}</p>
            <div className="flex items-center gap-2 mt-0.5">
              <span className={`text-xs ${DOMAIN_COLORS[item.domain ?? ''] ?? 'text-slate-500'}`}>
                {item.domain}
              </span>
              <span className="text-xs text-slate-600">·</span>
              <span className="text-xs text-slate-500">
                {TYPE_LABELS[item.type] ?? item.type}
              </span>
              <span className="text-xs text-slate-600">·</span>
              <span className="text-xs text-slate-600">
                {new Date(item.timestamp).toLocaleDateString('en-CH', {
                  day: '2-digit', month: 'short', year: 'numeric',
                })}
              </span>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

export default function DashboardPage() {
  const [stats, setStats] = useState<StatsResponse | undefined>()
  const [activity, setActivity] = useState<ActivityItem[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([api.stats(), api.recent()])
      .then(([s, r]) => {
        setStats(s)
        setActivity(r.items)
      })
      .catch((e) => setError(String(e)))
  }, [])

  return (
    <div className="p-8 max-w-6xl">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-slate-100">Dashboard</h1>
        <p className="text-sm text-slate-500 mt-1">Platform overview — live data from PostgreSQL</p>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-900/20 border border-red-800 rounded-lg text-red-400 text-sm">
          Could not load data: {error}. Make sure the API server is running on{' '}
          <code className="font-mono">localhost:8002</code>.
        </div>
      )}

      {/* KPI Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <KpiCard label="Documents Indexed" value={stats?.documents_indexed} icon={FileText} color="text-blue-400" />
        <KpiCard label="Skills Indexed" value={stats?.skills_indexed} icon={Cpu} color="text-teal-400" />
        <KpiCard label="Radar Signals" value={stats && stats.radar_signals + stats.competitor_signals + stats.regulatory_changes} icon={Zap} color="text-yellow-400" />
        <KpiCard label="Reports Generated" value={stats?.reports_generated} icon={BarChart3} color="text-green-400" />
        <KpiCard label="Agents Active" value={stats?.agents_active} icon={Bot} color="text-purple-400" />
        <KpiCard label="Tech Signals" value={stats?.radar_signals} icon={TrendingUp} color="text-blue-300" />
        <KpiCard label="Competitor Signals" value={stats?.competitor_signals} icon={TrendingUp} color="text-orange-300" />
        <KpiCard label="Regulatory Changes" value={stats?.regulatory_changes} icon={TrendingUp} color="text-purple-300" />
      </div>

      {/* Recent Activity */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-6">
        <h2 className="text-sm font-semibold text-slate-300 mb-4 uppercase tracking-wide">
          Recent Activity
        </h2>
        {activity.length === 0 && !error ? (
          <p className="text-sm text-slate-600">Loading activity…</p>
        ) : (
          <ActivityFeed items={activity} />
        )}
      </div>
    </div>
  )
}
