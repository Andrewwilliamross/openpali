/* Native WebGL2 feature-addressable I3S roof layer. Raster/camera streaming is
 * provided by MapLibre; geometry, source filtering and byte patches are ours.
 * Textures are dated aerial projections, not measured façade photographs.
 */
window.PalisadesBuildings={async create(map){
 const response=await fetch('buildings/manifest.json');if(!response.ok)throw Error('Building manifest unavailable');
 const data=await response.json(),selected=new Set(),overrides=new Map(),loaded=new Map(),pending=new Set(),texturePending=new Set();
 let gl,program,statesTexture,width,height,states,policy='off',date='july2026',geometryUploads=0,geometryBytes=0,stateUploads=0,stateBytes=0,atlasUploads=0,errors=[];
 const LOWER_DAMAGE=new Set(['No Damage','Affected (1-9%)','Minor (10-25%)']);
 const multiply=(a,b)=>{const o=new Float32Array(16);for(let c=0;c<4;c++)for(let r=0;r<4;r++){let v=0;for(let k=0;k<4;k++)v+=a[k*4+r]*b[c*4+k];o[c*4+r]=v}return o};
 const scale=data.mercator_metre_scale,model=[scale,0,0,0,0,scale,0,0,0,0,scale,0,data.mercator_origin[0],data.mercator_origin[1],0,1];
 function upload(id){gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,statesTexture);gl.pixelStorei(gl.UNPACK_ALIGNMENT,1);gl.texSubImage2D(gl.TEXTURE_2D,0,id%width,Math.floor(id/width),1,1,gl.RED_INTEGER,gl.UNSIGNED_BYTE,states.subarray(id,id+1));stateUploads++;stateBytes++;}
 function update(){if(!states)return;states.fill(0);for(const s of data.structures){const mode=overrides.get(s.gpu_id)??(policy==='all'||policy==='retained'&&LOWER_DAMAGE.has(s.damage)?1:0);states[s.gpu_id]=mode+(selected.has(s.gpu_id)?4:0)}gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,statesTexture);gl.pixelStorei(gl.UNPACK_ALIGNMENT,1);gl.texSubImage2D(gl.TEXTURE_2D,0,0,0,width,height,gl.RED_INTEGER,gl.UNSIGNED_BYTE,states);stateUploads++;stateBytes+=states.byteLength;map.triggerRepaint();}
 async function load(node){pending.add(node.id);try{
  const [vertices,indices]=await Promise.all([fetch(`buildings/${node.id}.vertices.bin`).then(r=>{if(!r.ok)throw Error('Vertex buffer unavailable');return r.arrayBuffer()}),fetch(`buildings/${node.id}.indices.bin`).then(r=>{if(!r.ok)throw Error('Index buffer unavailable');return r.arrayBuffer()})]);
  if(vertices.byteLength!==node.vertex_bytes||indices.byteLength!==node.index_bytes)throw Error('GPU buffer length mismatch');
  const vao=gl.createVertexArray(),vbo=gl.createBuffer(),ibo=gl.createBuffer();gl.bindVertexArray(vao);gl.bindBuffer(gl.ARRAY_BUFFER,vbo);gl.bufferData(gl.ARRAY_BUFFER,vertices,gl.STATIC_DRAW);gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,ibo);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,indices,gl.STATIC_DRAW);for(const [i,n,offset] of [[0,3,0],[1,3,12],[2,2,24],[3,1,32]]){gl.enableVertexAttribArray(i);gl.vertexAttribPointer(i,n,gl.FLOAT,false,36,offset)}gl.bindVertexArray(null);geometryUploads+=2;geometryBytes+=vertices.byteLength+indices.byteLength;
  const i=new Uint32Array(indices),lines=new Uint32Array(i.length*2);for(let j=0;j<i.length;j+=3)lines.set([i[j],i[j+1],i[j+1],i[j+2],i[j+2],i[j]],j*2);
  const wire=gl.createBuffer();gl.bindVertexArray(vao);gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,wire);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,lines,gl.STATIC_DRAW);gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,ibo);gl.bindVertexArray(null);geometryUploads++;geometryBytes+=lines.byteLength;
  loaded.set(node.id,{...node,vao,vbo,ibo,textures:new Map(),wire,wireCount:lines.length});map.triggerRepaint();
 }catch(e){errors.push(e.message);console.error(e)}finally{pending.delete(node.id)}}
 async function loadTexture(node,key){const id=`${node.id}:${key}`;texturePending.add(id);try{
  const response=await fetch(`atlas/${key}/${node.id}.png`);if(!response.ok)throw Error(`Aerial texture unavailable for node ${node.id}`);const bitmap=await createImageBitmap(await response.blob());const texture=gl.createTexture();gl.activeTexture(gl.TEXTURE1);gl.bindTexture(gl.TEXTURE_2D,texture);gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,false);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,bitmap);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR_MIPMAP_LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);gl.generateMipmap(gl.TEXTURE_2D);bitmap.close();node.textures.set(key,texture);atlasUploads++;map.triggerRepaint();
 }catch(e){errors.push(e.message);node.textures.set(key,null);console.error(e)}finally{texturePending.delete(id)}}
 function visible(node){const b=map.getBounds(),n=node.bounds;return n[2]>=b.getWest()&&n[0]<=b.getEast()&&n[3]>=b.getSouth()&&n[1]<=b.getNorth()}
 const layer={id:'palisades-roof-meshes',type:'custom',renderingMode:'3d',
  onAdd(m,context){gl=context;if(!(gl instanceof WebGL2RenderingContext))throw Error('Roof rendering requires WebGL2');
   const vs=`#version 300 es
layout(location=0) in vec3 position;layout(location=1) in vec3 normal;layout(location=2) in vec2 uv;layout(location=3) in float feature;
uniform mat4 matrix;out vec3 n;out vec2 tex;flat out int id;void main(){gl_Position=matrix*vec4(position,1.);n=normal;tex=uv;id=int(feature+.5);}`;
   const fs=`#version 300 es
precision highp float;precision highp int;precision highp usampler2D;uniform usampler2D states;uniform sampler2D aerial;uniform int pass;in vec3 n;in vec2 tex;flat in int id;out vec4 color;
void main(){ivec2 dims=textureSize(states,0);uint state=texelFetch(states,ivec2(id%dims.x,id/dims.x),0).r;uint mode=state&3u;if(mode==0u||(pass==0&&mode!=1u)||(pass==1&&mode!=2u))discard;
if(pass==1){color=vec4(.67,.94,.83,1.);return;}vec4 photo=texture(aerial,tex);if(photo.a<.1)discard;float roof=smoothstep(.10,.65,abs(normalize(n).z));vec3 base=mix(vec3(.64,.62,.56),photo.rgb,roof);float shade=mix(.73+.27*abs(dot(normalize(n),normalize(vec3(-.5,-.4,1.)))),1.,roof);if((state&4u)>0u)base=mix(base,vec3(.45,.93,.72),.35);color=vec4(base*shade,1.);}`;
   const shader=(type,source)=>{const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s};program=gl.createProgram();gl.attachShader(program,shader(gl.VERTEX_SHADER,vs));gl.attachShader(program,shader(gl.FRAGMENT_SHADER,fs));gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(program));
   width=Math.min(4096,gl.getParameter(gl.MAX_TEXTURE_SIZE));height=Math.ceil((data.structures.length+1)/width);states=new Uint8Array(width*height);statesTexture=gl.createTexture();gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,statesTexture);gl.pixelStorei(gl.UNPACK_ALIGNMENT,1);gl.texImage2D(gl.TEXTURE_2D,0,gl.R8UI,width,height,0,gl.RED_INTEGER,gl.UNSIGNED_BYTE,states);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.NEAREST);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.NEAREST);update();
  },
  render(context,args){if(policy==='off'||map.getZoom()<15)return;const nodes=data.nodes.filter(visible);for(const node of nodes)if(!loaded.has(node.id)&&!pending.has(node.id)&&pending.size<3)load(node);
   gl.useProgram(program);gl.uniformMatrix4fv(gl.getUniformLocation(program,'matrix'),false,multiply(args.defaultProjectionData.mainMatrix,model));gl.uniform1i(gl.getUniformLocation(program,'states'),0);gl.uniform1i(gl.getUniformLocation(program,'aerial'),1);gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,statesTexture);gl.enable(gl.DEPTH_TEST);gl.depthMask(true);gl.disable(gl.CULL_FACE);gl.disable(gl.BLEND);
   let hasWire=false;for(const value of overrides.values())if(value===2)hasWire=true;
   for(const node of nodes){const batch=loaded.get(node.id);if(!batch)continue;const key=date;if(!batch.textures.has(key)&&!texturePending.has(`${node.id}:${key}`)&&texturePending.size<3)loadTexture(batch,key);const texture=batch.textures.get(key);if(!texture)continue;gl.activeTexture(gl.TEXTURE1);gl.bindTexture(gl.TEXTURE_2D,texture);gl.bindVertexArray(batch.vao);gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,batch.ibo);gl.uniform1i(gl.getUniformLocation(program,'pass'),0);gl.drawElements(gl.TRIANGLES,batch.index_count,gl.UNSIGNED_INT,0);
    if(hasWire){gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,batch.wire);gl.uniform1i(gl.getUniformLocation(program,'pass'),1);gl.drawElements(gl.LINES,batch.wireCount,gl.UNSIGNED_INT,0)}
   }gl.bindVertexArray(null);
  },
  setPolicy(value){if(!['off','retained','all'].includes(value))throw Error('Invalid building policy');policy=value;overrides.clear();update()},setDate(value){date=value;map.triggerRepaint()},
  idsForApn(apn){return data.structures.filter(s=>s.apn===apn).map(s=>s.gpu_id)},
  representationFor(id){return states[id]&3},
  select(ids){for(const id of selected){states[id]&=3;upload(id)}selected.clear();for(const id of ids){selected.add(id);states[id]|=4;upload(id)}map.triggerRepaint()},
  setRepresentation(id,mode){if(id<1||id>data.structures.length||![0,1,2].includes(mode))throw Error('Invalid structure display');overrides.set(id,mode);states[id]=mode+(selected.has(id)?4:0);upload(id);map.triggerRepaint()},
  get metrics(){return{policy,date,structures:data.structures.length,sourceNodes:data.nodes.length,loadedNodes:loaded.size,pendingNodes:pending.size,pendingTextures:texturePending.size,geometryUploads,geometryBytes,stateUploads,stateBytes,atlasUploads,selectedIds:[...selected],selectedModes:[...selected].map(id=>states?.[id]&3),errors}},
  onRemove(){for(const b of loaded.values()){gl.deleteVertexArray(b.vao);gl.deleteBuffer(b.vbo);gl.deleteBuffer(b.ibo);if(b.wire)gl.deleteBuffer(b.wire);for(const t of b.textures.values())if(t)gl.deleteTexture(t)}gl.deleteTexture(statesTexture);gl.deleteProgram(program)}
 };return layer;
}};
