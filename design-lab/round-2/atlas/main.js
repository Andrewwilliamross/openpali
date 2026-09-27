const stage = document.querySelector('.atlas-scene');
const slider = document.querySelector('#fold');
const label = document.querySelector('#fold-state');
const noteIndex = document.querySelector('#note-index');
const noteCopy = document.querySelector('#note-copy');
const motion = matchMedia('(prefers-reduced-motion: reduce)');
const notes = [
  ['The source', 'Event date.', 'When a source says something happened.'],
  ['The observation', 'Observed date.', 'When a source was first collected.'],
  ['The release', 'Published date.', 'When a snapshot was shared.'],
];
let setSceneAmount = null;
function updateControl() {
  const amount = Number(slider.value) / 100;
  const index = amount < .33 ? 0 : amount < .76 ? 1 : 2;
  label.textContent = notes[index][0];
  noteIndex.textContent = `0${index + 1}`;
  noteCopy.replaceChildren();
  const strong = document.createElement('strong'); strong.textContent = notes[index][1];
  noteCopy.append(strong, ` ${notes[index][2]}`);
  slider.style.setProperty('--position', `${slider.value}%`);
  slider.setAttribute('aria-valuetext', `${slider.value} percent unfolded. ${notes[index][0]}.`);
  document.querySelector('.fallback').style.transform = `perspective(1000px) rotateY(${(1-amount)*-8}deg) scale(${.96+amount*.04})`;
  setSceneAmount?.(amount);
}
slider.addEventListener('input', updateControl);
updateControl();

import('../../vendor/three/three.module.js').then(async THREE => {
  let renderer;
  try { renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: 'low-power' }); }
  catch { return; }
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.5));
  renderer.setClearColor(0xf8f9f5, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.domElement.setAttribute('aria-hidden', 'true');
  stage.append(renderer.domElement);
  await document.fonts.ready;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(29, 1, .1, 100);
  const root = new THREE.Group(); scene.add(root);
  scene.add(new THREE.HemisphereLight(0xffffff,0xbdc8be,2.35));
  const key = new THREE.DirectionalLight(0xffffff,3.0);
  key.position.set(-5,12,7); key.castShadow=true;
  key.shadow.mapSize.set(1024,1024);
  Object.assign(key.shadow.camera,{left:-10,right:10,top:10,bottom:-10,near:.1,far:35});
  key.shadow.bias=-.00035; key.shadow.normalBias=.025;
  scene.add(key);
  const fill = new THREE.DirectionalLight(0xe4edff,.9); fill.position.set(7,5,-6);scene.add(fill);
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(55,55),new THREE.ShadowMaterial({color:0x4b6154,opacity:.12}));
  ground.rotation.x=-Math.PI/2;ground.position.y=-.08;ground.receiveShadow=true;scene.add(ground);

  const W=3.55,H=5.05,BACK=-1.78,FRONT=1.52;
  const blue = new THREE.MeshStandardMaterial({color:0x003de6,roughness:.6,metalness:0});
  const land = new THREE.MeshStandardMaterial({color:0xf6f7ee,roughness:.96,metalness:0,flatShading:false});
  const cut = new THREE.MeshStandardMaterial({color:0xe9ece1,roughness:1});
  const edge = new THREE.MeshStandardMaterial({color:0xe0e5da,roughness:1});
  const contourMaterial=new THREE.LineBasicMaterial({color:0xbdcbbc,transparent:true,opacity:.48});
  const waterLineMaterial=new THREE.LineBasicMaterial({color:0xb6d5ff,transparent:true,opacity:.44});
  function shore(u) {return .25+.28*Math.sin(u*.65)+.18*Math.sin(u*1.38+.8);}
  function elevation(u,z) {
    const distance=shore(u)-z;
    if(distance<0)return .038;
    const ridge=.77+.12*Math.sin(u*.57)+.1*Math.cos(u*1.5+z*.7);
    const g=(x,c,width)=>Math.exp(-(((x-c)/width)**2));
    const canyon=.64*g(u,2.5+.35*(z+1),.34)+.58*g(u,6.15-.27*(z+1),.35)+.59*g(u,8.9+.38*Math.sin(z),.3);
    const within=u-Math.floor(u/W)*W;
    const edgeDistance=Math.min(within,W-within);
    const seam=THREE.MathUtils.smoothstep(edgeDistance,.025,.26);
    return .041+(.089+(1-Math.exp(-distance*1.4))*ridge*(1-Math.min(.83,canyon)))*seam;
  }
  function paperTexture(index) {
    const canvas=document.createElement('canvas');canvas.width=1024;canvas.height=1456;
    const c=canvas.getContext('2d');c.fillStyle='#fcfcf8';c.fillRect(0,0,1024,1456);
    c.strokeStyle='#c2cebf';c.lineWidth=1.2;c.strokeRect(35,36,954,1384);
    c.strokeStyle='#bfcbdc';c.beginPath();c.moveTo(55,1222);c.lineTo(968,1222);c.stroke();
    c.fillStyle='#1557ff';c.font='500 20px "DM Sans", Arial';c.letterSpacing='3px';
    c.fillText('OPENPALI  /  FIELD ATLAS',60,91);
    c.font='500 17px "DM Sans", Arial';c.letterSpacing='1px';c.fillText('ABSTRACT COASTAL STUDY',60,123);
    c.font='500 17px "DM Sans", Arial';c.fillText(`0${index+1}  /  ${['SOURCE','OBSERVATION','RELEASE'][index]}`,61,1278);
    c.fillStyle='#233d3d';c.font='450 55px Fraunces, Georgia';c.letterSpacing='-1px';
    c.fillText(['Event date','Observed date','Published date'][index],60,1350);
    c.fillStyle='#637d76';c.font='400 19px "DM Sans", Arial';c.letterSpacing='0px';
    c.fillText(['As reported in the source','When the source was collected','When the snapshot was shared'][index],62,1389);
    c.strokeStyle='#9fb9b0';c.lineWidth=1;for(let i=0;i<25;i++){const x=55+i*38;c.beginPath();c.moveTo(x,157);c.lineTo(x,157+(i%5===0?14:7));c.stroke();}
    const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;texture.anisotropy=Math.min(renderer.capabilities.getMaxAnisotropy(),4);return texture;
  }
  function edgeWall(points) {
    const positions=[];
    for(let i=0;i<points.length-1;i++){
      const a=points[i],b=points[i+1];
      positions.push(a[0],a[1],a[2],a[0],.038,a[2],b[0],b[1],b[2], b[0],b[1],b[2],a[0],.038,a[2],b[0],.038,b[2]);
    }
    const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));g.computeVertexNormals();
    const mesh=new THREE.Mesh(g,cut);mesh.castShadow=true;mesh.receiveShadow=true;return mesh;
  }
  function terrain(index) {
    const nx=42,nz=48,positions=[],indices=[],grid=[];
    for(let j=0;j<=nz;j++)for(let i=0;i<=nx;i++){
      const x=W*i/nx,u=index*W+x,z=BACK+(shore(u)-BACK)*j/nz,y=elevation(u,z);
      positions.push(x,y,z);grid.push([x,y,z]);
    }
    for(let j=0;j<nz;j++)for(let i=0;i<nx;i++){
      const a=j*(nx+1)+i,b=a+1,c=a+nx+1,d=c+1;
      indices.push(a,c,b,b,c,d);
    }
    const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));geometry.setIndex(indices);geometry.computeVertexNormals();
    const group=new THREE.Group();const mesh=new THREE.Mesh(geometry,land);mesh.castShadow=true;mesh.receiveShadow=true;group.add(mesh);
    group.add(edgeWall(grid.slice(nz*(nx+1))));
    group.add(edgeWall(grid.filter((_,i)=>i%(nx+1)===0).reverse()));
    group.add(edgeWall(grid.filter((_,i)=>i%(nx+1)===nx)));
    group.add(edgeWall(grid.slice(0,nx+1).reverse()));
    // True geometric contour intersections, on a deliberately imagined landform.
    const lines=[];
    for(const height of [.22,.34,.46,.58,.7,.82]) for(let t=0;t<indices.length;t+=3){
      const tri=[grid[indices[t]],grid[indices[t+1]],grid[indices[t+2]]],cross=[];
      for(let e=0;e<3;e++){
        const a=tri[e],b=tri[(e+1)%3];
        if((a[1]<height&&b[1]>=height)||(b[1]<height&&a[1]>=height)){
          const f=(height-a[1])/(b[1]-a[1]);cross.push([a[0]+(b[0]-a[0])*f,height+.012,a[2]+(b[2]-a[2])*f]);
        }
      }
      if(cross.length===2)lines.push(...cross[0],...cross[1]);
    }
    const lineGeometry=new THREE.BufferGeometry();lineGeometry.setAttribute('position',new THREE.Float32BufferAttribute(lines,3));group.add(new THREE.LineSegments(lineGeometry,contourMaterial));
    return group;
  }
  const panels=[];
  for(let index=0;index<3;index++){
    const panel=new THREE.Group();panels.push(panel);
    if(index===0)root.add(panel);else{panels[index-1].add(panel);panel.position.x=W;}
    const base=new THREE.Mesh(new THREE.BoxGeometry(W,.055,H),edge);base.position.set(W/2,-.005,0);base.castShadow=true;base.receiveShadow=true;panel.add(base);
    const face=new THREE.Mesh(new THREE.PlaneGeometry(W-.006,H-.006),new THREE.MeshStandardMaterial({map:paperTexture(index),roughness:.98,side:THREE.DoubleSide}));
    face.rotation.x=-Math.PI/2;face.position.set(W/2,.024,0);face.receiveShadow=true;panel.add(face);
    const waterShape=new THREE.Shape();waterShape.moveTo(0,-FRONT);waterShape.lineTo(W,-FRONT);
    for(let i=44;i>=0;i--){const x=W*i/44;waterShape.lineTo(x,-shore(index*W+x));}
    waterShape.closePath();const water=new THREE.Mesh(new THREE.ShapeGeometry(waterShape),blue);water.rotation.x=-Math.PI/2;water.position.y=.04;water.receiveShadow=true;panel.add(water);
    panel.add(terrain(index));
    const wavePositions=[];
    for(const offset of [.18,.34,.56,.83])for(let i=0;i<52;i++){
      const a=W*i/52,b=W*(i+1)/52,za=shore(index*W+a)+offset,zb=shore(index*W+b)+offset;
      if(za<FRONT-.06&&zb<FRONT-.06)wavePositions.push(a,.046,za,b,.046,zb);
    }
    const waves=new THREE.BufferGeometry();waves.setAttribute('position',new THREE.Float32BufferAttribute(wavePositions,3));panel.add(new THREE.LineSegments(waves,waterLineMaterial));
    // A printed hinge rule is deliberately visible along the fold.
    const hinge=new THREE.Mesh(new THREE.BoxGeometry(.016,.002,H-.25),new THREE.MeshBasicMaterial({color:0x9dada0}));hinge.position.set(.012,.033,0);panel.add(hinge);
  }
  // A blue cloth bookmark: the one soft interruption in the paper's geometry.
  const bookmarkShape=new THREE.Shape();bookmarkShape.moveTo(0,0);bookmarkShape.lineTo(.26,0);bookmarkShape.lineTo(.26,-.82);bookmarkShape.lineTo(.13,-.68);bookmarkShape.lineTo(0,-.82);bookmarkShape.closePath();
  const bookmark=new THREE.Mesh(new THREE.ShapeGeometry(bookmarkShape),new THREE.MeshStandardMaterial({color:0x1557ff,roughness:.98,side:THREE.DoubleSide}));
  bookmark.rotation.x=-Math.PI/2;bookmark.rotation.z=.11;bookmark.position.set(.26,.044,H/2-.25);panels[0].add(bookmark);

  // Fit the actual articulated geometry, not a loose world-axis box.
  const fitObjects=[];
  root.traverse(object=>{if(object.geometry){object.geometry.computeBoundingBox();fitObjects.push(object);}});
  const fittingPoint=new THREE.Vector3();
  function fitCamera(){
    root.updateMatrixWorld(true);camera.updateMatrixWorld(true);
    let tanHalf=0;
    const xMargin=innerWidth<651?1.4:1.055;
    for(const object of fitObjects){const b=object.geometry.boundingBox;
      for(let mask=0;mask<8;mask++){
        fittingPoint.set(mask&1?b.max.x:b.min.x,mask&2?b.max.y:b.min.y,mask&4?b.max.z:b.min.z);
        fittingPoint.applyMatrix4(object.matrixWorld).applyMatrix4(camera.matrixWorldInverse);
        const depth=-fittingPoint.z;
        if(depth>.1)tanHalf=Math.max(tanHalf,Math.abs(fittingPoint.y)*1.075/depth,Math.abs(fittingPoint.x)*xMargin/(depth*camera.aspect));
      }
    }
    camera.fov=THREE.MathUtils.radToDeg(2*Math.atan(tanHalf));camera.updateProjectionMatrix();
  }
  let amount=Number(slider.value)/100,targetAmount=amount,frame=0,visible=true,disposed=false;
  let pointer=0,targetPointer=0;
  let drag=null;
  const isActive=()=>visible&&!document.hidden&&!disposed;
  function requestRender(){if(!frame&&isActive())frame=requestAnimationFrame(render);}
  function pose(){
    const angle=THREE.MathUtils.degToRad(76-amount*71);
    panels[1].rotation.z=angle;panels[2].rotation.z=-angle*2;
    root.position.x=-(W+2*W*Math.cos(angle))/2;
    root.position.y=.17;
    root.rotation.y=-.14+pointer*.028;
    fitCamera();
  }
  function render(){frame=0;if(!isActive())return;
    amount=motion.matches?targetAmount:THREE.MathUtils.lerp(amount,targetAmount,.13);
    pointer=motion.matches?0:THREE.MathUtils.lerp(pointer,targetPointer,.09);
    if(Math.abs(amount-targetAmount)<.0004)amount=targetAmount;
    if(Math.abs(pointer-targetPointer)<.001)pointer=targetPointer;
    pose();renderer.render(scene,camera);stage.classList.add('webgl-ready');
    if(Math.abs(amount-targetAmount)>.0004||Math.abs(pointer-targetPointer)>.001)requestRender();
  }
  function resize(){const {width,height}=stage.getBoundingClientRect();if(!width||!height)return;
    renderer.setSize(width,height,false);camera.aspect=width/height;
    const mobile=innerWidth<651;
    camera.position.set(mobile?10:9.1,mobile?14.7:13.2,mobile?15.7:14.4);
    camera.fov=mobile?28.5:19.5;camera.lookAt(0,0,0);camera.updateProjectionMatrix();requestRender();
  }
  setSceneAmount=value=>{targetAmount=value;requestRender();};
  stage.style.cursor='grab';
  stage.addEventListener('pointerdown',event=>{
    if(event.button!==0)return;
    drag={id:event.pointerId,startX:event.clientX,value:Number(slider.value)};
    stage.setPointerCapture(event.pointerId);stage.style.cursor='grabbing';
  });
  stage.addEventListener('pointermove',event=>{
    const rect=stage.getBoundingClientRect();
    if(drag?.id===event.pointerId){
      slider.value=String(Math.round(THREE.MathUtils.clamp(drag.value+(event.clientX-drag.startX)/rect.width*180,0,100)));updateControl();
    }else if(!motion.matches&&event.pointerType!=='touch'){
      targetPointer=(event.clientX-rect.left)/rect.width*2-1;requestRender();
    }
  },{passive:true});
  const endDrag=()=>{drag=null;stage.style.cursor='grab';};
  stage.addEventListener('pointerup',endDrag);stage.addEventListener('pointercancel',endDrag);
  stage.addEventListener('pointerleave',()=>{if(!drag){targetPointer=0;requestRender();}});
  motion.addEventListener('change',()=>{targetPointer=0;requestRender();});
  new ResizeObserver(resize).observe(stage);
  new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;if(visible)requestRender();else{cancelAnimationFrame(frame);frame=0;}}).observe(stage);
  document.addEventListener('visibilitychange',()=>{if(document.hidden){cancelAnimationFrame(frame);frame=0;}else requestRender();});
  renderer.domElement.addEventListener('webglcontextlost',event=>{event.preventDefault();disposed=true;cancelAnimationFrame(frame);stage.classList.remove('webgl-ready');});
  window.addEventListener('pagehide',()=>{cancelAnimationFrame(frame);frame=0;});window.addEventListener('pageshow',requestRender);
  resize();
}).catch(()=>{ /* The illustrated atlas, native control, and GitHub link stay present. */ });
