# 自建三维人体模型接入说明

把自建人体模型按目录放到这里：

```text
models/avatars/
└── demo-human/
    ├── body.obj
    ├── body.mtl
    ├── texture.png
    └── avatar.json
```

当前前端支持加载：

- `.obj`
- `.glb`
- `.gltf`
- `.fbx`

`avatar.json` 是可选文件，用于覆盖显示名、默认模型文件和初始变换：

```json
{
  "name": "Demo Human",
  "model_file": "body.obj",
  "material_file": "body.mtl",
  "scale": 1.0,
  "position": [0, 0, 0],
  "rotation": [0, 0, 0],
  "head_node": "",
  "notes": "自建人体模型示例"
}
```

如果没有 `avatar.json`，系统会自动扫描目录内第一个支持的模型文件。

启动后端后，可通过接口查看已发现的模型：

```text
GET http://localhost:8000/api/avatars
```

前端会自动读取该接口，并在控制区显示模型选择下拉框。没有可用模型时，会回退到内置占位数字人。

## 真实数字人驱动接口预留

大模型不会直接绑定某个具体 runtime。它会输出语义动作，后端统一转换为 `AvatarAction`，再通过 `avatar.adapter: http` 转发到你的真实数字人服务：

```text
POST /avatar/action
```

请求体使用统一 envelope：

```json
{
  "session_id": "session-a",
  "type": "morph_target",
  "priority": "realtime",
  "duration_ms": 80,
  "payload": {
    "name": "mouthSmile_L",
    "weight": 0.5
  }
}
```

当前预留的真实数字人动作类型：

- `bone_pose`：骨骼姿态，`payload.bones` 放骨骼名、旋转、位移、缩放和权重。
- `morph_target`：表情 BlendShape / MorphTarget，`payload.name` 和 `payload.weight` 对应你的模型形变名和权重。
- `viseme`：口型形变，`payload.name` 是口型/音素标识，`payload.weight` 是权重。
- `animation_clip`：动画片段，`payload.name` 是动画名，可带 `loop`、`speed`、`fade_ms`。
- `motion_sequence`：组合动作，`payload.steps` 按顺序描述多个动作。

示例：

```json
{
  "reply_text": "好的，我给你展示一下。",
  "emotion": "friendly",
  "intent": "chat",
  "actions": [
    {"type": "animation_clip", "name": "wave", "loop": false, "fade_ms": 150},
    {"type": "morph_target", "name": "mouthSmile_L", "weight": 0.6},
    {"type": "bone_pose", "priority": "realtime", "bones": [{"name": "Head", "rotation": [0, 10, 0], "weight": 0.8}]}
  ],
  "tool_calls": [],
  "memory_updates": {}
}
```

接入真实 runtime 时，只需要让你的服务实现 `/avatar/action`，并把这些标准动作映射到实际骨骼、BlendShape、口型或动画系统。
