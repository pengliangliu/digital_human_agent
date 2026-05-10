import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { BrowserAvatarRuntime, AvatarAction } from './avatarActions';

type Props = {
  onAvatarReady: (runtime: BrowserAvatarRuntime) => void;
  actions: AvatarAction[];
};

export default function AvatarScene({ onAvatarReady, actions }: Props) {
  const mountRef = useRef<HTMLDivElement>(null);
  const runtimeRef = useRef<BrowserAvatarRuntime | null>(null);

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    // Scene setup
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x1a1a2e);
    scene.fog = new THREE.Fog(0x1a1a2e, 2, 15);

    const camera = new THREE.PerspectiveCamera(50, container.clientWidth / container.clientHeight, 0.1, 50);
    camera.position.set(0, 1.6, 3.5);
    camera.lookAt(0, 1.35, 0);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    container.appendChild(renderer.domElement);

    // Lighting
    scene.add(new THREE.AmbientLight(0x404060, 1.5));
    const keyLight = new THREE.DirectionalLight(0xffffff, 2);
    keyLight.position.set(2, 3, 3);
    scene.add(keyLight);
    const rimLight = new THREE.DirectionalLight(0x8888ff, 1);
    rimLight.position.set(-2, 1, -1);
    scene.add(rimLight);

    // Floor
    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(10, 10),
      new THREE.MeshStandardMaterial({ color: 0x2a2a3e, roughness: 0.8 })
    );
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    scene.add(floor);

    // ---- Rotatable container for the whole model ----
    const modelRoot = new THREE.Group();
    scene.add(modelRoot);

    // Digital Human placeholder
    const bodyGroup = new THREE.Group();
    const headGroup = new THREE.Group();

    // Body
    const bodyGeo = new THREE.CylinderGeometry(0.3, 0.35, 1.2, 32);
    const bodyMat = new THREE.MeshStandardMaterial({ color: 0x6677cc, roughness: 0.4, metalness: 0.1 });
    const body = new THREE.Mesh(bodyGeo, bodyMat);
    body.position.y = 0.6;
    body.castShadow = true;
    bodyGroup.add(body);

    // Shoulders
    const shoulderGeo = new THREE.SphereGeometry(0.22, 16, 16);
    const shoulderMat = new THREE.MeshStandardMaterial({ color: 0x5566bb, roughness: 0.4 });
    const leftShoulder = new THREE.Mesh(shoulderGeo, shoulderMat);
    leftShoulder.position.set(0.35, 1.15, 0);
    const rightShoulder = new THREE.Mesh(shoulderGeo, shoulderMat);
    rightShoulder.position.set(-0.35, 1.15, 0);
    bodyGroup.add(leftShoulder, rightShoulder);

    // Head
    const headGeo = new THREE.SphereGeometry(0.18, 32, 32);
    const headMat = new THREE.MeshStandardMaterial({ color: 0xffddbb, roughness: 0.5 });
    const head = new THREE.Mesh(headGeo, headMat);
    head.position.y = 1.45;
    head.castShadow = true;
    headGroup.add(head);

    // Eyes — placed on +z side (toward camera)
    const eyeGeo = new THREE.SphereGeometry(0.03, 8, 8);
    const eyeMat = new THREE.MeshBasicMaterial({ color: 0x111111 });
    const leftEye = new THREE.Mesh(eyeGeo, eyeMat);
    leftEye.position.set(-0.06, 1.48, 0.16);
    const rightEye = new THREE.Mesh(eyeGeo, eyeMat);
    rightEye.position.set(0.06, 1.48, 0.16);
    headGroup.add(leftEye, rightEye);

    // Mouth
    const mouthGeo = new THREE.TorusGeometry(0.03, 0.008, 8, 8);
    const mouthMat = new THREE.MeshStandardMaterial({ color: 0xcc6666 });
    const mouth = new THREE.Mesh(mouthGeo, mouthMat);
    mouth.position.set(0, 1.42, 0.15);
    mouth.rotation.x = -0.2;
    headGroup.add(mouth);

    // Hair
    const hairGeo = new THREE.SphereGeometry(0.2, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2);
    const hairMat = new THREE.MeshStandardMaterial({ color: 0x222222, roughness: 0.6 });
    const hair = new THREE.Mesh(hairGeo, hairMat);
    hair.position.y = 1.5;
    headGroup.add(hair);

    // Nose — cone on +z face, pointing toward camera
    const noseGeo = new THREE.ConeGeometry(0.025, 0.08, 8, 8);
    const noseMat = new THREE.MeshStandardMaterial({ color: 0xff9977, roughness: 0.3 });
    const nose = new THREE.Mesh(noseGeo, noseMat);
    nose.position.set(0, 1.45, 0.2);
    nose.rotation.x = -Math.PI / 2;  // cone tip (+y) → +z (toward camera)
    headGroup.add(nose);

    // Direction arrow on top
    const arrowGroup = new THREE.Group();
    const pillarGeo = new THREE.CylinderGeometry(0.012, 0.012, 0.15, 8);
    const pillarMat = new THREE.MeshStandardMaterial({ color: 0xff4444, emissive: 0xcc2222, emissiveIntensity: 0.6 });
    const pillar = new THREE.Mesh(pillarGeo, pillarMat);
    pillar.position.y = 0.075;
    arrowGroup.add(pillar);
    const tipGeo = new THREE.ConeGeometry(0.03, 0.07, 8, 8);
    const tip = new THREE.Mesh(tipGeo, pillarMat);
    tip.position.y = 0.16;
    arrowGroup.add(tip);
    arrowGroup.position.set(0, 1.72, 0.06);
    arrowGroup.rotation.x = 0.15;
    headGroup.add(arrowGroup);

    headGroup.position.y = 0;
    bodyGroup.add(headGroup);
    bodyGroup.position.set(0, 0.5, 0);
    modelRoot.add(bodyGroup);

    const runtime = new BrowserAvatarRuntime(headGroup, null);
    runtimeRef.current = runtime;
    onAvatarReady(runtime);

    // ---- Mouse drag to rotate model ----
    let isDragging = false;
    let prevMouse = { x: 0, y: 0 };
    const targetRotY = modelRoot.rotation.y;

    const onMouseDown = (e: MouseEvent) => {
      isDragging = true;
      prevMouse = { x: e.clientX, y: e.clientY };
    };
    const onMouseMove = (e: MouseEvent) => {
      if (!isDragging) return;
      const dx = e.clientX - prevMouse.x;
      modelRoot.rotation.y += dx * 0.005;
      prevMouse = { x: e.clientX, y: e.clientY };
    };
    const onMouseUp = () => { isDragging = false; };

    // Touch support
    const onTouchStart = (e: TouchEvent) => {
      if (e.touches.length === 1) {
        isDragging = true;
        prevMouse = { x: e.touches[0].clientX, y: e.touches[0].clientY };
      }
    };
    const onTouchMove = (e: TouchEvent) => {
      if (!isDragging || e.touches.length !== 1) return;
      const dx = e.touches[0].clientX - prevMouse.x;
      modelRoot.rotation.y += dx * 0.005;
      prevMouse = { x: e.touches[0].clientX, y: e.touches[0].clientY };
    };
    const onTouchEnd = () => { isDragging = false; };

    container.addEventListener('mousedown', onMouseDown);
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    container.addEventListener('touchstart', onTouchStart, { passive: true });
    window.addEventListener('touchmove', onTouchMove);
    window.addEventListener('touchend', onTouchEnd);

    // Animation loop
    let animId: number;
    const clock = new THREE.Clock();

    function animate() {
      animId = requestAnimationFrame(animate);
      clock.getDelta();

      // Idle breathing
      body.scale.y = 1 + Math.sin(performance.now() * 0.002) * 0.01;
      body.scale.x = 1 - Math.sin(performance.now() * 0.002) * 0.005;

      // Mouth
      if (runtime.speaking) {
        const s = 1 + Math.abs(Math.sin(performance.now() * 0.01)) * 0.4;
        mouth.scale.set(s, s, 1);
      } else {
        mouth.scale.lerp(new THREE.Vector3(1, 1, 1), 0.1);
      }

      // Idle head — skip if recent look_at
      const sinceAction = performance.now() - runtime.lastHeadActionTime;
      if (!runtime.speaking && sinceAction > 2000) {
        const t = performance.now() * 0.001;
        headGroup.rotation.y += (Math.sin(t * 0.7) * 0.01 - headGroup.rotation.y) * 0.02;
        headGroup.rotation.x += (Math.sin(t * 0.5 + 1) * 0.005 - headGroup.rotation.x) * 0.02;
      }

      renderer.render(scene, camera);
    }
    requestAnimationFrame(animate);

    const onResize = () => {
      camera.aspect = container.clientWidth / container.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(container.clientWidth, container.clientHeight);
    };
    window.addEventListener('resize', onResize);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', onResize);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      window.removeEventListener('touchmove', onTouchMove);
      window.removeEventListener('touchend', onTouchEnd);
      renderer.dispose();
      container.removeChild(renderer.domElement);
    };
  }, []);

  useEffect(() => {
    if (!runtimeRef.current || !actions.length) return;
    const latest = actions[actions.length - 1];
    runtimeRef.current.apply(latest);
  }, [actions]);

  return <div ref={mountRef} style={{ width: '100%', height: '100%', cursor: 'grab' }} />;
}
