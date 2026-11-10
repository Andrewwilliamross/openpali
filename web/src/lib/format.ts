export function titleCase(s: string): string {
  return s
    .toLowerCase()
    .replace(/\b([a-z])/g, (m) => m.toUpperCase())
    .replace(/\b(Dr|St|Ave|Blvd|Pl|Ln|Rd|Ct|Way|Ter)\b\.?/gi, (m) => m)
}

/** 0 when the user asks for reduced motion (WCAG 2.3.3), else the given ms. */
export function motionMs(ms: number): number {
  if (typeof window !== 'undefined'
      && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
    return 0
  }
  return ms
}
