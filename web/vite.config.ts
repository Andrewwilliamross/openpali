import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import { createReadStream, statSync } from 'node:fs';
import { extname, join, normalize, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

// The building scene (`make scene-build`) and the imagery mirror
// (`make imagery-mirror`) are generated artifacts, not part of the web source
// tree. In development each is served from where its build writes it; in
// production the same directories are mounted under /scene/ and /imagery/.
// Scene directories are immutable and named by their content; the two small
// documents that say what is current are always revalidated.
const here = fileURLToPath(new URL('.', import.meta.url));
const generated: Record<string, () => string> = {
  '/scene': () => resolve(here, process.env.OPENPALI_SCENE_DIR ?? '../data/out/scene'),
  '/imagery': () => resolve(here, process.env.OPENPALI_IMAGERY_DIR ?? '../data/out/imagery'),
};
function cacheControl(mount: string, path: string): string {
  if (path.endsWith(`${sep}current.json`) || path.endsWith(`${sep}index.json`)) return 'no-cache';
  return mount === '/scene' ? 'public, max-age=31536000, immutable' : 'public, max-age=604800';
}
const types: Record<string, string> = { '.json': 'application/json', '.bin': 'application/octet-stream', '.png': 'image/png', '.webp': 'image/webp' };
function scene(): Plugin {
  return {
    name: 'openpali-scene',
    configureServer(server) {
      for (const [mount, where] of Object.entries(generated)) server.middlewares.use(mount, (req, res) => {
        const dir = where();
        const path = normalize(join(dir, decodeURIComponent((req.url ?? '/').split('?')[0])));
        try {
          if (!path.startsWith(dir + sep)) throw new Error('outside the mount');
          const stat = statSync(path);
          if (!stat.isFile()) throw new Error('not a file');
          res.writeHead(200, { 'Content-Type': types[extname(path)] ?? 'application/octet-stream', 'Content-Length': stat.size, 'Cache-Control': cacheControl(mount, path) });
          createReadStream(path).pipe(res);
        } catch {
          // a missing file is a 404, never the app's index page
          res.writeHead(404, { 'Content-Type': 'text/plain' });
          res.end('not found');
        }
      });
    },
  };
}
export default defineConfig({plugins:[react(),scene()],worker:{format:'es'},server:{port:5173,proxy:{'/v1':'http://127.0.0.1:8000'}}});
