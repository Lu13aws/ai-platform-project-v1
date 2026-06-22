'use client'

import { useState, useEffect } from 'react'
import { Loader2, RefreshCw, Send, Trash2, Copy, Check, Pencil, X, ExternalLink, Linkedin, ShieldOff } from 'lucide-react'
import { getPlatformAuth, isCorpAdmin, type PlatformAuth } from '@/lib/platform-auth'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? ''

interface Post {
  id: string
  domain: string
  angle: string
  company: string
  content: string
  status: string
  linkedin_post_url: string | null
  posted_at: string | null
  created_at: string
}

async function apiFetch(path: string, auth: PlatformAuth, options?: RequestInit) {
  const res = await fetch(`${API_BASE}/api/v1/kp${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options?.headers ?? {}),
      Authorization: `Bearer ${auth.idToken}`,
    },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? `HTTP ${res.status}`)
  }
  return res.json()
}

// ── Status badge ──────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    draft:     'bg-yellow-900/40 text-yellow-400 border-yellow-800',
    published: 'bg-green-900/40 text-green-400 border-green-800',
    rejected:  'bg-red-900/40 text-red-500 border-red-900',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded border font-medium ${styles[status] ?? 'bg-slate-800 text-slate-400 border-slate-700'}`}>
      {status}
    </span>
  )
}

// ── Copy button ───────────────────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  function copy() {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <button onClick={copy} title="Copy to clipboard"
      className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200 border border-slate-700 hover:border-slate-500 rounded-md transition-colors">
      {copied ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  )
}

// ── Post card ─────────────────────────────────────────────────────────────────

function PostCard({ post, auth, onUpdate, onRemove }: {
  post: Post
  auth: PlatformAuth
  onUpdate: (updated: Post) => void
  onRemove: (id: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [editContent, setEditContent] = useState(post.content)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function run(action: string, fn: () => Promise<Post | null>) {
    setBusy(action)
    setError(null)
    try {
      const result = await fn()
      if (result) onUpdate(result)
    } catch (e) {
      setError(String(e).replace('Error: ', ''))
    } finally {
      setBusy(null)
    }
  }

  async function handleEdit() {
    await run('edit', async () => {
      const data = await apiFetch(`/linkedin/${post.id}`, auth, {
        method: 'PATCH',
        body: JSON.stringify({ content: editContent }),
      })
      setEditing(false)
      return data
    })
  }

  async function handleRegenerate() {
    await run('regenerate', () =>
      apiFetch(`/linkedin/${post.id}/regenerate`, auth, { method: 'POST' })
    )
  }

  async function handlePublish() {
    await run('publish', async () => {
      const data = await apiFetch(`/linkedin/${post.id}/publish`, auth, { method: 'POST' })
      if (data.status === 'published') return { ...post, ...data }
      throw new Error(data.message)
    })
  }

  async function handleReject() {
    setBusy('reject')
    setError(null)
    try {
      await apiFetch(`/linkedin/${post.id}`, auth, { method: 'DELETE' })
      onRemove(post.id)
    } catch (e) {
      setError(String(e).replace('Error: ', ''))
      setBusy(null)
    }
  }

  const isDraft = post.status === 'draft'
  const isPublished = post.status === 'published'

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            <StatusBadge status={post.status} />
            <span className="text-xs text-slate-500 bg-slate-800 px-2 py-0.5 rounded">{post.domain}</span>
            <span className="text-xs text-slate-500 bg-slate-800 px-2 py-0.5 rounded">{post.angle}</span>
          </div>
          <p className="text-sm font-medium text-slate-200">{post.company}</p>
          <p className="text-xs text-slate-600">
            {new Date(post.created_at).toLocaleDateString('de-CH', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
          </p>
        </div>
        {isPublished && post.linkedin_post_url && (
          <a href={post.linkedin_post_url} target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-blue-400 border border-blue-800 hover:border-blue-600 rounded-md transition-colors shrink-0">
            <ExternalLink size={11} /> View on LinkedIn
          </a>
        )}
      </div>

      {/* Content */}
      {editing ? (
        <div className="space-y-2">
          <textarea
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            rows={12}
            className="w-full px-4 py-3 bg-slate-800 border border-blue-700 rounded-lg text-sm text-slate-200 resize-y focus:outline-none font-mono leading-relaxed"
          />
          <div className="flex gap-2">
            <button onClick={handleEdit} disabled={busy !== null}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 rounded-md text-xs font-medium transition-colors">
              {busy === 'edit' ? <Loader2 size={11} className="animate-spin" /> : <Check size={11} />}
              Save
            </button>
            <button onClick={() => { setEditing(false); setEditContent(post.content) }}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-400 border border-slate-700 hover:border-slate-500 rounded-md transition-colors">
              <X size={11} /> Cancel
            </button>
          </div>
        </div>
      ) : (
        <pre className="whitespace-pre-wrap text-sm text-slate-300 leading-relaxed font-sans bg-slate-800/50 rounded-lg px-4 py-4 max-h-80 overflow-y-auto">
          {post.content}
        </pre>
      )}

      {/* Error */}
      {error && (
        <p className="text-xs text-red-400 bg-red-950/30 border border-red-900/50 rounded px-3 py-2">{error}</p>
      )}

      {/* Actions */}
      {!editing && (
        <div className="flex gap-2 flex-wrap">
          <CopyButton text={post.content} />

          {isDraft && (
            <>
              <button onClick={() => { setEditing(true); setEditContent(post.content) }}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200 border border-slate-700 hover:border-slate-500 rounded-md transition-colors">
                <Pencil size={12} /> Edit
              </button>

              <button onClick={handleRegenerate} disabled={busy !== null}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200 border border-slate-700 hover:border-slate-500 rounded-md transition-colors disabled:opacity-50">
                {busy === 'regenerate' ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
                Regenerate
              </button>

              <button onClick={handlePublish} disabled={busy !== null}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-white bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 rounded-md transition-colors font-medium">
                {busy === 'publish' ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
                Publish
              </button>

              <button onClick={handleReject} disabled={busy !== null}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-red-400 hover:text-red-300 border border-red-900 hover:border-red-700 rounded-md transition-colors disabled:opacity-50">
                {busy === 'reject' ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                Reject
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ── Filter tabs ───────────────────────────────────────────────────────────────

const FILTERS = [
  { label: 'Drafts', value: 'draft' },
  { label: 'Published', value: 'published' },
  { label: 'Rejected', value: 'rejected' },
  { label: 'All', value: '' },
]

// ── Page ──────────────────────────────────────────────────────────────────────

export default function LinkedInPage() {
  const [auth, setAuth] = useState<PlatformAuth | null | undefined>(undefined)
  const [posts, setPosts] = useState<Post[]>([])
  const [filter, setFilter] = useState('draft')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const stored = getPlatformAuth()
    setAuth(stored && isCorpAdmin(stored) ? stored : null)
  }, [])

  useEffect(() => {
    if (auth) load()
  }, [filter, auth])

  async function load() {
    if (!auth) return
    setLoading(true)
    setError(null)
    try {
      const params = filter ? `?status=${filter}` : ''
      const data = await apiFetch(`/linkedin${params}`, auth)
      setPosts(data.posts)
    } catch (e) {
      setError(String(e).replace('Error: ', ''))
    } finally {
      setLoading(false)
    }
  }

  function handleUpdate(updated: Post) {
    setPosts((prev) => prev.map((p) => (p.id === updated.id ? updated : p)))
  }

  function handleRemove(id: string) {
    setPosts((prev) => prev.filter((p) => p.id !== id))
  }

  // Hydrating
  if (auth === undefined) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 size={20} className="animate-spin text-slate-500" />
      </div>
    )
  }

  // Not admin
  if (!auth) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-slate-600">
        <ShieldOff size={32} />
        <p className="text-sm">Access restricted — admin only.</p>
      </div>
    )
  }

  const draftCount = posts.filter((p) => p.status === 'draft').length

  return (
    <div className="max-w-3xl mx-auto px-8 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Linkedin size={22} className="text-blue-500" />
          <div>
            <h1 className="text-xl font-semibold text-slate-100">LinkedIn Review</h1>
            <p className="text-xs text-slate-500 mt-0.5">Review AI-generated posts before publishing</p>
          </div>
        </div>
        <button onClick={load} disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200 border border-slate-700 hover:border-slate-500 rounded-md transition-colors disabled:opacity-50">
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-1 mb-6 border-b border-slate-800">
        {FILTERS.map(({ label, value }) => (
          <button
            key={value}
            onClick={() => setFilter(value)}
            className={`px-4 py-2 text-xs font-medium transition-colors border-b-2 -mb-px ${
              filter === value
                ? 'text-blue-400 border-blue-500'
                : 'text-slate-500 border-transparent hover:text-slate-300'
            }`}
          >
            {label}
            {value === 'draft' && draftCount > 0 && filter !== 'draft' && (
              <span className="ml-1.5 px-1.5 py-0.5 bg-yellow-900/60 text-yellow-400 rounded text-[10px]">
                {draftCount}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 size={20} className="animate-spin text-slate-500" />
        </div>
      ) : error ? (
        <p className="text-sm text-red-400 bg-red-950/30 border border-red-900/50 rounded px-4 py-3">{error}</p>
      ) : posts.length === 0 ? (
        <div className="text-center py-16 text-slate-600">
          <Linkedin size={32} className="mx-auto mb-3 opacity-30" />
          <p className="text-sm">No {filter || ''} posts found.</p>
          {filter === 'draft' && (
            <p className="text-xs mt-1">The Content Creator Lambda generates a new draft every Thursday.</p>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          {posts.map((post) => (
            <PostCard key={post.id} post={post} auth={auth} onUpdate={handleUpdate} onRemove={handleRemove} />
          ))}
        </div>
      )}
    </div>
  )
}
