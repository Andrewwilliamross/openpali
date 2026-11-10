// Minimal float64 4×4 matrix kit for the splat layer.
// Column-major, matching WebGL/MapLibre conventions: m[col*4 + row].
// Kept in Float64Array end-to-end — matrix products against mercator-scale
// translations lose metres of precision in f32; we only downcast at upload.

export type Mat4 = Float64Array

export function identity(): Mat4 {
  const m = new Float64Array(16)
  m[0] = m[5] = m[10] = m[15] = 1
  return m
}

/** out = a · b (column-major). Safe when out aliases a or b. */
export function multiply(a: Mat4, b: Mat4, out?: Mat4): Mat4 {
  const o = new Float64Array(16)
  for (let c = 0; c < 4; c++) {
    const b0 = b[c * 4], b1 = b[c * 4 + 1], b2 = b[c * 4 + 2], b3 = b[c * 4 + 3]
    o[c * 4] = a[0] * b0 + a[4] * b1 + a[8] * b2 + a[12] * b3
    o[c * 4 + 1] = a[1] * b0 + a[5] * b1 + a[9] * b2 + a[13] * b3
    o[c * 4 + 2] = a[2] * b0 + a[6] * b1 + a[10] * b2 + a[14] * b3
    o[c * 4 + 3] = a[3] * b0 + a[7] * b1 + a[11] * b2 + a[15] * b3
  }
  if (out) {
    out.set(o)
    return out
  }
  return o
}

/** out = m · T(t) · S(s)  — translate then scale (applied to incoming points). */
export function composeTRS(m: Mat4, t: [number, number, number],
                           s: [number, number, number]): Mat4 {
  const o = new Float64Array(16)
  // columns of the local transform: diag(s) with translation t
  for (let i = 0; i < 3; i++) {
    o[i * 4] = m[i * 4] * s[i]
    o[i * 4 + 1] = m[i * 4 + 1] * s[i]
    o[i * 4 + 2] = m[i * 4 + 2] * s[i]
    o[i * 4 + 3] = m[i * 4 + 3] * s[i]
  }
  o[12] = m[0] * t[0] + m[4] * t[1] + m[8] * t[2] + m[12]
  o[13] = m[1] * t[0] + m[5] * t[1] + m[9] * t[2] + m[13]
  o[14] = m[2] * t[0] + m[6] * t[1] + m[10] * t[2] + m[14]
  o[15] = m[3] * t[0] + m[7] * t[1] + m[11] * t[2] + m[15]
  return o
}

/** General 4×4 inverse (cofactor expansion). Returns null when singular. */
export function invert(m: Mat4): Mat4 | null {
  const a00 = m[0], a01 = m[1], a02 = m[2], a03 = m[3]
  const a10 = m[4], a11 = m[5], a12 = m[6], a13 = m[7]
  const a20 = m[8], a21 = m[9], a22 = m[10], a23 = m[11]
  const a30 = m[12], a31 = m[13], a32 = m[14], a33 = m[15]

  const b00 = a00 * a11 - a01 * a10
  const b01 = a00 * a12 - a02 * a10
  const b02 = a00 * a13 - a03 * a10
  const b03 = a01 * a12 - a02 * a11
  const b04 = a01 * a13 - a03 * a11
  const b05 = a02 * a13 - a03 * a12
  const b06 = a20 * a31 - a21 * a30
  const b07 = a20 * a32 - a22 * a30
  const b08 = a20 * a33 - a23 * a30
  const b09 = a21 * a32 - a22 * a31
  const b10 = a21 * a33 - a23 * a31
  const b11 = a22 * a33 - a23 * a32

  const det = b00 * b11 - b01 * b10 + b02 * b09 + b03 * b08 - b04 * b07 + b05 * b06
  if (!det || !Number.isFinite(det)) return null
  const id = 1.0 / det

  const o = new Float64Array(16)
  o[0] = (a11 * b11 - a12 * b10 + a13 * b09) * id
  o[1] = (a02 * b10 - a01 * b11 - a03 * b09) * id
  o[2] = (a31 * b05 - a32 * b04 + a33 * b03) * id
  o[3] = (a22 * b04 - a21 * b05 - a23 * b03) * id
  o[4] = (a12 * b08 - a10 * b11 - a13 * b07) * id
  o[5] = (a00 * b11 - a02 * b08 + a03 * b07) * id
  o[6] = (a32 * b02 - a30 * b05 - a33 * b01) * id
  o[7] = (a20 * b05 - a22 * b02 + a23 * b01) * id
  o[8] = (a10 * b10 - a11 * b08 + a13 * b06) * id
  o[9] = (a01 * b08 - a00 * b10 - a03 * b06) * id
  o[10] = (a30 * b04 - a31 * b02 + a33 * b00) * id
  o[11] = (a21 * b02 - a20 * b04 - a23 * b00) * id
  o[12] = (a11 * b07 - a10 * b09 - a12 * b06) * id
  o[13] = (a00 * b09 - a01 * b07 + a02 * b06) * id
  o[14] = (a31 * b01 - a30 * b03 - a32 * b00) * id
  o[15] = (a20 * b03 - a21 * b01 + a22 * b00) * id
  return o
}

/** Transform a point with perspective divide. Returns [x, y, z, wClip]. */
export function transformPoint(m: Mat4, p: [number, number, number]
                               ): [number, number, number, number] {
  const x = m[0] * p[0] + m[4] * p[1] + m[8] * p[2] + m[12]
  const y = m[1] * p[0] + m[5] * p[1] + m[9] * p[2] + m[13]
  const z = m[2] * p[0] + m[6] * p[1] + m[10] * p[2] + m[14]
  const w = m[3] * p[0] + m[7] * p[1] + m[11] * p[2] + m[15]
  if (Math.abs(w) < 1e-12) return [x, y, z, w]
  return [x / w, y / w, z / w, w]
}
