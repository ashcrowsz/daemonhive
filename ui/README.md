# Daemonhive web UI

React 19 + [Astryx](https://github.com/meta/astryx) (Meta's design system), Vite, Recharts, d3-force.

Five pages, all reading Concierge's read-only API (`/api/*`), which asks the agent that owns
the data over A2A. The UI never touches a database.

| page | what |
|---|---|
| Chat | talk to the hive; each answer shows its route and tier, and the tools the model called |
| Overview | sessions, PRs, sleep and calories, best lifts |
| Training | e1RM progression per exercise, every session (click one for details), all PRs |
| Memory graph | the Neo4j facts, seen through each agent's permission scope |
| Hive | Agent Cards, routing tiers, the memory audit log |

```bash
npm install
npm run dev      # http://localhost:5173, API proxied to Concierge on :8100
npm run build    # then Concierge serves ui/dist at http://localhost:8100
npm run astryx -- doctor --built .
```
