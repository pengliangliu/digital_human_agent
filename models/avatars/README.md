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
