'use client'

import { useState, useRef, useEffect } from 'react'
import { Send, Loader2, LogOut, Lock, ChevronDown, ChevronRight, Eye, EyeOff } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { login, logout, getStoredAuth, type AuthState } from '@/lib/auth'
import { corpQuery, type CorpQueryResponse } from '@/lib/corp-api'

// ── Login form ─────────────────────────────────────────────────────────────────

function LoginForm({ onLogin }: { onLogin: (auth: AuthState) => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const auth = await login(email, password)
      onLogin(auth)
    } catch (err) {
      setError(String(err).replace('Error: ', ''))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col items-center justify-center h-full px-8">
      <div className="w-full max-w-sm">
        <div className="flex items-center gap-2 mb-8">
          <Lock size={20} className="text-blue-400" />
          <h1 className="text-xl font-semibold text-slate-100">Corporate Access</h1>
        </div>

        <p className="text-sm text-slate-400 mb-6">
          Sign in with your corporate account to access private documents.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-slate-500 mb-1.5">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              required
              disabled={loading}
              className="w-full px-3 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-600 transition-colors"
            />
          </div>

          <div>
            <label className="block text-xs text-slate-500 mb-1.5">Password</label>
            <div className="relative">
              <input
                type={showPw ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                disabled={loading}
                className="w-full px-3 py-2.5 pr-10 bg-slate-900 border border-slate-700 rounded-lg text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-600 transition-colors"
              />
              <button
                type="button"
                onClick={() => setShowPw(!showPw)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
              >
                {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </div>

          {error && (
            <p className="text-xs text-red-400 bg-red-950/30 border border-red-900/50 rounded px-3 py-2">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading || !email || !password}
            className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-600 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : null}
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="text-xs text-slate-600 text-center mt-6">
          Access is restricted to authorised users only.
        </p>
      </div>
    </div>
  )
}

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

function CorpChat({ auth, onLogout }: { auth: AuthState; onLogout: () => void }) {
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
      <div className="px-8 py-6 border-b border-slate-800 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Lock size={16} className="text-blue-400" />
            <h1 className="text-2xl font-semibold text-slate-100">Corporate Chat</h1>
          </div>
          <p className="text-sm text-slate-500 mt-1">Private documents — {auth.email}</p>
        </div>
        <button
          onClick={onLogout}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200 border border-slate-700 hover:border-slate-500 rounded-md transition-colors"
        >
          <LogOut size={12} />
          Sign out
        </button>
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
  const [auth, setAuth] = useState<AuthState | null>(null)
  const [hydrated, setHydrated] = useState(false)

  // Restore session from localStorage after hydration
  useEffect(() => {
    setAuth(getStoredAuth())
    setHydrated(true)
  }, [])

  if (!hydrated) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 size={20} className="animate-spin text-slate-500" />
      </div>
    )
  }

  if (!auth) {
    return <LoginForm onLogin={setAuth} />
  }

  return (
    <CorpChat
      auth={auth}
      onLogout={() => {
        logout()
        setAuth(null)
      }}
    />
  )
}
