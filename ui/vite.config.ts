import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// dev: `npm run dev` on :5173, API calls proxied to Concierge on :8100
// prod: `npm run build`, then Concierge serves ui/dist itself at http://localhost:8100
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:8100' } },
})
