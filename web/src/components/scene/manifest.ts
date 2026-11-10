// The scene manifest, fetched once and shared by the building layer and the
// terrain protocol, so both describe the same build.
import type { SceneManifest } from './format'

const pending = new Map<string, Promise<SceneManifest>>()

export function loadSceneManifest(baseUrl: string): Promise<SceneManifest> {
  let request = pending.get(baseUrl)
  if (!request) {
    request = fetch(`${baseUrl}/manifest.json`).then((response) => {
      if (!response.ok) throw new Error(`scene manifest: HTTP ${response.status}`)
      return response.json() as Promise<SceneManifest>
    })
    // a failed load must be retryable, not cached as a rejection
    request.catch(() => pending.delete(baseUrl))
    pending.set(baseUrl, request)
  }
  return request
}
