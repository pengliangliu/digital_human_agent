import * as THREE from 'three';

export type AvatarAction = {
  type: string;
  priority: 'realtime' | 'normal' | 'blocking';
  duration_ms?: number;
  payload: Record<string, unknown>;
};

export class BrowserAvatarRuntime {
  private headGroup: THREE.Group | null = null;
  private bodyGroup: THREE.Group | null = null;
  private currentExpression: string = 'neutral';
  private isSpeaking: boolean = false;
  lastHeadActionTime: number = 0;

  constructor(headGroup: THREE.Group | null, bodyGroup: THREE.Group | null) {
    this.headGroup = headGroup;
    this.bodyGroup = bodyGroup;
  }

  apply(action: AvatarAction) {
    switch (action.type) {
      case 'look_at':
        this.lookAt(action.payload);
        this.lastHeadActionTime = performance.now();
        break;
      case 'head_pose':
        this.setHeadPose(action.payload);
        this.lastHeadActionTime = performance.now();
        break;
      case 'gesture':
        this.playGesture(action.payload);
        break;
      case 'expression':
        this.setExpression(action.payload);
        break;
      case 'speech_start':
        this.isSpeaking = true;
        break;
      case 'speech_end':
        this.isSpeaking = false;
        break;
      default:
        console.log('[avatar] unhandled action:', action.type, action.payload);
    }
  }

  private lookAt(payload: Record<string, unknown>) {
    if (!this.headGroup) return;
    const yaw = ((payload.yaw as number) || 0) * (Math.PI / 180) * 1.5;
    const pitch = ((payload.pitch as number) || 0) * (Math.PI / 180) * 1.5;
    this.headGroup.rotation.y = yaw;
    this.headGroup.rotation.x = -pitch;
  }

  private setHeadPose(payload: Record<string, unknown>) {
    if (!this.headGroup) return;
    const yaw = ((payload.yaw as number) || 0) * (Math.PI / 180) * 1.5;
    const pitch = ((payload.pitch as number) || 0) * (Math.PI / 180) * 1.5;
    const roll = ((payload.roll as number) || 0) * (Math.PI / 180);
    this.headGroup.rotation.set(-pitch, yaw, roll);
  }

  private playGesture(payload: Record<string, unknown>) {
    const name = payload.name as string;
    if (name === 'nod' && this.headGroup) {
      // Simple nod animation: oscillate pitch
      const startPitch = this.headGroup.rotation.x;
      const intensity = (payload.intensity as number) || 0.5;
      const amplitude = 0.15 * intensity;
      const duration = 800;
      const startTime = performance.now();
      const animate = () => {
        const elapsed = performance.now() - startTime;
        const t = Math.min(elapsed / duration, 1);
        const bounce = Math.sin(t * Math.PI * 2) * amplitude * (1 - t);
        if (this.headGroup) {
          this.headGroup.rotation.x = startPitch - bounce;
        }
        if (t < 1) requestAnimationFrame(animate);
      };
      requestAnimationFrame(animate);
    }
    console.log('[avatar] gesture:', name, payload);
  }

  private setExpression(payload: Record<string, unknown>) {
    this.currentExpression = (payload.name as string) || 'neutral';
    console.log('[avatar] expression:', this.currentExpression);
  }

  get speaking(): boolean {
    return this.isSpeaking;
  }

  get expression(): string {
    return this.currentExpression;
  }
}
