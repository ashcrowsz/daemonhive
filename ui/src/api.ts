// Every number in the UI comes from Concierge's read-only API, which asks the owning agent over A2A.

export type ChatReply = {
  reply: string
  route: string
  agents: string[]
  tier: number
  steps: { tool: string; args: Record<string, unknown> }[]
}

export type Pr = {
  day: string
  session: string
  kind: string
  exercise: string
  top_set: string
  e1rm: number
  previous_best: number | null
  previous_set: string | null
  marked_in_log: boolean
}

export type FitnessOverview = {
  sessions: number
  first: string
  last: string
  kinds: Record<string, number>
  sets: number
  prs: number
  regressions: number
  last_pr: { day: string; prs: Omit<Pr, 'day'>[] }
  best_lifts: Record<string, { day: string; kind: string; set: string; e1rm: number }>
  weekly: Record<string, number>
  exercises: string[]
  last_session: string
}

export type Recovery = {
  target: number
  series: { day: string; kcal: number | null; sleep_h: number | null }[]
  sleep_7d: { avg_h: number; min_h: number; short_nights: number }
  kcal_7d: { avg_kcal: number; vs_target: number }
  weight: { latest_kg: number; on: string; change_kg: number }
  phase: { current: string; since: string; history: { phase: string; from: string; to: string | null }[] }
  weights: { day: string; kg: number }[]
}

export type SessionRow = {
  day: string
  kind: string
  exercises: number
  sets: number
  estimated: boolean
  regression: boolean
  prs: number
}

export type SessionDetail = {
  day: string
  kind: string
  key: string
  notes: string[]
  drops: { exercise: string; volume_change: number; previous: string }[]
  prs: Pr[]
  exercises: { name: string; summary: string }[]
}

export type Progression = {
  exercise: string
  sessions: number
  first: Point
  best: Point
  last: Point
  recent: Point[]
  points?: Point[]
  error?: string
}
type Point = { day: string; set: string; e1rm: number }

export type GraphEdge = {
  subject: string
  relation: string
  object: string
  valid_from: string
  valid_to: string | null
  source: string
  props: string
}
export type Graph = { nodes: { key: string; type: string }[]; edges: GraphEdge[]; error?: string }

export type Agents = {
  agents: { name: string; up: boolean; description: string; skills: { id: string; name: string }[] }[]
  tiers: Record<string, number>
}
export type AuditEntry = { ts: number; agent: string; action: string; target: string; allowed: boolean }

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path)
  if (!r.ok) throw new Error(`${path}: ${r.status}`)
  return (await r.json()) as T
}

export const api = {
  chat: async (text: string): Promise<ChatReply> => {
    const r = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ text }),
    })
    if (!r.ok) throw new Error(`chat: ${r.status}`)
    return (await r.json()) as ChatReply
  },
  overview: () => get<{ fitness: FitnessOverview; wellbeing: Recovery }>('/api/overview'),
  sessions: () => get<{ sessions: SessionRow[] }>('/api/sessions'),
  session: (day: string, kind: string) =>
    get<SessionDetail>(`/api/session?day=${encodeURIComponent(day)}&kind=${encodeURIComponent(kind)}`),
  prs: () => get<{ prs: Pr[] }>('/api/prs'),
  progression: (exercise: string) =>
    get<Progression>(`/api/progression?exercise=${encodeURIComponent(exercise)}`),
  recovery: (days = 120) => get<Recovery>(`/api/recovery?days=${days}`),
  graph: () => get<Graph>('/api/graph'),
  agents: () => get<Agents>('/api/agents'),
  audit: () => get<{ entries: AuditEntry[] }>('/api/audit?n=80'),
}

export function nice(day: string): string {
  const d = new Date(day + 'T00:00:00')
  return d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
}
