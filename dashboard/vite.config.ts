import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, '..');

// Middleware serves /logs/* and /kill-switch from the project-root logs/ dir.
// Lets the bot keep writing to logs/decisions.jsonl without touching the dashboard.
function projectLogsMiddleware() {
  return {
    name: 'serve-project-logs',
    configureServer(server: any) {
      server.middlewares.use((req: any, res: any, next: any) => {
        const url = (req.url || '').split('?')[0];
        let target: string | null = null;
        if (url.startsWith('/logs/')) {
          target = path.join(PROJECT_ROOT, 'logs', url.slice('/logs/'.length));
        } else if (url === '/api/kill-switch') {
          target = path.join(PROJECT_ROOT, 'logs', 'kill_switch.json');
        }
        if (!target) return next();
        if (!fs.existsSync(target) || !fs.statSync(target).isFile()) {
          // Cleaner UX than a 404: kill-switch endpoint returns "not engaged",
          // log endpoint returns an empty body — dashboard hooks handle both.
          res.statusCode = 200;
          res.setHeader('Cache-Control', 'no-cache');
          if (url === '/api/kill-switch') {
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(JSON.stringify({ engaged: false }));
          } else {
            res.setHeader('Content-Type', 'application/x-ndjson; charset=utf-8');
            res.end('');
          }
          return;
        }
        res.setHeader('Cache-Control', 'no-cache');
        res.setHeader(
          'Content-Type',
          target.endsWith('.jsonl')
            ? 'application/x-ndjson; charset=utf-8'
            : 'application/json; charset=utf-8',
        );
        fs.createReadStream(target).pipe(res);
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), projectLogsMiddleware()],
  server: {
    host: '127.0.0.1',
    port: 3005,
    strictPort: false, // fall through to 3006/3007/… if 3005 is busy
  },
});
