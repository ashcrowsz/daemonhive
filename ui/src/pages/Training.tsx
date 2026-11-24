import { useEffect, useState } from 'react'
import { HStack, VStack, Layout, LayoutContent } from '@astryxdesign/core/Layout'
import { Heading, Text } from '@astryxdesign/core/Text'
import { Card } from '@astryxdesign/core/Card'
import { Button } from '@astryxdesign/core/Button'
import { Badge } from '@astryxdesign/core/Badge'
import { Token } from '@astryxdesign/core/Token'
import { Drawer } from '@astryxdesign/core/Drawer'
import { Divider } from '@astryxdesign/core/Divider'
import { Selector } from '@astryxdesign/core/Selector'
import { SegmentedControl, SegmentedControlItem } from '@astryxdesign/core/SegmentedControl'
import { Spinner } from '@astryxdesign/core/Spinner'
import { Table } from '@astryxdesign/core/Table'
import type { TableColumn } from '@astryxdesign/core/Table'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, nice, type Pr, type Progression, type SessionDetail, type SessionRow } from '../api'
import { C, tick } from './Overview'

function SessionDrawer({ row, onClose }: { row: SessionRow | null; onClose: () => void }) {
  const [detail, setDetail] = useState<SessionDetail | null>(null)
  useEffect(() => {
    setDetail(null)
    if (row) api.session(row.day, row.kind).then(setDetail)
  }, [row])
  return (
    <Drawer isOpen={row !== null} onOpenChange={o => !o && onClose()} label="Session detail">
      {!detail ? (
        <Spinner label="Loading session..." />
      ) : (
        <VStack gap={4}>
          <VStack gap={1}>
            <Heading level={2}>
              {detail.kind} · {nice(detail.day)}
            </Heading>
            <Text type="supporting" color="secondary">
              {detail.key}
            </Text>
          </VStack>
          <HStack gap={1} wrap="wrap">
            {detail.prs.map(p => (
              <Token key={p.exercise} label={`PR ${p.exercise} ${p.top_set}`} color="green" />
            ))}
            {detail.drops.map(d => (
              <Token key={d.exercise} label={`${d.exercise} ${Math.round(d.volume_change * 100)}% vs ${d.previous}`} color="red" />
            ))}
            {detail.notes.map(n => (
              <Token key={n} label={n} color="gray" />
            ))}
          </HStack>
          <Divider />
          <VStack gap={3}>
            {detail.exercises.map(e => (
              <VStack key={e.name} gap={0.5}>
                <Text weight="semibold">{e.name}</Text>
                <Text color="secondary">{e.summary}</Text>
              </VStack>
            ))}
          </VStack>
          {detail.drops.length > 0 && (
            <Text type="supporting" color="secondary">
              Ask the chat “why did my lifts drop on {detail.day}?” to see what memory links this to.
            </Text>
          )}
        </VStack>
      )}
    </Drawer>
  )
}

export default function TrainingPage() {
  const [sessions, setSessions] = useState<SessionRow[]>([])
  const [prs, setPrs] = useState<Pr[]>([])
  const [exercises, setExercises] = useState<string[]>([])
  const [exercise, setExercise] = useState('bench press')
  const [prog, setProg] = useState<Progression | null>(null)
  const [open, setOpen] = useState<SessionRow | null>(null)
  const [filter, setFilter] = useState('all')

  useEffect(() => {
    api.sessions().then(r => setSessions(r.sessions))
    api.prs().then(r => setPrs(r.prs))
    api.overview().then(o => setExercises(o.fitness.exercises))
  }, [])
  useEffect(() => {
    setProg(null)
    api.progression(exercise).then(setProg)
  }, [exercise])

  const shown = sessions.filter(s =>
    filter === 'all' ? true : filter === 'drops' ? s.regression : s.prs > 0,
  )
  const columns: TableColumn<SessionRow>[] = [
    {
      key: 'day',
      header: 'Date',
      renderCell: s => <Button label={nice(s.day)} variant="ghost" size="sm" onClick={() => setOpen(s)} />,
    },
    { key: 'kind', header: 'Session' },
    { key: 'exercises', header: 'Exercises', align: 'end' },
    { key: 'sets', header: 'Sets', align: 'end' },
    {
      key: 'prs',
      header: 'Signals',
      renderCell: s => (
        <HStack gap={1}>
          {s.prs > 0 && <Badge label={`${s.prs} PR`} variant="success" />}
          {s.regression && <Badge label="drop" variant="error" />}
          {s.estimated && <Badge label="date estimated" variant="neutral" />}
        </HStack>
      ),
    },
  ]
  const prColumns: TableColumn<Pr>[] = [
    { key: 'day', header: 'Date', renderCell: p => nice(p.day) },
    { key: 'exercise', header: 'Exercise' },
    { key: 'top_set', header: 'Set' },
    { key: 'e1rm', header: 'Est. 1RM', align: 'end', renderCell: p => `${p.e1rm} kg` },
    { key: 'previous_set', header: 'Beat', renderCell: p => p.previous_set ?? 'marked in log' },
  ]

  return (
    <Layout
      height="fill"
      content={
        <LayoutContent role="main" padding={6}>
          <VStack gap={6}>
            <Heading level={1}>Training</Heading>
            <Card>
              <VStack gap={3}>
                <HStack hAlign="between" vAlign="center" wrap="wrap" gap={2}>
                  <Heading level={3}>Estimated 1RM over time</Heading>
                  <Selector
                    label="Exercise"
                    isLabelHidden
                    hasSearch
                    value={exercise}
                    onChange={setExercise}
                    options={exercises.length ? exercises : [exercise]}
                    width={260}
                  />
                </HStack>
                {!prog ? (
                  <Spinner label="Loading..." />
                ) : prog.error ? (
                  <Text color="secondary">{prog.error}</Text>
                ) : (
                  <VStack gap={2}>
                    <Text color="secondary">
                      Best {prog.best.set} ({prog.best.e1rm} kg est.) on {nice(prog.best.day)} · {prog.sessions} sessions
                      with a known load
                    </Text>
                    <ProgressionChart points={prog.points ?? prog.recent} />
                  </VStack>
                )}
              </VStack>
            </Card>

            <HStack hAlign="between" vAlign="center" wrap="wrap" gap={2}>
              <Heading level={3}>Sessions</Heading>
              <SegmentedControl label="Filter sessions" value={filter} onChange={setFilter} size="sm">
                <SegmentedControlItem value="all" label={`All ${sessions.length}`} />
                <SegmentedControlItem value="prs" label="With a PR" />
                <SegmentedControlItem value="drops" label="Lift dropped" />
              </SegmentedControl>
            </HStack>
            <Table data={shown.slice(0, 60)} columns={columns} idKey={s => `${s.day}-${s.kind}`} hasHover density="compact" />

            <Heading level={3}>Personal records</Heading>
            <Table data={prs.slice(0, 40)} columns={prColumns} idKey={p => `${p.day}-${p.exercise}`} density="compact" />
          </VStack>
          <SessionDrawer row={open} onClose={() => setOpen(null)} />
        </LayoutContent>
      }
    />
  )
}

function ProgressionChart({ points }: { points: { day: string; e1rm: number; set: string }[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={points} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke={C.grid} />
        <XAxis dataKey="day" tick={tick} axisLine={false} tickLine={false} minTickGap={40} />
        <YAxis tick={tick} axisLine={false} tickLine={false} domain={['auto', 'auto']} unit=" kg" />
        <Tooltip formatter={(v, _n, item) => [`${v} kg (${(item.payload as { set: string }).set})`, 'est. 1RM']} />
        <Line dataKey="e1rm" stroke={C.blue} strokeWidth={2} dot={{ r: 2 }} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}
