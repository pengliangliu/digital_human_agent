from typing import Any

from app.schemas import ToolCall


class AgentTools:
    def __init__(self) -> None:
        self._garments: list[dict[str, Any]] = [
            {"garment_id": "top_white_001", "name": "白色商务衬衫", "category": "upper", "style": "formal", "color": "white"},
            {"garment_id": "top_blue_002", "name": "蓝色休闲T恤", "category": "upper", "style": "casual", "color": "blue"},
            {"garment_id": "top_stripe_003", "name": "条纹通勤衬衫", "category": "upper", "style": "commute", "color": "mixed"},
            {"garment_id": "pant_black_001", "name": "黑色直筒西裤", "category": "lower", "style": "formal", "color": "black"},
            {"garment_id": "pant_khaki_002", "name": "卡其色休闲裤", "category": "lower", "style": "casual", "color": "khaki"},
            {"garment_id": "pant_grey_003", "name": "灰色通勤裤", "category": "lower", "style": "commute", "color": "grey"},
            {"garment_id": "jacket_navy_001", "name": "藏青色西装外套", "category": "outer", "style": "formal", "color": "navy"},
            {"garment_id": "jacket_denim_002", "name": "牛仔夹克", "category": "outer", "style": "casual", "color": "blue"},
            {"garment_id": "dress_red_001", "name": "红色连衣裙", "category": "full", "style": "formal", "color": "red"},
            {"garment_id": "dress_floral_002", "name": "碎花连衣裙", "category": "full", "style": "casual", "color": "mixed"},
        ]

    async def recommend_outfits(
        self,
        user_id: str = "",
        style: str | None = None,
        color_preference: str | None = None,
    ) -> list[dict[str, Any]]:
        results = []
        for g in self._garments:
            if style and g["style"] != style:
                continue
            if color_preference and color_preference not in g.get("color", ""):
                continue
            results.append({
                "garment_id": g["garment_id"],
                "name": g["name"],
                "reason": f"这件{g['name']}很适合你",
                "preview_url": None,
            })
        return results[:4]

    async def try_on(self, avatar_id: str, garment_id: str) -> dict[str, Any]:
        garment = next((g for g in self._garments if g["garment_id"] == garment_id), None)
        return {
            "status": "ok",
            "avatar_id": avatar_id,
            "garment_id": garment_id,
            "garment_name": garment["name"] if garment else garment_id,
            "layer_id": garment["category"] if garment else "unknown",
        }

    async def get_user_profile(self, user_id: str = "") -> dict[str, Any]:
        return {
            "user_id": user_id or "anonymous",
            "body_type": "standard",
            "height_cm": 170,
            "weight_kg": 65,
            "preferences": {"style": "casual", "color": "light"},
        }

    async def handle_tool_call(self, tool_call: ToolCall) -> dict[str, Any]:
        name = tool_call.name
        args = tool_call.arguments or {}
        if name == "recommend_outfits":
            return {"items": await self.recommend_outfits(**args)}
        elif name == "try_on":
            return await self.try_on(**args)
        elif name == "get_user_profile":
            return await self.get_user_profile(**args)
        return {"error": f"Unknown tool: {name}"}
