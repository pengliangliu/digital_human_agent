export type AvatarModelInfo = {
  id: string;
  name: string;
  format: 'glb' | 'gltf' | 'obj' | 'fbx';
  model_path: string;
  model_url: string;
  material_path?: string;
  material_url?: string;
  scale: number;
  position: [number, number, number];
  rotation: [number, number, number];
  head_node?: string;
  notes?: string;
};

type AvatarModelsResponse = {
  items: AvatarModelInfo[];
  supported_formats: string[];
};

export async function fetchAvatarModels(): Promise<AvatarModelInfo[]> {
  const response = await fetch('/api/avatars');
  if (!response.ok) {
    throw new Error(`Failed to load avatar models: ${response.status}`);
  }

  const data = (await response.json()) as AvatarModelsResponse;
  return data.items;
}
