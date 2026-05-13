import json

from app.avatar_models import discover_avatar_models


def test_discovers_obj_avatar_model(tmp_path):
    avatar_dir = tmp_path / "avatars" / "demo-human"
    avatar_dir.mkdir(parents=True)
    (avatar_dir / "body.obj").write_text("o Body\nv 0 0 0\n", encoding="utf-8")
    (avatar_dir / "body.mtl").write_text("newmtl Skin\n", encoding="utf-8")

    models = discover_avatar_models(tmp_path / "avatars")

    assert len(models) == 1
    assert models[0]["id"] == "demo-human"
    assert models[0]["format"] == "obj"
    assert models[0]["model_path"] == "demo-human/body.obj"
    assert models[0]["model_url"] == "/models/avatars/demo-human/body.obj"
    assert models[0]["material_url"] == "/models/avatars/demo-human/body.mtl"


def test_avatar_metadata_overrides_defaults(tmp_path):
    avatar_dir = tmp_path / "avatars" / "avatar-a"
    avatar_dir.mkdir(parents=True)
    (avatar_dir / "human.glb").write_bytes(b"glb")
    (avatar_dir / "avatar.json").write_text(
        json.dumps(
            {
                "name": "Custom Human",
                "model_file": "human.glb",
                "scale": 1.2,
                "position": [0, 0.05, 0],
                "rotation": [0, 180, 0],
            }
        ),
        encoding="utf-8",
    )

    models = discover_avatar_models(tmp_path / "avatars")

    assert models[0]["name"] == "Custom Human"
    assert models[0]["format"] == "glb"
    assert models[0]["scale"] == 1.2
    assert models[0]["position"] == [0, 0.05, 0]
    assert models[0]["rotation"] == [0, 180, 0]
