// Headless/hidden-tab frame driver for scripted E2E verification (DEV only).
//
// Chrome never fires requestAnimationFrame in hidden tabs, so MapLibre's boot
// and render loop stall there (CDP screenshots still capture the DOM, which
// makes the stall easy to misread as an app bug). MapLibre binds the native
// rAF at module-eval time, so this shim must be imported BEFORE maplibre-gl —
// it is the first import in main.tsx.
//
// Activation is explicit: ?headlessRaf=1 (and dev builds only). Frames are
// driven off MessageChannel tasks (not throttled in hidden tabs); every 4th
// frame routes through the macrotask timer queue so polling timers used by
// test scripts still interleave with a continuously-repainting map.
if (import.meta.env.DEV &&
    new URLSearchParams(window.location.search).has('headlessRaf')) {
  const native = window.requestAnimationFrame.bind(window)
  let hidden = document.visibilityState === 'hidden'
  document.addEventListener('visibilitychange', () => {
    hidden = document.visibilityState === 'hidden'
  })
  let n = 0
  window.requestAnimationFrame = (cb: FrameRequestCallback): number => {
    if (!hidden) return native(cb)
    n++
    if (n % 4 === 0) {
      setTimeout(() => cb(performance.now()), 16)
    } else {
      const mc = new MessageChannel()
      mc.port1.onmessage = () => cb(performance.now())
      mc.port2.postMessage(null)
    }
    return 0
  }
  console.info('[headless-raf] hidden-tab frame driver active')
}

export {}
