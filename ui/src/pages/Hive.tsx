import { useEffect, useState } from 'react'
import { HStack, VStack, Layout, LayoutContent } from '@astryxdesign/core/Layout'
import { Heading, Text } from '@astryxdesign/core/Text'
import { Card } from '@astryxdesign/core/Card'
import { Grid } from '@astryxdesign/core/Grid'
import { Badge } from '@astryxdesign/core/Badge'
import { Token } from '@astryxdesign/core/Token'
import { Button } from '@astryxdesign/core/Button'
import { Spinner } from '@astryxdesign/core/Spinner'
import { Table } from '@astryxdesign/core/Table'
import type { TableColumn } from '@astryxdesign/core/Table'
import { api, type Agents, type AuditEntry } from '../api'

const auditColumns: TableColumn<AuditEntry>[] = [
  { key: 'ts', header: 'Time', renderCell: a => new Date(a.ts * 1000).toLocaleString() },
  { key: 'agent', header: 'Agent' },
  { key: 'action', header: 'Action' },
  { key: 'target', header: 'Target' },
  {
    key: 'allowed',
    header: 'Allowed',
    renderCell: a => <Badge label={a.allowed ? 'yes' : 'denied'} variant={a.allowed ? 'success' : 'error'} />,
  },
]

export default function HivePage() {
  const [agents, setAgents] = useState<Agents | null>(null)
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const load = () => {
    api.agents().then(setAgents)
    api.audit().then(r => setAudit(r.entries))
  }
  useEffect(load, [])

  const tiers = agents?.tiers ?? {}
  const total = Object.values(tiers).reduce((a, b) => a + b, 0)
  return (
    <Layout
      height="fill"
      content={
        <LayoutContent role="main" padding={6}>
          <VStack gap={6}>
            <HStack hAlign="between" vAlign="center">
              <VStack gap={1}>
                <Heading level={1}>The hive</Heading>
                <Text color="secondary">
                  Each agent publishes an A2A Agent Card. Concierge reaches them over A2A; memory goes through MCP with a
                  per-agent permission check, logged below.
                </Text>
              </VStack>
              <Button label="Refresh" variant="secondary" onClick={load} />
            </HStack>
            {!agents ? (
              <Spinner label="Reading Agent Cards..." />
            ) : (
              <Grid columns={{ minWidth: 260, repeat: 'fit' }} gap={4}>
                {agents.agents.map(a => (
                  <Card key={a.name}>
                    <VStack gap={2}>
                      <HStack hAlign="between" vAlign="center">
                        <Heading level={3}>{a.name}</Heading>
                        <Badge label={a.up ? 'up' : 'down'} variant={a.up ? 'success' : 'error'} />
                      </HStack>
                      <Text color="secondary">{a.description || 'not reachable'}</Text>
                      <HStack gap={1} wrap="wrap">
                        {a.skills.map(s => (
                          <Token key={s.id} size="sm" label={s.id} />
                        ))}
                      </HStack>
                    </VStack>
                  </Card>
                ))}
                <Card>
                  <VStack gap={2}>
                    <Heading level={3}>Routing tiers</Heading>
                    <Text color="secondary">
                      {total === 0
                        ? 'No messages since Concierge started.'
                        : `${Math.round((100 * (tiers['0'] ?? 0)) / total)}% of ${total} messages routed by code, no model.`}
                    </Text>
                    <HStack gap={1} wrap="wrap">
                      <Token size="sm" color="green" label={`tier 0 code: ${tiers['0'] ?? 0}`} />
                      <Token size="sm" color="blue" label={`tier 1 small: ${tiers['1'] ?? 0}`} />
                      <Token size="sm" color="purple" label={`tier 2 large: ${tiers['2'] ?? 0}`} />
                    </HStack>
                  </VStack>
                </Card>
              </Grid>
            )}
            <Heading level={3}>Memory audit log</Heading>
            <Table data={audit} columns={auditColumns} idKey={a => `${a.ts}-${a.target}`} density="compact" />
          </VStack>
        </LayoutContent>
      }
    />
  )
}
