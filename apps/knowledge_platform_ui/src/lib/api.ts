const BASE = process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8002'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`)
  return res.json() as Promise<T>
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`POST ${path} → ${res.status}`)
  return res.json() as Promise<T>
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface StatsResponse {
  documents_indexed: number
  radar_signals: number
  competitor_signals: number
  regulatory_changes: number
  reports_generated: number
  agents_active: number
  skills_indexed: number
}

export interface ActivityItem {
  type: string
  title: string
  domain: string | null
  timestamp: string
}

export interface RecentActivityResponse {
  items: ActivityItem[]
}

export interface ReportItem {
  id: string
  domain: string
  generated_at: string
  signal_count: number
  s3_key_html: string | null
  s3_key_json: string | null
}

export interface ReportsResponse {
  total: number
  reports: ReportItem[]
}

export interface AgentStatus {
  name: string
  lambda_function: string
  domain: string
  schedule: string
  last_run: string | null
  next_run: string
  status: 'ok' | 'warning' | 'unknown'
  last_post_url: string | null
}

export interface AgentsResponse {
  agents: AgentStatus[]
}

export interface SkillItem {
  document_id: string
  title: string
  source_uri: string
  category: string
  created_at: string
}

export interface SkillsResponse {
  total: number
  skills: SkillItem[]
}

export interface SourceReference {
  chunk_id: string
  source_uri: string
  score: number
  excerpt: string
}

export interface QueryResponse {
  answer: string
  sources: SourceReference[]
  model: string
  input_tokens: number
  output_tokens: number
}

// ── API calls ─────────────────────────────────────────────────────────────────

export const api = {
  stats: () => get<StatsResponse>('/api/v1/kp/stats'),
  recent: () => get<RecentActivityResponse>('/api/v1/kp/recent'),
  reports: () => get<ReportsResponse>('/api/v1/kp/reports'),
  agents: () => get<AgentsResponse>('/api/v1/kp/agents'),
  skills: () => get<SkillsResponse>('/api/v1/kp/skills'),
  query: (question: string, top_k = 5) =>
    post<QueryResponse>('/api/v1/kp/query', { question, top_k }),
}
