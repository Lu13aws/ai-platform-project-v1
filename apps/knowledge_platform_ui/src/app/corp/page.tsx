'use client'

import { useState, useRef, useEffect } from 'react'
import { Send, Loader2, Lock, ShieldOff, ChevronDown, ChevronRight } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { getPlatformAuth, isCorpAdmin, type PlatformAuth } from '@/lib/platform-auth'
import { corpQuery, type CorpQueryResponse } from '@/lib/corp-api'

// ── Sources panel ──────────────────────────────────────────────────────────────

function CorpSourcesPanel({ sources }: { sources: CorpQueryResponse['sources'] }) {
  const [open, setOpen] = useState(false)
  if (sources.length === 0) return null
  return (
    <div className="mt-3 border border-slate-700 rounded-md overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-2 text-xs text-slate-400 bg-slate-800 hover:bg-slate-750"
      >
        <span>{sources.length} source{sources.length !== 1 ? 's' : ''}</span>
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
      </button>
      {open && (
        <div className="divide-y divide-slate-700">
          {sources.map((s, i) => (
            <div key={i} className="px-3 py-2 bg-slate-900">
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono text-slate-500">[{i + 1}]</span>
                <span className="text-xs text-blue-400 truncate">{s.source_uri}</span>
                <span className="text-xs text-slate-600 ml-auto shrink-0">
                  {(s.similarity * 100).toFixed(0)}%
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Corp chat ──────────────────────────────────────────────────────────────────

type ChatMessage =
  | { role: 'user'; content: string }
  | { role: 'assistant'; response: CorpQueryResponse }

const SUGGESTED = [
  'What is the current status of Phase 6?',
  'What compliance frameworks are required for Phase 6?',
  'Which agents are deployed and what do they do?',
  'What are the data retention policies for each application?',
]

function CorpChat({ auth }: { auth: PlatformAuth }) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  async function submit(question: string) {
    if (!question.trim() || loading) return
    setInput('')
    setMessages((m) => [...m, { role: 'user', content: question }])
    setLoading(true)
    try {
      const response = await corpQuery(question, auth.idToken)
      setMessages((m) => [...m, { role: 'assistant', response }])
    } catch (e) {
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          response: { answer: `Error: ${String(e)}`, sources: [], user_id: '' },
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-full max-w-4xl mx-auto">
      {/* Header */}
      <div className="px-8 py-6 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <Lock size={16} className="text-blue-400" />
          <h1 className="text-2xl font-semibold text-slate-100">Corporate Chat</h1>
        </div>
        <p className="text-sm text-slate-500 mt-1">Private documents — {auth.email}</p>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-8 py-6 space-y-6">
        {messages.length === 0 && (
          <div className="space-y-3">
            <p className="text-sm text-slate-500 mb-4">Suggested questions:</p>
            {SUGGESTED.map((q) => (
              <button
                key={q}
                onClick={() => submit(q)}
                className="block w-full text-left px-4 py-3 rounded-lg border border-slate-800 bg-slate-900 text-sm text-slate-300 hover:border-blue-700 hover:bg-slate-800 transition-colors"
              >
                {q}
              </button>
            ))}
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i}>
            {msg.role === 'user' ? (
              <div className="flex justify-end">
                <div className="max-w-lg bg-blue-600/20 border border-blue-700/40 rounded-lg px-4 py-3">
                  <p className="text-sm text-slate-200">{msg.content}</p>
                </div>
              </div>
            ) : (
              <div className="max-w-3xl">
                <div className="bg-slate-900 border border-slate-800 rounded-lg px-4 py-4">
                  <div className="prose prose-sm prose-invert max-w-none text-slate-300">
                    <ReactMarkdown>{msg.response.answer}</ReactMarkdown>
                  </div>
                </div>
                <CorpSourcesPanel sources={msg.response.sources} />
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Loader2 size={14} className="animate-spin" />
            Thinking…
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-8 py-5 border-t border-slate-800">
        <div className="flex gap-3">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && submit(input)}
            placeholder="Ask about private corporate documents…"
            className="flex-1 px-4 py-3 bg-slate-900 border border-slate-700 rounded-lg text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-600 transition-colors"
            disabled={loading}
          />
          <button
            onClick={() => submit(input)}
            disabled={loading || !input.trim()}
            className="px-4 py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-600 rounded-lg text-sm font-medium transition-colors"
          >
            <Send size={16} />
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function CorpPage() {
  const [auth, setAuth] = useState<PlatformAuth | null | undefined>(undefined)

  useEffect(() => {
    setAuth(getPlatformAuth())
  }, [])

  // Still hydrating
  if (auth === undefined) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 size={20} className="animate-spin text-slate-500" />
      </div>
    )
  }

  // Not in corp-admins group
  if (!auth || !isCorpAdmin(auth)) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 px-8">
        <ShieldOff size={40} className="text-slate-600" />
        <h2 className="text-lg font-semibold text-slate-300">Access Restricted</h2>
        <p className="text-sm text-slate-500 text-center max-w-sm">
          Corporate Chat is available to authorised administrators only.
          Contact the platform owner to request access.
        </p>
      </div>
    )
  }

  return <CorpChat auth={auth} />
}
