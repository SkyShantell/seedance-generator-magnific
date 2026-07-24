"""
Seedance Video Generator — Streamlit App (v2)
==============================================
Paste TikTok Shop links → pick a style → select the right product photo →
generate videos automatically OR get prompts to generate manually.
"""

import streamlit as st
import anthropic
import hashlib
import json
import os
import re
import time
import requests
import shutil
import subprocess
import tempfile
from datetime import datetime
from urllib.parse import urlparse
from html import unescape as html_unescape
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except Exception:
    Image = None
    ImageDraw = None
    ImageFont = None
    PIL_AVAILABLE = False


# ── Page config ─────────────────────────────────────────────────────
st.set_page_config(
    page_title="Seedance Video Generator",
    page_icon="🎬",
    layout="wide",
)

# ── Persistent storage ─────────────────────────────────────────────
SAVE_FILE = Path("generations.json")
PRESETS_FILE = Path("text_presets.json")
PROCESSED_DIR = Path("processed_videos")
EMOJI_ASSET_DIR = Path("emoji_assets")
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# Apple-style transparent PNG files created by MakeAppleEmojis.swift.
EMOJI_ASSET_MAP = {
    "😭": "loudly_crying_face.png",
    "😩": "weary_face.png",
    "💀": "skull.png",
    "😂": "face_with_tears_of_joy.png",
    "🤣": "rolling_on_the_floor_laughing.png",
    "🥺": "pleading_face.png",
    "🤩": "star_struck.png",
    "😍": "smiling_face_with_heart_eyes.png",
    "🥲": "smiling_face_with_tear.png",
    "😮‍💨": "face_exhaling.png",
    "🫠": "melting_face.png",
    "🙃": "upside_down_face.png",
}

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]

DEFAULT_TEXT_SETTINGS = {
    "font_size": 28,
    "max_width_pct": 78,
    "vertical_position_pct": 22,
    "outline_width": 2,
    "line_spacing_pct": 112,
    "emoji_size_px": 38,
}

BUILT_IN_TEXT_PRESETS = {
    "Apple Compact": {
        "font_size": 26,
        "max_width_pct": 82,
        "vertical_position_pct": 20,
        "outline_width": 2,
        "line_spacing_pct": 108,
        "emoji_size_px": 34,
    },
    "TikTok Clean": {
        "font_size": 30,
        "max_width_pct": 76,
        "vertical_position_pct": 21,
        "outline_width": 2,
        "line_spacing_pct": 112,
        "emoji_size_px": 40,
    },
    "Minimal Small": {
        "font_size": 23,
        "max_width_pct": 86,
        "vertical_position_pct": 24,
        "outline_width": 1,
        "line_spacing_pct": 106,
        "emoji_size_px": 30,
    },
    "Bold Center": {
        "font_size": 34,
        "max_width_pct": 72,
        "vertical_position_pct": 26,
        "outline_width": 3,
        "line_spacing_pct": 116,
        "emoji_size_px": 46,
    },
}


def inject_apple_glass_css():
    """Apply a modern Apple-inspired glass UI without changing app behavior."""
    st.markdown(
        """
        <style>
        :root {
            --glass-bg: rgba(255, 255, 255, 0.58);
            --glass-border: rgba(255, 255, 255, 0.72);
            --glass-shadow: 0 18px 45px rgba(15, 23, 42, 0.10);
            --ink: #111827;
            --muted: #667085;
            --accent: #0A84FF;
            --accent-2: #5E5CE6;
        }

        .stApp {
            background:
                radial-gradient(circle at 8% 0%, rgba(10,132,255,.17), transparent 30%),
                radial-gradient(circle at 92% 8%, rgba(94,92,230,.15), transparent 27%),
                radial-gradient(circle at 50% 100%, rgba(52,199,89,.10), transparent 32%),
                linear-gradient(145deg, #f7f9fc 0%, #eef3f8 52%, #f8f9fb 100%);
            color: var(--ink);
        }

        [data-testid="stAppViewContainer"] > .main {
            background: transparent;
        }

        .block-container {
            max-width: 1380px;
            padding-top: 1.5rem;
            padding-bottom: 4rem;
        }

        .apple-hero {
            position: relative;
            overflow: hidden;
            padding: 28px 30px;
            border-radius: 28px;
            background: linear-gradient(135deg, rgba(255,255,255,.78), rgba(255,255,255,.46));
            border: 1px solid rgba(255,255,255,.88);
            box-shadow: 0 24px 60px rgba(15,23,42,.12);
            backdrop-filter: blur(28px) saturate(160%);
            -webkit-backdrop-filter: blur(28px) saturate(160%);
            margin-bottom: 1.3rem;
        }

        .apple-hero:after {
            content: "";
            position: absolute;
            width: 220px;
            height: 220px;
            right: -70px;
            top: -90px;
            border-radius: 999px;
            background: linear-gradient(135deg, rgba(10,132,255,.30), rgba(94,92,230,.18));
            filter: blur(8px);
        }

        .apple-hero h1 {
            margin: 0;
            font-size: clamp(2rem, 4vw, 3.4rem);
            letter-spacing: -0.045em;
            line-height: .98;
            font-weight: 800;
            color: #0b1220;
        }

        .apple-hero p {
            margin: 12px 0 0 0;
            color: #5f6b7a;
            font-size: 1rem;
            max-width: 720px;
        }

        .apple-kicker {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 7px 11px;
            border-radius: 999px;
            background: rgba(10,132,255,.10);
            color: #0969c8;
            font-weight: 700;
            font-size: .78rem;
            margin-bottom: 14px;
        }

        [data-testid="stSidebar"] {
            background: rgba(246, 249, 252, .72);
            border-right: 1px solid rgba(255,255,255,.85);
            backdrop-filter: blur(28px) saturate(160%);
            -webkit-backdrop-filter: blur(28px) saturate(160%);
        }

        [data-testid="stSidebar"] > div:first-child {
            padding-top: 1.35rem;
        }

        div[data-testid="stExpander"],
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 22px !important;
            border: 1px solid rgba(255,255,255,.86) !important;
            background: rgba(255,255,255,.54) !important;
            box-shadow: var(--glass-shadow);
            backdrop-filter: blur(22px) saturate(145%);
            -webkit-backdrop-filter: blur(22px) saturate(145%);
        }

        div[data-testid="stExpander"] details {
            border: none !important;
            background: transparent !important;
        }

        .stButton > button,
        .stDownloadButton > button {
            border-radius: 14px !important;
            border: 1px solid rgba(255,255,255,.72) !important;
            background: rgba(255,255,255,.72) !important;
            color: #152033 !important;
            box-shadow: 0 8px 22px rgba(15,23,42,.08) !important;
            backdrop-filter: blur(16px);
            font-weight: 700 !important;
            transition: transform .16s ease, box-shadow .16s ease, background .16s ease;
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover {
            transform: translateY(-1px);
            background: rgba(255,255,255,.94) !important;
            box-shadow: 0 12px 28px rgba(15,23,42,.13) !important;
        }

        .stButton > button[kind="primary"] {
            color: white !important;
            background: linear-gradient(135deg, #0A84FF, #5E5CE6) !important;
            border: none !important;
            box-shadow: 0 12px 28px rgba(10,132,255,.28) !important;
        }

        .stTextInput input,
        .stTextArea textarea,
        div[data-baseweb="select"] > div {
            border-radius: 14px !important;
            border: 1px solid rgba(148,163,184,.26) !important;
            background: rgba(255,255,255,.72) !important;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.75);
        }

        .stTextInput input:focus,
        .stTextArea textarea:focus {
            border-color: rgba(10,132,255,.55) !important;
            box-shadow: 0 0 0 4px rgba(10,132,255,.11) !important;
        }

        [data-testid="stMetric"] {
            padding: 16px 18px;
            border-radius: 18px;
            background: rgba(255,255,255,.58);
            border: 1px solid rgba(255,255,255,.80);
            box-shadow: 0 12px 30px rgba(15,23,42,.07);
        }

        [data-testid="stAlert"] {
            border-radius: 16px !important;
            border: 1px solid rgba(255,255,255,.72) !important;
            backdrop-filter: blur(18px);
        }

        .preset-pill {
            display: inline-block;
            padding: 6px 10px;
            border-radius: 999px;
            background: rgba(10,132,255,.10);
            color: #0969c8;
            font-size: .78rem;
            font-weight: 700;
            margin-bottom: 8px;
        }

        h1, h2, h3 {
            letter-spacing: -0.025em;
        }

        hr {
            border-color: rgba(148,163,184,.18) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def normalize_text_settings(settings: dict | None) -> dict:
    """Migrate older saved settings and return a complete settings dictionary."""
    normalized = dict(DEFAULT_TEXT_SETTINGS)
    if settings:
        normalized.update(settings)

    # Migrate the older percentage-based emoji setting to a clear pixel size.
    if "emoji_size_px" not in (settings or {}):
        old_scale = int((settings or {}).get("emoji_scale_pct", 105))
        font_size = int(normalized.get("font_size", 28))
        normalized["emoji_size_px"] = max(18, round(font_size * old_scale / 100))

    normalized.pop("emoji_scale_pct", None)
    return normalized


def load_text_presets_data() -> dict:
    """Load custom text presets and the user's preferred default preset."""
    data = {"default": "Apple Compact", "presets": {}}
    if PRESETS_FILE.exists():
        try:
            loaded = json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data["default"] = loaded.get("default") or data["default"]
                presets = loaded.get("presets")
                if isinstance(presets, dict):
                    data["presets"] = {
                        str(name): normalize_text_settings(value)
                        for name, value in presets.items()
                        if isinstance(value, dict)
                    }
        except (json.JSONDecodeError, IOError):
            pass
    return data


def save_text_presets_data(data: dict):
    """Persist custom presets and the selected default preset."""
    payload = {
        "default": data.get("default") or "Apple Compact",
        "presets": data.get("presets") or {},
    }
    try:
        PRESETS_FILE.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except IOError:
        pass


def all_text_presets() -> tuple[dict, dict]:
    """Return merged presets plus the raw persistent preset data."""
    data = load_text_presets_data()
    merged = {name: normalize_text_settings(value) for name, value in BUILT_IN_TEXT_PRESETS.items()}
    merged.update(data.get("presets") or {})
    return merged, data


def default_text_settings_from_presets() -> tuple[dict, str]:
    """Return settings for the global default preset."""
    presets, data = all_text_presets()
    default_name = data.get("default") or "Apple Compact"
    if default_name not in presets:
        default_name = "Apple Compact"
    return dict(presets[default_name]), default_name


def set_editor_widget_values(index: int, settings: dict):
    """Load preset settings into the Streamlit editor widgets."""
    normalized = normalize_text_settings(settings)
    st.session_state[f"editor_size_{index}"] = int(normalized["font_size"])
    st.session_state[f"editor_width_{index}"] = int(normalized["max_width_pct"])
    st.session_state[f"editor_position_{index}"] = int(normalized["vertical_position_pct"])
    st.session_state[f"editor_outline_{index}"] = int(normalized["outline_width"])
    st.session_state[f"editor_spacing_{index}"] = int(normalized["line_spacing_pct"])
    st.session_state[f"editor_emoji_{index}"] = int(normalized["emoji_size_px"])


def load_generations() -> list[dict]:
    """Load saved generations from disk."""
    if SAVE_FILE.exists():
        try:
            with open(SAVE_FILE, encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_generations(generations: list[dict]):
    """Save generations to disk."""
    try:
        with open(SAVE_FILE, "w", encoding="utf-8") as f:
            json.dump(generations, f, indent=2, ensure_ascii=False, default=str)
    except IOError:
        pass


def add_generation(result: dict):
    """Append a single generation result to the saved file."""
    gens = load_generations()
    gens.insert(0, result)
    save_generations(gens[:200])


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_video_bytes(video_url: str) -> bytes | None:
    """Download video bytes and cache the result for Streamlit reruns."""
    try:
        resp = requests.get(video_url, timeout=90)
        resp.raise_for_status()
        return resp.content
    except Exception:
        return None


def get_ffmpeg_executable() -> str | None:
    """Find FFmpeg from the OS, with imageio-ffmpeg as an optional fallback."""
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return ffmpeg_path

    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def get_ffprobe_executable(ffmpeg_path: str | None = None) -> str | None:
    """Find ffprobe, including beside a discovered FFmpeg executable."""
    probe = shutil.which("ffprobe")
    if probe:
        return probe

    if ffmpeg_path:
        candidate = Path(ffmpeg_path).with_name("ffprobe")
        if candidate.exists():
            return str(candidate)
    return None


def get_overlay_font() -> str | None:
    """Return a bold font file that Pillow can use."""
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def probe_video_size(video_path: Path, ffmpeg_path: str | None = None) -> tuple[int, int]:
    """Read video dimensions with ffprobe; fall back to Seedance's 720p 9:16 size."""
    ffprobe_path = get_ffprobe_executable(ffmpeg_path)
    if not ffprobe_path:
        return 720, 1280

    command = [
        ffprobe_path,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=s=x:p=0",
        str(video_path),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
        match = re.search(r"(\d+)x(\d+)", completed.stdout or "")
        if match:
            return int(match.group(1)), int(match.group(2))
    except Exception:
        pass
    return 720, 1280


def split_trailing_emojis(text: str) -> tuple[str, list[str]]:
    """Remove supported trailing emojis so they can be rendered from PNG assets."""
    remaining = re.sub(r"\s+", " ", (text or "").strip())
    trailing: list[str] = []

    while remaining:
        found = None
        for emoji_char in sorted(EMOJI_ASSET_MAP.keys(), key=len, reverse=True):
            if remaining.endswith(emoji_char):
                found = emoji_char
                break
        if not found:
            break
        trailing.insert(0, found)
        remaining = remaining[:-len(found)].rstrip()

    return remaining, trailing


def load_emoji_png(emoji_char: str, target_height: int) -> Image.Image | None:
    """Load, tightly crop, and resize one Apple-style emoji PNG.

    Cropping the transparent canvas first makes the emoji-size slider visually
    accurate. The Swift exporter creates square PNGs with transparent padding,
    so resizing the uncropped file made size changes look much smaller than they were.
    """
    if not PIL_AVAILABLE:
        return None
    filename = EMOJI_ASSET_MAP.get(emoji_char)
    if not filename:
        return None
    path = EMOJI_ASSET_DIR / filename
    if not path.exists():
        return None

    try:
        image = Image.open(path).convert("RGBA")
        alpha = image.getchannel("A")
        bbox = alpha.getbbox()
        if bbox:
            image = image.crop(bbox)

        target_height = max(8, int(target_height))
        ratio = target_height / max(1, image.height)
        target_width = max(1, round(image.width * ratio))
        return image.resize((target_width, target_height), Image.Resampling.LANCZOS)
    except Exception:
        return None


def text_size(draw: ImageDraw.ImageDraw, text: str, font, stroke_width: int = 0) -> tuple[int, int]:
    """Measure text accurately with Pillow."""
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    return max(1, bbox[2] - bbox[0]), max(1, bbox[3] - bbox[1])


def wrap_text_pixels(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    max_width: int,
    stroke_width: int,
    max_lines: int = 4,
) -> list[str]:
    """Wrap text according to actual rendered width rather than character count."""
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]

    for word in words[1:]:
        candidate = f"{current} {word}"
        width, _ = text_size(draw, candidate, font, stroke_width)
        if width <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)

    if len(lines) > max_lines:
        kept = lines[:max_lines]
        overflow_words = " ".join(lines[max_lines - 1:]).split()
        last_line = ""
        for word in overflow_words:
            candidate = f"{last_line} {word}".strip()
            display_candidate = candidate + "…"
            width, _ = text_size(draw, display_candidate, font, stroke_width)
            if width <= max_width:
                last_line = candidate
            else:
                break
        kept[-1] = (last_line or kept[-1]).rstrip(" .") + "…"
        lines = kept

    return lines


def create_hook_overlay_png(
    hook: str,
    output_path: Path,
    canvas_size: tuple[int, int],
    settings: dict,
) -> tuple[bool, str | None]:
    """Create a transparent, editable text overlay PNG for FFmpeg."""
    if not PIL_AVAILABLE:
        return False, "Pillow is missing. Add Pillow to requirements.txt."

    width, height = canvas_size
    text_only, emojis = split_trailing_emojis(hook)

    settings = normalize_text_settings(settings)
    requested_size = int(settings.get("font_size", DEFAULT_TEXT_SETTINGS["font_size"]))
    max_width = int(width * int(settings.get("max_width_pct", 78)) / 100)
    top_y = int(height * int(settings.get("vertical_position_pct", 22)) / 100)
    stroke_width = int(settings.get("outline_width", 2))
    line_spacing_pct = int(settings.get("line_spacing_pct", 112))
    emoji_size_px = int(settings.get("emoji_size_px", DEFAULT_TEXT_SETTINGS["emoji_size_px"]))

    font_path = get_overlay_font()
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    chosen_font = None
    chosen_lines: list[str] = []
    actual_size = requested_size

    # Keep the user's selected size when possible, but shrink slightly if needed
    # so long hooks never explode into five oversized lines.
    for size in range(requested_size, 15, -1):
        try:
            font = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()
        except Exception:
            font = ImageFont.load_default()

        lines = wrap_text_pixels(draw, text_only, font, max_width, stroke_width, max_lines=4)
        widest = max(text_size(draw, line, font, stroke_width)[0] for line in lines)
        if len(lines) <= 4 and widest <= max_width:
            chosen_font = font
            chosen_lines = lines
            actual_size = size
            break

    if chosen_font is None:
        chosen_font = ImageFont.load_default()
        chosen_lines = wrap_text_pixels(draw, text_only, chosen_font, max_width, stroke_width, max_lines=4)

    line_metrics = [text_size(draw, line, chosen_font, stroke_width) for line in chosen_lines]
    base_line_height = max(h for _, h in line_metrics)
    line_step = max(base_line_height + 2, round(base_line_height * line_spacing_pct / 100))

    # Emoji size is an explicit pixel value, so every slider movement produces
    # an obvious, deterministic change independent of the selected text size.
    emoji_height = max(12, emoji_size_px)
    emoji_images = [load_emoji_png(e, emoji_height) for e in emojis]
    missing_emojis = [e for e, img in zip(emojis, emoji_images) if img is None]
    emoji_images = [img for img in emoji_images if img is not None]
    emoji_gap = max(3, round(actual_size * 0.16))

    for line_index, line in enumerate(chosen_lines):
        text_w, text_h = line_metrics[line_index]
        y = top_y + line_index * line_step
        is_last = line_index == len(chosen_lines) - 1

        emoji_total_width = 0
        if is_last and emoji_images:
            emoji_total_width = sum(img.width for img in emoji_images) + emoji_gap * len(emoji_images)

        combined_width = text_w + emoji_total_width
        x = round((width - combined_width) / 2)

        # Small TikTok-style shadow, white text, thin black outline.
        draw.text(
            (x + 1, y + 1),
            line,
            font=chosen_font,
            fill=(0, 0, 0, 115),
            stroke_width=stroke_width,
            stroke_fill=(0, 0, 0, 210),
        )
        draw.text(
            (x, y),
            line,
            font=chosen_font,
            fill=(255, 255, 255, 255),
            stroke_width=stroke_width,
            stroke_fill=(0, 0, 0, 235),
        )

        if is_last and emoji_images:
            emoji_x = x + text_w + emoji_gap
            for emoji_img in emoji_images:
                emoji_y = y + max(0, round((text_h - emoji_img.height) / 2))
                overlay.alpha_composite(emoji_img, (emoji_x, emoji_y))
                emoji_x += emoji_img.width + emoji_gap

    output_path.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(output_path, "PNG")

    warning = None
    if missing_emojis:
        warning = "Missing emoji PNG asset(s): " + " ".join(missing_emojis)
    return True, warning


def processed_video_path(creation_id: str | None, hook: str, settings: dict) -> Path:
    """Create a stable output filename based on the video and editor settings."""
    key_data = json.dumps({"hook": hook, "settings": settings}, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(key_data.encode("utf-8")).hexdigest()[:12]
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", creation_id or "video")[:60]
    return PROCESSED_DIR / f"{safe_id}_{digest}.mp4"


def apply_text_with_ffmpeg(
    video_url: str,
    creation_id: str | None,
    hook: str,
    settings: dict,
) -> tuple[Path | None, str | None]:
    """Apply the user-configured text only after they click the editor button."""
    if not video_url:
        return None, "No completed video URL is available."
    if not hook.strip():
        return None, "Enter text before applying the overlay."

    ffmpeg_path = get_ffmpeg_executable()
    if not ffmpeg_path:
        return None, "FFmpeg is not installed. Keep `ffmpeg` in packages.txt."

    source_bytes = fetch_video_bytes(video_url)
    if not source_bytes:
        return None, "The original video could not be downloaded from Magnific."

    final_path = processed_video_path(creation_id, hook, settings)
    if final_path.exists() and final_path.stat().st_size > 0:
        return final_path, None

    try:
        with tempfile.TemporaryDirectory(prefix="seedance_editor_") as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "original.mp4"
            overlay_path = temp_path / "overlay.png"
            input_path.write_bytes(source_bytes)

            canvas_size = probe_video_size(input_path, ffmpeg_path)
            overlay_ok, overlay_warning = create_hook_overlay_png(
                hook=hook,
                output_path=overlay_path,
                canvas_size=canvas_size,
                settings=settings,
            )
            if not overlay_ok:
                return None, overlay_warning or "Could not build the text overlay."

            command = [
                ffmpeg_path,
                "-hide_banner",
                "-loglevel", "error",
                "-y",
                "-i", str(input_path),
                "-loop", "1",
                "-framerate", "30",
                "-i", str(overlay_path),
                "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto:shortest=1[v]",
                "-map", "[v]",
                "-map", "0:a?",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart",
                "-shortest",
                str(final_path),
            ]

            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )

            if completed.returncode != 0 or not final_path.exists():
                final_path.unlink(missing_ok=True)
                details = (completed.stderr or "Unknown FFmpeg error").strip().splitlines()
                return None, details[-1] if details else "Unknown FFmpeg error"

            return final_path, overlay_warning

    except subprocess.TimeoutExpired:
        final_path.unlink(missing_ok=True)
        return None, "FFmpeg timed out while applying the text."
    except Exception as exc:
        final_path.unlink(missing_ok=True)
        return None, f"FFmpeg editor failed: {exc}"


def read_local_video(path_value: str | None) -> bytes | None:
    """Read a previously processed local MP4 safely."""
    if not path_value:
        return None
    path = Path(path_value)
    try:
        if path.exists() and path.is_file():
            return path.read_bytes()
    except Exception:
        pass
    return None


# ── Constants ───────────────────────────────────────────────────────
MAGNIFIC_MCP_URL = "https://mcp.magnific.com"
MAGNIFIC_MCP_NAME = "magnific"
MODEL = "claude-sonnet-4-6"
MCP_BETA = "mcp-client-2025-11-20"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# ═══════════════════════════════════════════════════════════════════
#  SYSTEM PROMPTS
# ═══════════════════════════════════════════════════════════════════

SHOE_VIDEO_SYSTEM = """You are a TikTok Shop affiliate content producer. Write a Seedance 2.0
video prompt for the product described. Follow these HARD RULES:
- 9:16 vertical, TikTok UGC aesthetic
- NO person above the ankle — EVER
- NO on-screen text, captions, subtitles, overlays, signs, logos
- Feet-and-shoes ONLY — the shoe IS the star
- Warm natural lighting, phone-camera handheld feel
- 3 timecoded shots (looking-down POV → low side-angle → back to overhead)

Shot structure:
[00:00-00:05] Looking-down POV. Feet in [product] on [surface]. [Opening movement].
[00:05-00:10] Low side-angle. Camera tilts to reveal [feature]. Foot lifts, sets down.
[00:10-00:15] Overhead POV. [Natural movement]. [Product detail] catches warm light.

Surface matching:
- Sandals/flip-flops → light hardwood, tile, poolside concrete
- Sneakers → pavement, gym floor, clean concrete
- Boots → wood floor, outdoor path, autumn leaves
- Heels → marble, polished tile
- Slippers → carpet, rug, cozy indoor floor

{voiceover_instruction}

Return ONLY valid JSON (no markdown, no backticks):
{{"product_name": "...", "prompt": "the full seedance prompt under 1900 chars", "char_count": 123}}"""

TEXTHOOK_HOOKS_SYSTEM = """You are a TikTok Shop affiliate content producer. Generate 5
on-screen text hook options for a product video.

Text hook rules (gen-z texting voice):
- ur, bc, &, lowercase drift, no period
- Deadpan, self-deprecating money humor
- Exactly one emoji at the end (😭 😩 💀 — pick one). No emoji spam
- No "link in bio", no CTA. ~14-22 words
- Each hook MUST be a completely different angle/joke — NOT minor rewording:
  1) broke-flex ("I spent rent money on this")
  2) relatable overspending ("add to cart at 3am type behavior")
  3) "this fixed my life" ("idk how I lived without this")
  4) self-roast ("no one asked but here's my 47th order this month")
  5) unexpected gratitude ("whoever invented this I owe u my life")

Return ONLY valid JSON (no markdown, no backticks):
{{"product_name": "...", "hook_options": ["hook 1", "hook 2", "hook 3", "hook 4", "hook 5"], "caption": "tiktok caption (NOT the hook — a separate short caption for the post)", "hashtags": "#tag1 #tag2..."}}"""

TEXTHOOK_PROMPT_SYSTEM = """You are a TikTok Shop affiliate content producer. Write a
Seedance 2.0 video prompt for a clean text-hook b-roll video.

HARD RULES:
- SILENT video — NO audio, NO voiceover
- ABSOLUTELY NO on-screen text, captions, subtitles, overlays, signs, watermarks, or logos
- No face, no person, no character — only a hand in the reveal shot
- Two acts: random b-roll (~3s) → hard cut to product reveal (~5s)
- ~8 seconds total, 9:16 vertical
- Under 1,900 characters

CRITICAL — B-ROLL RULES:
The opening b-roll must be a RANDOM outdoor real-life scene that has absolutely nothing
to do with the product. The scene should usually take place on a street, sidewalk, park,
beach, boardwalk, parking lot, or another casual public outdoor location.

Pick ONE scene at random from examples like:
- First-person view of someone walking down a sidewalk
- Feet walking along a park path
- Cars passing on a city street
- Cars driving on a highway at golden hour
- A quiet neighborhood street filmed while walking
- People walking through a public park
- A dog trotting ahead on a leash, filmed from behind
- Waves rolling onto a beach
- Someone walking along a beach or boardwalk
- Palm trees moving slightly in the wind
- A crosswalk signal changing while people cross
- A city intersection filmed from the sidewalk
- Leaves blowing across a parking lot
- Sunlight moving through trees in a park
- A distant train passing through an outdoor station
- Boats moving slowly across the water
- A casual view from a moving car window
- People walking through an outdoor shopping area
- Sneakers walking across pavement
- A bike rider passing on a park trail

HARD EXCLUSIONS:
- No rain droplets on windows
- No grocery carts or grocery aisles
- No laundry, dryers, washing machines, or household chores
- No coffee pouring or close-up drink shots
- No kitchens, bedrooms, bathrooms, or indoor home scenes
- No desk shots or hands using unrelated objects
- No product-related locations
- No b-roll that visually hints at the product
- No dramatic cinematic scene
- No staged or polished commercial footage

The b-roll should feel casual, slightly imperfect, and filmed on a phone by a normal
person. The more unrelated it is to the product, the better.

Prompt template:
9:16 vertical, TikTok UGC aesthetic, silent, no audio, no voiceover. Handheld phone-camera
feel with natural micro-shake. Warm bright daylight, slightly saturated. No face, no person,
no character — only a hand in the second half. No text or graphics anywhere in the video.

[00:00-00:03] Establishing b-roll: first-person POV of one random mundane scene that is
completely unrelated to the product. Casual handheld drift. No product on screen.

[00:03-00:08] Hard cut to an outdoor or casual real-life surface. A single
medium-brown-skinned hand holds up [PRODUCT + visual detail] toward camera, slowly rotating
and tilting so the detail catches warm light. Hand fills the lower half. Soft blurred
background. No face. No person above the wrist.

Return ONLY valid JSON (no markdown, no backticks):
{{"product_name": "...", "prompt": "the full seedance prompt under 1900 chars", "char_count": 123}}"""

VOICEOVER_SILENT = "## Audio:\nNO voiceover. Ambient sound only."
VOICEOVER_WITH_SCRIPT = '## Voiceover:\nInclude this voiceover (warm excited woman, casual and friendly):\n"{script}"'


# ═══════════════════════════════════════════════════════════════════
#  SCRAPER
# ═══════════════════════════════════════════════════════════════════

def _name_from_url(url: str) -> str:
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    best = ""
    for part in parts:
        if len(part) < 5 or part.isdigit() or part.lower() in ("us", "pdp", "dp", "ip", "product"):
            continue
        if len(part) > len(best):
            best = part
    if best:
        words = best.replace("-", " ").replace("_", " ").split()[:10]
        return " ".join(words).title()
    return "Unknown Product"


def _find_images_in_dict(obj, depth=0, max_depth=8):
    if depth > max_depth:
        return []
    images = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and v.startswith("http") and any(
                ext in v.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']
            ):
                images.append(v)
            else:
                images.extend(_find_images_in_dict(v, depth + 1, max_depth))
    elif isinstance(obj, list):
        for item in obj:
            images.extend(_find_images_in_dict(item, depth + 1, max_depth))
    return images


def scrape_product(url: str) -> dict | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        html = resp.text

        # og:image
        img_match = re.search(
            r'<meta\s+(?:property|name)=["\']og:image["\']\s+content=["\']([^"\']+)["\']',
            html, re.IGNORECASE
        )
        if not img_match:
            img_match = re.search(
                r'content=["\']([^"\']+)["\']\s+(?:property|name)=["\']og:image["\']',
                html, re.IGNORECASE
            )

        # og:title
        title_match = re.search(
            r'<meta\s+(?:property|name)=["\']og:title["\']\s+content=["\']([^"\']+)["\']',
            html, re.IGNORECASE
        )
        if not title_match:
            title_match = re.search(
                r'content=["\']([^"\']+)["\']\s+(?:property|name)=["\']og:title["\']',
                html, re.IGNORECASE
            )
        if not title_match:
            title_match = re.search(r'<title>([^<]+)</title>', html, re.IGNORECASE)

        images = []
        if img_match:
            images.append(img_match.group(1))

        # JSON-LD
        ld_blocks = re.findall(
            r'<script\s+type=["\']application/ld\+json["\']>\s*({.*?})\s*</script>',
            html, re.DOTALL
        )
        for block in ld_blocks:
            try:
                ld = json.loads(block)
                if isinstance(ld, dict) and "image" in ld:
                    img_val = ld["image"]
                    if isinstance(img_val, str):
                        images.append(img_val)
                    elif isinstance(img_val, list):
                        images.extend([i for i in img_val if isinstance(i, str)])
            except json.JSONDecodeError:
                pass

        # __NEXT_DATA__
        next_data = re.search(
            r'<script\s+id=["\']__NEXT_DATA__["\']\s+type=["\']application/json["\']>\s*({.*?})\s*</script>',
            html, re.DOTALL
        )
        if next_data:
            try:
                nd = json.loads(next_data.group(1))
                images.extend(_find_images_in_dict(nd))
            except json.JSONDecodeError:
                pass

        # CDN image URLs
        cdn_imgs = re.findall(
            r'(https?://[^"\'\s]+(?:\.jpg|\.jpeg|\.png|\.webp)(?:\?[^"\'\s]*)?)',
            html
        )
        for ci in cdn_imgs:
            if any(kw in ci.lower() for kw in ['product', 'pdp', 'origin', 'large', '800', '1000', '1200']):
                images.append(ci)

        if not images:
            return None

        # Deduplicate and clean
        seen = set()
        unique = []
        for img in images:
            cleaned = html_unescape(img)
            if cleaned not in seen:
                seen.add(cleaned)
                unique.append(cleaned)

        name = title_match.group(1).strip() if title_match else ""
        name = re.sub(r'\s*[|\-–—]\s*(TikTok|Shop|Amazon|Walmart).*$', '', name, flags=re.IGNORECASE)
        if not name or name == "Unknown Product":
            name = _name_from_url(url)

        return {"name": name[:100], "images": unique[:8], "source_url": url}

    except Exception as e:
        return None


# ═══════════════════════════════════════════════════════════════════
#  PROMPT WRITER (Claude only — no MCP, cheap + fast)
# ═══════════════════════════════════════════════════════════════════

def write_hooks(api_key: str, product_name: str) -> dict:
    """Generate 5 hook options for a product. Cheap/fast — no MCP."""
    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=TEXTHOOK_HOOKS_SYSTEM,
            messages=[{
                "role": "user",
                "content": f"Write 5 text hook options for this product: {product_name}"
            }],
        )
        text = response.content[0].text
        cleaned = re.sub(r'```json\s*', '', text)
        cleaned = re.sub(r'```\s*', '', cleaned)
        json_start = cleaned.find("{")
        json_end = cleaned.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            return json.loads(cleaned[json_start:json_end])
        return {"error": "Couldn't parse JSON", "product_name": product_name}
    except Exception as e:
        return {"error": str(e), "product_name": product_name}


def write_prompt(
    api_key: str,
    product_name: str,
    style: str,
    duration: int = 15,
    voice_script: str | None = None,
    selected_hook: str | None = None,
) -> dict:
    """Use Claude to write the Seedance prompt. No MCP, no Magnific."""
    if style == "shoe_video":
        vo = VOICEOVER_WITH_SCRIPT.format(script=voice_script) if voice_script else VOICEOVER_SILENT
        system = SHOE_VIDEO_SYSTEM.format(voiceover_instruction=vo)
        dur = duration
    else:
        # The selected hook is added after generation with FFmpeg.
        system = TEXTHOOK_PROMPT_SYSTEM
        dur = 8

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=system,
            messages=[{
                "role": "user",
                "content": f"Write a {dur}-second Seedance 2.0 prompt for this product: {product_name}"
            }],
        )

        text = response.content[0].text
        cleaned = re.sub(r'```json\s*', '', text)
        cleaned = re.sub(r'```\s*', '', cleaned)
        json_start = cleaned.find("{")
        json_end = cleaned.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            return json.loads(cleaned[json_start:json_end])

        return {"prompt": text, "product_name": product_name, "error": "Couldn't parse JSON"}

    except Exception as e:
        return {"error": str(e), "product_name": product_name}


# ═══════════════════════════════════════════════════════════════════
#  VIDEO GENERATOR (Claude + Magnific MCP)
# ═══════════════════════════════════════════════════════════════════

GENERATE_SYSTEM = """You are a video production assistant. You have access to Magnific tools.

Your job:
1. Upload the product image to Magnific using creations_upload_image with the provided URL
2. Generate a video using video_generate with:
   - The prompt provided
   - The uploaded creation as image reference
   - Model slug: bytedance-seedance-fast-2.0
   - Aspect ratio: 9:16, resolution: 720p
   - Duration as specified

Return ONLY valid JSON (no markdown):
{{"creation_id": "the magnific creation identifier", "status": "queued", "error": null}}
"""

def generate_video(
    api_key: str,
    magnific_token: str,
    image_url: str,
    prompt: str,
    duration: int,
) -> dict:
    """Upload image + generate video via Magnific MCP."""
    mcp_servers = [{
        "type": "url",
        "url": MAGNIFIC_MCP_URL,
        "name": MAGNIFIC_MCP_NAME,
    }]
    if magnific_token:
        mcp_servers[0]["authorization_token"] = magnific_token

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=GENERATE_SYSTEM,
            messages=[{
                "role": "user",
                "content": (
                    f"Upload this image and generate a {duration}s video.\n"
                    f"Image URL: {image_url}\n"
                    f"Prompt:\n{prompt}"
                ),
            }],
            mcp_servers=mcp_servers,
            tools=[{"type": "mcp_toolset", "mcp_server_name": MAGNIFIC_MCP_NAME}],
            betas=[MCP_BETA],
        )

        result = {"creation_id": None, "status": "unknown", "error": None}

        # Parse text response
        for block in response.content:
            if block.type == "text":
                try:
                    cleaned = re.sub(r'```json\s*|```\s*', '', block.text)
                    j = cleaned.find("{")
                    k = cleaned.rfind("}") + 1
                    if j >= 0 and k > j:
                        parsed = json.loads(cleaned[j:k])
                        result.update({k2: v for k2, v in parsed.items() if v is not None})
                except json.JSONDecodeError:
                    pass

            elif block.type == "mcp_tool_result":
                if hasattr(block, "content") and block.content:
                    for sub in block.content:
                        if hasattr(sub, "text"):
                            try:
                                tr = json.loads(sub.text)
                                if isinstance(tr, dict):
                                    if "creations" in tr:
                                        for c in tr["creations"]:
                                            if "identifier" in c:
                                                result["creation_id"] = c["identifier"]
                                                result["status"] = c.get("status", "queued")
                                    elif "identifier" in tr:
                                        result["creation_id"] = tr["identifier"]
                                        result["status"] = tr.get("status", "queued")
                            except (json.JSONDecodeError, TypeError):
                                pass

        return result

    except Exception as e:
        return {"creation_id": None, "status": "error", "error": str(e)}


# ═══════════════════════════════════════════════════════════════════
#  STATUS CHECKER — polls Magnific for finished videos
# ═══════════════════════════════════════════════════════════════════

CHECK_STATUS_SYSTEM = """You have access to Magnific tools. Check the status of a creation
and return its details.

Use creations_get with the identifier provided. Return ONLY valid JSON (no markdown):
{"status": "completed|queued|processing|error", "url": "full-res video URL or null", "preview_url": "preview URL or null"}

If the creation is a video and it's completed, the url field should contain the video URL.
Extract URLs from the creation data — look for fields like url, videoUrl, previewUrl, etc.
"""

def check_creation_status(api_key: str, magnific_token: str, creation_id: str) -> dict:
    """Check a Magnific creation's status via MCP."""
    mcp_servers = [{
        "type": "url",
        "url": MAGNIFIC_MCP_URL,
        "name": MAGNIFIC_MCP_NAME,
    }]
    if magnific_token:
        mcp_servers[0]["authorization_token"] = magnific_token

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=CHECK_STATUS_SYSTEM,
            messages=[{
                "role": "user",
                "content": f"Check the status of creation: {creation_id}"
            }],
            mcp_servers=mcp_servers,
            tools=[{"type": "mcp_toolset", "mcp_server_name": MAGNIFIC_MCP_NAME}],
            betas=[MCP_BETA],
        )

        result = {"status": "unknown", "url": None, "preview_url": None}

        for block in response.content:
            if block.type == "text":
                try:
                    cleaned = re.sub(r'```json\s*|```\s*', '', block.text)
                    j = cleaned.find("{")
                    k = cleaned.rfind("}") + 1
                    if j >= 0 and k > j:
                        parsed = json.loads(cleaned[j:k])
                        result.update({k2: v for k2, v in parsed.items() if v is not None})
                except json.JSONDecodeError:
                    pass

            elif block.type == "mcp_tool_result":
                if hasattr(block, "content") and block.content:
                    for sub in block.content:
                        if hasattr(sub, "text"):
                            try:
                                tr = json.loads(sub.text)
                                if isinstance(tr, dict):
                                    # Extract video URL from creation data
                                    for url_key in ["url", "videoUrl", "video_url", "previewUrl", "preview_url"]:
                                        if url_key in tr and tr[url_key]:
                                            if "preview" in url_key.lower():
                                                result["preview_url"] = tr[url_key]
                                            else:
                                                result["url"] = tr[url_key]
                                    if "status" in tr:
                                        result["status"] = tr["status"]
                            except (json.JSONDecodeError, TypeError):
                                pass

        return result

    except Exception as e:
        return {"status": "error", "url": None, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════
#  STREAMLIT UI
# ═══════════════════════════════════════════════════════════════════

def get_secret(key: str) -> str:
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        return os.environ.get(key, "")


def main():
    inject_apple_glass_css()

    # ── Header ──
    st.markdown(
        """
        <section class="apple-hero">
            <div class="apple-kicker">✦ AI VIDEO WORKSPACE</div>
            <h1>Seedance Studio</h1>
            <p>Turn TikTok Shop products into finished vertical videos, then refine the text styling with reusable presets and Apple-style emoji overlays.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    # ── Sidebar ──
    with st.sidebar:
        st.header("⚙️ Settings")

        # Anthropic key
        api_key = get_secret("ANTHROPIC_API_KEY")
        if api_key:
            st.success("🔑 Anthropic key loaded")
        else:
            api_key = st.text_input("Anthropic API Key", type="password")

        st.divider()

        # Magnific token
        st.subheader("🔄 Magnific Token")
        saved_token = get_secret("MAGNIFIC_AUTH_TOKEN")
        magnific_token = st.text_input(
            "Paste token here",
            type="password",
            value=saved_token,
        )

        if magnific_token:
            st.success("✅ Token set — auto-generate enabled")
        else:
            st.info("ℹ️ No token — you'll get prompts to generate manually")

        with st.expander("📖 How to get / refresh the token"):
            st.markdown("""
**You need:** A computer with Node.js installed.

**Steps:**
1. Open Terminal and run:
   ```
   npx @modelcontextprotocol/inspector
   ```
2. A browser page opens. Set:
   - **Transport Type** → `Streamable HTTP`
   - **URL** → `https://mcp.magnific.com`
3. Click **Connect**
4. Click **"Open Auth Settings"**
5. Click **"Quick OAuth Flow"**
6. **Log in** with the Magnific account
7. Click **Continue** until it says **"Authentication complete"**
8. **Copy the `access_token`** value
9. **Paste it above** ⬆️

The token lasts a few hours. When you see auth errors,
repeat these steps to get a fresh one.

**Don't have Node.js?** Ask Sky to get you a token.
            """)

        st.divider()

        # Video style
        st.subheader("🎨 Video Style")
        style = st.radio(
            "Choose style:",
            options=["shoe_video", "texthook_broll"],
            format_func=lambda x: {
                "shoe_video": "👟 Shoe Video (feet-only, 15s)",
                "texthook_broll": "📱 Text-Hook B-Roll (reveal, 8s)",
            }[x],
        )

        if style == "shoe_video":
            duration = st.select_slider("Duration", options=[5, 10, 15], value=15)
            voice_script = st.text_area(
                "Voiceover (optional)",
                placeholder="Leave empty for silent video",
                height=80,
            )
        else:
            duration = 8
            voice_script = None
            st.caption("Always 8s and silent. The clean video is generated first; add or modify text afterward in Past Generations.")

    # ════════════════════════════════════════════════════════════════
    #  STEP 1 — PASTE LINKS
    # ════════════════════════════════════════════════════════════════
    st.subheader("① Paste Product Links")
    links_input = st.text_area(
        "One TikTok Shop URL per line",
        placeholder=(
            "https://shop.tiktok.com/us/pdp/womens-leopard-bow-slipper.../123456\n"
            "https://shop.tiktok.com/us/pdp/suede-clogs-cork-footbed.../789012"
        ),
        height=120,
        label_visibility="collapsed",
    )

    scrape_btn = st.button("🔍 Scrape Product Photos", use_container_width=True)

    links = [
        line.strip() for line in links_input.strip().split("\n")
        if line.strip() and not line.strip().startswith("#")
    ] if links_input.strip() else []

    # ════════════════════════════════════════════════════════════════
    #  STEP 2 — SCRAPE + SELECT PHOTOS
    # ════════════════════════════════════════════════════════════════
    if scrape_btn and not links:
        st.warning("Paste at least one product link.")

    if scrape_btn and links:
        st.divider()
        st.subheader("② Select the Right Photo for Each Product")
        st.caption("Some products have multiple colors or angles — pick the one you want in the video.")

        scraped_products = []
        progress = st.progress(0, text="Scraping...")

        for i, url in enumerate(links):
            progress.progress(i / len(links), text=f"Scraping {i+1}/{len(links)}...")
            scraped = scrape_product(url)

            if scraped and scraped["images"]:
                scraped_products.append(scraped)
            else:
                st.error(f"❌ Couldn't scrape: {url[:70]}...")

        progress.progress(1.0, text=f"Found {len(scraped_products)} product(s)")

        if scraped_products:
            # Store in session state so selections persist
            st.session_state["scraped"] = scraped_products
        else:
            st.error("No products could be scraped. Check your links.")

    # ── Show image selection if we have scraped data (doesn't block the rest of the page) ──
    if "scraped" in st.session_state:
        scraped_products = st.session_state["scraped"]
        selections = {}  # product_index → selected image url

        for idx, product in enumerate(scraped_products):
            st.markdown(f"---")
            st.markdown(f"### {product['name']}")
            st.caption(f"Source: {product['source_url'][:80]}...")

            images = product["images"]

            if len(images) == 1:
                # Only one image — auto-select, still show it
                selections[idx] = images[0]
                try:
                    st.image(images[0], width=200)
                except Exception:
                    st.caption(f"Image: {images[0][:60]}...")
            else:
                # Multiple images — let VA pick
                cols = st.columns(min(len(images), 4))
                for img_idx, img_url in enumerate(images[:8]):
                    with cols[img_idx % 4]:
                        try:
                            st.image(img_url, width=150, caption=f"Option {img_idx + 1}")
                        except Exception:
                            st.caption(f"Option {img_idx + 1}: {img_url[:40]}...")

                selected = st.radio(
                    f"Pick photo for **{product['name'][:40]}**:",
                    options=list(range(len(images[:8]))),
                    format_func=lambda x: f"Option {x + 1}",
                    key=f"select_{idx}",
                    horizontal=True,
                )
                selections[idx] = images[selected]

        # ════════════════════════════════════════════════════════════════
        #  STEP 3 — GENERATE OR GET PROMPTS
        # ════════════════════════════════════════════════════════════════
        st.divider()
        st.subheader("③ Generate")

        has_token = bool(magnific_token)

        # ── Build final product list with selected images ──
        final_products = []
        for idx, product in enumerate(scraped_products):
            final_products.append({
                "name": product["name"],
                "image_url": selections.get(idx, product["images"][0]),
                "source_url": product["source_url"],
            })

        # ── For texthook_broll: pick hooks FIRST, then generate ──
        hooks_ready = True  # True for shoe_video (no hooks needed)
        if style == "texthook_broll":
            hooks_ready = False

            # ── Step 3a: Generate hook options ──
            if "product_hooks" not in st.session_state:
                st.session_state["product_hooks"] = {}

            hooks_btn = st.button("📝 Step 1 — Generate Hook Options",
                                   type="primary" if not st.session_state["product_hooks"] else "secondary",
                                   use_container_width=True)

            if hooks_btn and api_key:
                progress = st.progress(0, text="Generating hook options...")
                for i, product in enumerate(final_products):
                    progress.progress(i / len(final_products),
                                      text=f"Hooks {i+1}/{len(final_products)}: {product['name'][:30]}...")
                    with st.spinner(f"Writing hooks for {product['name'][:30]}..."):
                        hook_result = write_hooks(api_key, product["name"])
                    st.session_state["product_hooks"][i] = {
                        "product_name": product["name"],
                        "hook_options": hook_result.get("hook_options", []),
                        "caption": hook_result.get("caption", ""),
                        "hashtags": hook_result.get("hashtags", ""),
                        "accepted_hook": None,
                    }
                    if hook_result.get("error"):
                        st.error(f"❌ {product['name']}: {hook_result['error']}")
                progress.progress(1.0, text="Done!")
                st.rerun()
            elif hooks_btn and not api_key:
                st.error("❌ Anthropic API key is missing. Ask Sky to set it up.")

            # ── Step 3b: Show hooks + pick/accept ──
            if st.session_state["product_hooks"]:
                all_accepted = True
                for i, product in enumerate(final_products):
                    hook_data = st.session_state["product_hooks"].get(i)
                    if not hook_data or not hook_data.get("hook_options"):
                        all_accepted = False
                        continue

                    st.markdown(f"---")
                    st.markdown(f"**{product['name']}** — Pick on-screen text hook:")

                    if hook_data.get("accepted_hook"):
                        st.success(f"✅ Accepted: {hook_data['accepted_hook']}")
                        if st.button("Change hook", key=f"changehook_{i}"):
                            st.session_state["product_hooks"][i]["accepted_hook"] = None
                            st.rerun()
                    else:
                        all_accepted = False
                        picked = st.radio(
                            "Options:",
                            options=list(range(len(hook_data["hook_options"]))),
                            format_func=lambda x, hd=hook_data: hd["hook_options"][x],
                            key=f"hookpick_{i}",
                            label_visibility="collapsed",
                        )
                        if st.button("✅ Accept this hook", key=f"accepthook_{i}"):
                            st.session_state["product_hooks"][i]["accepted_hook"] = hook_data["hook_options"][picked]
                            st.rerun()

                    if hook_data.get("caption"):
                        st.caption(f"Caption: {hook_data['caption']}")
                    if hook_data.get("hashtags"):
                        st.caption(f"Hashtags: {hook_data['hashtags']}")

                hooks_ready = all_accepted
                if not hooks_ready:
                    st.info("👆 Accept a hook for each product, then generate.")
                else:
                    st.success("✅ All hooks accepted! Ready to generate.")

        # ── Step 3c: Generate buttons (only appear when hooks are ready) ──
        auto_btn = False
        prompt_btn = False
        if hooks_ready:
            st.markdown("---")
            if has_token:
                col1, col2 = st.columns(2)
                auto_btn = col1.button("🎬 Step 2 — Auto-Generate Videos" if style == "texthook_broll" else "🎬 Auto-Generate Videos",
                                        type="primary", use_container_width=True)
                prompt_btn = col2.button("📝 Just Get Prompts", use_container_width=True)
            else:
                prompt_btn = st.button("📝 Get Prompts + Images (generate manually in Magnific)",
                                       type="primary", use_container_width=True)

        if (auto_btn or prompt_btn) and not api_key:
            st.error("❌ Anthropic API key is missing. Ask Sky to set it up.")
            auto_btn = False
            prompt_btn = False
    else:
        auto_btn = False
        prompt_btn = False
        final_products = []

    # ════════════════════════════════════════════════════════════════
    #  PROMPT-ONLY MODE
    # ════════════════════════════════════════════════════════════════
    if prompt_btn:
        st.divider()
        st.subheader("📝 Prompts & Images")
        st.caption("Copy each prompt and generate manually in Magnific → magnific.com/ai/video-generator")

        results = []
        progress = st.progress(0, text="Writing prompts...")

        for i, product in enumerate(final_products):
            progress.progress(i / len(final_products), text=f"Writing prompt {i+1}/{len(final_products)}...")

            # Get the accepted hook for texthook_broll style
            selected_hook = None
            hook_data_for_product = None
            if style == "texthook_broll":
                hook_data_for_product = st.session_state.get("product_hooks", {}).get(i)
                if hook_data_for_product:
                    selected_hook = hook_data_for_product.get("accepted_hook")

            with st.spinner(f"Writing prompt for {product['name'][:30]}..."):
                result = write_prompt(
                    api_key=api_key,
                    product_name=product["name"],
                    style=style,
                    duration=duration,
                    voice_script=voice_script if voice_script else None,
                    selected_hook=selected_hook,
                )

            # Carry over hook data into result for persistence
            if hook_data_for_product:
                result["accepted_hook"] = selected_hook
                result["hook_options"] = hook_data_for_product.get("hook_options", [])
                result["caption"] = hook_data_for_product.get("caption")
                result["hashtags"] = hook_data_for_product.get("hashtags")

            results.append(result)

            st.markdown(f"---")
            st.markdown(f"### {product['name']}")

            # Show selected image
            col_img, col_prompt = st.columns([1, 2])
            with col_img:
                try:
                    st.image(product["image_url"], width=250)
                except Exception:
                    st.caption(f"Image URL:\n{product['image_url'][:80]}")

                st.text_input(
                    "Image URL (copy this):",
                    value=product["image_url"],
                    key=f"imgurl_{i}",
                )

            with col_prompt:
                if result.get("prompt"):
                    st.text_area(
                        "Seedance Prompt (copy this):",
                        value=result["prompt"],
                        height=250,
                        key=f"prompt_{i}",
                    )
                    char_count = result.get("char_count", len(result["prompt"]))
                    st.caption(f"Characters: {char_count}")
                elif result.get("error"):
                    st.error(f"Error: {result['error']}")

                # Show the selected hook. The text can be added later in the completed-video editor.
                if result.get("accepted_hook"):
                    st.success(f"📝 Selected hook: {result['accepted_hook']}")
                if result.get("caption"):
                    st.text_input("Caption:", value=result["caption"], key=f"cap_{i}")
                if result.get("hashtags"):
                    st.text_input("Hashtags:", value=result["hashtags"], key=f"hash_{i}")

            time.sleep(1)  # Rate limit

        progress.progress(1.0, text="Done!")

        # Persist to file so hooks can be reviewed/accepted below without re-running
        for r, fp in zip(results, final_products):
            entry = dict(r)
            entry["product_name"] = fp["name"]
            entry["image_url"] = fp["image_url"]
            entry["source_url"] = fp["source_url"]
            entry["style"] = style
            entry["status"] = "prompt_only"
            entry["generated_at"] = datetime.now().isoformat()
            add_generation(entry)

        # Manual generation instructions
        st.divider()
        st.info("""
**How to generate manually in Magnific:**
1. Go to [magnific.com/ai/video-generator](https://www.magnific.com/ai/video-generator)
2. Select model **Seedance 2.0 Fast**
3. Upload the product image (copy the URL above, or save the image first)
4. Paste the prompt
5. Set aspect ratio to **9:16**, resolution **720p**
6. Click **Generate**
        """)

        # Download all prompts
        st.download_button(
            "📥 Download All Prompts (JSON)",
            data=json.dumps({
                "generated_at": datetime.now().isoformat(),
                "style": style,
                "products": [
                    {
                        "name": fp["name"],
                        "image_url": fp["image_url"],
                        "source_url": fp["source_url"],
                        "prompt": r.get("prompt", ""),
                        "accepted_hook": r.get("accepted_hook"),
                        "hook_options": r.get("hook_options"),
                        "caption": r.get("caption"),
                        "hashtags": r.get("hashtags"),
                    }
                    for fp, r in zip(final_products, results)
                ],
            }, indent=2),
            file_name=f"prompts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
        )

    # ════════════════════════════════════════════════════════════════
    #  AUTO-GENERATE MODE
    # ════════════════════════════════════════════════════════════════
    if auto_btn:
        st.divider()
        st.subheader("🎬 Generating Videos")

        results = []
        progress = st.progress(0, text="Starting...")
        token_expired = False

        for i, product in enumerate(final_products):
            if token_expired:
                break

            progress.progress(i / len(final_products),
                              text=f"Processing {i+1}/{len(final_products)}: {product['name'][:30]}...")

            # Step A: Write the prompt (cheap, no MCP)
            selected_hook = None
            hook_data_for_product = None
            if style == "texthook_broll":
                hook_data_for_product = st.session_state.get("product_hooks", {}).get(i)
                if hook_data_for_product:
                    selected_hook = hook_data_for_product.get("accepted_hook")

            with st.spinner(f"Writing prompt for {product['name'][:30]}..."):
                prompt_result = write_prompt(
                    api_key=api_key,
                    product_name=product["name"],
                    style=style,
                    duration=duration,
                    voice_script=voice_script if voice_script else None,
                    selected_hook=selected_hook,
                )

            if prompt_result.get("error") or not prompt_result.get("prompt"):
                st.error(f"❌ **{product['name']}** — Prompt error: {prompt_result.get('error', 'No prompt')}")
                results.append({"product_name": product["name"], "status": "error",
                                "error": prompt_result.get("error"), "creation_id": None})
                continue

            prompt_text = prompt_result["prompt"]

            # Step B: Generate via Magnific MCP
            with st.spinner(f"Generating video for {product['name'][:30]}... (may take a minute)"):
                gen_result = generate_video(
                    api_key=api_key,
                    magnific_token=magnific_token,
                    image_url=product["image_url"],
                    prompt=prompt_text,
                    duration=duration if style == "shoe_video" else 8,
                )

            gen_result["product_name"] = product["name"]
            gen_result["prompt_used"] = prompt_text
            results.append(gen_result)

            if gen_result.get("creation_id") and gen_result["status"] == "queued":
                st.success(f"✅ **{product['name']}** — Creation ID: `{gen_result['creation_id']}`")
            elif gen_result["status"] == "error":
                error_msg = gen_result.get("error", "")
                st.error(f"❌ **{product['name']}** — {error_msg}")

                if any(kw in error_msg.lower() for kw in ['401', 'unauthorized', 'auth', 'token', 'forbidden', '403']):
                    st.warning("🔄 **Token expired.** Paste a fresh token in the sidebar and re-run.")
                    token_expired = True

                    # Show the prompt so they can still use it manually
                    with st.expander(f"📝 Prompt for {product['name']} (use manually)"):
                        st.code(prompt_text, language=None)
                        st.text_input("Image URL:", value=product["image_url"], key=f"fallback_img_{i}")
            else:
                st.warning(f"⚠️ **{product['name']}** — Status: {gen_result['status']}")

            # Save the hook as the starting text for the completed-video editor
            if hook_data_for_product:
                gen_result["accepted_hook"] = selected_hook
                gen_result["hook_options"] = hook_data_for_product.get("hook_options", [])
                gen_result["caption"] = hook_data_for_product.get("caption")
                gen_result["hashtags"] = hook_data_for_product.get("hashtags")
                if selected_hook:
                    st.info(f"📝 Hook saved for the text editor: {selected_hook}")
                if hook_data_for_product.get("caption"):
                    st.caption(f"Caption: {hook_data_for_product['caption']}")
                if hook_data_for_product.get("hashtags"):
                    st.caption(f"Hashtags: {hook_data_for_product['hashtags']}")

            if i < len(final_products) - 1:
                time.sleep(5)

        progress.progress(1.0, text="Done!")

        # Save each result to persistent file
        for r, fp in zip(results, final_products):
            r["image_url"] = fp["image_url"]
            r["source_url"] = fp["source_url"]
            r["style"] = style
            r["duration"] = duration if style == "shoe_video" else 8
            r["generated_at"] = datetime.now().isoformat()
            add_generation(r)

        # Summary
        st.divider()
        queued = sum(1 for r in results if r.get("status") == "queued")
        errors = sum(1 for r in results if r.get("status") == "error")

        col1, col2, col3 = st.columns(3)
        col1.metric("Total", len(results))
        col2.metric("Queued ✅", queued)
        col3.metric("Errors ❌", errors)

    # ════════════════════════════════════════════════════════════════
    #  STEP 4 — PAST GENERATIONS (persisted to file, survives refresh)
    # ════════════════════════════════════════════════════════════════
    saved_gens = load_generations()

    if saved_gens:
        st.divider()
        st.subheader("④ Past Generations")
        st.caption(f"{len(saved_gens)} saved — completed videos stay clean until you open the text editor and apply your settings.")

        # Bulk actions
        action_col1, action_col2, action_col3 = st.columns(3)
        if magnific_token and api_key:
            check_all = action_col1.button("🔄 Refresh & Show Finished", use_container_width=True)
        else:
            check_all = False
        clear_completed = action_col2.button("🧹 Clear Completed", use_container_width=True)
        clear_all = action_col3.button("🗑️ Clear All", use_container_width=True)

        if clear_all:
            save_generations([])
            st.rerun()

        if clear_completed:
            remaining = [g for g in saved_gens if g.get("status") != "completed"]
            save_generations(remaining)
            st.rerun()

        # Display each generation
        needs_save = False

        for i, result in enumerate(saved_gens):
            creation_id = result.get("creation_id")
            product_name = result.get("product_name", "Unknown")
            status = result.get("status", "unknown")
            generated_at = result.get("generated_at", "")

            st.markdown("---")

            status_badges = {
                "queued": "🟡 Queued",
                "processing": "🟠 Processing",
                "completed": "🟢 Completed",
                "error": "🔴 Error",
                "prompt_only": "📝 Prompt Only (manual generation)",
            }
            badge = status_badges.get(status, f"⚪ {status}")

            # Timestamp
            time_str = ""
            if generated_at:
                try:
                    dt = datetime.fromisoformat(generated_at)
                    time_str = f" · {dt.strftime('%b %d, %I:%M %p')}"
                except Exception:
                    pass

            col_info, col_actions = st.columns([3, 1])

            with col_info:
                st.markdown(f"**{product_name}** — {badge}{time_str}")
                if creation_id:
                    st.caption(f"Creation ID: `{creation_id}`")

                # Completed videos are shown clean first. FFmpeg does nothing until
                # the user opens the editor and clicks Apply / Update Text.
                video_url = result.get("url") or result.get("preview_url")
                if video_url and status == "completed":
                    video_col, _spacer = st.columns([1, 2])
                    with video_col:
                        st.caption("Original clean video")
                        try:
                            st.video(video_url)
                        except Exception:
                            st.markdown(f"🎬 [Watch original video]({video_url})")

                        original_bytes = fetch_video_bytes(video_url)
                        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", product_name)[:40]
                        if original_bytes:
                            st.download_button(
                                "⬇️ Download original",
                                data=original_bytes,
                                file_name=f"{safe_name}_{creation_id or i}_original.mp4",
                                mime="video/mp4",
                                key=f"dl_original_{i}",
                                use_container_width=True,
                            )

                        processed_bytes = read_local_video(result.get("processed_path"))
                        if processed_bytes:
                            st.divider()
                            st.caption("Edited text version")
                            st.video(processed_bytes)
                            st.download_button(
                                "⬇️ Download text version",
                                data=processed_bytes,
                                file_name=f"{safe_name}_{creation_id or i}_with_text.mp4",
                                mime="video/mp4",
                                key=f"dl_processed_{i}",
                                use_container_width=True,
                            )

                # Show product image thumbnail
                if result.get("image_url") and status != "completed":
                    try:
                        st.image(result["image_url"], width=120)
                    except Exception:
                        pass

            with col_actions:
                # Check status
                if creation_id and status not in ("completed", "error") and magnific_token and api_key:
                    if st.button("🔄 Check", key=f"chk_{i}") or check_all:
                        with st.spinner("Checking..."):
                            status_result = check_creation_status(
                                api_key, magnific_token, creation_id
                            )
                        saved_gens[i]["status"] = status_result.get("status", status)
                        if status_result.get("url"):
                            saved_gens[i]["url"] = status_result["url"]
                        if status_result.get("preview_url"):
                            saved_gens[i]["preview_url"] = status_result["preview_url"]
                        needs_save = True

                # Regenerate
                if result.get("prompt_used") and result.get("image_url") and magnific_token and api_key:
                    if st.button("🔁 Regen", key=f"regen_{i}"):
                        with st.spinner("Regenerating..."):
                            new_result = generate_video(
                                api_key=api_key,
                                magnific_token=magnific_token,
                                image_url=result["image_url"],
                                prompt=result["prompt_used"],
                                duration=result.get("duration", 15),
                            )
                        new_result["product_name"] = product_name
                        new_result["prompt_used"] = result["prompt_used"]
                        new_result["image_url"] = result["image_url"]
                        new_result["source_url"] = result.get("source_url", "")
                        new_result["style"] = result.get("style", "")
                        new_result["duration"] = result.get("duration", 15)
                        new_result["accepted_hook"] = result.get("accepted_hook")
                        new_result["hook_options"] = result.get("hook_options", [])
                        new_result["caption"] = result.get("caption")
                        new_result["hashtags"] = result.get("hashtags")
                        new_result["generated_at"] = datetime.now().isoformat()
                        # Add new generation, keep old one
                        add_generation(new_result)
                        st.rerun()

            # Expandable prompt (works for both "prompt_used" and "prompt" keys)
            prompt_text_field = result.get("prompt_used") or result.get("prompt")
            if prompt_text_field:
                with st.expander(f"📋 Prompt — {product_name}", expanded=False):
                    st.code(prompt_text_field, language=None)
                    if result.get("image_url"):
                        st.text_input("Image URL:", value=result["image_url"], key=f"img_{i}")

            # Text is applied only here, after the video has finished. Every setting
            # can be changed and applied again without regenerating the AI video.
            video_url = result.get("url") or result.get("preview_url")
            if video_url and status == "completed":
                has_processed_version = bool(read_local_video(result.get("processed_path")))
                editor_title = "✍️ Modify on-screen text" if has_processed_version else "✍️ Add on-screen text"

                with st.expander(editor_title, expanded=False):
                    st.caption(
                        "The original video stays untouched. Change the settings below, "
                        "then click Apply / Update Text to create a separate version."
                    )

                    presets, preset_data = all_text_presets()
                    default_preset_settings, default_preset_name = default_text_settings_from_presets()

                    if result.get("text_settings"):
                        stored_settings = normalize_text_settings(result.get("text_settings"))
                    else:
                        stored_settings = dict(default_preset_settings)

                    active_preset_name = result.get("text_preset_name") or default_preset_name
                    if active_preset_name not in presets:
                        active_preset_name = default_preset_name

                    # Initialize each editor once. Preset buttons update these keys
                    # before the sliders render, so the selected style loads cleanly.
                    widget_keys = [
                        f"editor_size_{i}",
                        f"editor_width_{i}",
                        f"editor_position_{i}",
                        f"editor_outline_{i}",
                        f"editor_spacing_{i}",
                        f"editor_emoji_{i}",
                    ]
                    if not any(key in st.session_state for key in widget_keys):
                        set_editor_widget_values(i, stored_settings)

                    st.markdown('<span class="preset-pill">TEXT STYLE PRESETS</span>', unsafe_allow_html=True)
                    preset_col, load_col, default_col = st.columns([2.2, 1, 1.25])
                    with preset_col:
                        selected_preset = st.selectbox(
                            "Preset",
                            options=list(presets.keys()),
                            index=list(presets.keys()).index(active_preset_name),
                            key=f"preset_select_{i}",
                            help="Load a saved style across any completed video.",
                        )
                    with load_col:
                        st.write("")
                        if st.button(
                            "Load",
                            key=f"load_preset_{i}",
                            use_container_width=True,
                        ):
                            set_editor_widget_values(i, presets[selected_preset])
                            saved_gens[i]["text_preset_name"] = selected_preset
                            save_generations(saved_gens)
                            st.rerun()
                    with default_col:
                        st.write("")
                        if st.button(
                            "Use by default",
                            key=f"default_preset_{i}",
                            use_container_width=True,
                            help="New text editors will start with this preset.",
                        ):
                            preset_data["default"] = selected_preset
                            save_text_presets_data(preset_data)
                            st.success(f"{selected_preset} is now your default preset.")

                    edited_hook = st.text_area(
                        "Hook text",
                        value=result.get("accepted_hook", ""),
                        key=f"editor_hook_{i}",
                        height=90,
                    )

                    size_col, width_col, position_col = st.columns(3)
                    with size_col:
                        font_size = st.slider(
                            "Text size",
                            min_value=16,
                            max_value=48,
                            step=1,
                            key=f"editor_size_{i}",
                            help="Font height in pixels. 24–30 usually matches compact TikTok text.",
                        )
                    with width_col:
                        max_width_pct = st.slider(
                            "Text width",
                            min_value=45,
                            max_value=92,
                            step=1,
                            key=f"editor_width_{i}",
                            help="A wider text box creates fewer lines.",
                        )
                    with position_col:
                        vertical_position_pct = st.slider(
                            "Vertical position",
                            min_value=8,
                            max_value=60,
                            step=1,
                            key=f"editor_position_{i}",
                            help="Percentage down from the top of the video.",
                        )

                    outline_col, spacing_col, emoji_col = st.columns(3)
                    with outline_col:
                        outline_width = st.slider(
                            "Outline thickness",
                            min_value=1,
                            max_value=5,
                            step=1,
                            key=f"editor_outline_{i}",
                        )
                    with spacing_col:
                        line_spacing_pct = st.slider(
                            "Line spacing",
                            min_value=95,
                            max_value=145,
                            step=1,
                            key=f"editor_spacing_{i}",
                        )
                    with emoji_col:
                        emoji_size_px = st.slider(
                            "Emoji size",
                            min_value=18,
                            max_value=90,
                            step=2,
                            key=f"editor_emoji_{i}",
                            help="Exact visible emoji height in pixels. Transparent padding is removed before resizing.",
                        )

                    editor_settings = normalize_text_settings({
                        "font_size": font_size,
                        "max_width_pct": max_width_pct,
                        "vertical_position_pct": vertical_position_pct,
                        "outline_width": outline_width,
                        "line_spacing_pct": line_spacing_pct,
                        "emoji_size_px": emoji_size_px,
                    })

                    st.markdown('<span class="preset-pill">SAVE THIS STYLE</span>', unsafe_allow_html=True)
                    save_name_col, save_button_col, delete_button_col = st.columns([2.2, 1, 1])
                    with save_name_col:
                        custom_preset_name = st.text_input(
                            "Preset name",
                            placeholder="My favorite style",
                            key=f"custom_preset_name_{i}",
                            label_visibility="collapsed",
                        )
                    with save_button_col:
                        if st.button(
                            "Save preset",
                            key=f"save_preset_{i}",
                            type="primary",
                            use_container_width=True,
                        ):
                            cleaned_name = custom_preset_name.strip()
                            if not cleaned_name:
                                st.error("Enter a preset name first.")
                            elif cleaned_name in BUILT_IN_TEXT_PRESETS:
                                st.error("Choose a different name; built-in presets cannot be overwritten.")
                            else:
                                preset_data.setdefault("presets", {})[cleaned_name] = editor_settings
                                save_text_presets_data(preset_data)
                                saved_gens[i]["text_preset_name"] = cleaned_name
                                save_generations(saved_gens)
                                st.success(f"Saved preset: {cleaned_name}")
                                st.rerun()
                    with delete_button_col:
                        can_delete_preset = selected_preset not in BUILT_IN_TEXT_PRESETS
                        if st.button(
                            "Delete",
                            key=f"delete_preset_{i}",
                            disabled=not can_delete_preset,
                            use_container_width=True,
                            help="Only custom presets can be deleted.",
                        ):
                            preset_data.get("presets", {}).pop(selected_preset, None)
                            if preset_data.get("default") == selected_preset:
                                preset_data["default"] = "Apple Compact"
                            save_text_presets_data(preset_data)
                            saved_gens[i]["text_preset_name"] = "Apple Compact"
                            save_generations(saved_gens)
                            st.rerun()

                    available_assets = sum(
                        1 for filename in EMOJI_ASSET_MAP.values()
                        if (EMOJI_ASSET_DIR / filename).exists()
                    )
                    st.caption(
                        f"Apple-style emoji PNGs found: {available_assets}/{len(EMOJI_ASSET_MAP)}. "
                        "The editor uses a PNG when the hook ends with a supported emoji."
                    )

                    apply_col, remove_col = st.columns(2)
                    apply_label = "🎨 Update text version" if has_processed_version else "🎨 Apply text"

                    if apply_col.button(apply_label, key=f"apply_text_{i}", type="primary", use_container_width=True):
                        with st.spinner("Applying your text settings with FFmpeg..."):
                            output_path, editor_warning = apply_text_with_ffmpeg(
                                video_url=video_url,
                                creation_id=creation_id,
                                hook=edited_hook.strip(),
                                settings=editor_settings,
                            )

                        if output_path:
                            old_path = result.get("processed_path")
                            if old_path and old_path != str(output_path):
                                try:
                                    Path(old_path).unlink(missing_ok=True)
                                except Exception:
                                    pass

                            saved_gens[i]["accepted_hook"] = edited_hook.strip()
                            saved_gens[i]["text_settings"] = editor_settings
                            saved_gens[i]["text_preset_name"] = selected_preset
                            saved_gens[i]["processed_path"] = str(output_path)
                            saved_gens[i]["processed_at"] = datetime.now().isoformat()
                            save_generations(saved_gens)
                            if editor_warning:
                                st.warning(editor_warning)
                            st.rerun()
                        else:
                            st.error(f"Text editor error: {editor_warning or 'Unknown error'}")

                    if has_processed_version and remove_col.button(
                        "🗑️ Remove text version",
                        key=f"remove_text_{i}",
                        use_container_width=True,
                    ):
                        old_path = result.get("processed_path")
                        if old_path:
                            try:
                                Path(old_path).unlink(missing_ok=True)
                            except Exception:
                                pass
                        saved_gens[i].pop("processed_path", None)
                        saved_gens[i].pop("processed_at", None)
                        save_generations(saved_gens)
                        st.rerun()

                    if result.get("hook_options"):
                        st.caption("Other generated hook options:")
                        for hook_option in result["hook_options"]:
                            st.caption(f"• {hook_option}")
                    if result.get("caption"):
                        st.caption(f"Caption: {result['caption']}")
                    if result.get("hashtags"):
                        st.caption(f"Hashtags: {result['hashtags']}")


        # Save any status updates
        if needs_save:
            save_generations(saved_gens)
            st.rerun()

        # Download
        st.divider()
        st.download_button(
            "📥 Download All (JSON)",
            data=json.dumps(saved_gens, indent=2, default=str),
            file_name=f"generations_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
        )


if __name__ == "__main__":
    main()