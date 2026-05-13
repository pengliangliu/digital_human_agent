import * as THREE from 'three';
import type { AvatarModelInfo } from './avatarModels';

export async function loadAvatarModel(model: AvatarModelInfo): Promise<THREE.Group> {
  const url = encodeURI(model.model_url);
  let object: THREE.Object3D;

  if (model.format === 'glb' || model.format === 'gltf') {
    const { GLTFLoader } = await import('three/examples/jsm/loaders/GLTFLoader.js');
    const gltf = await new GLTFLoader().loadAsync(url);
    object = gltf.scene;
  } else if (model.format === 'obj') {
    const { OBJLoader } = await import('three/examples/jsm/loaders/OBJLoader.js');
    const loader = new OBJLoader();
    if (model.material_url) {
      const { MTLLoader } = await import('three/examples/jsm/loaders/MTLLoader.js');
      const materials = await new MTLLoader().loadAsync(encodeURI(model.material_url));
      materials.preload();
      loader.setMaterials(materials);
    }
    object = await loader.loadAsync(url);
  } else if (model.format === 'fbx') {
    const { FBXLoader } = await import('three/examples/jsm/loaders/FBXLoader.js');
    object = await new FBXLoader().loadAsync(url);
  } else {
    throw new Error(`Unsupported avatar model format: ${model.format}`);
  }

  const group = new THREE.Group();
  group.name = model.id;
  group.add(object);
  normalizeAvatarObject(group, model);
  return group;
}

function normalizeAvatarObject(group: THREE.Group, model: AvatarModelInfo) {
  group.traverse((child) => {
    const mesh = child as THREE.Mesh;
    if (mesh.isMesh) {
      mesh.castShadow = true;
      mesh.receiveShadow = true;
    }
  });

  const initialBox = new THREE.Box3().setFromObject(group);
  const size = new THREE.Vector3();
  initialBox.getSize(size);
  const fitScale = size.y > 0 ? 1.75 / size.y : 1;
  group.scale.setScalar(fitScale * (model.scale || 1));

  const scaledBox = new THREE.Box3().setFromObject(group);
  const center = new THREE.Vector3();
  scaledBox.getCenter(center);
  group.position.set(-center.x, -scaledBox.min.y, -center.z);

  group.position.x += model.position?.[0] ?? 0;
  group.position.y += model.position?.[1] ?? 0;
  group.position.z += model.position?.[2] ?? 0;
  group.rotation.set(
    THREE.MathUtils.degToRad(model.rotation?.[0] ?? 0),
    THREE.MathUtils.degToRad(model.rotation?.[1] ?? 0),
    THREE.MathUtils.degToRad(model.rotation?.[2] ?? 0),
  );
}
