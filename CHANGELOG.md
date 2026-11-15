# changelog

### 2026-11-15 · helm chart + CI
`deploy/helm`
- helm: deployment + netpol per agent, cronjobs
- ci: unit + offline scenarios, live scenarios on main

### 2026-11-14 · work planner + nightly scribe
`feat/work-scribe`
- work: move deep work past 11:00 after short nights
- scribe: entity merge candidates + fact invalidation

### 2026-11-12 · concierge, events and the telegram gateway
`feat/concierge-events`
- nats events: idempotent consumer + dead letter
- concierge: rules first, small model second
- telegram gateway, single allowed chat

### 2026-11-09 · shared temporal memory with per-agent scopes
`feat/temporal-memory`
- memory permission guard + audit log
- memory-mcp on graphiti/neo4j
- reference scenario harness: trajectory + graph end state

### 2026-11-06 · fitness agent end to end
`feat/fitness-agent`
- tiered model routing + per-agent litellm keys
- fitness agent: regression -> ask well-being -> memory -> message
- fitness-db MCP server + fitness A2A service

### 2026-11-01 · agent-to-agent protocol + well-being agent
`feat/a2a`
- a2a: agent cards, task server, client that degrades on failure
- per-skill caller allow-lists + a2a tests
- well-being: recovery_summary skill (aggregates only)

### 2026-10-28 · workout log grammar + session analysis
`feat/fitness-parser`
- workout log grammar (tier 0, no model)
- parser test cases
- fix: whole-name aliases ('Bench Press' became 'bench press press')
- session comparison: PRs, regressions, epley e1RM
