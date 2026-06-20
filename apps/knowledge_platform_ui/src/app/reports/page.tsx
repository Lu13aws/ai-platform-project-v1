'use client'

import { useEffect, useState } from 'react'
import { ExternalLink, Filter } from 'lucide-react'
import { api, ReportItem } from '@/lib/api'

const DOMAINS = ['All', 'Technology', 'Regulatory', 'Competitor']

const DOMAIN_BADGE: Record<string, string> = {
  Technology: 'bg-blue-900/40 text-blue-300 border-blue-800',
  Regulatory: 'bg-purple-900/40 text-purple-300 border-purple-800',
  Competitor: 'bg-orange-900/40 text-orange-300 border-orange-800',
}

export default function ReportsPage() {
  const [reports, setReports] = useState<ReportItem[]>([])
  const [filter, setFilter] = useState('All')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.reports()
      .then((r) => setReports(r.reports))
      .catch((e) => setError(String(e)))
  }, [])

  const filtered = filter === 'All' ? reports : reports.filter((r) => r.domain === filter)

  return (
    <div className="p-8 max-w-5xl">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-slate-100">Reports Center</h1>
        <p className="text-sm text-slate-500 mt-1">All generated radar reports across domains</p>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-900/20 border border-red-800 rounded-lg text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Filter bar */}
      <div className="flex items-center gap-2 mb-6">
        <Filter size={14} className="text-slate-500" />
        {DOMAINS.map((d) => (
          <button
            key={d}
            onClick={() => setFilter(d)}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              filter === d
                ? 'bg-blue-600/20 text-blue-400 border border-blue-700'
                : 'bg-slate-900 text-slate-400 border border-slate-800 hover:text-slate-200'
            }`}
          >
            {d}
          </button>
        ))}
        <span className="ml-auto text-xs text-slate-600">{filtered.length} reports</span>
      </div>

      {/* Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-800">
              <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Domain</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Generated</th>
              <th className="text-right px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Signals</th>
              <th className="text-right px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Links</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-slate-600 text-sm">
                  {reports.length === 0 ? 'Loading…' : 'No reports for this filter.'}
                </td>
              </tr>
            ) : (
              filtered.map((r) => (
                <tr key={r.id} className="hover:bg-slate-800/50 transition-colors">
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded border text-xs font-medium ${DOMAIN_BADGE[r.domain] ?? 'bg-slate-800 text-slate-400 border-slate-700'}`}>
                      {r.domain}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-300">
                    {new Date(r.generated_at).toLocaleString('en-CH', {
                      day: '2-digit', month: 'short', year: 'numeric',
                      hour: '2-digit', minute: '2-digit',
                    })}
                  </td>
                  <td className="px-4 py-3 text-right text-slate-400 font-mono">
                    {r.signal_count}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      {r.s3_key_html && (
                        <a
                          href={`https://ai-platform-documents-dev.s3.eu-central-1.amazonaws.com/${r.s3_key_html}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300"
                        >
                          HTML <ExternalLink size={10} />
                        </a>
                      )}
                      {r.s3_key_json && r.s3_key_json !== r.s3_key_html && (
                        <a
                          href={`https://ai-platform-documents-dev.s3.eu-central-1.amazonaws.com/${r.s3_key_json}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-300"
                        >
                          JSON <ExternalLink size={10} />
                        </a>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
