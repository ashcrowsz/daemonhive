# changelog

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
