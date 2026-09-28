const stage = document.querySelector('.scene');
const range = document.querySelector('#assembly');
const output = document.querySelector('#assembly-state');
const fallbackCubes = [...document.querySelectorAll('[data-cube]')];
const motion = matchMedia('(prefers-reduced-motion: reduce)');
let updateScene = null;

function updateControl() {
  const amount = Number(range.value) / 100;
  range.style.setProperty('--range-value', `${range.value}%`);
  output.textContent = amount > .96 ? 'Together' : amount < .04 ? 'Room to play' : 'Finding its shape';
  range.setAttribute('aria-valuetext', `${range.value} percent assembled`);
  for (const [i, cube] of fallbackCubes.entries()) {
    const col = Number(cube.dataset.col), row = Number(cube.dataset.row);
    const spread = 1 - amount;
    cube.setAttribute('transform', `translate(${((col - 2) * 23 + (i % 3 - 1) * 10) * spread} ${((row - 3) * 13) * spread})`);
  }
  updateScene?.(amount);
}
range.addEventListener('input', updateControl);
updateControl();

import('../../vendor/three/three.module.js').then(THREE => {
  let renderer;
  try { renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' }); }
  catch { return; }
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.65));
  renderer.setClearColor(0xffffff, 0);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.1;
  renderer.domElement.setAttribute('aria-hidden', 'true');
  stage.append(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(33, 1, .1, 100);
  camera.position.set(8.3, 4.0, 17.8);
  camera.lookAt(0, -.15, 0);
  scene.add(new THREE.HemisphereLight(0xeef4ff, 0xa0b4dc, 2.4));
  const key = new THREE.DirectionalLight(0xffffff, 4.2);
  key.position.set(-3, 9, 7);
  key.castShadow = true;
  key.shadow.mapSize.set(1024, 1024);
  key.shadow.camera.left = -10; key.shadow.camera.right = 10;
  key.shadow.camera.top = 10; key.shadow.camera.bottom = -10;
  key.shadow.bias = -.0005;
  key.shadow.normalBias = .035;
  scene.add(key);
  const fill = new THREE.DirectionalLight(0xc3d3ff, 2.5);
  fill.position.set(7, 2, -5); scene.add(fill);
  const root = new THREE.Group(); scene.add(root);
  const geometry = new THREE.BoxGeometry(.92, .92, .92);
  const material = new THREE.MeshStandardMaterial({ color: 0x1557ff, roughness: .25, metalness: .06 });
  const matrix = ['11110','10001','10001','11110','10000','10000','10000'];
  const locations = [];
  matrix.forEach((row,y) => [...row].forEach((value,x) => {
    if (value === '1') locations.push(new THREE.Vector3((x - 2) * 1.16, (3 - y) * 1.16, 0));
  }));
  const cubes = new THREE.InstancedMesh(geometry, material, locations.length);
  cubes.castShadow = true; cubes.receiveShadow = true;
  root.add(cubes);
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(35,35), new THREE.ShadowMaterial({ color: 0x5b75ad, opacity: .11 }));
  floor.rotation.x = -Math.PI / 2; floor.position.y = -4.25; floor.receiveShadow = true; scene.add(floor);
  const dummy = new THREE.Object3D();
  let amount = Number(range.value) / 100, targetAmount = amount;
  const targetPointer = new THREE.Vector2(), pointer = new THREE.Vector2();
  let frame = 0, visible = true, disposed = false;
  const isActive = () => visible && !document.hidden && !disposed;
  function requestRender() { if (!frame && isActive()) frame = requestAnimationFrame(render); }
  function setCubes() {
    const spread = 1 - amount;
    locations.forEach((position, i) => {
      dummy.position.copy(position);
      dummy.position.x += (position.x * .55 + Math.sin(i * 2.7) * 1.05) * spread;
      dummy.position.y += (position.y * .19 + Math.cos(i * 3.3) * .65) * spread;
      dummy.position.z = Math.sin(i * 1.63) * 4.2 * spread;
      dummy.rotation.set(Math.sin(i * 1.6) * spread * .6, Math.cos(i * 2.3) * spread * .7, Math.sin(i * 3.1) * spread * .45);
      dummy.updateMatrix(); cubes.setMatrixAt(i, dummy.matrix);
    });
    cubes.instanceMatrix.needsUpdate = true;
  }
  function render() {
    frame = 0;
    if (!isActive()) return;
    amount = motion.matches ? targetAmount : THREE.MathUtils.lerp(amount, targetAmount, .11);
    if (Math.abs(targetAmount - amount) < .0005) amount = targetAmount;
    pointer.lerp(targetPointer, motion.matches ? 1 : .085);
    root.rotation.set(pointer.y * .06, -.12 + pointer.x * .1, -.055);
    setCubes(); renderer.render(scene, camera);
    stage.classList.add('webgl-ready');
    if (Math.abs(targetAmount - amount) > .0005 || pointer.distanceTo(targetPointer) > .001) requestRender();
  }
  function resize() {
    const { width, height } = stage.getBoundingClientRect();
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.position.set(8.3, 4.0, width / height < .85 ? 21 : 17.8);
    camera.lookAt(0, -.15, 0); camera.updateProjectionMatrix(); requestRender();
  }
  updateScene = value => { targetAmount = value; requestRender(); };
  stage.addEventListener('pointermove', event => {
    if (motion.matches || event.pointerType === 'touch') return;
    const rect = stage.getBoundingClientRect();
    targetPointer.set((event.clientX - rect.left) / rect.width * 2 - 1, (event.clientY - rect.top) / rect.height * 2 - 1);
    requestRender();
  }, { passive: true });
  stage.addEventListener('pointerleave', () => { targetPointer.set(0,0); requestRender(); });
  motion.addEventListener('change', () => { targetPointer.set(0,0); requestRender(); });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { cancelAnimationFrame(frame); frame = 0; } else requestRender();
  });
  new IntersectionObserver(entries => {
    visible = entries[0].isIntersecting;
    if (visible) requestRender(); else { cancelAnimationFrame(frame); frame = 0; }
  }).observe(stage);
  new ResizeObserver(resize).observe(stage);
  renderer.domElement.addEventListener('webglcontextlost', event => {
    event.preventDefault(); disposed = true; cancelAnimationFrame(frame); stage.classList.remove('webgl-ready');
  });
  window.addEventListener('pagehide', () => { cancelAnimationFrame(frame); frame = 0; });
  window.addEventListener('pageshow', () => requestRender());
  resize();
}).catch(() => { /* The inline illustration and range control remain fully usable. */ });
