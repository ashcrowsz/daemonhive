import { useEffect, useMemo, useState } from 'react'
import { HStack, VStack, Layout, LayoutContent } from '@astryxdesign/core/Layout'
import { Heading, Text } from '@astryxdesign/core/Text'
import { Card } from '@astryxdesign/core/Card'
import { Token } from '@astryxdesign/core/Token'
import { Spinner } from '@astryxdesign/core/Spinner'
import { EmptyState } from '@astryxdesign/core/EmptyState'
import { SegmentedControl, SegmentedControlItem } from '@astryxdesign/core/SegmentedControl'
import { Table } from '@astryxdesign/core/Table'
import type { TableColumn } from '@astryxdesign/core/Table'
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY } from 'd3-force'
import type { SimulationLinkDatum, SimulationNodeDatum } from 'd3-force'
import { api, type Graph, type GraphEdge } from '../api'

type Policy = Record<string, { read: string[]; write: string[]; relations: string[] }>
type N = SimulationNodeDatum & { id: string; type: string; degree: number }
type L = SimulationLinkDatum<N> & { e: GraphEdge }

// one colour per owning agent, as in the walkthrough: Fitness red, Well-being green
const TYPE_COLOR: Record<string, string> = {
  Session: 'var(--color-data-categorical-red)',
  Exercise: 'var(--color-data-categorical-orange)',
  Injury: 'var(--color-data-categorical-pink)',
  SleepDeficit: 'var(--color-data-categorical-green)',
  CalorieDeficit: 'var(--color-data-categorical-teal)',
  Person: 'var(--color-text-primary)',
  Weight: 'var(--color-data-categorical-cyan)',
  Phase: 'var(--color-data-categorical-purple)',
}
const REL_COLOR: Record<string, string> = {
  HIT_PR: 'var(--color-data-categorical-orange)',
  AFFECTED_BY: 'var(--color-data-categorical-red)',
  IN_PHASE: 'var(--color-data-categorical-purple)',
  HAS_WEIGHT: 'var(--color-data-categorical-cyan)',
}
const W = 1000
const H = 620

function layout(g: Graph): { nodes: N[]; links: L[] } {
  const degree: Record<string, number> = {}
  for (const e of g.edges) {
    degree[e.subject] = (degree[e.subject] ?? 0) + 1
    degree[e.object] = (degree[e.object] ?? 0) + 1
  }
  const nodes: N[] = g.nodes.map(n => ({ id: n.key, type: n.type, degree: degree[n.key] ?? 0 }))
  const links: L[] = g.edges.map(e => ({ source: e.subject, target: e.object, e }))
  forceSimulation(nodes)
    .force('link', forceLink<N, L>(links).id(d => d.id).distance(l => (l.e.relation === 'HIT_PR' ? 40 : 70)).strength(0.4))
    .force('charge', forceManyBody().strength(-45))
    .force('collide', forceCollide<N>().radius(d => 4 + Math.sqrt(d.degree) * 2.2))
    .force('x', forceX(W / 2).strength(0.04))
    .force('y', forceY(H / 2).strength(0.06))
    .force('center', forceCenter(W / 2, H / 2))
    .stop()
    .tick(320)
  for (const n of nodes) {
    n.x = Math.max(12, Math.min(W - 12, n.x ?? 0))
    n.y = Math.max(12, Math.min(H - 12, n.y ?? 0))
  }
  return { nodes, links }
}

export default function MemoryPage() {
  const [g, setG] = useState<(Graph & { policy?: Policy }) | null>(null)
  const [lens, setLens] = useState('all')
  const [picked, setPicked] = useState<string | null>(null)
  useEffect(() => {
    api.graph().then(setG)
  }, [])
  const laid = useMemo(() => (g ? layout(g) : null), [g])

  if (!g || !laid) return <Spinner size="lg" label="Reading memory as the read-only viewer..." />
  if (g.nodes.length === 0) return <EmptyState title="Memory is empty" description={g.error ?? 'Import your history first.'} />

  const policy = g.policy ?? {}
  const readable = (type: string) => lens === 'all' || policy[lens]?.read.includes('*') || policy[lens]?.read.includes(type)
  const writable = (type: string) => lens !== 'all' && (policy[lens]?.write.includes('*') || policy[lens]?.write.includes(type))
  const facts = picked ? g.edges.filter(e => e.subject === picked || e.object === picked) : []
  const counts: Record<string, number> = {}
  for (const e of g.edges) counts[e.relation] = (counts[e.relation] ?? 0) + 1

  const columns: TableColumn<GraphEdge>[] = [
    { key: 'subject', header: 'Subject' },
    { key: 'relation', header: 'Relation' },
    { key: 'object', header: 'Object' },
    { key: 'valid_from', header: 'Valid from' },
    { key: 'valid_to', header: 'Valid to', renderCell: e => e.valid_to ?? 'still true' },
    { key: 'source', header: 'Written by' },
  ]

  return (
    <Layout
      height="fill"
      content={
        <LayoutContent role="main" padding={6}>
          <VStack gap={5}>
            <VStack gap={1}>
              <Heading level={1}>Shared memory</Heading>
              <Text color="secondary">
                {g.nodes.length} entities and {g.edges.length} dated facts in Neo4j, written through the memory MCP server
                by the agent that owns them. Pick an agent to see only what its permissions let it read; a ringed node is a
                type it may write. Click a node for its facts.
              </Text>
            </VStack>
            <HStack gap={2} wrap="wrap" hAlign="between" vAlign="center">
              <SegmentedControl label="View memory as" value={lens} onChange={setLens} size="sm">
                <SegmentedControlItem value="all" label="Whole graph" />
                {Object.keys(policy).map(a => (
                  <SegmentedControlItem key={a} value={a} label={a} />
                ))}
              </SegmentedControl>
              <HStack gap={1} wrap="wrap">
                {Object.entries(counts).map(([r, n]) => (
                  <Token key={r} size="sm" label={`${r} ${n}`} />
                ))}
              </HStack>
            </HStack>
            <HStack gap={3} wrap="wrap">
              {Object.keys(TYPE_COLOR).map(t => (
                <HStack key={t} gap={1} vAlign="center">
                  <svg width="12" height="12" aria-hidden>
                    <circle cx="6" cy="6" r="5" fill={TYPE_COLOR[t]} />
                  </svg>
                  <Text type="supporting">{t}</Text>
                </HStack>
              ))}
              <Text type="supporting" color="secondary">
                Dashed edge: no longer true (has a valid_to). Nothing is deleted.
              </Text>
            </HStack>
            <Card padding={2}>
                <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Memory graph" width="100%">
                  {laid.links.map((l, i) => {
                    const s = l.source as N
                    const t = l.target as N
                    const vis = readable(s.type) && readable(t.type)
                    const hot = picked !== null && (s.id === picked || t.id === picked)
                    return (
                      <line
                        key={i}
                        x1={s.x}
                        y1={s.y}
                        x2={t.x}
                        y2={t.y}
                        stroke={REL_COLOR[l.e.relation] ?? 'var(--color-border-emphasized)'}
                        strokeOpacity={vis ? (hot ? 0.95 : 0.35) : 0.05}
                        strokeWidth={hot ? 2.5 : 1}
                        strokeDasharray={l.e.valid_to ? '4 4' : undefined}
                      />
                    )
                  })}
                  {laid.nodes.map(n => {
                    const vis = readable(n.type)
                    const r = 4 + Math.sqrt(n.degree) * 2.4
                    const label = n.type !== 'Session' && (n.degree >= 4 || n.type !== 'Exercise')
                    return (
                      <g
                        key={n.id}
                        transform={`translate(${n.x},${n.y})`}
                        opacity={vis ? 1 : 0.12}
                        onClick={() => setPicked(n.id === picked ? null : n.id)}
                        style={{ cursor: 'pointer' }}>
                        <title>{`${n.id} · ${n.degree} facts`}</title>
                        <circle
                          r={r}
                          fill={TYPE_COLOR[n.type] ?? 'var(--color-text-secondary)'}
                          stroke={writable(n.type) || n.id === picked ? 'var(--color-text-primary)' : 'var(--color-background-card)'}
                          strokeWidth={writable(n.type) || n.id === picked ? 2.5 : 1}
                        />
                        {label && vis && (
                          <text
                            x={r + 3}
                            y={4}
                            fontSize={n.degree > 10 ? 17 : 13}
                            fill="var(--color-text-primary)"
                            stroke="var(--color-background-card)"
                            strokeWidth={3}
                            paintOrder="stroke">
                            {n.id.split(':').slice(1).join(':') || n.id}
                          </text>
                        )}
                      </g>
                    )
                  })}
                </svg>
              </Card>
            {picked && (
              <Card>
                <VStack gap={2}>
                  <Heading level={3}>{picked}</Heading>
                  {facts.map((e, i) => (
                    <VStack key={i} gap={0.5}>
                      <Text weight="semibold">
                        {e.subject} → {e.relation} → {e.object}
                      </Text>
                      <Text type="supporting" color="secondary">
                        {e.valid_from}
                        {e.valid_to ? ` to ${e.valid_to}` : ', still true'} · by {e.source}
                      </Text>
                    </VStack>
                  ))}
                </VStack>
              </Card>
            )}
            <Heading level={3}>Most recent facts</Heading>
            <Table
              data={[...g.edges].reverse().slice(0, 30)}
              columns={columns}
              idKey={e => `${e.subject}-${e.relation}-${e.object}-${e.valid_from}`}
              density="compact"
            />
          </VStack>
        </LayoutContent>
      }
    />
  )
}
