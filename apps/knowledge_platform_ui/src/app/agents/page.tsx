'use client'

import { useEffect, useState } from 'react'
import { CheckCircle, AlertTriangle, HelpCircle, Clock, ExternalLink } from 'lucide-react'
import { api, AgentStatus } from '@/lib/api'

const STATUS_CONFIG = {
  ok:      { icon: CheckCircle,   color: 'text-green-400',  bg: 'bg-green-900/20 border-green-800',  label: 'OK'      },
  warning: { icon: AlertTriangle, color: 'text-yellow-400', bg: 'bg-yellow-900/20 border-yellow-800', label: 'Warning' },
  unknown: { icon: HelpCircle,    color: 'text-slate-500',  bg: 'bg-slate-800 border-slate-700',      label: 'Unknown' },
}

const DOMAIN_COLORS: Record<string, string> = {
  Technology: 'text-blue-400',
  Regulatory: 'text-purple-400',
  Competitor: 'text-orange-400',
  Platform:   'text-slate-400',
  RAG:        'text-green-400',
  Skills:     'text-teal-400',
  Content:    'text-pink-400',
}

function AgentCard({ agent }: { agent: AgentStatus }) {
  const cfg = STATUS_CONFIG[agent.status]
  const Icon = cfg.icon

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="font-medium text-slate-200 text-sm">{agent.name}</h3>
          <p className={`text-xs mt-0.5 ${DOMAIN_COLORS[agent.domain] ?? 'text-slate-500'}`}>
            {agent.domain}
          </p>
        </div>
        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium ${cfg.bg} ${cfg.color}`}>
          <Icon size={11} />
          {cfg.label}
        </span>
      </div>

      <div className="space-y-2 text-xs">
        <div className="flex items-center justify-between">
          <span className="text-slate-500">Lambda</span>
          <span className="font-mono text-slate-400">{agent.lambda_function}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-slate-500">Schedule</span>
          <span className="text-slate-300">{agent.schedule}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-slate-500">Last run</span>
          <span className="text-slate-300">
            {agent.last_run
              ? new Date(agent.last_run).toLocaleDateString('en-CH', {
                  day: '2-digit', month: 'short', year: 'numeric',
                })
              : '—'}
          </span>
        </div>
        {agent.last_indexed !== undefined && agent.last_indexed !== null && (
          <div className="flex items-center justify-between">
            <span className="text-slate-500">Indexed</span>
            <span className="text-slate-300">
              {new Date(agent.last_indexed).toLocaleDateString('en-CH', {
                day: '2-digit', month: 'short', year: 'numeric',
              })}
            </span>
          </div>
        )}
      </div>

      <div className="mt-4 pt-3 border-t border-slate-800 space-y-2">
        <div className="flex items-center gap-1.5 text-xs text-slate-500">
          <Clock size={10} />
          Next: {agent.next_run}
        </div>
        {agent.last_post_url && (
          <a
            href={agent.last_post_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-xs text-pink-400 hover:text-pink-300 transition-colors"
          >
            <ExternalLink size={10} />
            View last LinkedIn post
          </a>
        )}
      </div>
    </div>
  )
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<AgentStatus[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.agents()
      .then((r) => setAgents(r.agents))
      .catch((e) => setError(String(e)))
  }, [])

  const okCount = agents.filter((a) => a.status === 'ok').length
  const warnCount = agents.filter((a) => a.status === 'warning').length

  return (
    <div className="p-8 max-w-5xl">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-slate-100">Agent Center</h1>
        <p className="text-sm text-slate-500 mt-1">
          All Lambda functions — status derived from last report generation
        </p>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-900/20 border border-red-800 rounded-lg text-red-400 text-sm">
          {error}
        </div>
      )}

      {agents.length > 0 && (
        <div className="flex items-center gap-4 mb-6 text-sm">
          <span className="flex items-center gap-1.5 text-green-400">
            <CheckCircle size={14} /> {okCount} OK
          </span>
          {warnCount > 0 && (
            <span className="flex items-center gap-1.5 text-yellow-400">
              <AlertTriangle size={14} /> {warnCount} Warning
            </span>
          )}
          <span className="text-slate-600 text-xs ml-auto">
            Status: OK = last report &lt; 8 days ago
          </span>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {agents.length === 0 && !error ? (
          <p className="text-sm text-slate-600 col-span-3">Loading…</p>
        ) : (
          agents.map((a) => <AgentCard key={a.lambda_function} agent={a} />)
        )}
      </div>
    </div>
  )
}
