'use client'

import { useState, useRef, useEffect, Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import { Send, Loader2, ChevronDown, ChevronRight } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api, QueryResponse } from '@/lib/api'

type Message =
  | { role: 'user'; content: string }
  | { role: 'assistant'; response: QueryResponse }

const SUGGESTED = [
  'What applications does this AI platform support?',
  'Summarize the latest competitor signals',
  'What cybersecurity risks does FINMA identify for 2025?',
  'What are the layers of this AI platform?',
  'What is the MVP roadmap for this platform?',
]

function SourcesPanel({ sources }: { sources: QueryResponse['sources'] }) {
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
            <div key={s.chunk_id} className="px-3 py-2 bg-slate-900">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-mono text-slate-500">[{i + 1}]</span>
                <span className="text-xs text-blue-400 truncate">{s.source_uri}</span>
                <span className="text-xs text-slate-600 ml-auto shrink-0">
                  {(s.score * 100).toFixed(0)}%
                </span>
              </div>
              <p className="text-xs text-slate-500 line-clamp-2">{s.excerpt}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ChatPageInner() {
  const searchParams = useSearchParams()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const initialQueryFired = useRef(false)

  useEffect(() => {
    const q = searchParams.get('q')
    if (q && !initialQueryFired.current) {
      initialQueryFired.current = true
      submit(q)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  async function submit(question: string) {
    if (!question.trim() || loading) return
    setInput('')
    setMessages((m) => [...m, { role: 'user', content: question }])
    setLoading(true)
    try {
      const response = await api.query(question)
      setMessages((m) => [...m, { role: 'assistant', response }])
    } catch (e) {
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          response: {
            answer: `Error: ${String(e)}`,
            sources: [],
            model: '',
            input_tokens: 0,
            output_tokens: 0,
          },
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
        <h1 className="text-2xl font-semibold text-slate-100">AI Chat</h1>
        <p className="text-sm text-slate-500 mt-1">Ask questions across all indexed knowledge</p>
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
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.response.answer}</ReactMarkdown>
                  </div>
                  {msg.response.model && (
                    <p className="text-xs text-slate-600 mt-2">
                      {msg.response.model} · {msg.response.input_tokens + msg.response.output_tokens} tokens
                    </p>
                  )}
                </div>
                <SourcesPanel sources={msg.response.sources} />
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
            placeholder="Ask the Knowledge Hub…"
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

export default function ChatPage() {
  return (
    <Suspense>
      <ChatPageInner />
    </Suspense>
  )
}
