// GLSL 300 es shaders for EWA Gaussian-splat rendering inside MapLibre.
//
// Approach: the vertex shader receives ONE matrix u_matrix that maps local-ENU
// metres directly to clip space (CPU composes: maplibreMercatorMatrix ·
// T(originMercator) · S(s, -s, s), all in float64). The screen-space EWA
// Jacobian A = ∂(pixels)/∂(ENU metres) is derived analytically from u_matrix
// per splat via the chain rule — no separate view/projection split, no focal
// lengths, no axis-convention assumptions about MapLibre's matrix internals.
//
//   clip   = M · p,   w = clip.w
//   ndc    = clip.xy / w
//   px     = (ndc · 0.5 + 0.5) * viewport
//   ∂px_x/∂p_j = 0.5 · vw · (M[0][j] · w − clip.x · M[3][j]) / w²
//   ∂px_y/∂p_j = 0.5 · vh · (M[1][j] · w − clip.y · M[3][j]) / w²
//
// Σ' = A Σ Aᵀ (+0.3 px² low-pass) → closed-form 2×2 eigen → oriented quad at
// ±√8·σ. Quad corners share the CENTER's clip z and w so the depth test
// against MapLibre's terrain slices whole splats cleanly (no half-clipped
// ellipses along the ground line). Depth writes are off; order comes from the
// CPU sort. Premultiplied-alpha output, (ONE, ONE_MINUS_SRC_ALPHA) blending.

export const SPLAT_VERT = /* glsl */ `#version 300 es
precision highp float;

// 32-byte instanced splat record
layout(location = 0) in vec3 a_center;   // ENU metres about the tileset origin
layout(location = 1) in vec3 a_scale;    // metres (σ along local axes)
layout(location = 2) in vec4 a_color;    // normalized u8 rgba (straight alpha)
layout(location = 3) in vec4 a_rot;      // normalized u8 quat wxyz (q·128+128)

uniform mat4 u_matrix;      // local ENU metres → clip
uniform vec2 u_viewport;    // framebuffer pixels
uniform float u_fade;       // temporal fade-in [0..1]
uniform float u_zOffset;    // terrain clamp, metres ENU up
// projective texturing (per node): texture rect in ENU metres
uniform float u_hasTex;     // 1.0 when an aerial texture is bound for this node
uniform vec2 u_texOrigin;   // [west edge X, NORTH edge Y] of the texture rect
uniform vec2 u_texInvSize;  // [1/widthM, 1/heightM]

out vec2 v_uv;
out vec4 v_color;
out vec2 v_texUv;           // orthophoto sample coordinate (splat centre)
out float v_texW;           // projection weight: 1 roof → 0 wall (anti-smear)

void cull() { gl_Position = vec4(0.0, 0.0, 2.0, 1.0); v_color = vec4(0.0); v_uv = vec2(0.0); v_texUv = vec2(0.0); v_texW = 0.0; }

void main() {
  // corner of the instanced quad from gl_VertexID (TRIANGLE_STRIP, 4 verts)
  vec2 corner = vec2(float(gl_VertexID & 1) * 2.0 - 1.0,
                     float((gl_VertexID >> 1) & 1) * 2.0 - 1.0);

  vec3 p = a_center + vec3(0.0, 0.0, u_zOffset);
  vec4 clip = u_matrix * vec4(p, 1.0);
  float w = clip.w;

  // guard band: 1.2·w so the ±2.83σ footprint of edge splats survives
  float lim = 1.2 * abs(w);
  if (w <= 0.0 || clip.z < -lim || abs(clip.x) > lim || abs(clip.y) > lim) { cull(); return; }

  // ---- decode rotation quaternion (wxyz, u8 → unit) ----
  vec4 q = a_rot * 255.0;
  q = (q - 128.0) / 128.0;
  q = normalize(q);
  float qw = q.x, qx = q.y, qy = q.z, qz = q.w;
  // R from quaternion (columns are the rotated basis vectors)
  mat3 R = mat3(
    1.0 - 2.0*(qy*qy + qz*qz), 2.0*(qx*qy + qw*qz),       2.0*(qx*qz - qw*qy),
    2.0*(qx*qy - qw*qz),       1.0 - 2.0*(qx*qx + qz*qz), 2.0*(qy*qz + qw*qx),
    2.0*(qx*qz + qw*qy),       2.0*(qy*qz - qw*qx),       1.0 - 2.0*(qx*qx + qy*qy)
  );
  mat3 S2 = mat3(a_scale.x*a_scale.x, 0.0, 0.0,
                 0.0, a_scale.y*a_scale.y, 0.0,
                 0.0, 0.0, a_scale.z*a_scale.z);
  mat3 Vrk = R * S2 * transpose(R);   // world (ENU) covariance, m²

  // ---- anti-smear projection mask ----
  // disk normal n = R·ẑ (third column). The orthophoto is projected straight
  // down, so the weight is w_p = clamp(n·up, 0, 1) — |n_z| in our z-up ENU
  // frame (abs() makes it winding-proof). Smoothstepped so the photo
  // cross-fades to the score tint as faces approach vertical, instead of
  // smearing a roof pixel column down the whole wall.
  vec3 diskNormal = R[2];
  v_texW = u_hasTex * smoothstep(0.25, 0.6, clamp(abs(diskNormal.z), 0.0, 1.0));
  // orthophoto uv at the splat centre: x east of the west edge, v grows
  // SOUTH from the north edge (texture row 0 = north)
  v_texUv = vec2((p.x - u_texOrigin.x) * u_texInvSize.x,
                 (u_texOrigin.y - p.y) * u_texInvSize.y);

  // ---- analytic screen-space Jacobian from u_matrix ----
  // rows of M (column-major storage: M[col][row])
  vec3 m0 = vec3(u_matrix[0][0], u_matrix[1][0], u_matrix[2][0]); // row 0 · xyz
  vec3 m1 = vec3(u_matrix[0][1], u_matrix[1][1], u_matrix[2][1]); // row 1
  vec3 m3 = vec3(u_matrix[0][3], u_matrix[1][3], u_matrix[2][3]); // row 3 (w)
  float inv_w = 1.0 / w;
  float inv_w2 = inv_w * inv_w;
  vec3 dpx = 0.5 * u_viewport.x * (m0 * w - clip.x * m3) * inv_w2; // ∂px/∂p
  vec3 dpy = 0.5 * u_viewport.y * (m1 * w - clip.y * m3) * inv_w2; // ∂py/∂p

  // Σ' = A Σ Aᵀ  (2×2, pixels²) + low-pass dilation WITH energy compensation
  // (EWA Eq. 33 / Mip-Splatting 2D mip filter / gsplat "antialiased" mode).
  // The +0.3 px² guarantees a ≥~1px footprint, but without rescaling alpha by
  // sqrt(det₀/det₁) every dilated sub-pixel surfel keeps full opacity: 10M of
  // them accumulate into opaque shimmer that crawls under motion, and edge-on
  // flat disks (σ_z≈1 mm, det₀→0) draw as full-alpha 1-px flicker lines.
  float sa0 = dot(dpx, Vrk * dpx);
  float sb  = dot(dpx, Vrk * dpy);
  float sc0 = dot(dpy, Vrk * dpy);
  float det0 = max(sa0 * sc0 - sb * sb, 0.0);
  float sa = sa0 + 0.3;
  float sc = sc0 + 0.3;
  float det = sa * sc - sb * sb;
  if (det <= 0.0) { cull(); return; }
  float comp = sqrt(det0 / det); // energy conservation: α·√det is invariant

  // closed-form symmetric 2×2 eigendecomposition
  float mid = 0.5 * (sa + sc);
  float disc = sqrt(max(mid * mid - det, 1e-7));
  float l1 = mid + disc;
  float l2 = max(mid - disc, 0.1);
  // NaN guard for perfectly isotropic splats (surfels viewed face-on hit this)
  vec2 e1 = (abs(sb) > 1e-11) ? normalize(vec2(sb, l1 - sa)) : vec2(1.0, 0.0);
  vec2 e2 = vec2(e1.y, -e1.x);

  const float K = 2.8284271; // sqrt(8) σ quad extent
  vec2 axis1 = min(K * sqrt(l1), 1024.0) * e1;  // pixels
  vec2 axis2 = min(K * sqrt(l2), 1024.0) * e2;

  vec2 offNdc = (corner.x * axis1 + corner.y * axis2) * 2.0 / u_viewport;

  float a0 = min(a_color.a, 0.99) * comp;
  // transmittance-correct LOD cross-fade: the layer hands the child t and the
  // parent (1−t); with α' = 1−(1−α)^t the pair's combined transmittance is
  // (1−α)^t · (1−α)^(1−t) = (1−α) — constant through the fade, so REPLACE
  // refinement produces no brightness pulse (linear weights dim mid-fade).
  float alpha = u_fade >= 0.999 ? a0 : 1.0 - pow(1.0 - a0, u_fade);
  // near-plane fade hides viewport-sized quads when flying through facades
  alpha *= clamp(clip.z * inv_w + 1.0, 0.0, 1.0);
  if (alpha < 0.0039) { cull(); return; }  // < 1/255

  v_uv = corner;
  v_color = vec4(a_color.rgb, alpha);

  // corners share the center's z and w → coherent depth vs terrain
  float cz = clamp(clip.z, -abs(w), abs(w));
  gl_Position = vec4(clip.xy + offNdc * w, cz, w);
}
`

export const SPLAT_FRAG = /* glsl */ `#version 300 es
precision mediump float;

uniform sampler2D u_tex;    // per-node aerial orthophoto (or 1px fallback)

in vec2 v_uv;
in vec4 v_color;
in vec2 v_texUv;
in float v_texW;
out vec4 fragColor;

void main() {
  float r2 = dot(v_uv, v_uv);
  if (r2 > 1.0) discard;
  // edge-normalised gaussian: exactly 0 at the quad rim (no hard cutoff ring)
  // 1/(1 - e^-4) = 1.0186574
  float falloff = (exp(-4.0 * r2) - 0.0183156) * 1.0186574;
  float alpha = v_color.a * max(falloff, 0.0);
  // projective texture: photo on horizontal surfaces, score tint on walls
  vec3 photo = texture(u_tex, v_texUv).rgb;
  vec3 rgb = mix(v_color.rgb, photo, v_texW);
  fragColor = vec4(rgb * alpha, alpha);  // premultiplied
}
`

export function compileProgram(gl: WebGL2RenderingContext, vsSrc: string,
                               fsSrc: string): WebGLProgram {
  const compile = (type: number, src: string): WebGLShader => {
    const sh = gl.createShader(type)
    if (!sh) throw new Error('createShader failed')
    gl.shaderSource(sh, src)
    gl.compileShader(sh)
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
      const log = gl.getShaderInfoLog(sh)
      gl.deleteShader(sh)
      throw new Error(`shader compile failed: ${log}`)
    }
    return sh
  }
  const vs = compile(gl.VERTEX_SHADER, vsSrc)
  let fs: WebGLShader
  try {
    fs = compile(gl.FRAGMENT_SHADER, fsSrc)
  } catch (e) {
    gl.deleteShader(vs)
    throw e
  }
  const prog = gl.createProgram()
  if (!prog) {
    gl.deleteShader(vs)
    gl.deleteShader(fs)
    throw new Error('createProgram failed')
  }
  gl.attachShader(prog, vs)
  gl.attachShader(prog, fs)
  gl.linkProgram(prog)
  gl.deleteShader(vs)
  gl.deleteShader(fs)
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
    const log = gl.getProgramInfoLog(prog)
    gl.deleteProgram(prog)
    throw new Error(`program link failed: ${log}`)
  }
  return prog
}
