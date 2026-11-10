import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import { createReadStream, statSync } from 'node:fs';
import { extname, join, normalize, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

// The building scene is a generated artifact (`make scene-build`), not part of
// the web source tree. In development the scene root (immutable `<scene-id>/`
// directories plus the `current.json` pointer) is served from where the build
// writes it; in production the same directory is mounted under /scene/.
const here = fileURLToPath(new URL('.', import.meta.url));
function sceneDir(): string {
  return resolve(here, process.env.OPENPALI_SCENE_DIR ?? '../data/out/scene');
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
          if (!path.startsWith(dir + sep)) throw new Error('outside the scene');
          const stat = statSync(path);
          if (!stat.isFile()) throw new Error('not a file');
          res.writeHead(200, { 'Content-Type': types[extname(path)] ?? 'application/octet-stream', 'Content-Length': stat.size, 'Cache-Control': path.endsWith(`${sep}current.json`) ? 'no-cache' : 'public, max-age=31536000, immutable' });
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
