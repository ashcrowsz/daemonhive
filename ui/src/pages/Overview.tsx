import { useEffect, useState } from 'react'
import { HStack, VStack, Layout, LayoutContent } from '@astryxdesign/core/Layout'
import { Heading, Text } from '@astryxdesign/core/Text'
import { Card } from '@astryxdesign/core/Card'
import { Grid } from '@astryxdesign/core/Grid'
import { Divider } from '@astryxdesign/core/Divider'
import { Table } from '@astryxdesign/core/Table'
import type { TableColumn } from '@astryxdesign/core/Table'
import { Spinner } from '@astryxdesign/core/Spinner'
import { EmptyState } from '@astryxdesign/core/EmptyState'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api, nice, type FitnessOverview, type Recovery } from '../api'

export const C = {
  blue: 'var(--color-data-categorical-blue)',
  orange: 'var(--color-data-categorical-orange)',
  purple: 'var(--color-data-categorical-purple)',
  green: 'var(--color-data-categorical-green)',
  red: 'var(--color-data-categorical-red)',
  grid: 'var(--color-border)',
  label: 'var(--color-text-secondary)',
}
export const tick = { fontSize: 12, fill: C.label }

function Tile({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <Card>
      <VStack gap={1}>
        <Text type="supporting" color="secondary">
          {label}
        </Text>
        <Heading level={2}>{value}</Heading>
        <Text type="supporting" color="secondary">
          {note}
        </Text>
      </VStack>
    </Card>
  )
}

type Best = { lift: string; set: string; e1rm: number; day: string }
const bestColumns: TableColumn<Best>[] = [
  { key: 'lift', header: 'Lift' },
  { key: 'set', header: 'Best set' },
  { key: 'e1rm', header: 'Est. 1RM', align: 'end', renderCell: b => `${b.e1rm} kg` },
  { key: 'day', header: 'When', renderCell: b => nice(b.day) },
]

export default function OverviewPage() {
  const [data, setData] = useState<{ fitness: FitnessOverview; wellbeing: Recovery } | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    api.overview().then(setData, e => setError(String(e)))
  }, [])

  if (error) return <EmptyState title="The hive is not reachable" description={error} />
  if (!data) return <Spinner size="lg" label="Asking Fitness and Well-being..." />
  const f = data.fitness
  const w = data.wellbeing
  const weekly = Object.entries(f.weekly)
    .slice(-30)
    .map(([week, n]) => ({ week: week.slice(5), n }))
  const series = w.series.slice(-90).map(s => ({ ...s, day: s.day.slice(5) }))
  const lastPr = f.last_pr.prs[0]
  const best: Best[] = Object.entries(f.best_lifts).map(([lift, b]) => ({ lift, ...b }))

  return (
    <Layout
      height="fill"
      content={
        <LayoutContent role="main" padding={6}>
          <VStack gap={6}>
            <VStack gap={1}>
              <Heading level={1}>A year of training, in one place</Heading>
              <Text color="secondary">
                {f.sessions} sessions from {nice(f.first)} to {nice(f.last)}. Training comes from your log; sleep and
                calories are simulated around it (7 h and 1,800 to 2,000 kcal normally; 4 h and 1,400 kcal before a
                bad day).
              </Text>
            </VStack>

            <Grid columns={{ minWidth: 170, repeat: "fit" }} gap={4}>
              <Tile label="Sessions" value={String(f.sessions)} note={`${f.sets.toLocaleString()} sets logged`} />
              <Tile
                label="Last PR"
                value={lastPr ? lastPr.exercise : 'none'}
                note={lastPr ? `${lastPr.top_set} on ${nice(f.last_pr.day)}` : ''}
              />
              <Tile label="PRs" value={String(f.prs)} note={`${f.regressions} sessions where a lift dropped`} />
              <Tile
                label="Sleep, last 7 nights"
                value={`${w.sleep_7d.avg_h} h`}
                note={`shortest ${w.sleep_7d.min_h} h`}
              />
              <Tile
                label="Calories, last 7 days"
                value={`${w.kcal_7d.avg_kcal}`}
                note={`${w.kcal_7d.vs_target > 0 ? '+' : ''}${w.kcal_7d.vs_target} vs ${w.target} target`}
              />
              <Tile label="Diet phase" value={w.phase.current ?? '?'} note={`since ${w.phase.since ?? '?'}`} />
            </Grid>

            <Grid columns={{ minWidth: 420, repeat: 'fit' }} gap={4}>
              <Card>
                <VStack gap={3}>
                  <Heading level={3}>Sessions per week</Heading>
                  <ResponsiveContainer width="100%" height={240}>
                    <BarChart data={weekly} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                      <CartesianGrid vertical={false} stroke={C.grid} />
                      <XAxis dataKey="week" tick={tick} axisLine={false} tickLine={false} interval={3} />
                      <YAxis allowDecimals={false} tick={tick} axisLine={false} tickLine={false} />
                      <Tooltip />
                      <Bar dataKey="n" name="sessions" fill={C.blue} radius={[3, 3, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </VStack>
              </Card>
              <Card>
                <VStack gap={3}>
                  <HStack hAlign="between" vAlign="center">
                    <Heading level={3}>Recovery, last 90 days</Heading>
                    <Text type="supporting" color="secondary">
                      dips line up with the sessions where a lift dropped
                    </Text>
                  </HStack>
                  <Text type="supporting" color="secondary">
                    Calories per day (dashed: {w.target} kcal target)
                  </Text>
                  <ResponsiveContainer width="100%" height={120}>
                    <ComposedChart data={series} syncId="recovery" margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
                      <CartesianGrid vertical={false} stroke={C.grid} />
                      <XAxis dataKey="day" hide />
                      <YAxis domain={[1200, 2100]} ticks={[1400, 1800, 2000]} tick={tick} axisLine={false} tickLine={false} />
                      <Tooltip />
                      <ReferenceLine y={w.target} stroke={C.label} strokeDasharray="4 4" />
                      <Bar dataKey="kcal" name="kcal" fill={C.orange} />
                    </ComposedChart>
                  </ResponsiveContainer>
                  <Text type="supporting" color="secondary">
                    Sleep per night (dashed: 6 h)
                  </Text>
                  <ResponsiveContainer width="100%" height={110}>
                    <ComposedChart data={series} syncId="recovery" margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
                      <CartesianGrid vertical={false} stroke={C.grid} />
                      <XAxis dataKey="day" tick={tick} axisLine={false} tickLine={false} interval={14} />
                      <YAxis domain={[3, 8]} ticks={[4, 6, 8]} tick={tick} axisLine={false} tickLine={false} unit="h" />
                      <Tooltip />
                      <ReferenceLine y={6} stroke={C.label} strokeDasharray="4 4" />
                      <Line dataKey="sleep_h" name="sleep (h)" stroke={C.purple} dot={false} strokeWidth={2} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </VStack>
              </Card>
            </Grid>

            <Divider />
            <Heading level={3}>Best estimated 1RM on the main lifts</Heading>
            <Table data={best} columns={bestColumns} idKey="lift" hasHover />
          </VStack>
        </LayoutContent>
      }
    />
  )
}
