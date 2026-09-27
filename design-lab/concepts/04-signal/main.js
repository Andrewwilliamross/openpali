const field = document.querySelector('.signal-field');
const toggle = document.querySelector('.field-toggle');
const toggleLabel = document.querySelector('#field-state');
const motion = matchMedia('(prefers-reduced-motion: reduce)');
let focused = true, updateScene = null;
toggle.addEventListener('click', () => {
  focused = !focused;
  toggle.setAttribute('aria-pressed', String(focused));
  toggleLabel.textContent = focused ? 'Together' : 'Scattered';
  document.body.classList.toggle('is-scattered', !focused);
  updateScene?.();
});

import('../../vendor/three/three.module.js').then(THREE => {
  let renderer;
  try { renderer = new THREE.WebGLRenderer({ antialias: false, powerPreference: 'low-power' }); }
  catch { return; }
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.5));
  renderer.setClearColor(0x1557ff, 1);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.domElement.setAttribute('aria-hidden', 'true');
  field.append(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-1,1,1,-1,.1,10);
  camera.position.z = 5;
  const geometry = new THREE.PlaneGeometry(1,1);
  const material = new THREE.MeshBasicMaterial({ color: 0xffffff });
  const background = new THREE.Color(0x1557ff), white = new THREE.Color(0xffffff), tint = new THREE.Color();
  const dummy = new THREE.Object3D();
  const mark = ['11110','10001','10001','11110','10000','10000','10000'];
  let mesh = null, cells = [], width = 1, height = 1;
  let focus = 1, targetFocus = 1, frame = 0, visible = true, disposed = false;
  let pointer = { x: -2000, y: -2000 }, pointerCurrent = { x: -2000, y: -2000 };
  let pointerStrength = 0, targetStrength = 0;
  const isActive = () => visible && !document.hidden && !disposed;
  function requestRender() { if (!frame && isActive()) frame = requestAnimationFrame(render); }
  function buildField() {
    const rect = field.getBoundingClientRect(); width = rect.width; height = rect.height;
    if (!width || !height) return;
    renderer.setSize(width,height,false);
    camera.left = -width/2; camera.right = width/2; camera.top = height/2; camera.bottom = -height/2;
    camera.updateProjectionMatrix();
    const mobile = width < 681;
    // Fixed physical square sizes keep the field crisp at every viewport.
    const step = mobile ? 18 : Math.max(26, Math.min(37, width / 44));
    const cols = Math.ceil(width / step), rows = Math.ceil(height / step);
    const scale = mobile ? 2 : Math.max(2, Math.min(3, Math.floor(height / step / 9)));
    const markX = mobile ? Math.round(cols / 2 - 2.5 * scale) : Math.round(cols * .755 - 2.5 * scale);
    const markY = mobile ? Math.round(height * .60 / step) : Math.round(rows / 2 - 3.5 * scale);
    cells = [];
    for (let row=0; row<rows; row++) for (let col=0; col<cols; col++) {
      const x = col * step + step/2, y = row * step + step/2;
      const markCol = Math.floor((col - markX) / scale), markRow = Math.floor((row - markY) / scale);
      const isMark = markCol >= 0 && markCol < 5 && markRow >= 0 && markRow < 7 && mark[markRow][markCol] === '1';
      const hash = ((col * 19 + row * 37 + col * row * 7) % 43) / 43;
      // Keep the typography area quiet; this is artwork, not a plotted dataset.
      const textMask = mobile ? (y < height * .54 ? .09 : 1) : THREE.MathUtils.smoothstep(x / width, .38, .67);
      const baseline = (.025 + hash * .1) * textMask;
      cells.push({ x, y, step, isMark, hash, baseline, textMask, markSize: step * .77 });
    }
    if (mesh) { scene.remove(mesh); mesh.dispose(); }
    mesh = new THREE.InstancedMesh(geometry, material, cells.length);
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage); mesh.frustumCulled = false;
    scene.add(mesh); requestRender();
  }
  function render() {
    frame = 0;
    if (!isActive() || !mesh) return;
    const damping = motion.matches ? 1 : .09;
    focus = THREE.MathUtils.lerp(focus,targetFocus,damping);
    pointerStrength = THREE.MathUtils.lerp(pointerStrength,targetStrength,damping);
    pointerCurrent.x = THREE.MathUtils.lerp(pointerCurrent.x,pointer.x,damping);
    pointerCurrent.y = THREE.MathUtils.lerp(pointerCurrent.y,pointer.y,damping);
    if (Math.abs(focus-targetFocus)<.0005) focus=targetFocus;
    if (Math.abs(pointerStrength-targetStrength)<.0005) pointerStrength=targetStrength;
    const reach = width < 681 ? 120 : 210;
    cells.forEach((cell,i) => {
      const distance = Math.hypot(cell.x-pointerCurrent.x,cell.y-pointerCurrent.y);
      const glow = Math.max(0,1-distance/reach) ** 2 * pointerStrength * cell.textMask;
      const signal = cell.isMark ? focus : 0;
      const scatter = (1-focus) * (cell.hash > .67 ? .36 : .07) * cell.textMask;
      const brightness = Math.min(1, cell.baseline + signal * .96 + glow * .62 + scatter);
      const scatteredSize = cell.step * (.095 + cell.hash * .19) + scatter * cell.step * .42;
      const size = THREE.MathUtils.lerp(scatteredSize, cell.markSize, signal) + glow * cell.step * .15;
      dummy.position.set(cell.x-width/2,height/2-cell.y,0);
      dummy.rotation.set(0,0,0); dummy.scale.set(size,size,1); dummy.updateMatrix(); mesh.setMatrixAt(i,dummy.matrix);
      tint.copy(background).lerp(white,brightness); mesh.setColorAt(i,tint);
    });
    mesh.instanceMatrix.needsUpdate=true; mesh.instanceColor.needsUpdate=true;
    renderer.render(scene,camera); field.classList.add('webgl-ready');
    if (Math.abs(focus-targetFocus)>.0005 || Math.abs(pointerStrength-targetStrength)>.0005 || Math.abs(pointerCurrent.x-pointer.x)>.1 || Math.abs(pointerCurrent.y-pointer.y)>.1) requestRender();
  }
  updateScene = () => { targetFocus=focused ? 1 : 0; requestRender(); };
  // Hover only: touching the field never blocks page scrolling.
  document.querySelector('.page').addEventListener('pointermove', event => {
    if (motion.matches || event.pointerType==='touch') return;
    const rect=field.getBoundingClientRect();
    pointer.x=event.clientX-rect.left; pointer.y=event.clientY-rect.top; targetStrength=1; requestRender();
  },{passive:true});
  document.querySelector('.page').addEventListener('pointerleave',()=>{targetStrength=0;requestRender();});
  motion.addEventListener('change',()=>{targetStrength=0;requestRender();});
  document.addEventListener('visibilitychange',()=>{
    if(document.hidden){cancelAnimationFrame(frame);frame=0;}else requestRender();
  });
  new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;if(visible)requestRender();else{cancelAnimationFrame(frame);frame=0;}}).observe(field);
  new ResizeObserver(buildField).observe(field);
  renderer.domElement.addEventListener('webglcontextlost',event=>{event.preventDefault();disposed=true;cancelAnimationFrame(frame);field.classList.remove('webgl-ready');});
  window.addEventListener('pagehide',()=>{cancelAnimationFrame(frame);frame=0;});
  window.addEventListener('pageshow',()=>requestRender());
  buildField();
}).catch(()=>{ /* The blue poster and inline P remain visible without WebGL. */ });
