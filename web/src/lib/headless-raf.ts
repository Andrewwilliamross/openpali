// Headless/hidden-tab frame driver for scripted E2E verification (DEV only).
//
// Chrome never fires requestAnimationFrame in hidden tabs, so MapLibre's boot
// and render loop stall there (CDP screenshots still capture the DOM, which
// makes the stall easy to misread as an app bug). MapLibre binds the native
// rAF at module-eval time, so this shim must be imported BEFORE maplibre-gl —
// it is the first import in main.tsx.
//
// Activation is explicit: ?headlessRaf=1 (and dev builds only). Frames are
// driven PURELY off MessageChannel tasks: hidden tabs align ALL timer
// wake-ups to ≥1 s boundaries, so any setTimeout in the frame path caps the
// map at ~1 fps. Test scripts must therefore also wait via MessageChannel
// yields (window.__mcYield), not setTimeout — message tasks interleave with
// network/decode completions, so the page still makes full progress.
if (import.meta.env.DEV &&
    new URLSearchParams(window.location.search).has('headlessRaf')) {
  // UNCONDITIONAL while the flag is on: occluded/minimized windows can report
  // visibilityState 'visible' while the browser still suspends native rAF —
  // any per-call delegation reintroduces the stall nondeterministically.
  //
  // In-flight channels MUST be retained: an unreferenced MessageChannel can
  // be garbage-collected with its message still queued, silently dropping the
  // frame callback — MapLibre's _frameRequest then dangles forever and the
  // map freezes as soon as GC pressure rises (sort/upload churn).
  const live = new Set<MessageChannel>()
  const stats = { requested: 0, fired: 0 }
  ;(window as unknown as { __rafStats?: typeof stats }).__rafStats = stats
  const postFrame = (fn: () => void): void => {
    const mc = new MessageChannel()
    live.add(mc)
    mc.port1.onmessage = () => {
      live.delete(mc)
      fn()
    }
    mc.port2.postMessage(null)
  }
  window.requestAnimationFrame = (cb: FrameRequestCallback): number => {
    stats.requested++
    postFrame(() => {
      stats.fired++
      cb(performance.now())
    })
    return 0
  }
  ;(window as unknown as { __mcYield?: () => Promise<void> }).__mcYield = () =>
    new Promise<void>((resolve) => postFrame(resolve))
  console.info('[headless-raf] frame driver active (pure MessageChannel, unconditional)')
}

export {}
