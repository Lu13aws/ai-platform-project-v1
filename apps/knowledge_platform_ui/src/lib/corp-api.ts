const CORP_BASE =
  process.env.NEXT_PUBLIC_CORP_API_BASE ??
  'http://localhost:8003'

export interface CorpSource {
  title: string | null
  source_uri: string
  similarity: number
}

export interface CorpQueryResponse {
  answer: string
  sources: CorpSource[]
  user_id: string
}

export async function corpQuery(
  question: string,
  idToken: string,
  top_k = 5,
): Promise<CorpQueryResponse> {
  const res = await fetch(`${CORP_BASE}/api/v1/corp/query`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${idToken}`,
    },
    body: JSON.stringify({ question, top_k }),
  })
  if (!res.ok) throw new Error(`Corp query failed (${res.status})`)
  return res.json() as Promise<CorpQueryResponse>
}
