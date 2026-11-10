import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import { createReadStream, existsSync, readFileSync, statSync } from 'node:fs';
import { extname, join, normalize, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

// The building scene is a generated artifact (`make scene-build`), not part of
// the web source tree. In development it is served from where the build writes
// it; in production the same directory is published under /scene/.
const here = fileURLToPath(new URL('.', import.meta.url));
function sceneDir(): string {
  if (process.env.OPENPALI_SCENE_DIR) return resolve(here, process.env.OPENPALI_SCENE_DIR);
  const root = resolve(here, '../data/out/scene');
  const pointer = join(root, 'current.json');
  // read per request: a rebuild is picked up on reload, without a restart
  if (existsSync(pointer)) return join(root, JSON.parse(readFileSync(pointer, 'utf8')).scene_id);
  return resolve(here, '../data/out/scene-prototype/buildings');
}
const types: Record<string, string> = { '.json': 'application/json', '.bin': 'application/octet-stream', '.png': 'image/png' };
function scene(): Plugin {
  return {
    name: 'openpali-scene',
    configureServer(server) {
      server.middlewares.use('/scene', (req, res) => {
        const dir = sceneDir();
        const path = normalize(join(dir, decodeURIComponent((req.url ?? '/').split('?')[0])));
        try {
          if (!path.startsWith(dir)) throw new Error('outside the scene');
          const stat = statSync(path);
          if (!stat.isFile()) throw new Error('not a file');
          res.writeHead(200, { 'Content-Type': types[extname(path)] ?? 'application/octet-stream', 'Content-Length': stat.size, 'Cache-Control': 'no-cache' });
          createReadStream(path).pipe(res);
        } catch {
          // a missing scene file is a 404, never the app's index page
          res.writeHead(404, { 'Content-Type': 'text/plain' });
          res.end('scene asset not found');
        }
      });
    },
  };
}
export default defineConfig({plugins:[react(),scene()],worker:{format:'es'},server:{port:5173,proxy:{'/v1':'http://127.0.0.1:8000'}}});
