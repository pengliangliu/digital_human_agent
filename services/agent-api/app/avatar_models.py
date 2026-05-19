from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SUPPORTED_MODEL_FORMATS = ("glb", "gltf", "obj", "fbx")
_MODEL_PRIORITY = {fmt: index for index, fmt in enumerate(SUPPORTED_MODEL_FORMATS)}


def discover_avatar_models(avatars_root: Path) -> list[dict[str, Any]]:
    """Discover self-hosted avatar models under models/avatars/<avatar_id>/."""
    if not avatars_root.exists():
        return []

    models: list[dict[str, Any]] = []
    for avatar_dir in sorted(path for path in avatars_root.iterdir() if path.is_dir()):
        metadata = _read_metadata(avatar_dir / "avatar.json")
        model_file = _select_model_file(avatar_dir, metadata.get("model_file"))
        if not model_file:
            continue

        fmt = model_file.suffix.lower().lstrip(".")
        model_path = _as_posix_relative(model_file, avatars_root)
        model_url = f"/models/avatars/{model_path}"
        material_file = _select_material_file(avatar_dir, model_file, metadata.get("material_file"))
        material_path = _as_posix_relative(material_file, avatars_root) if material_file else ""
        material_url = f"/models/avatars/{material_path}" if material_path else ""
        avatar_id = metadata.get("id") or avatar_dir.name

        models.append(
            {
                "id": avatar_id,
                "name": metadata.get("name") or avatar_dir.name,
                "format": fmt,
                "model_path": model_path,
                "model_url": model_url,
                "material_path": material_path,
                "material_url": material_url,
                "scale": metadata.get("scale", 1.0),
                "position": metadata.get("position", [0, 0, 0]),
                "rotation": metadata.get("rotation", [0, 0, 0]),
                "head_node": metadata.get("head_node", ""),
                "notes": metadata.get("notes", ""),
            }
        )

    return models


def _read_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _select_model_file(avatar_dir: Path, configured_file: str | None) -> Path | None:
    if configured_file:
        candidate = avatar_dir / configured_file
        if _is_supported_model(candidate) and candidate.exists():
            return candidate

    candidates = [path for path in avatar_dir.rglob("*") if _is_supported_model(path)]
    candidates.sort(key=lambda path: (_MODEL_PRIORITY.get(path.suffix.lower().lstrip("."), 99), str(path)))
    return candidates[0] if candidates else None


def _select_material_file(avatar_dir: Path, model_file: Path, configured_file: str | None) -> Path | None:
    if configured_file:
        candidate = avatar_dir / configured_file
        if candidate.exists() and candidate.suffix.lower() == ".mtl":
            return candidate

    if model_file.suffix.lower() != ".obj":
        return None

    candidate = model_file.with_suffix(".mtl")
    return candidate if candidate.exists() else None


def _is_supported_model(path: Path) -> bool:
    return path.is_file() and path.suffix.lower().lstrip(".") in SUPPORTED_MODEL_FORMATS


def _as_posix_relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()
