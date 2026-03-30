"""
Custom Styles Router
Allows users to customize colors and fonts of overlays from the dashboard.
Stores settings in overlay_custom.json and generates CSS on demand.
"""
import asyncio
import json
import re
from fastapi import APIRouter
from fastapi.requests import Request
from fastapi.responses import JSONResponse

router = APIRouter()

_CUSTOM_FILE = "overlay_custom.json"
_VALID_KEYS = {"chat", "music", "viewers", "cam", "countdown"}

# Google Fonts specs per font name
_FONT_SPECS = {
    "Inter":          "Inter:wght@400;600;700;800",
    "Roboto":         "Roboto:wght@400;700",
    "Oswald":         "Oswald:wght@400;600;700",
    "JetBrains Mono": "JetBrains+Mono:wght@400;700",
    "Bebas Neue":     "Bebas+Neue",
    "Montserrat":     "Montserrat:wght@400;600;700;800",
    "Nunito":         "Nunito:wght@400;600;700;800",
    "Space Grotesk":  "Space+Grotesk:wght@400;600;700",
}


def _load() -> dict:
    try:
        with open(_CUSTOM_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: dict):
    with open(_CUSTOM_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _valid_hex(value: str) -> bool:
    """Validate hex color: must start with # and be 4 or 7 chars total."""
    if not isinstance(value, str):
        return False
    return bool(re.match(r'^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$', value))


def _generate_css(key: str, params: dict) -> str:
    accent = params.get("accent", "")
    text   = params.get("text", "")
    font   = params.get("font", "")
    radius = params.get("radius")

    # Validate hex colors
    if accent and not _valid_hex(accent):
        accent = ""
    if text and not _valid_hex(text):
        text = ""

    parts = []

    # Google Fonts import
    if font and font in _FONT_SPECS:
        spec = _FONT_SPECS[font]
        family_param = spec.replace(" ", "+")
        parts.append(f"@import url('https://fonts.googleapis.com/css2?family={family_param}&display=swap');")

    if key == "chat":
        if accent:
            parts.append(f".username {{ color: {accent} !important; }}")
        if text or font:
            rule_parts = []
            if text:
                rule_parts.append(f"color: {text} !important;")
            if font:
                rule_parts.append(f"font-family: '{font}', sans-serif !important;")
            parts.append(f".msg-text {{ {' '.join(rule_parts)} }}")

    elif key == "music":
        if accent or font:
            rule_parts = []
            if accent:
                rule_parts.append(f"color: {accent} !important;")
            if font:
                rule_parts.append(f"font-family: '{font}', sans-serif !important;")
            parts.append(f"#title {{ {' '.join(rule_parts)} }}")
        if text or font:
            rule_parts = []
            if text:
                rule_parts.append(f"color: {text} !important;")
            if font:
                rule_parts.append(f"font-family: '{font}', sans-serif !important;")
            parts.append(f"#artist {{ {' '.join(rule_parts)} }}")

    elif key == "viewers":
        if accent:
            parts.append(
                f".dot {{ background: {accent} !important; "
                f"box-shadow: 0 0 6px {accent}80 !important; }}"
            )
        if text or font:
            rule_parts = []
            if text:
                rule_parts.append(f"color: {text} !important;")
            if font:
                rule_parts.append(f"font-family: '{font}', sans-serif !important;")
            parts.append(f".viewer-count {{ {' '.join(rule_parts)} }}")

    elif key == "cam":
        if accent or radius is not None:
            rule_parts = []
            if accent:
                rule_parts.append(f"border-color: {accent} !important;")
                rule_parts.append(f"box-shadow: 0 0 18px {accent}55 !important;")
            if radius is not None:
                rule_parts.append(f"border-radius: {radius}px !important;")
            parts.append(f".cam-frame {{ {' '.join(rule_parts)} }}")
        if accent:
            parts.append(f".corner {{ border-color: {accent} !important; }}")

    elif key == "countdown":
        if accent or font:
            rule_parts = []
            if accent:
                rule_parts.append(f"color: {accent} !important;")
            if font:
                rule_parts.append(f"font-family: '{font}', sans-serif !important;")
            parts.append(f".cd-time {{ {' '.join(rule_parts)} }}")
        if text or font:
            rule_parts = []
            if text:
                rule_parts.append(f"color: {text} !important;")
            if font:
                rule_parts.append(f"font-family: '{font}', sans-serif !important;")
            parts.append(f".cd-message, .cd-sub {{ {' '.join(rule_parts)} }}")

    return "\n".join(parts)


@router.get("/overlay/custom-styles", include_in_schema=False)
async def get_all_custom_styles():
    """Return all custom style params for every overlay key."""
    return JSONResponse(_load())


@router.get("/overlay/custom-styles/{key}", include_in_schema=False)
async def get_custom_styles_css(key: str):
    """Return generated CSS for a specific overlay key."""
    if key not in _VALID_KEYS:
        return JSONResponse({"css": ""})
    data = _load()
    params = data.get(key, {})
    css = _generate_css(key, params)
    return JSONResponse({"css": css})


@router.post("/overlay/custom-styles", include_in_schema=False)
async def save_custom_styles(request: Request):
    """Save custom style params for an overlay key and broadcast change."""
    body = await request.json()
    key    = body.get("key", "")
    params = body.get("params", {})

    if key not in _VALID_KEYS:
        return JSONResponse({"ok": False, "error": "Invalid key"}, status_code=400)

    # Sanitize params
    clean: dict = {}
    for field in ("accent", "text", "bg", "font"):
        val = params.get(field, "")
        if isinstance(val, str) and val.strip():
            clean[field] = val.strip()
    if "radius" in params and isinstance(params["radius"], (int, float)):
        clean["radius"] = int(params["radius"])

    # Validate hex colors
    for color_field in ("accent", "text", "bg"):
        if color_field in clean and not _valid_hex(clean[color_field]):
            del clean[color_field]

    data = _load()
    data[key] = clean
    _save(data)

    css = _generate_css(key, clean)

    # Broadcast to connected overlay clients
    from main import overlay_events
    asyncio.create_task(overlay_events.broadcast({
        "type": "styles_changed",
        "key":  key,
        "css":  css,
    }))

    return JSONResponse({"ok": True, "css": css})


@router.delete("/overlay/custom-styles/{key}", include_in_schema=False)
async def reset_custom_styles(key: str):
    """Reset (delete) custom styles for a specific overlay key."""
    if key not in _VALID_KEYS:
        return JSONResponse({"ok": False, "error": "Invalid key"}, status_code=400)

    data = _load()
    data.pop(key, None)
    _save(data)

    # Broadcast reset (empty CSS)
    from main import overlay_events
    asyncio.create_task(overlay_events.broadcast({
        "type": "styles_changed",
        "key":  key,
        "css":  "",
    }))

    return JSONResponse({"ok": True})
