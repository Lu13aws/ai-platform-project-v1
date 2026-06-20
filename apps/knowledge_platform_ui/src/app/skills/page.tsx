'use client'

import { useEffect, useState } from 'react'
import { Search, ExternalLink } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { api, SkillItem } from '@/lib/api'

const CATEGORY_COLORS: Record<string, string> = {
  ai:             'bg-blue-900/40 text-blue-300 border-blue-800',
  aws:            'bg-orange-900/40 text-orange-300 border-orange-800',
  development:    'bg-green-900/40 text-green-300 border-green-800',
  orchestration:  'bg-purple-900/40 text-purple-300 border-purple-800',
  databases:      'bg-teal-900/40 text-teal-300 border-teal-800',
  machine_learning: 'bg-pink-900/40 text-pink-300 border-pink-800',
  documentation:  'bg-slate-700 text-slate-300 border-slate-600',
  organization:   'bg-yellow-900/40 text-yellow-300 border-yellow-800',
  portfolio:      'bg-indigo-900/40 text-indigo-300 border-indigo-800',
}

export default function SkillsPage() {
  const [skills, setSkills] = useState<SkillItem[]>([])
  const [search, setSearch] = useState('')
  const [error, setError] = useState<string | null>(null)
  const router = useRouter()

  useEffect(() => {
    api.skills()
      .then((r) => setSkills(r.skills))
      .catch((e) => setError(String(e)))
  }, [])

  const categories = [...new Set(skills.map((s) => s.category))].sort()

  const filtered = skills.filter((s) => {
    if (!search) return true
    const q = search.toLowerCase()
    return s.title.toLowerCase().includes(q) || s.category.toLowerCase().includes(q)
  })

  const grouped = categories.reduce<Record<string, SkillItem[]>>((acc, cat) => {
    const items = filtered.filter((s) => s.category === cat)
    if (items.length > 0) acc[cat] = items
    return acc
  }, {})

  function openInChat(skill: SkillItem) {
    const q = encodeURIComponent(`Tell me about the ${skill.title} skill and its related projects`)
    router.push(`/chat?q=${q}`)
  }

  return (
    <div className="p-8 max-w-5xl">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-slate-100">Skills Hub</h1>
        <p className="text-sm text-slate-500 mt-1">
          {skills.length} skills indexed from personal-data-engineering-toolkit
        </p>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-900/20 border border-red-800 rounded-lg text-red-400 text-sm">
          {error}
          {skills.length === 0 && (
            <span className="block mt-1 text-slate-500">
              Run <code className="font-mono">uv run python scripts/index_skills.py</code> to index skills first.
            </span>
          )}
        </div>
      )}

      {/* Search */}
      <div className="relative mb-6">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search skills by name or category…"
          className="w-full pl-9 pr-4 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-600 transition-colors"
        />
        {search && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-500">
            {filtered.length} result{filtered.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* Grouped by category */}
      {skills.length === 0 && !error ? (
        <p className="text-sm text-slate-600">Loading…</p>
      ) : Object.keys(grouped).length === 0 ? (
        <p className="text-sm text-slate-600">No skills match your search.</p>
      ) : (
        <div className="space-y-8">
          {Object.entries(grouped).map(([cat, items]) => (
            <div key={cat}>
              <div className="flex items-center gap-3 mb-3">
                <span className={`inline-flex items-center px-2.5 py-0.5 rounded border text-xs font-semibold uppercase tracking-wide ${CATEGORY_COLORS[cat] ?? 'bg-slate-800 text-slate-400 border-slate-700'}`}>
                  {cat}
                </span>
                <span className="text-xs text-slate-600">{items.length} skill{items.length !== 1 ? 's' : ''}</span>
              </div>
              <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
                <table className="w-full text-sm">
                  <tbody className="divide-y divide-slate-800">
                    {items.map((skill) => (
                      <tr key={skill.document_id} className="hover:bg-slate-800/50 transition-colors">
                        <td className="px-4 py-3 font-medium text-slate-200">
                          {skill.title}
                        </td>
                        <td className="px-4 py-3 text-slate-500 text-xs font-mono truncate max-w-xs">
                          {skill.source_uri.replace(/\\/g, '/').split('/skills/')[1] ?? skill.source_uri}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <button
                            onClick={() => openInChat(skill)}
                            className="inline-flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 transition-colors"
                          >
                            Ask AI <ExternalLink size={10} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
