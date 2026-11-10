// The scene the map draws, resolved once per page and shared by the building
// layer and the terrain protocol so both describe the same build.
//
// A scene root holds immutable `<scene-id>/` directories and one small
// `current.json` naming the published one. The pointer is read once; every
// asset is then fetched through the scene-id path, so a rebuild published
// mid-session can never mix two builds, and scene files cache forever.
import type { SceneManifest } from './format'

export interface LoadedScene {
  /** `<root>/<scene-id>`: the prefix every asset of this scene is fetched under. */
  base: string
  manifest: SceneManifest
}

const SCENE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]*$/
const pending = new Map<string, Promise<LoadedScene>>()

async function load(root: string): Promise<LoadedScene> {
  const pointer = await fetch(`${root}/current.json`, { cache: 'no-cache' })
  if (!pointer.ok) throw new Error(`scene pointer: HTTP ${pointer.status}`)
  const sceneId: unknown = ((await pointer.json()) as { scene_id?: unknown }).scene_id
  if (typeof sceneId !== 'string' || !SCENE_ID.test(sceneId)) {
    throw new Error('scene pointer: no usable scene_id')
  }
  const base = `${root}/${sceneId}`
  const response = await fetch(`${base}/manifest.json`)
  if (!response.ok) throw new Error(`scene manifest: HTTP ${response.status}`)
  return { base, manifest: (await response.json()) as SceneManifest }
}

export function loadScene(root: string): Promise<LoadedScene> {
  const key = root.replace(/\/$/, '')
  let request = pending.get(key)
  if (!request) {
    request = load(key)
    // a failed load must be retryable, not cached as a rejection
    request.catch(() => pending.delete(key))
    pending.set(key, request)
  }
  return request
}
