// GLSL 300 es for the building meshes. One program, switched by `u_pass`
// (the PASS_* constants in BuildingLayer.ts).

export const BUILDING_VERT = /* glsl */ `#version 300 es
precision highp float;
precision highp int;
precision highp sampler2D;

layout(location = 0) in vec3 a_pos;   // u16 grid position
layout(location = 1) in vec2 a_oct;   // octahedral normal, [-1, 1]
layout(location = 2) in float a_id;   // structure id
layout(location = 3) in vec2 a_uv;    // aerial atlas coordinate

uniform mat4 u_matrix;          // batch grid → clip
uniform float u_gridPerMetreZ;  // grid z units per metre
uniform int u_pass;
uniform sampler2D u_state;      // rgb score colour, a = mode | flags
uniform sampler2D u_ground;     // metres added to rest the structure on terrain

out vec3 v_normal;
out vec2 v_uv;
flat out vec4 v_state;
flat out int v_id;

void main() {
  int id = int(a_id + 0.5);
  int width = textureSize(u_state, 0).x;
  ivec2 texel = ivec2(id % width, id / width);
  vec4 state = texelFetch(u_state, texel, 0);
  int mode = int(state.a * 255.0 + 0.5) & 3;

  v_state = state;
  v_id = id;
  v_uv = a_uv;
  vec3 n = vec3(a_oct, 1.0 - abs(a_oct.x) - abs(a_oct.y));
  if (n.z < 0.0) n.xy = (1.0 - abs(n.yx)) * vec2(n.x >= 0.0 ? 1.0 : -1.0, n.y >= 0.0 ? 1.0 : -1.0);
  v_normal = normalize(n);

  // 0 solid · 1 ghost depth · 2 ghost fill · 4 pick   (3 = edges, own program)
  bool wanted = (u_pass == 0 && mode == 1)
    || ((u_pass == 1 || u_pass == 2) && mode == 2)
    || (u_pass == 4 && mode != 0);
  if (!wanted) {
    // every vertex of a triangle shares one structure, so this drops it whole
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
    return;
  }

  float lift = texelFetch(u_ground, texel, 0).r * u_gridPerMetreZ;
  vec4 clip = u_matrix * vec4(a_pos.xy, a_pos.z + lift, 1.0);
  gl_Position = clip;
}
`

export const BUILDING_FRAG = /* glsl */ `#version 300 es
precision highp float;
precision highp int;

uniform int u_pass;
uniform sampler2D u_aerial;
uniform float u_hasAerial;

in vec3 v_normal;
in vec2 v_uv;
flat in vec4 v_state;
flat in int v_id;
out vec4 fragColor;

const vec3 LIGHT = vec3(-0.42, 0.34, 0.84); // from the north-west, local x east / y south / z up

void main() {
  vec3 n = normalize(v_normal);
  bool selected = (int(v_state.a * 255.0 + 0.5) & 4) != 0;
  float lambert = abs(dot(n, LIGHT));
  float roof = smoothstep(0.10, 0.65, abs(n.z));

  if (u_pass == 0) {
    // standing structure: the aerial photo on roofs, lit neutral walls
    vec4 photo = texture(u_aerial, v_uv);
    vec3 wall = vec3(0.82, 0.80, 0.76) * (0.58 + 0.42 * lambert);
    vec3 rgb = mix(wall, photo.rgb, roof * u_hasAerial * photo.a);
    if (selected) rgb = mix(rgb, vec3(1.0), 0.35);
    fragColor = vec4(rgb, 1.0);
  } else if (u_pass == 1) {
    fragColor = vec4(0.0);
  } else if (u_pass == 2) {
    // destroyed structure: a veil of its score colour over the 2026 ground
    // lifted toward white so the shell separates from its same-coloured lot
    float alpha = selected ? 0.62 : mix(0.46, 0.36, roof);
    vec3 rgb = mix(v_state.rgb, vec3(1.0), 0.38) * (0.62 + 0.38 * lambert);
    fragColor = vec4(rgb * alpha, alpha);
  } else {
    fragColor = vec4(float(v_id & 255) / 255.0, float((v_id >> 8) & 255) / 255.0, 0.0, 1.0);
  }
}
`

// Edges: one instanced quad per edge, expanded in screen space.
export const EDGE_VERT = /* glsl */ `#version 300 es
precision highp float;
precision highp int;
precision highp sampler2D;

layout(location = 0) in vec3 a_a;    // endpoint A, u16 grid position
layout(location = 1) in vec3 a_b;    // endpoint B
layout(location = 2) in float a_id;

uniform mat4 u_matrix;
uniform float u_gridPerMetreZ;
uniform vec2 u_viewport;        // drawing buffer pixels
uniform float u_width;          // line width, device pixels
uniform float u_lineBias;       // clip-space pull that keeps a line above its faces
uniform sampler2D u_state;
uniform sampler2D u_ground;

flat out vec4 v_state;
out float v_across;             // signed distance from the centre line, pixels

void main() {
  int id = int(a_id + 0.5);
  int width = textureSize(u_state, 0).x;
  ivec2 texel = ivec2(id % width, id / width);
  v_state = texelFetch(u_state, texel, 0);
  v_across = 0.0;
  if ((int(v_state.a * 255.0 + 0.5) & 3) == 0) {
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
    return;
  }
  float lift = texelFetch(u_ground, texel, 0).r * u_gridPerMetreZ;
  vec4 a = u_matrix * vec4(a_a.xy, a_a.z + lift, 1.0);
  vec4 b = u_matrix * vec4(a_b.xy, a_b.z + lift, 1.0);
  // an edge crossing the camera plane has no screen position: pull the far
  // side of the plane back to it, or drop the edge when both ends are behind
  const float NEAR = 1e-4;
  if (a.w < NEAR && b.w < NEAR) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }
  if (a.w < NEAR) a = mix(b, a, (b.w - NEAR) / (b.w - a.w));
  if (b.w < NEAR) b = mix(a, b, (a.w - NEAR) / (a.w - b.w));

  vec2 half_vp = 0.5 * u_viewport;
  vec2 along = b.xy / b.w * half_vp - a.xy / a.w * half_vp;
  float len = length(along);
  vec2 normal = len > 1e-5 ? vec2(-along.y, along.x) / len : vec2(0.0, 1.0);
  float side = (gl_VertexID & 1) == 0 ? -1.0 : 1.0;
  vec4 clip = (gl_VertexID >> 1) == 0 ? a : b;
  float reach = 0.5 * u_width + 1.0;       // one extra pixel to antialias into
  clip.xy += normal * side * reach / half_vp * clip.w;
  clip.z -= u_lineBias * clip.w;
  v_across = side * reach;
  gl_Position = clip;
}
`

export const EDGE_FRAG = /* glsl */ `#version 300 es
precision highp float;
precision highp int;

uniform float u_width;
flat in vec4 v_state;
in float v_across;
out vec4 fragColor;

void main() {
  int flags = int(v_state.a * 255.0 + 0.5);
  // destroyed: the lot's score colour lifted toward white; standing: ink
  vec4 line = (flags & 3) == 2
    ? vec4(mix(v_state.rgb, vec3(1.0), 0.72), 0.95)
    : vec4(vec3(0.10), 0.55);
  if ((flags & 4) != 0) line = vec4(1.0);
  float alpha = line.a * clamp(0.5 * u_width - abs(v_across) + 0.5, 0.0, 1.0);
  fragColor = vec4(line.rgb * alpha, alpha);
}
`

export function compile(gl: WebGL2RenderingContext, vertex: string, fragment: string,
                        ): WebGLProgram {
  const shader = (type: number, source: string): WebGLShader => {
    const s = gl.createShader(type)
    if (!s) throw new Error('createShader failed')
    gl.shaderSource(s, source)
    gl.compileShader(s)
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      const log = gl.getShaderInfoLog(s)
      gl.deleteShader(s)
      throw new Error(`shader compile failed: ${log}`)
    }
    return s
  }
  const program = gl.createProgram()
  if (!program) throw new Error('createProgram failed')
  const vs = shader(gl.VERTEX_SHADER, vertex)
  const fs = shader(gl.FRAGMENT_SHADER, fragment)
  gl.attachShader(program, vs)
  gl.attachShader(program, fs)
  gl.linkProgram(program)
  gl.deleteShader(vs)
  gl.deleteShader(fs)
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    const log = gl.getProgramInfoLog(program)
    gl.deleteProgram(program)
    throw new Error(`program link failed: ${log}`)
  }
  return program
}
