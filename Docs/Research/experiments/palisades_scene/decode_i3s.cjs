/* Bounded I3S research adapter. See the adjacent research note for sources.
 * Usage: node decode_i3s.cjs input.drc output.json /path/to/draco3d
 * Uses the official Draco decoder; no application dependency is added.
 */
const fs = require('node:fs');
const path = require('node:path');
const draco = require(process.argv[4] || 'draco3d');
const version = require(process.argv[4] ? path.join(process.argv[4], 'package.json') : 'draco3d/package.json').version;

async function main() {
  if (version !== '1.5.7') throw Error(`This experiment pins draco3d 1.5.7; found ${version}`);
  const M = await draco.createDecoderModule({});
  const decoder = new M.Decoder(), buffer = new M.DecoderBuffer();
  const mesh = new M.Mesh(), query = new M.MetadataQuerier();
  const objects = [query, mesh, buffer, decoder];
  try {
    const raw = fs.readFileSync(process.argv[2]);
    if (raw.subarray(0, 5).toString() !== 'DRACO') throw Error('Expected a Draco payload');
    buffer.Init(new Int8Array(raw), raw.length);
    if (decoder.GetEncodedGeometryType(buffer) !== M.TRIANGULAR_MESH) throw Error('Expected triangles');
    const status = decoder.DecodeBufferToMesh(buffer, mesh);
    if (!status.ok()) throw Error(status.error_msg());
    const attributes = [];
    for (let i = 0; i < mesh.num_attributes(); i++) {
      const attribute = decoder.GetAttribute(mesh, i);
      const metadata = decoder.GetAttributeMetadata(mesh, i);
      const values = new M.DracoFloat32Array();
      try {
        if (!decoder.GetAttributeFloatForAllPoints(mesh, attribute, values)) throw Error('Attribute decode failed');
        const entry = {
          type: attribute.attribute_type(), components: attribute.num_components(),
          values: Array.from({length: values.size()}, (_, j) => values.GetValue(j)),
        };
        if (attribute.attribute_type() === M.POSITION) {
          entry.scale = ['i3s-scale_x', 'i3s-scale_y'].map(k => query.HasEntry(metadata, k) ? query.GetDoubleEntry(metadata, k) : 1);
        } else if (query.HasEntry(metadata, 'i3s-attribute-type')) {
          entry.semantic = query.GetStringEntry(metadata, 'i3s-attribute-type');
          if (entry.semantic === 'feature-index') {
            const ids = new M.DracoInt32Array();
            try {
              query.GetIntEntryArray(metadata, 'i3s-feature-ids', ids);
              entry.featureIds = Array.from({length: ids.size()}, (_, j) => ids.GetValue(j));
            } finally { M.destroy(ids); }
          }
        }
        attributes.push(entry);
      } finally { M.destroy(values); }
    }
    const indices = [], face = new M.DracoInt32Array();
    try {
      for (let i = 0; i < mesh.num_faces(); i++) {
        if (!decoder.GetFaceFromMesh(mesh, i, face)) throw Error('Face decode failed');
        indices.push(face.GetValue(0), face.GetValue(1), face.GetValue(2));
      }
    } finally { M.destroy(face); }
    fs.writeFileSync(process.argv[3], JSON.stringify({attributes, indices, decoderVersion: version}));
  } finally { for (const object of objects) M.destroy(object); }
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
