"""
Seedance Video Generator — Streamlit App (v2)
==============================================
Paste TikTok Shop links → pick a style → select the right product photo →
generate videos automatically OR get prompts to generate manually.
"""

import streamlit as st
import anthropic
import base64
import csv
import hashlib
import io
import zipfile
import json
import os
import re
import time
import random
import requests
import shutil
import subprocess
import tempfile
from datetime import datetime
from urllib.parse import urlparse, unquote
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
    initial_sidebar_state="collapsed",
)

# ── Persistent storage ─────────────────────────────────────────────
SAVE_FILE = Path("generations.json")
PRESETS_FILE = Path("text_presets.json")
PROCESSED_DIR = Path("processed_videos")
EMOJI_ASSET_DIR = Path("emoji_assets")
AUDIO_TRACK_DIR = Path("audio_tracks")
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_TRACK_DIR.mkdir(parents=True, exist_ok=True)

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
    "🤯": "exploding_head.png",
    "😱": "face_screaming_in_fear.png",
    "🤑": "money_mouth_face.png",
    "😅": "grinning_face_with_sweat.png",
}

FONT_FILES = {
    "TikTok Sans Medium": ["TikTokSans-Medium.ttf", "/mnt/data/TikTokSans-Medium.ttf"],
    "TikTok Sans": ["TikTokSans.ttf", "/mnt/data/TikTokSans.ttf"],
    "DejaVu Sans Bold": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "Liberation Sans Bold": ["/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"],
    "Arial Bold": ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "C:/Windows/Fonts/arialbd.ttf"],
}

FONT_CANDIDATES = [
    "TikTokSans-Medium.ttf",
    "/mnt/data/TikTokSans-Medium.ttf",
    "TikTokSans.ttf",
    "/mnt/data/TikTokSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]

DEFAULT_TEXT_SETTINGS = {
    "font_name": "TikTok Sans",
    "font_size": 48,
    "max_width_pct": 89,
    "vertical_position_pct": 12,
    "outline_width": 4,
    "line_spacing_pct": 99,
    "emoji_size_px": 50,
}

# One built-in text style only. All previous built-in presets were removed.
BUILT_IN_TEXT_PRESETS = {
    "Default": dict(DEFAULT_TEXT_SETTINGS),
}


def inject_apple_glass_css():
    """Apply a dark Apple-inspired glass UI without changing app behavior."""
    st.markdown(
        """
        <style>
        :root {
            --page-bg: #07090f;
            --page-bg-2: #0c1019;
            --sidebar-bg: rgba(9, 12, 19, 0.94);
            --glass-bg: rgba(20, 24, 34, 0.72);
            --glass-bg-strong: rgba(25, 30, 42, 0.90);
            --glass-border: rgba(255, 255, 255, 0.10);
            --glass-border-hover: rgba(255, 255, 255, 0.18);
            --glass-shadow: 0 20px 55px rgba(0, 0, 0, 0.42);
            --ink: #f5f7fb;
            --muted: #a5adbd;
            --muted-2: #7d8799;
            --accent: #5aa7ff;
            --accent-2: #8c7dff;
            --accent-soft: rgba(90, 167, 255, 0.14);
            --success: #45d483;
            --danger: #ff6961;
            --warning: #ffbd5a;
        }

        html, body, [class*="css"] {
            color-scheme: dark;
        }

        .stApp {
            background:
                radial-gradient(circle at 12% -8%, rgba(40, 112, 255, .18), transparent 34%),
                radial-gradient(circle at 92% 2%, rgba(124, 92, 255, .16), transparent 30%),
                radial-gradient(circle at 48% 105%, rgba(28, 175, 120, .08), transparent 34%),
                linear-gradient(145deg, var(--page-bg) 0%, var(--page-bg-2) 48%, #090c13 100%);
            color: var(--ink);
        }

        [data-testid="stAppViewContainer"],
        [data-testid="stAppViewContainer"] > .main,
        [data-testid="stMain"] {
            background: transparent !important;
        }

        .block-container {
            max-width: 1380px;
            padding-top: 1.5rem;
            padding-bottom: 4rem;
        }

        /* Global text */
        .stApp h1,
        .stApp h2,
        .stApp h3,
        .stApp h4,
        .stApp h5,
        .stApp h6,
        .stApp p,
        .stApp label,
        .stApp li,
        .stApp span,
        .stApp div[data-testid="stMarkdownContainer"] {
            color: var(--ink);
        }

        .stCaption,
        [data-testid="stCaptionContainer"],
        [data-testid="stCaptionContainer"] p,
        small {
            color: var(--muted) !important;
        }

        .apple-hero {
            position: relative;
            overflow: hidden;
            padding: 22px 26px;
            border-radius: 28px;
            background:
                linear-gradient(145deg, rgba(31, 37, 51, .90), rgba(18, 22, 31, .76));
            border: 1px solid var(--glass-border);
            box-shadow: var(--glass-shadow);
            backdrop-filter: blur(30px) saturate(145%);
            -webkit-backdrop-filter: blur(30px) saturate(145%);
            margin-bottom: .95rem;
        }

        .apple-hero:before {
            content: "";
            position: absolute;
            inset: 0;
            background: linear-gradient(120deg, rgba(255,255,255,.055), transparent 42%);
            pointer-events: none;
        }

        .apple-hero:after {
            content: "";
            position: absolute;
            width: 240px;
            height: 240px;
            right: -80px;
            top: -105px;
            border-radius: 999px;
            background: linear-gradient(135deg, rgba(50,136,255,.26), rgba(126,92,255,.18));
            filter: blur(10px);
            pointer-events: none;
        }

        .apple-hero h1 {
            position: relative;
            z-index: 1;
            margin: 0;
            font-size: clamp(2rem, 3.2vw, 2.8rem);
            letter-spacing: -0.045em;
            line-height: .98;
            font-weight: 800;
            color: #ffffff !important;
        }

        .apple-hero p {
            position: relative;
            z-index: 1;
            margin: 10px 0 0 0;
            color: #b1b9c8 !important;
            font-size: 1rem;
            max-width: 760px;
        }

        .apple-kicker {
            position: relative;
            z-index: 1;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 7px 11px;
            border-radius: 999px;
            background: rgba(68, 145, 255, .14);
            border: 1px solid rgba(90, 167, 255, .20);
            color: #8fc2ff !important;
            font-weight: 700;
            font-size: .78rem;
            margin-bottom: 14px;
        }

        /* Sidebar */
        /* Keep the sidebar opener visible when the sidebar is collapsed. */
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="stSidebarCollapseButton"],
        button[kind="headerNoPadding"] {
            visibility: visible !important;
            display: flex !important;
            opacity: 1 !important;
            z-index: 1000000 !important;
        }

        [data-testid="stSidebarCollapsedControl"] {
            position: fixed !important;
            top: 14px !important;
            left: 14px !important;
            width: 44px !important;
            height: 44px !important;
            align-items: center !important;
            justify-content: center !important;
            border-radius: 14px !important;
            background: rgba(24, 30, 43, .96) !important;
            border: 1px solid rgba(255,255,255,.18) !important;
            box-shadow: 0 12px 28px rgba(0,0,0,.38) !important;
            backdrop-filter: blur(18px) !important;
            -webkit-backdrop-filter: blur(18px) !important;
        }

        [data-testid="stSidebarCollapsedControl"] button,
        [data-testid="stSidebarCollapsedControl"] svg,
        [data-testid="stSidebarCollapseButton"] button,
        [data-testid="stSidebarCollapseButton"] svg {
            color: #ffffff !important;
            fill: #ffffff !important;
            stroke: #ffffff !important;
        }

        [data-testid="stSidebar"] {
            background:
                linear-gradient(180deg, rgba(13, 17, 25, .98), rgba(7, 10, 16, .98)) !important;
            border-right: 1px solid rgba(255,255,255,.08);
            box-shadow: 18px 0 45px rgba(0,0,0,.22);
            backdrop-filter: blur(30px) saturate(135%);
            -webkit-backdrop-filter: blur(30px) saturate(135%);
        }

        [data-testid="stSidebar"] > div:first-child {
            padding-top: 1.35rem;
        }

        [data-testid="stSidebar"] * {
            color: var(--ink) !important;
        }

        [data-testid="stSidebar"] .stCaption,
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] *,
        [data-testid="stSidebar"] small {
            color: var(--muted) !important;
        }

        /* This version keeps all controls in the main workspace. Hide the unused
           Streamlit sidebar and its tiny floating arrow completely. */
        [data-testid="stSidebar"],
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="stSidebarCollapseButton"] {
            display: none !important;
            visibility: hidden !important;
        }

        /* Glass cards */
        div[data-testid="stExpander"],
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 22px !important;
            border: 1px solid var(--glass-border) !important;
            background: var(--glass-bg) !important;
            box-shadow: var(--glass-shadow);
            backdrop-filter: blur(24px) saturate(135%);
            -webkit-backdrop-filter: blur(24px) saturate(135%);
        }

        div[data-testid="stExpander"] details,
        div[data-testid="stExpander"] summary {
            border: none !important;
            background: transparent !important;
            color: var(--ink) !important;
        }

        div[data-testid="stExpander"] summary:hover {
            color: white !important;
        }

        /* Buttons */
        .stButton > button,
        .stDownloadButton > button {
            min-height: 44px;
            border-radius: 14px !important;
            border: 1.4px solid rgba(122, 177, 255, .48) !important;
            background: linear-gradient(145deg, rgba(49,58,77,.98), rgba(24,29,41,.98)) !important;
            color: #ffffff !important;
            box-shadow: 0 10px 26px rgba(0,0,0,.28), 0 0 0 1px rgba(255,255,255,.03) inset !important;
            backdrop-filter: blur(16px);
            font-weight: 800 !important;
            transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease, background .16s ease;
        }

        .stButton > button p,
        .stDownloadButton > button p,
        .stButton > button span,
        .stDownloadButton > button span {
            color: #ffffff !important;
            font-weight: 800 !important;
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover {
            transform: translateY(-1px);
            border-color: rgba(151, 196, 255, .82) !important;
            background: linear-gradient(145deg, rgba(59,69,91,.99), rgba(31,37,52,.99)) !important;
            box-shadow: 0 14px 34px rgba(0,0,0,.38), 0 0 0 1px rgba(151,196,255,.18) inset !important;
        }

        .stButton > button[kind="primary"] {
            color: white !important;
            background: linear-gradient(135deg, #2d8fff, #7b5dff) !important;
            border: 1.4px solid rgba(212,230,255,.42) !important;
            box-shadow: 0 14px 34px rgba(35, 103, 226, .36), 0 0 0 1px rgba(255,255,255,.06) inset !important;
        }

        .stButton > button[kind="primary"]:hover {
            background: linear-gradient(135deg, #45a0ff, #8e70ff) !important;
            border-color: rgba(255,255,255,.54) !important;
        }

        button:disabled,
        .stButton > button:disabled {
            opacity: .45 !important;
            background: rgba(31,36,48,.72) !important;
        }

        /* Inputs */
        .stTextInput input,
        .stTextArea textarea,
        .stNumberInput input,
        div[data-baseweb="select"] > div,
        div[data-baseweb="base-input"] > div {
            border-radius: 14px !important;
            border: 1px solid rgba(255,255,255,.10) !important;
            background: rgba(8, 11, 17, .78) !important;
            color: #f5f7fb !important;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.025), 0 8px 20px rgba(0,0,0,.18);
        }

        .stTextInput input::placeholder,
        .stTextArea textarea::placeholder {
            color: #687286 !important;
            opacity: 1 !important;
        }

        .stTextInput input:focus,
        .stTextArea textarea:focus,
        .stNumberInput input:focus {
            border-color: rgba(90,167,255,.68) !important;
            box-shadow: 0 0 0 4px rgba(64, 137, 255, .12) !important;
        }

        div[data-baseweb="select"] svg,
        div[data-baseweb="input"] svg {
            fill: var(--muted) !important;
        }

        div[data-baseweb="popover"],
        ul[data-testid="stSelectboxVirtualDropdown"] {
            background: #151a24 !important;
            border: 1px solid rgba(255,255,255,.10) !important;
        }

        div[role="option"] {
            background: #151a24 !important;
            color: #f5f7fb !important;
        }

        div[role="option"]:hover,
        div[aria-selected="true"] {
            background: #252c3b !important;
        }

        /* Radio, checkbox and toggle */
        [data-testid="stRadio"] label,
        [data-testid="stCheckbox"] label,
        [data-testid="stToggle"] label {
            color: var(--ink) !important;
        }

        [data-testid="stRadio"] [role="radiogroup"] label,
        [data-testid="stCheckbox"] label {
            background: transparent !important;
        }

        /* Sliders */
        [data-testid="stSlider"] [role="slider"] {
            background: #67a9ff !important;
            border-color: white !important;
        }

        [data-testid="stSlider"] div[data-baseweb="slider"] > div > div {
            background: linear-gradient(90deg, #438df4, #7a62ec) !important;
        }

        /* Metrics */
        [data-testid="stMetric"] {
            padding: 16px 18px;
            border-radius: 18px;
            background: var(--glass-bg-strong);
            border: 1px solid var(--glass-border);
            box-shadow: 0 14px 34px rgba(0,0,0,.26);
        }

        [data-testid="stMetricLabel"] *,
        [data-testid="stMetricDelta"] * {
            color: var(--muted) !important;
        }

        [data-testid="stMetricValue"] * {
            color: white !important;
        }

        /* Alerts */
        [data-testid="stAlert"] {
            border-radius: 16px !important;
            border: 1px solid rgba(255,255,255,.10) !important;
            background: rgba(20,24,34,.88) !important;
            box-shadow: 0 10px 28px rgba(0,0,0,.22);
            backdrop-filter: blur(18px);
        }

        [data-testid="stAlert"] * {
            color: #eef2f8 !important;
        }

        [data-testid="stAlert"] svg {
            fill: currentColor !important;
        }

        /* Preset UI */
        .preset-pill {
            display: inline-block;
            padding: 6px 10px;
            border-radius: 999px;
            background: rgba(73, 142, 255, .14);
            border: 1px solid rgba(90, 167, 255, .20);
            color: #9bc9ff !important;
            font-size: .78rem;
            font-weight: 700;
            margin-bottom: 8px;
        }

        /* Tabs */
        [data-baseweb="tab-list"] {
            gap: .45rem;
            background: rgba(10,13,19,.65);
            border-radius: 14px;
            padding: .35rem;
        }

        [data-baseweb="tab"] {
            border-radius: 10px;
            color: var(--muted) !important;
        }

        [aria-selected="true"][data-baseweb="tab"] {
            background: rgba(255,255,255,.08) !important;
            color: white !important;
        }

        /* File uploader */
        [data-testid="stFileUploaderDropzone"] {
            background: rgba(8,11,17,.74) !important;
            border: 1px dashed rgba(255,255,255,.16) !important;
            border-radius: 16px !important;
        }

        [data-testid="stFileUploaderDropzone"] * {
            color: var(--muted) !important;
        }

        /* Code blocks and tables */
        pre,
        code,
        [data-testid="stCodeBlock"] {
            background: #080b11 !important;
            color: #d9e1ef !important;
            border-color: rgba(255,255,255,.08) !important;
        }

        [data-testid="stDataFrame"],
        [data-testid="stTable"] {
            border-radius: 16px;
            overflow: hidden;
            border: 1px solid var(--glass-border);
        }

        /* Video and image polish */
        video,
        [data-testid="stImage"] img {
            border-radius: 18px !important;
            box-shadow: 0 16px 38px rgba(0,0,0,.34);
        }

        h1, h2, h3 {
            letter-spacing: -0.025em;
        }

        hr {
            border-color: rgba(255,255,255,.08) !important;
        }

        /* Scrollbars */
        *::-webkit-scrollbar {
            width: 10px;
            height: 10px;
        }

        *::-webkit-scrollbar-track {
            background: rgba(0,0,0,.12);
        }

        *::-webkit-scrollbar-thumb {
            background: rgba(255,255,255,.14);
            border-radius: 999px;
            border: 2px solid transparent;
            background-clip: padding-box;
        }

        *::-webkit-scrollbar-thumb:hover {
            background: rgba(255,255,255,.22);
            background-clip: padding-box;
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
    data = {"default": "Default", "presets": {}}
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
        "default": "Default",
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
    """Return the single built-in default text style."""
    data = {"default": "Default", "presets": {}}
    return {"Default": dict(DEFAULT_TEXT_SETTINGS)}, data


def default_text_settings_from_presets() -> tuple[dict, str]:
    """Return the fixed global default text style."""
    return dict(DEFAULT_TEXT_SETTINGS), "Default"


def set_editor_widget_values(index: int, settings: dict):
    """Load preset settings into the Streamlit editor widgets."""
    normalized = normalize_text_settings(settings)
    st.session_state[f"editor_font_{index}"] = normalized.get("font_name", "TikTok Sans")
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
def fetch_video_bytes(video_url: str, cache_key: str = "") -> bytes | None:
    """Download video bytes; cache_key separates regenerated creations even when a CDN URL is reused."""
    _ = cache_key
    try:
        resp = requests.get(
            video_url,
            timeout=90,
            headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
        )
        resp.raise_for_status()
        return resp.content
    except Exception:
        return None


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_image_bytes(image_url: str) -> tuple[bytes | None, str | None]:
    """Download image bytes and return the detected content type for Streamlit reruns."""
    try:
        resp = requests.get(image_url, timeout=90)
        resp.raise_for_status()
        content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip() or None
        return resp.content, content_type
    except Exception:
        return None, None


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


def available_overlay_fonts() -> list[str]:
    """Return font choices that are actually available on this machine."""
    available = []
    for name, candidates in FONT_FILES.items():
        if any(Path(candidate).exists() for candidate in candidates):
            available.append(name)
    return available or ["System Default"]


def get_overlay_font(settings: dict | None = None) -> str | None:
    """Return the selected font file, falling back safely when unavailable."""
    selected_name = normalize_text_settings(settings).get("font_name", "TikTok Sans")
    for candidate in FONT_FILES.get(selected_name, []):
        if Path(candidate).exists():
            return candidate
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

    font_path = get_overlay_font(settings)
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


AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}


def available_audio_tracks() -> list[Path]:
    """Return soundtrack files placed in the repository's audio_tracks folder."""
    try:
        return sorted(
            [path for path in AUDIO_TRACK_DIR.iterdir() if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS],
            key=lambda path: path.name.lower(),
        )
    except Exception:
        return []


def resolve_audio_track(track_name: str | None) -> Path | None:
    """Resolve a stored soundtrack filename safely inside audio_tracks/."""
    if not track_name:
        return None
    candidate = AUDIO_TRACK_DIR / Path(track_name).name
    if candidate.exists() and candidate.is_file() and candidate.suffix.lower() in AUDIO_EXTENSIONS:
        return candidate
    return None


def choose_random_audio_track(exclude: str | None = None) -> str:
    """Choose one soundtrack filename, avoiding the previous one when possible."""
    tracks = available_audio_tracks()
    if not tracks:
        return ""
    choices = [track for track in tracks if track.name != exclude] or tracks
    return random.SystemRandom().choice(choices).name


VIDEO_COLOR_FILTER_SETTINGS = {
    "temperature": -3,
    "tint": 2,
    "saturation": -6,
    "exposure": -3,
    "contrast": 12,
    "highlights": -35,
    "shadows": 18,
    "fade": 6,
}

VIDEO_COLOR_FILTER_LABEL = (
    "Temp -3 · Tint +2 · Saturation -6 · Exposure -3 · Contrast +12 · "
    "Highlights -35 · Shadows +18 · Fade +6"
)


def ffmpeg_color_filter_chain(enabled: bool) -> str:
    """Return an FFmpeg approximation of the saved mobile-editor color preset."""
    if not enabled:
        return ""

    # FFmpeg uses different scales than mobile editors. These values map the requested
    # controls to a cooler image, slight magenta tint, lower saturation/exposure,
    # stronger contrast, compressed highlights, lifted shadows, and a subtle fade.
    return (
        "colorbalance="
        "rs=-0.015:gs=-0.006:bs=0.020:"
        "rm=0.006:gm=-0.010:bm=0.008:"
        "rh=-0.010:gh=-0.004:bh=0.018,"
        "eq=brightness=-0.030:contrast=1.120:saturation=0.940,"
        "curves=all='0/0.06 0.18/0.26 0.50/0.50 0.82/0.73 1/0.89'"
    )


def processed_video_path(
    creation_id: str | None,
    hook: str,
    settings: dict,
    audio_track: str | None = None,
    audio_volume_pct: int = 100,
    apply_color_filter: bool = False,
) -> Path:
    """Create a stable output filename based on text and soundtrack settings."""
    key_data = json.dumps(
        {
            "hook": hook,
            "settings": settings,
            "audio_track": audio_track or "",
            "audio_volume_pct": int(audio_volume_pct),
            "apply_color_filter": bool(apply_color_filter),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    digest = hashlib.sha256(key_data.encode("utf-8")).hexdigest()[:12]
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", creation_id or "video")[:60]
    return PROCESSED_DIR / f"{safe_id}_{digest}.mp4"


def apply_text_with_ffmpeg(
    video_url: str,
    creation_id: str | None,
    hook: str,
    settings: dict,
    audio_track: str | None = None,
    audio_volume_pct: int = 100,
    apply_color_filter: bool = False,
) -> tuple[Path | None, str | None]:
    """Apply text, an optional soundtrack, and the optional saved color preset."""
    if not video_url:
        return None, "No completed video URL is available."
    if not hook.strip():
        return None, "Enter text before creating the final video."

    ffmpeg_path = get_ffmpeg_executable()
    if not ffmpeg_path:
        return None, "FFmpeg is not installed. Keep `ffmpeg` in packages.txt."

    source_bytes = fetch_video_bytes(video_url)
    if not source_bytes:
        return None, "The original video could not be downloaded from Magnific."

    selected_audio_path = resolve_audio_track(audio_track)
    final_path = processed_video_path(
        creation_id,
        hook,
        settings,
        audio_track=selected_audio_path.name if selected_audio_path else None,
        audio_volume_pct=audio_volume_pct,
        apply_color_filter=apply_color_filter,
    )
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

            color_chain = ffmpeg_color_filter_chain(apply_color_filter)
            if color_chain:
                video_filter_graph = (
                    f"[0:v]{color_chain}[graded];"
                    "[graded][1:v]overlay=0:0:format=auto:shortest=1[v]"
                )
            else:
                video_filter_graph = "[0:v][1:v]overlay=0:0:format=auto:shortest=1[v]"

            if selected_audio_path:
                volume_factor = max(0.0, min(2.0, int(audio_volume_pct) / 100.0))
                command = [
                    ffmpeg_path,
                    "-hide_banner",
                    "-loglevel", "error",
                    "-y",
                    "-i", str(input_path),
                    "-loop", "1",
                    "-framerate", "30",
                    "-i", str(overlay_path),
                    "-stream_loop", "-1",
                    "-i", str(selected_audio_path),
                    "-filter_complex",
                    f"{video_filter_graph};[2:a]volume={volume_factor:.3f}[a]",
                    "-map", "[v]",
                    "-map", "[a]",
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
            else:
                command = [
                    ffmpeg_path,
                    "-hide_banner",
                    "-loglevel", "error",
                    "-y",
                    "-i", str(input_path),
                    "-loop", "1",
                    "-framerate", "30",
                    "-i", str(overlay_path),
                    "-filter_complex", video_filter_graph,
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

            warnings = [warning for warning in [overlay_warning] if warning]
            if not selected_audio_path and available_audio_tracks():
                warnings.append("No soundtrack was selected, so the original audio was preserved.")
            return final_path, " ".join(warnings) or None

    except subprocess.TimeoutExpired:
        final_path.unlink(missing_ok=True)
        return None, "FFmpeg timed out while creating the final video."
    except Exception as exc:
        final_path.unlink(missing_ok=True)
        return None, f"FFmpeg finalizer failed: {exc}"


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


def generation_export_rows(generations: list[dict]) -> list[dict]:
    """Flatten saved generations into VA-friendly CSV rows."""
    rows = []
    for item in generations:
        video_url = item.get("url") or item.get("preview_url") or ""
        caption = (item.get("caption") or "").strip()
        hashtags = (item.get("hashtags") or "").strip()
        full_caption = " ".join(part for part in [caption, hashtags] if part).strip()
        rows.append({
            "product_name": item.get("product_name", ""),
            "product_link": item.get("source_url", ""),
            "caption": caption,
            "hashtags": hashtags,
            "sound_tip": item.get("sound_tip", ""),
            "audio_track": item.get("audio_track", ""),
            "audio_volume_pct": item.get("audio_volume_pct", 100),
            "color_filter_applied": bool(item.get("apply_color_filter", False)),
            "full_caption": full_caption,
            "on_screen_text": item.get("accepted_hook", ""),
            "video_url": video_url,
            "processed_video_file": item.get("processed_path", ""),
            "style": item.get("style", ""),
            "status": item.get("status", ""),
            "creation_id": item.get("creation_id", ""),
            "generated_at": item.get("generated_at", ""),
        })
    return rows


def generations_csv_bytes(generations: list[dict]) -> bytes:
    """Create a UTF-8 CSV containing product links, captions, hooks, and video links."""
    rows = generation_export_rows(generations)
    buffer = io.StringIO()
    fieldnames = [
        "product_name", "product_link", "caption", "hashtags", "sound_tip", "audio_track", "audio_volume_pct", "color_filter_applied", "full_caption",
        "on_screen_text", "video_url", "processed_video_file", "style",
        "status", "creation_id", "generated_at",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def past_hooks_csv_bytes(generations: list[dict]) -> bytes:
    """Export every accepted and generated hook so forgotten overlays can be recovered."""
    buffer = io.StringIO()
    fieldnames = [
        "product_name", "product_link", "accepted_hook", "hook_option_1",
        "hook_option_2", "hook_option_3", "hook_option_4", "hook_option_5",
        "caption", "hashtags", "sound_tip", "style", "status", "generated_at", "video_url",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for item in generations:
        options = list(item.get("hook_options") or [])[:5]
        options += [""] * (5 - len(options))
        writer.writerow({
            "product_name": item.get("product_name", ""),
            "product_link": item.get("source_url", ""),
            "accepted_hook": item.get("accepted_hook", ""),
            "hook_option_1": options[0],
            "hook_option_2": options[1],
            "hook_option_3": options[2],
            "hook_option_4": options[3],
            "hook_option_5": options[4],
            "caption": item.get("caption", ""),
            "hashtags": item.get("hashtags", ""),
            "sound_tip": item.get("sound_tip", ""),
            "style": item.get("style", ""),
            "status": item.get("status", ""),
            "generated_at": item.get("generated_at", ""),
            "video_url": item.get("url") or item.get("preview_url") or "",
        })
    return buffer.getvalue().encode("utf-8-sig")


def apply_text_to_uploaded_video(
    video_bytes: bytes,
    original_filename: str,
    hook: str,
    settings: dict,
    audio_track: str | None = None,
    audio_volume_pct: int = 100,
    apply_color_filter: bool = False,
) -> tuple[Path | None, str | None]:
    """Apply text, soundtrack, and the optional saved color preset to an uploaded video."""
    if not video_bytes:
        return None, "Upload a video first."
    if not hook.strip():
        return None, "Enter text before applying the overlay."

    ffmpeg_path = get_ffmpeg_executable()
    if not ffmpeg_path:
        return None, "FFmpeg is not installed. Keep `ffmpeg` in packages.txt."

    selected_audio_path = resolve_audio_track(audio_track)
    digest_payload = {
        "settings": settings,
        "hook": hook,
        "audio_track": selected_audio_path.name if selected_audio_path else "",
        "audio_volume_pct": int(audio_volume_pct),
        "apply_color_filter": bool(apply_color_filter),
    }
    digest_data = video_bytes[:1048576] + json.dumps(
        digest_payload, sort_keys=True, ensure_ascii=False
    ).encode("utf-8")
    digest = hashlib.sha256(digest_data).hexdigest()[:14]
    safe_stem = safe_export_filename(Path(original_filename or "uploaded_video").stem, "uploaded_video")
    final_path = PROCESSED_DIR / f"uploaded_{safe_stem}_{digest}.mp4"
    if final_path.exists() and final_path.stat().st_size > 0:
        return final_path, None

    try:
        with tempfile.TemporaryDirectory(prefix="seedance_upload_editor_") as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "uploaded.mp4"
            overlay_path = temp_path / "overlay.png"
            input_path.write_bytes(video_bytes)

            canvas_size = probe_video_size(input_path, ffmpeg_path)
            overlay_ok, overlay_warning = create_hook_overlay_png(
                hook=hook, output_path=overlay_path, canvas_size=canvas_size, settings=settings
            )
            if not overlay_ok:
                return None, overlay_warning or "Could not build the text overlay."

            color_chain = ffmpeg_color_filter_chain(apply_color_filter)
            if color_chain:
                video_filter_graph = (
                    f"[0:v]{color_chain}[graded];"
                    "[graded][1:v]overlay=0:0:format=auto:shortest=1[v]"
                )
            else:
                video_filter_graph = "[0:v][1:v]overlay=0:0:format=auto:shortest=1[v]"

            if selected_audio_path:
                volume_factor = max(0.0, min(2.0, int(audio_volume_pct) / 100.0))
                command = [
                    ffmpeg_path, "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(input_path), "-loop", "1", "-framerate", "30",
                    "-i", str(overlay_path), "-stream_loop", "-1", "-i", str(selected_audio_path),
                    "-filter_complex", f"{video_filter_graph};[2:a]volume={volume_factor:.3f}[a]",
                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                    "-shortest", str(final_path),
                ]
            else:
                command = [
                    ffmpeg_path, "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(input_path), "-loop", "1", "-framerate", "30",
                    "-i", str(overlay_path),
                    "-filter_complex", video_filter_graph,
                    "-map", "[v]", "-map", "0:a?", "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                    "-shortest", str(final_path),
                ]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=300, check=False)
            if completed.returncode != 0 or not final_path.exists():
                final_path.unlink(missing_ok=True)
                details = (completed.stderr or "Unknown FFmpeg error").strip().splitlines()
                return None, details[-1] if details else "Unknown FFmpeg error"
            warnings = [warning for warning in [overlay_warning] if warning]
            if not selected_audio_path and available_audio_tracks():
                warnings.append("No soundtrack was selected, so the original audio was preserved.")
            return final_path, " ".join(warnings) or None
    except subprocess.TimeoutExpired:
        final_path.unlink(missing_ok=True)
        return None, "FFmpeg timed out while applying the text."
    except Exception as exc:
        final_path.unlink(missing_ok=True)
        return None, f"Uploaded-video editor failed: {exc}"


def safe_export_filename(value: str, fallback: str = "video") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", value or "").strip("_")
    return (cleaned[:70] or fallback)


def generations_zip_bytes(generations: list[dict]) -> tuple[bytes | None, int, list[str]]:
    """Build one ZIP with available edited/original videos and captions.csv."""
    csv_bytes = generations_csv_bytes(generations)
    output = io.BytesIO()
    added = 0
    skipped = []

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("captions.csv", csv_bytes)

        used_names = set()
        for index, item in enumerate(generations, start=1):
            product_name = item.get("product_name", f"video_{index}")
            base = safe_export_filename(product_name, f"video_{index}")
            filename = f"{index:03d}_{base}.mp4"
            counter = 2
            while filename in used_names:
                filename = f"{index:03d}_{base}_{counter}.mp4"
                counter += 1
            used_names.add(filename)

            video_bytes = read_local_video(item.get("processed_path"))
            if not video_bytes:
                video_url = item.get("url") or item.get("preview_url")
                if video_url and item.get("status") == "completed":
                    video_bytes = fetch_video_bytes(video_url)

            if video_bytes:
                archive.writestr(f"videos/{filename}", video_bytes)
                added += 1
            else:
                skipped.append(product_name)

    return output.getvalue(), added, skipped


def lifestyle_images_zip_bytes(generations: list[dict]) -> tuple[bytes | None, int, list[str]]:
    """Build one ZIP with available generated lifestyle images."""
    output = io.BytesIO()
    added = 0
    skipped = []

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        used_names = set()
        for index, item in enumerate(generations, start=1):
            if item.get("style") != "lifestyle_animation":
                continue
            image_url = item.get("lifestyle_image_url")
            if not image_url:
                skipped.append(item.get("product_name", f"image_{index}"))
                continue

            image_bytes, content_type = fetch_image_bytes(image_url)
            if not image_bytes:
                skipped.append(item.get("product_name", f"image_{index}"))
                continue

            ext_map = {
                "image/jpeg": ".jpg",
                "image/jpg": ".jpg",
                "image/png": ".png",
                "image/webp": ".webp",
            }
            ext = ext_map.get((content_type or '').lower(), ".jpg")
            product_name = item.get("product_name", f"image_{index}")
            base = safe_export_filename(product_name, f"image_{index}")
            filename = f"{index:03d}_{base}{ext}"
            counter = 2
            while filename in used_names:
                filename = f"{index:03d}_{base}_{counter}{ext}"
                counter += 1
            used_names.add(filename)
            archive.writestr(f"lifestyle_images/{filename}", image_bytes)
            added += 1

    return output.getvalue(), added, skipped


# ── Constants ───────────────────────────────────────────────────────
MAGNIFIC_MCP_URL = "https://mcp.magnific.com"
XAI_IMAGE_API_URL = "https://api.x.ai/v1/images/edits"
XAI_IMAGE_MODEL = "grok-imagine-image-quality"
DIRECTOR_INGEST_URL_DEFAULT = "https://app.momentumacademy.co/api/director/ingest"
SEEDANCE_QUEUE_SCHEMA = "momentum.seedance.batch.v1"
SEEDANCE_QUEUE_PATH_DEFAULT = "seedance_inbox"
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
- Generate a CLEAN source video with NO baked-in on-screen text, captions, subtitles, overlays, signs, or logos
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

WAREHOUSE_HOOKS_SYSTEM = """You are a TikTok Shop affiliate content producer. Generate 5
on-screen deal/FOMO text hooks. This same hook library is used for EVERY workflow: Shoe,
Text-Hook B-Roll, Warehouse, Pool, and Lifestyle Animation.

Use the product name exactly where [product] appears. Select five DIFFERENT angles from this
proven library; preserve each template's casual wording and emoji pattern:
1. I am SO sorry if you already grabbed a [product] because the discount is huge today
2. Sincerely apologize to anyone who already got a [product] cus they are TRIPLE discounted today 😭
3. Sorry to the ladies who bought these [product] before the new Summer Reductions this week 😭😭
4. Condolences to the ladies who bought this New [product] before this Summer Half Off Reduction 😭😭
5. POV: You wake up and the [product] is SO affordable on TikTok now 🤯😱
6. Glad I waited to grab the [product] because they are TRIPLE DISCOUNTED RIGHT NOW 😱🤑
7. You got BLESSED today bc the [product] is now SUPER cheap 🤩
8. If you waited until today you absolutely won cause the [product] is soooo low 🤑
9. Yall must have bullied the price down because the [product] are crazy cheap rn 😭
10. TikTok bullied the price down and now the [product] is on a massive sale…..only for a limited time don't miss out 😅
11. Someone fcked up at TikTok cus today the [product] is violently low right now
12. Apparently if your TikTok account is old enough you can get the [product] on a mega discount… its only for today though
13. Anyone else grabbing a boatload of the [product] or am I just stupid
14. I am so sorry if you already grabbed a [product], because the discount is huge today.
15. Before you ask...No it's not a typo. Yes the [product] is literal Pennie's today..😱😅
16. This is your sign to finally grab the [product].
17. Do NOT scroll past the [product] if it has been sitting in your cart.
18. POV: you found the [product] before everyone else did.
19. If you have been waiting on the [product], now is the time.
20. Run, do not walk, to grab the [product].
21. The [product] everyone has been asking me about is finally back.
22. Stop overthinking the [product] and just tap the cart.
23. Me telling you to grab the [product] before it sells out again.
24. Your future self will thank you for grabbing the [product] today.
25. Adding the [product] to my cart before I change my mind.
26. The [product] is about to be everywhere. Get it first.
27. I can not believe how good the [product] is for the price.
28. Consider this your reminder to grab the [product] you keep eyeing.
29. Trust me, you want the [product] in your cart today.

Rules:
- Select exactly five hooks from different angles. Do not return five near-duplicates.
- Casual, chaotic, sassy deal-drop/FOMO voice; never polished corporate copy.
- Preserve the wording and punctuation of the selected templates as closely as possible while replacing [product].
- No link in bio.
- Do not invent an exact price or percentage unless the selected template already uses broad sale wording.
- The hook is burned into the finished video later with FFmpeg.
- Caption: one short deal-find line in the same voice.
- Hashtags: 8-12 tags including #tiktokshop and #tiktokmademebuyit plus product/category tags.
  Add #costcofinds and #warehousedeals only when the user message says the style is warehouse.
- Sound tip: short reminder that the app assigns a random soundtrack after generation.

Return ONLY valid JSON (no markdown, no backticks):
{{"product_name": "...", "hook_options": ["hook 1", "hook 2", "hook 3", "hook 4", "hook 5"], "caption": "...", "hashtags": "#tag1 #tag2", "sound_tip": "..."}}"""

WAREHOUSE_PROMPT_SYSTEM = """You are a TikTok Shop affiliate content producer. Write a
Seedance 2.0 prompt for the Warehouse beside-the-display deal-drop style.

HARD RULES:
- 9:16 vertical, exactly about 5 seconds, raw TikTok UGC phone footage.
- COMPLETELY SILENT: no audio, no voiceover, no narration.
- ONE continuous take with zero cuts, jumps, scene changes, montage, orbit, or dramatic camera moves.
- Pure first-person shopper POV. No people, hands, face, body, characters, or animals.
- The camera begins ALREADY STANDING DIRECTLY BESIDE the product display at arm's length.
- NO aisle walk-up, NO approach from several feet away, NO multiple footsteps, and NO distant establishing shot.
- In the opening frame, the product display already dominates roughly 75-85% of the frame.
- The camera stays almost stationary. Use only a tiny natural handheld lean-in or half-step of about 6-12 inches,
  just enough for the packaging to fill roughly 90-95% of the final frame.
- Natural phone micro-shake and subtle body sway are allowed, but do not simulate walking or repeated gait bounce.
- Start slightly off-center beside the display, then make a small natural reframe toward the hero products.
- Chest-height handheld phone perspective with a mildly wide phone lens; no polished gimbal movement and no digital zoom.
- Keep a narrow amount of warehouse context visible around the display: metal racking, fluorescent light,
  concrete floor, pallet edges, and generic adjacent bulk merchandise.
- Show abundant repeated units in a real pallet display, branded cardboard shipper, shelf, or wire bin. Match all
  supplied reference images exactly for packaging, colors, proportions, labels, finish, logo, and product shape.
- ZERO rendered overlay text: no captions, subtitles, prices, sale signs, promotional graphics, or watermarks.
  Existing physical branding printed on the actual product packaging is allowed.
- Prompt must be under 1,900 characters.

Required structure inside the prompt:
[00:00-00:02] Already beside the display: camera is stationary at arm's length with the complete product display
already filling most of the frame. Hold briefly with natural handheld micro-shake and a small off-center angle.
[00:02-00:05] Tiny close reveal: make one subtle 6-12 inch lean-in or half-step and gently reframe so repeated
products and authentic packaging dominate the frame. End beside the display with a natural handheld hold.
End with a NEGATIVE sentence repeating no people/hands/body, no walking sequence, no cuts, no audio,
no rendered overlay text, no start-frame behavior, and no digital zoom.

Return ONLY valid JSON (no markdown, no backticks):
{{"product_name": "...", "prompt": "the full Seedance prompt under 1900 characters", "char_count": 123}}"""

POOL_PROMPT_SYSTEM = """You are a TikTok Shop affiliate content producer. Write a
Seedance 2.0 video prompt for the Pool style.

HARD RULES:
- 9:16 vertical, exactly 8 seconds, realistic TikTok Shop UGC filmed on a handheld iPhone.
- Bright natural summer daylight beside a residential backyard swimming pool.
- The text hook is added later with FFmpeg, so render ZERO on-screen text, captions, stickers, graphics, or price labels.
- Use the uploaded product images only as general visual references for exact packaging, colors, shape, logo placement, and proportions.
- NEVER use any image as a start frame, first frame, end frame, keyframe, or start_image.
- Silent video: no dialogue, no narration, no voiceover.
- Casual amateur phone footage, not a polished commercial.
- Keep one accurate product package throughout the entire video.
- No warped hands, no extra fingers, no packaging changes, no invented words, no duplicate products, no studio lighting, and no digital zoom.
- Prompt must stay under 1,900 characters.

Required scene structure:
[00:00-00:03] Handheld product close-up beside the pool. One natural hand holds the product upright over the textured pool edge with turquoise pool water visible beside it. The packaging faces the camera and fills about 65-75% of the frame. Slight natural wrist movement and casual phone micro-shake.
[00:03-00:05.5] Quick clean cut. The product stands upright by itself on a small round mosaic patio table beside the pool. The camera makes a short casual half-orbit and subtle push-in around the package. Green backyard plants and trees remain softly visible behind it.
[00:05.5-00:08] Quick clean cut. The product is held upright again beside the pool while the camera moves slowly along the pool edge. Only one or two small natural steps, not a long walking sequence. Keep the package centered and dominant while the blue pool water and concrete walkway move gently in the background.
End with a NEGATIVE sentence repeating: no rendered text, no voiceover, no start-frame behavior, no packaging changes, no duplicate products, no digital zoom, and no polished commercial look.

Return ONLY valid JSON (no markdown, no backticks):
{{"product_name": "...", "prompt": "the full seedance prompt under 1900 chars", "char_count": 123}}"""

BROLL_OPENING_SCENES = [
    "Cars pass through a sunlit city intersection while the camera remains still on the sidewalk; no walking POV",
    "Ocean waves roll onto a quiet beach while the phone drifts slightly from left to right",
    "A dog trots several feet ahead on a leash through a public park, filmed from behind without showing the owner",
    "Dry leaves blow across an almost-empty parking lot in bright afternoon light",
    "A commuter train passes through an outdoor station while the camera waits beside the platform railing",
    "Small boats move slowly across a marina while sunlight flickers on the water",
    "A crosswalk signal changes and a distant crowd crosses the street; camera stays planted at the corner",
    "Palm-tree shadows move across a concrete walkway in a light breeze; no people in frame",
    "A cyclist rides past on a park trail while the camera casually follows for one second",
    "A city bus pulls up to an outdoor stop and opens its doors, filmed from several feet away",
    "Pigeons scatter near a park bench when a bicycle passes in the background",
    "Water sprays from a public fountain with trees and pedestrians softly blurred far behind",
    "Traffic flows beneath an overpass at golden hour, filmed from a safe stationary viewpoint",
    "A skateboarder rolls across the far side of an outdoor plaza, seen only from the knees down",
    "A red traffic light changes to green above a busy road while cars begin moving",
    "Sunlight flickers through tree branches onto an empty park path; camera tilts gently upward",
    "A ferry moves across open water in the distance while birds cross the sky",
    "A row of parked cars reflects moving clouds as the phone makes a small sideways pan",
    "A beach umbrella flutters in the wind beside an empty stretch of sand",
    "A basketball bounces across an outdoor court after rolling out of frame; no player is shown",
    "A delivery truck turns slowly into a commercial parking lot while the camera remains stationary",
    "A public escalator rises toward an outdoor train entrance with only distant anonymous commuters visible",
    "A flag moves in the wind above a neighborhood storefront while cars pass below",
    "Ripples spread across a park pond as ducks swim through the middle distance",
]


def choose_broll_scene(previous_scene: str | None = None) -> str:
    """Choose a concrete scene in Python and avoid the previous one on regeneration."""
    choices = [scene for scene in BROLL_OPENING_SCENES if scene != previous_scene]
    return random.SystemRandom().choice(choices or BROLL_OPENING_SCENES)


TEXTHOOK_PROMPT_SYSTEM = """You are a TikTok Shop affiliate content producer. Write a
Seedance 2.0 video prompt for a clean text-hook b-roll video.

HARD RULES:
- SILENT video — NO audio, NO voiceover
- ABSOLUTELY NO on-screen text, captions, subtitles, overlays, signs, watermarks, or logos
- No identifiable face or featured character; only a hand in the product reveal shot
- Two acts: unrelated opening b-roll (~3s) → hard cut to product reveal (~5s)
- ~8 seconds total, 9:16 vertical
- Under 1,900 characters

CRITICAL OPENING-SCENE RULE:
- The user message supplies one exact MANDATORY OPENING B-ROLL SCENE selected by the app.
- Use that exact scene faithfully. Do not choose another scene and do not replace it with a generic walking shot.
- Unless the supplied scene explicitly includes walking, do NOT show first-person walking, feet walking, sneakers walking,
  a sidewalk walking POV, a park-path walking POV, or repeated step/bounce motion.
- The opening must remain completely unrelated to the product.
- Casual handheld iPhone footage with natural micro-shake; ordinary daylight; not cinematic or polished.

HARD EXCLUSIONS:
- No rain droplets on windows
- No grocery carts or grocery aisles
- No laundry, dryers, washing machines, or household chores
- No coffee pouring or close-up drink shots
- No kitchens, bedrooms, bathrooms, or indoor home scenes
- No product-related location or visual hint
- No dramatic commercial footage

Required structure:
9:16 vertical TikTok UGC, silent, no audio, no voiceover, no rendered text or graphics.
[00:00-00:03] Show the exact mandatory opening scene supplied by the app. Keep it unrelated to the product.
[00:03-00:08] Hard cut to an outdoor or casual real-life surface. One medium-brown-skinned hand holds up
[PRODUCT + accurate visual detail], slowly rotating and tilting it in warm natural light. Hand fills the lower half.
Soft blurred background. No face or person above the wrist.

Return ONLY valid JSON (no markdown, no backticks):
{{"product_name": "...", "prompt": "the full seedance prompt under 1900 chars", "char_count": 123}}"""

VOICEOVER_SILENT = "## Audio:\nNO voiceover. Ambient sound only."
VOICEOVER_WITH_SCRIPT = '## Voiceover:\nInclude this voiceover (warm excited woman, casual and friendly):\n"{script}"'



LIFESTYLE_PRODUCT_TYPES = {
    "small_handheld": {
        "label": "Small / handheld — supplements, beauty, personal care",
        "description": "a small handheld product such as a bottle, jar, box, spray, cosmetic, supplement, accessory, or personal-care item",
        "framing": "Use a close phone-camera composition where the product fills roughly 45-75% of the frame without looking oversized.",
        "appearance_help": "Include packaging color, label, cap, logo placement, count, material, and proportions.",
    },
    "clothing_shoe": {
        "label": "Clothing / shoes — apparel, footwear, fashion accessories",
        "description": "a clothing, footwear, or wearable fashion product shown at realistic human scale",
        "framing": "Show the full clothing or shoe product clearly at believable scale. For shoes, keep the complete pair or complete single product visible. For clothing, show the main garment cleanly on-body or staged naturally in a realistic wardrobe setting.",
        "appearance_help": "Include garment type, cut, silhouette, color, fabric, texture, stitching, hardware, sole, laces, straps, logo placement, and any included pieces.",
    },
    "countertop_appliance": {
        "label": "Countertop appliance — air fryer, blender, coffee maker",
        "description": "a medium countertop appliance or home device",
        "framing": "Show the complete appliance at believable real-world scale, filling roughly 45-70% of the vertical frame with enough counter and room context to prove its size.",
        "appearance_help": "Include body color, finish, controls, display, lid, basket, cord, attachments, logo, and proportions.",
    },
    "floor_cleaning": {
        "label": "Floor-care / cleaning — vacuum, mop, carpet cleaner",
        "description": "a full-size floor-care or cleaning product",
        "framing": "Show the complete product from floor level to handle at believable scale. Do not crop away the cleaner head, body, hose, tank, or handle unless the references show a compact model.",
        "appearance_help": "Include floor head, handle, tank/bin, hose, attachments, controls, color blocking, logo, and proportions.",
    },
    "furniture_large": {
        "label": "Furniture / large home item — couch, chair, table, mattress",
        "description": "a room-scale furniture piece or large home item",
        "framing": "Use a wider vertical room composition. Show the entire furniture item at correct human-scale proportions, occupying roughly 50-80% of the frame with visible floor and surrounding room context.",
        "appearance_help": "Include dimensions, silhouette, upholstery/material, legs, cushions, seams, color, texture, hardware, and included pieces.",
    },
    "electronics": {
        "label": "Electronics / office — TV, monitor, speaker, printer",
        "description": "a consumer electronic or office product",
        "framing": "Show the complete device at realistic scale with its stand, ports, controls, screen/bezel, cables, or accessories visible where appropriate.",
        "appearance_help": "Include finish, screen/bezel, buttons, ports, stand, cables, accessories, logo, and proportions.",
    },
    "fitness_large": {
        "label": "Fitness equipment — treadmill, bike, bench, weights",
        "description": "a medium or large fitness product",
        "framing": "Show the full equipment footprint at realistic scale with enough floor and room context to establish size. Do not miniaturize or crop off key frames, pedals, rails, handles, or consoles.",
        "appearance_help": "Include frame shape, padding, console, handles, pedals, rails, weights, attachments, finish, logo, and proportions.",
    },
    "outdoor_large": {
        "label": "Outdoor / patio — grill, canopy, garden, pool item",
        "description": "an outdoor, patio, garden, or recreation product",
        "framing": "Show the complete product at believable outdoor scale with patio, yard, driveway, deck, or garden context. Preserve weather-resistant materials and all structural parts.",
        "appearance_help": "Include frame, fabric, wheels, handles, shelves, canopy, hardware, finish, accessories, logo, and proportions.",
    },
    "other": {
        "label": "Other / mixed-size item",
        "description": "a product whose size and category should be inferred from the references",
        "framing": "Infer the true real-world size from the references and show the complete product with enough environmental context to make that scale unmistakable.",
        "appearance_help": "Describe the real size, construction, materials, colors, controls, accessories, branding, and proportions.",
    },
}

LIFESTYLE_PRODUCT_TYPE_OPTIONS = ["auto"] + list(LIFESTYLE_PRODUCT_TYPES.keys())
LIFESTYLE_PRODUCT_TYPE_LABELS = {
    "auto": "Auto-detect from product name",
    **{key: value["label"] for key, value in LIFESTYLE_PRODUCT_TYPES.items()},
}

LIFESTYLE_TYPE_KEYWORDS = {
    "furniture_large": (
        "couch", "sofa", "loveseat", "recliner", "armchair", "accent chair", "ottoman", "coffee table",
        "dining table", "desk", "dresser", "nightstand", "cabinet", "bookshelf", "shelf", "bed frame",
        "mattress", "headboard", "bench", "bar stool", "stool", "storage chest", "tv stand",
    ),
    "floor_cleaning": (
        "vacuum", "carpet cleaner", "floor cleaner", "floor washer", "steam mop", "mop", "broom",
        "spot cleaner", "scrubber", "wet dry vac", "shop vac", "dustbuster",
    ),
    "countertop_appliance": (
        "air fryer", "blender", "coffee maker", "espresso", "toaster", "kettle", "juicer", "mixer",
        "food processor", "rice cooker", "slow cooker", "pressure cooker", "ice maker", "microwave",
        "waffle maker", "griddle", "countertop oven", "creami",
    ),
    "fitness_large": (
        "treadmill", "walking pad", "exercise bike", "stationary bike", "rowing machine", "rower",
        "elliptical", "weight bench", "power rack", "squat rack", "home gym", "dumbbell set",
        "kettlebell", "stepper", "pilates reformer", "vibration plate",
    ),
    "outdoor_large": (
        "patio", "grill", "barbecue", "smoker", "canopy", "gazebo", "tent", "garden", "lawn",
        "outdoor chair", "outdoor table", "pool", "cooler", "fire pit", "umbrella", "hammock",
        "pressure washer", "leaf blower", "lawn mower", "hose reel",
    ),
    "electronics": (
        "television", " tv ", "smart tv", "monitor", "speaker", "soundbar", "printer", "projector",
        "laptop", "tablet", "keyboard", "microphone", "camera", "router", "gaming chair", "headphones",
        "earbuds", "charging station", "computer", "scanner",
    ),
    "clothing_shoe": (
        "shoe", "shoes", "sneaker", "sneakers", "trainer", "trainers", "boot", "boots", "heel", "heels",
        "slipper", "slippers", "loafer", "loafers", "sandal", "sandals", "slide", "slides", "slip on",
        "sock", "socks", "legging", "leggings", "hoodie", "sweatshirt", "jacket", "coat", "dress", "shirt",
        "tee", "t shirt", "top", "skirt", "jeans", "pants", "shorts", "bra", "bralette", "shapewear",
        "sweater", "cardigan", "activewear", "athleisure", "set", "two piece", "tracksuit", "onesie", "robe",
    ),
    "small_handheld": (
        "gummies", "capsules", "supplement", "vitamin", "serum", "cream", "lotion", "perfume", "spray",
        "toner", "cleanser", "shampoo", "conditioner", "makeup", "lip", "mask", "powder", "drink mix",
        "bottle", "jar", "drops", "soap", "deodorant", "toothpaste", "mouthwash", "earplugs", "wallet",
    ),
}


def infer_lifestyle_product_type(product_name: str) -> str:
    """Infer a practical product-size profile from the product title; the user can override it."""
    normalized = f" {re.sub(r'[^a-z0-9]+', ' ', (product_name or '').lower()).strip()} "
    for type_key in (
        "furniture_large", "floor_cleaning", "countertop_appliance", "fitness_large",
        "outdoor_large", "electronics", "clothing_shoe", "small_handheld",
    ):
        if any(keyword in normalized for keyword in LIFESTYLE_TYPE_KEYWORDS[type_key]):
            return type_key
    return "other"


def infer_lifestyle_default_scene(product_name: str, product_type: str) -> str:
    """Pick a sensible first scene for the product while still allowing manual scene selection."""
    normalized = f" {re.sub(r'[^a-z0-9]+', ' ', (product_name or '').lower()).strip()} "
    if product_type == "electronics":
        if any(word in normalized for word in (" tv ", "television", "soundbar", "speaker", "projector")):
            return "living_room_electronics"
        return "home_office_device"
    if product_type == "furniture_large":
        if any(word in normalized for word in ("mattress", "bed frame", "headboard", "nightstand", "dresser")):
            return "bedroom_large_item"
        if any(word in normalized for word in ("desk", "bookshelf", "shelf", "cabinet")):
            return "furniture_room_corner"
        return "living_room_furniture"
    if product_type == "floor_cleaning":
        if any(word in normalized for word in ("shop vac", "wet dry vac", "pressure washer")):
            return "garage_storage"
        return "vacuum_living_room"
    if product_type == "countertop_appliance":
        if any(word in normalized for word in ("coffee", "espresso", "kettle")):
            return "appliance_coffee_corner"
        return "kitchen_appliance"
    if product_type == "fitness_large":
        if any(word in normalized for word in ("walking pad", "stepper", "vibration plate", "dumbbell", "kettlebell")):
            return "fitness_living_space"
        return "home_gym_equipment"
    if product_type == "outdoor_large":
        if any(word in normalized for word in ("lawn", "blower", "mower", "pressure washer", "hose", "driveway")):
            return "yard_driveway_product"
        return "patio_product"
    if product_type == "clothing_shoe":
        if any(word in normalized for word in ("shoe", "shoes", "sneaker", "sneakers", "boot", "boots", "heel", "heels", "sandal", "sandals", "slide", "slides", "slipper", "slippers", "loafer", "loafers")):
            return "shoe_entryway"
        if any(word in normalized for word in ("legging", "leggings", "bra", "bralette", "activewear", "athleisure", "tracksuit")):
            return "clothing_mirror"
        return "clothing_closet"
    if product_type == "small_handheld":
        if any(word in normalized for word in ("gummies", "capsules", "supplement", "vitamin", "drink mix", "powder", "prebiotic", "probiotic", "collagen", "sea moss", "enzyme")):
            return "counter_kitchen"
        if any(word in normalized for word in ("toothpaste", "mouthwash", "oral", "tooth", "cleanser", "serum", "cream", "lotion", "toner", "deodorant", "soap", "spray")):
            return "counter_bathroom"
        if any(word in normalized for word in ("perfume", "sleep", "earplugs", "eye mask")):
            return "nightstand"
        return "hand_bathroom"
    return "custom"


LIFESTYLE_SCENES = {
    # Small / handheld products
    "hand_bathroom": {
        "label": "Held in hand — bathroom",
        "types": ["small_handheld", "other"],
        "setting": (
            "held casually in one hand against a real bathroom background. A bathroom mirror edge, toothbrush holder, "
            "folded towel, and one ordinary personal-care item sit softly blurred behind it. Warm overhead vanity light"
        ),
        "placement": "held in one hand against a bathroom background",
        "background": "a bathroom mirror edge, toothbrush holder, and folded towel",
        "hand_present": True,
        "camera_motion": "a small side-to-side handheld arc and slight push-in",
    },
    "counter_bathroom": {
        "label": "On bathroom counter",
        "types": ["small_handheld", "other"],
        "setting": (
            "placed naturally on a clean, realistic bathroom counter or vanity. Keep the surface bright, tidy, and uncluttered with only one or two subtle context items, "
            "such as a toothbrush holder, folded towel, or soap dish softly out of focus. Use clean natural or soft indoor light so the scene feels clear and well exposed rather than dark"
        ),
        "placement": "positioned naturally on a bathroom counter or vanity",
        "background": "a bright clean bathroom counter with minimal clutter and soft realistic bathroom details",
        "hand_present": False,
        "camera_motion": "a gentle handheld side arc with a subtle push-in",
    },
    "hand_kitchen": {
        "label": "Held in hand — kitchen",
        "types": ["small_handheld", "other"],
        "setting": (
            "held in one hand over a clean, realistic kitchen countertop. Keep the space bright and tidy with only light context, "
            "such as a single water glass, a simple mug, or a subtle cutting-board edge softly out of focus. Use bright natural "
            "window light from the side so the scene feels airy, realistic, and well exposed rather than dark"
        ),
        "placement": "held in one hand over a clean kitchen countertop",
        "background": "a bright realistic kitchen counter with only a water glass, simple mug, or light kitchen detail",
        "hand_present": True,
        "camera_motion": "a gentle handheld reframe and tiny push-in",
    },
    "counter_kitchen": {
        "label": "On kitchen counter",
        "types": ["small_handheld", "countertop_appliance", "electronics", "other"],
        "setting": (
            "placed naturally on a clean, realistic kitchen countertop, slightly off-center. Keep the counter mostly clear with "
            "only one or two simple nearby items such as a mug, a folded dish towel, or a subtle everyday kitchen detail. The "
            "scene should feel realistic and lived-in but not messy or crowded. Use bright natural side light so the image feels "
            "clean, clear, and well exposed rather than dark or moody"
        ),
        "placement": "positioned naturally on a clean kitchen countertop",
        "background": "a clean realistic kitchen counter with minimal clutter and soft natural light",
        "hand_present": False,
        "camera_motion": "a slow phone-camera half-arc with mild parallax",
    },
    "nightstand": {
        "label": "On nightstand",
        "types": ["small_handheld", "electronics", "other"],
        "setting": (
            "sitting on a nightstand beside a charging phone, half-empty water glass, and a small lamp that is turned on. "
            "Rumpled bedsheets appear at the lower edge. Warm low light"
        ),
        "placement": "positioned on a nightstand",
        "background": "a charging phone, water glass, lamp, and rumpled bedsheets",
        "hand_present": False,
        "camera_motion": "a subtle bedside push-in and short lateral drift",
    },
    "bed_toss": {
        "label": "Tossed on bed",
        "types": ["small_handheld", "electronics", "other"],
        "setting": (
            "resting casually on a rumpled duvet with a pillow behind it and a book or earbuds nearby. Soft natural "
            "bedroom-window light, slightly imperfect exposure"
        ),
        "placement": "resting naturally on a rumpled bed duvet",
        "background": "a pillow, duvet folds, and small everyday bedroom items",
        "hand_present": False,
        "camera_motion": "a short top-down drift with natural phone shake",
    },
    "bag_peek": {
        "label": "Inside a bag",
        "types": ["small_handheld", "electronics"],
        "setting": (
            "peeking out of an open purse, tote, or gym bag with keys, a wallet, hair tie, and water bottle visible. "
            "Shot from above as if someone just opened the bag"
        ),
        "placement": "peeking out of an open everyday bag",
        "background": "keys, a wallet, hair tie, and other normal bag contents",
        "hand_present": False,
        "camera_motion": "a slight top-down lean-in and natural wrist movement",
    },
    "closeup_label": {
        "label": "Close-up product detail",
        "types": ["small_handheld", "countertop_appliance", "electronics", "floor_cleaning", "other"],
        "setting": (
            "shown in a close product-detail composition with its branding, controls, materials, or key construction details "
            "sharp and recognizable while the background falls softly out of focus"
        ),
        "placement": "positioned close to the camera with its main identifying details facing forward",
        "background": "a softly blurred real-life surface and room context",
        "hand_present": False,
        "camera_motion": "a very small detail-oriented side drift and push-in",
    },
    "desk": {
        "label": "On desk / home office",
        "types": ["small_handheld", "electronics", "countertop_appliance", "other"],
        "setting": (
            "placed on a real home-office desk beside the edge of a laptop or monitor, pen, sticky note, charging cable, "
            "and water bottle. Ordinary overhead light with a little screen glow"
        ),
        "placement": "positioned on a lived-in home-office desk",
        "background": "a laptop or monitor edge, pen, sticky notes, cable, and water bottle",
        "hand_present": False,
        "camera_motion": "a casual desk-height slide and slight push-in",
    },
    "car_cupholder": {
        "label": "In car",
        "types": ["small_handheld", "electronics"],
        "setting": (
            "sitting in a car cupholder or securely on the passenger seat. A seatbelt, console, and steering wheel appear "
            "blurred behind it. Natural daylight enters through the windshield"
        ),
        "placement": "sitting securely in a car cupholder or on the passenger seat",
        "background": "a car console, blurred steering wheel, and seatbelt",
        "hand_present": False,
        "camera_motion": "a small handheld reframe from the passenger-seat angle",
    },
    "gym_bag": {
        "label": "With gym gear",
        "types": ["small_handheld", "fitness_large", "other"],
        "setting": (
            "placed naturally beside gym gear on a bench or locker-room shelf. A water bottle and towel sit nearby with "
            "real gym equipment softly blurred in the background"
        ),
        "placement": "positioned beside normal gym gear",
        "background": "a water bottle, towel, bench, and softly blurred gym equipment",
        "hand_present": False,
        "camera_motion": "a short bench-height arc and subtle push-in",
    },

    # Clothing and shoes
    "shoe_entryway": {
        "label": "Shoes — entryway / hallway",
        "types": ["clothing_shoe", "other"],
        "setting": (
            "placed naturally on the floor in a real entryway, hallway, or mudroom. Show the full shoes at believable scale with laces, soles, straps, logos, and material texture clearly visible. A rug, baseboards, and casual everyday clutter make the scene feel real"
        ),
        "placement": "positioned naturally at full scale in a real entryway or hallway",
        "background": "a rug, baseboards, doorway, wall, and ordinary entryway details",
        "hand_present": False,
        "camera_motion": "a low handheld side arc with a gentle push-in across the shoes",
    },
    "clothing_mirror": {
        "label": "Clothing — on-body mirror / bedroom",
        "types": ["clothing_shoe", "other"],
        "setting": (
            "worn naturally in a casual bedroom or dressing-area mirror setup. Show the clothing item clearly at correct human scale with realistic drape, fit, fabric texture, seams, and proportions. The scene should feel like a genuine UGC outfit check, not a polished fashion campaign"
        ),
        "placement": "worn naturally at realistic scale in a casual bedroom or dressing-area setting",
        "background": "a bedroom mirror, bed edge, dresser, laundry basket, or ordinary bedroom details",
        "hand_present": False,
        "camera_motion": "a casual handheld mirror-style reframe with slight body-level drift while the clothing stays visually fixed in the approved start frame",
    },
    "clothing_closet": {
        "label": "Clothing — closet / wardrobe area",
        "types": ["clothing_shoe", "other"],
        "setting": (
            "displayed naturally in a closet, wardrobe, or bedroom corner. Show the full garment or outfit at believable scale on a hanger, rack, chair, or styled drape so its cut, length, texture, and details are easy to see. Nearby clothing and room details should make the scene feel lived-in"
        ),
        "placement": "displayed naturally at full scale in a closet or wardrobe area",
        "background": "a clothing rack, hangers, dresser, mirror, or ordinary wardrobe details",
        "hand_present": False,
        "camera_motion": "a slow wardrobe-area side reveal with a subtle push-in",
    },

    # Countertop appliances
    "kitchen_appliance": {
        "label": "Countertop appliance — real kitchen",
        "types": ["countertop_appliance", "electronics", "other"],
        "setting": (
            "installed naturally on a real kitchen counter with correct clearance around it. Its complete body, controls, "
            "lid or basket, cord, and included attachments are visible. Nearby are a dish towel, cutting board, and mug; "
            "the kitchen is casual rather than staged"
        ),
        "placement": "sitting at full real-world scale on a kitchen countertop",
        "background": "a lived-in kitchen with cabinets, counter items, and natural side light",
        "hand_present": False,
        "camera_motion": "a slow counter-height half-orbit that reveals the front and one side",
    },
    "appliance_coffee_corner": {
        "label": "Appliance — coffee / breakfast corner",
        "types": ["countertop_appliance", "electronics"],
        "setting": (
            "placed in a believable breakfast or coffee corner with a mug, small tray, paper towel roll, and wall outlet. "
            "The full appliance remains visible at correct scale with natural morning light"
        ),
        "placement": "positioned in a real breakfast or coffee-station corner",
        "background": "a mug, tray, outlet, backsplash, and normal kitchen details",
        "hand_present": False,
        "camera_motion": "a gentle front-to-side arc with realistic reflections",
    },

    # Vacuums and floor-care products
    "vacuum_living_room": {
        "label": "Vacuum / floor cleaner — living room",
        "types": ["floor_cleaning", "other"],
        "setting": (
            "standing naturally on a real living-room floor beside a sofa and low table. The complete cleaner head, body, "
            "tank or bin, handle, hose, and attachments are visible at accurate scale. The room has ordinary lived-in details"
        ),
        "placement": "standing upright at full scale on a living-room floor",
        "background": "a sofa, low table, rug edge, baseboard, and normal living-room clutter",
        "hand_present": False,
        "camera_motion": "a low handheld side-to-side arc from floor-head height up toward the handle",
    },
    "vacuum_hallway": {
        "label": "Vacuum / floor cleaner — hallway",
        "types": ["floor_cleaning"],
        "setting": (
            "parked naturally in a hallway or entryway with its full floor head and handle visible. A runner rug, shoes, "
            "doorframe, and baseboards establish believable scale and household use"
        ),
        "placement": "standing at full scale in a hallway or entryway",
        "background": "a runner rug, shoes, doorframe, baseboards, and ordinary entryway details",
        "hand_present": False,
        "camera_motion": "a slow low-angle push-in with a small side reveal",
    },
    "cleaner_storage": {
        "label": "Cleaning product — laundry / utility area",
        "types": ["floor_cleaning", "countertop_appliance", "other"],
        "setting": (
            "positioned in a real laundry or utility area beside a shelf, basket, cleaning cloths, and wall outlet. The full "
            "product and all major attachments are visible with slightly harsh household lighting"
        ),
        "placement": "positioned at full scale in a laundry or utility area",
        "background": "a shelf, laundry basket, cleaning cloths, outlet, and utility-room details",
        "hand_present": False,
        "camera_motion": "a casual utility-room reframe and small push-in",
    },

    # Furniture and room-scale products
    "living_room_furniture": {
        "label": "Furniture — lived-in living room",
        "types": ["furniture_large", "other"],
        "setting": (
            "installed naturally in a lived-in living room. Show the entire furniture piece at correct room scale, including "
            "all cushions, legs, arms, seams, panels, and included sections. A rug, side table, lamp, and ordinary decor prove its size"
        ),
        "placement": "installed at full human scale in a lived-in living room",
        "background": "a rug, side table, lamp, wall, windows, and ordinary living-room decor",
        "hand_present": False,
        "camera_motion": "a wide iPhone 0.5x room-level arc that reveals the front and one side",
    },
    "furniture_room_corner": {
        "label": "Furniture — room corner / apartment",
        "types": ["furniture_large", "electronics", "other"],
        "setting": (
            "placed in a believable apartment or bedroom corner with enough wall, floor, doorway, and nearby furniture visible "
            "to establish real dimensions. The complete product remains unobstructed and accurately proportioned"
        ),
        "placement": "placed at full scale in a believable apartment room corner",
        "background": "visible walls, floor, doorway, window light, and nearby everyday furniture",
        "hand_present": False,
        "camera_motion": "a slow wide-angle corner-to-front reveal with natural handheld sway",
    },
    "bedroom_large_item": {
        "label": "Large item — bedroom",
        "types": ["furniture_large", "fitness_large", "other"],
        "setting": (
            "positioned naturally in a bedroom with the complete product visible at correct scale. Bedside furniture, a rug, "
            "curtains, and doorway provide believable size reference without making the room look staged"
        ),
        "placement": "positioned at full scale in a real bedroom",
        "background": "a bed or bedside furniture, rug, curtains, doorway, and natural window light",
        "hand_present": False,
        "camera_motion": "a wide room-level side drift and gentle push-in",
    },

    # Electronics and office items
    "home_office_device": {
        "label": "Electronics — home office setup",
        "types": ["electronics", "countertop_appliance", "other"],
        "setting": (
            "set up naturally in a real home office with its complete stand, cables, ports, controls, screen or output area, "
            "and included accessories visible. A keyboard, notebook, chair, and wall outlet establish realistic use"
        ),
        "placement": "set up at correct scale in a home-office workspace",
        "background": "a desk, keyboard, notebook, chair, cables, outlet, and ordinary office details",
        "hand_present": False,
        "camera_motion": "a desk-height front-to-side arc with subtle screen or material reflections",
    },
    "living_room_electronics": {
        "label": "Electronics — living room console",
        "types": ["electronics", "other"],
        "setting": (
            "installed naturally on or above a living-room media console. Show the entire device, stand, bezel, speakers, "
            "cables, remote, and accessories at correct scale with casual home decor around it"
        ),
        "placement": "installed at realistic scale in a living-room media area",
        "background": "a media console, remote, cables, wall, lamp, and ordinary living-room decor",
        "hand_present": False,
        "camera_motion": "a slow wide-angle media-console reveal with a small push-in",
    },

    # Fitness equipment
    "home_gym_equipment": {
        "label": "Fitness equipment — home gym",
        "types": ["fitness_large", "other"],
        "setting": (
            "assembled naturally in a real home gym or spare room. Show the complete frame, base, handles, pedals, rails, "
            "console, padding, attachments, and footprint at correct scale. A mat, water bottle, and small rack provide context"
        ),
        "placement": "assembled at full scale in a home-gym or spare-room setting",
        "background": "a floor mat, water bottle, small weight rack, wall, doorway, and ordinary home-gym details",
        "hand_present": False,
        "camera_motion": "a wide low-to-mid-height arc that reveals the full footprint and controls",
    },
    "fitness_living_space": {
        "label": "Fitness equipment — living space",
        "types": ["fitness_large", "other"],
        "setting": (
            "positioned in a realistic apartment living area as someone would actually store and use it. The whole product, "
            "floor contact points, moving parts, controls, and accessories remain visible with furniture nearby for scale"
        ),
        "placement": "positioned at full scale in a realistic apartment living area",
        "background": "a sofa or chair, floor mat, wall outlet, window, and normal apartment details",
        "hand_present": False,
        "camera_motion": "a wide handheld side reveal with natural parallax",
    },

    # Outdoor and patio products
    "patio_product": {
        "label": "Outdoor product — patio / deck",
        "types": ["outdoor_large", "furniture_large", "other"],
        "setting": (
            "placed naturally on a real patio or deck at correct outdoor scale. Show the full frame, fabric, shelves, wheels, "
            "handles, canopy, hardware, or included parts. Patio furniture, a fence, and plants provide believable context"
        ),
        "placement": "positioned at full scale on a real patio or deck",
        "background": "patio furniture, deck boards or concrete, fence, plants, and daylight",
        "hand_present": False,
        "camera_motion": "a wide outdoor half-orbit with gentle handheld movement",
    },
    "yard_driveway_product": {
        "label": "Outdoor product — yard / driveway",
        "types": ["outdoor_large", "floor_cleaning", "fitness_large", "other"],
        "setting": (
            "positioned naturally in a real yard or driveway with the complete product visible at accurate scale. Grass, concrete, "
            "garage edge, hose, tools, or outdoor storage provide casual real-life context"
        ),
        "placement": "positioned at full scale in a real yard or driveway",
        "background": "grass or concrete, a garage edge, outdoor tools, fence, and natural daylight",
        "hand_present": False,
        "camera_motion": "a practical wide-angle walk-around arc without dramatic movement",
    },

    # Universal fallback
    "garage_storage": {
        "label": "Large / mixed item — garage or storage area",
        "types": ["floor_cleaning", "fitness_large", "outdoor_large", "furniture_large", "other"],
        "setting": (
            "positioned naturally in a real garage, utility room, or storage area. Show the complete item and all important parts "
            "at accurate scale with shelves, boxes, tools, and floor markings providing real-world context"
        ),
        "placement": "positioned at full scale in a real garage or storage area",
        "background": "storage shelves, boxes, tools, concrete floor, and ordinary utility details",
        "hand_present": False,
        "camera_motion": "a wide practical side-to-front reveal with mild phone shake",
    },
    "custom": {
        "label": "Custom scene",
        "types": list(LIFESTYLE_PRODUCT_TYPES.keys()),
        "setting": "placed in the exact custom real-life scene supplied by the user",
        "placement": "positioned naturally in the custom scene supplied by the user",
        "background": "the user-supplied custom environment",
        "hand_present": False,
        "camera_motion": "a natural phone-camera move appropriate for the product size and custom scene",
    },
}

DEFAULT_LIFESTYLE_SCENE_BY_TYPE = {
    "small_handheld": "hand_bathroom",
    "clothing_shoe": "shoe_entryway",
    "countertop_appliance": "kitchen_appliance",
    "floor_cleaning": "vacuum_living_room",
    "furniture_large": "living_room_furniture",
    "electronics": "home_office_device",
    "fitness_large": "home_gym_equipment",
    "outdoor_large": "patio_product",
    "other": "custom",
}


def lifestyle_scene_options(product_type: str) -> list[str]:
    """Return scenes that make physical sense for the resolved product type."""
    resolved_type = product_type if product_type in LIFESTYLE_PRODUCT_TYPES else "other"
    options = [
        scene_key for scene_key, scene in LIFESTYLE_SCENES.items()
        if resolved_type in scene.get("types", [])
    ]
    default_scene = DEFAULT_LIFESTYLE_SCENE_BY_TYPE.get(resolved_type, "custom")
    if default_scene in options:
        options.remove(default_scene)
        options.insert(0, default_scene)
    if "custom" not in options:
        options.append("custom")
    return options


def resolve_lifestyle_scene(scene_key: str, custom_scene: str = "") -> dict:
    """Resolve a standard scene or turn the user's free-text scene into a complete scene profile."""
    scene = dict(LIFESTYLE_SCENES.get(scene_key, LIFESTYLE_SCENES["custom"]))
    custom_scene = re.sub(r"\s+", " ", (custom_scene or "").strip())
    if scene_key == "custom" and custom_scene:
        scene.update({
            "setting": (
                f"placed naturally in this exact real-life scene: {custom_scene}. The environment must be believable, "
                "lived-in, correctly scaled, and photographed casually rather than staged"
            ),
            "placement": f"positioned naturally in this exact scene: {custom_scene}",
            "background": custom_scene,
            "camera_motion": "a natural handheld arc, push-in, or wide reveal appropriate for the product's real size",
        })
    return scene


LIFESTYLE_IPHONE_STYLE = (
    "Unedited iPhone 16 photo, raw HEIC-to-JPEG look, zero retouching. True vertical 9:16 framing, 2k high quality, "
    "slightly imperfect crop, subtle phone-camera grain, realistic edge distortion, and natural shadows from ordinary real light. "
    "No studio lighting, softboxes, ring light, commercial reflections, color grading, or polished ad composition. "
)


def build_lifestyle_image_prompt(
    product_name: str,
    scene_key: str,
    product_type: str = "other",
    custom_scene: str = "",
) -> str:
    scene = resolve_lifestyle_scene(scene_key, custom_scene)
    profile = LIFESTYLE_PRODUCT_TYPES.get(product_type, LIFESTYLE_PRODUCT_TYPES["other"])
    normalized_name = (product_name or "").lower()
    supplement_like = any(word in normalized_name for word in (
        "gummies", "capsules", "supplement", "vitamin", "powder", "drink mix", "prebiotic", "probiotic", "sea moss", "enzyme", "collagen"
    ))
    hand_rule = (
        "Show one natural hand only, with correct fingers and a believable grip; the hand must not hide the product. "
        if scene.get("hand_present")
        else "Do not add a person or hand unless it is essential to the user-supplied custom scene. "
    )
    brightness_rule = ""
    if scene_key in ("hand_kitchen", "counter_kitchen", "counter_bathroom"):
        brightness_rule = (
            "Keep the lighting bright, natural, and well exposed. The counter should look clean and realistic with minimal clutter, "
            "not crowded, dirty, messy, or dark. "
        )
    if supplement_like and scene_key in ("hand_kitchen", "counter_kitchen", "counter_bathroom"):
        brightness_rule += (
            "For supplement or wellness products, make the counter scene especially clean and simple, with only one or two subtle "
            "background objects and no moody shadows. "
        )
    safety_rule = (
        "Do not include moving water, fire, steam, dirt, sand, powder clouds, pulsing light, animated electronic screens, pets, animals, or any living beings. "
        "Do not show cluttered environments, other brand titles, prices, retail messaging, cartoon or abstract environments, spaceships, levitating products, physics-breaking product orientation, or the same environment as the original listing image. "
        "Keep all visible text clear and readable rather than warped, hieroglyphic, or illegible. The product must be fully visible in frame during image generation, correctly scaled, correctly colored, and realistically lit so it matches the environment. "
    )
    return (
        f"{LIFESTYLE_IPHONE_STYLE}Photograph the exact {product_name} as {profile['description']}, {scene['setting']}. "
        f"{profile['framing']} {hand_rule}{brightness_rule}{safety_rule}Use all uploaded images as strict visual references for the real product: preserve its "
        "true dimensions, silhouette, colors, materials, texture, seams, controls, attachments, accessories, logo placement, "
        "physical label text where applicable, and exact proportions. Do not turn a large item into a miniature and do not enlarge "
        "a small item unnaturally. Show only the correct number of products and included parts. The environment should feel lived-in, "
        "casual, slightly imperfect, and believable, like a quick TikTok Shop customer photo. Do not make it look like AI, a 3D render, "
        "a catalog cutout, a floating mockup, a showroom, or a polished brand shoot. No rendered captions, promotional text, prices, "
        "stickers, graphics, or watermarks. Physical writing printed on the real product is allowed."
    )


def build_lifestyle_kling_prompt(
    product_name: str,
    product_details: str,
    scene_key: str,
    product_type: str = "other",
    custom_scene: str = "",
) -> str:
    scene = resolve_lifestyle_scene(scene_key, custom_scene)
    profile = LIFESTYLE_PRODUCT_TYPES.get(product_type, LIFESTYLE_PRODUCT_TYPES["other"])
    hand_present = bool(scene.get("hand_present"))
    subject = "the hand and product" if hand_present else "the product"
    pronoun = "they" if hand_present else "it"
    prompt = (
        f"Use the approved lifestyle image as the exact source image. Create a realistic vertical TikTok Shop UGC video of "
        f"{product_name} {scene['placement']}. Treat it as {profile['description']} at the exact real-world scale shown in the approved image. "
        f"{subject.capitalize()} remain completely stationary and fixed for the entire clip; {pronoun} must not lift, rotate, slide, bend, "
        "float, duplicate, shrink, grow, melt, warp, open, close, or change shape. Strictly preserve these details: "
        f"{product_details}. Keep the same environment and lighting: {scene['background']}. Only the handheld phone camera moves: "
        f"{scene.get('camera_motion', 'a natural side-to-side arc and slight push-in')}, with realistic parallax, contact shadows, reflections, "
        "depth of field, and small phone micro-shake. For furniture, appliances, vacuums, electronics, fitness equipment, and outdoor products, "
        "keep the full footprint and major parts visible and correctly attached. The product must stay entirely in frame and occupy most of the video, ideally 80% or more of the clip. Repeat: the product stays fixed while only the camera moves. "
        "Do not add moving water, fire, steam, dirt, sand, powder, pulsing lights, animated electronic screens, pets, animals, or living beings. Do not create mismatching lighting between the product and environment, warped or illegible text, mis-colored products, cluttered environments, other brand titles, prices or retail messaging, levitation, physics-breaking orientation, or unrealistic/cartoon/abstract environments. "
        "No rendered text, captions, stickers, particles, new people or hands, flicker, broken shadows, hallucinated accessories, "
        "miniaturization, scale changes, or polished commercial styling. Sound off. True 9:16."
    )
    return re.sub(r"\s+", " ", prompt).strip()[:2800]


STYLE_LABELS = {
    "shoe_video": "👟 Shoe Video (feet-only)",
    "texthook_broll": "📱 Text-Hook B-Roll",
    "warehouse": "🏬 Warehouse",
    "pool": "🏝️ Pool",
    "lifestyle_animation": "📸 Lifestyle Animation",
    "avatar_outfit": "🪞 Avatar Outfit",
}

LIFESTYLE_IMAGE_MODEL_LABEL = "Grok Imagine Image Quality · 2k · 9:16"
LIFESTYLE_VIDEO_MODEL_LABEL = "Kling O1 · 720p · 5s · start frame"
AVATAR_OUTFIT_IMAGE_MODEL_LABEL = "GPT Image 2 · 2k · High · 9:16 · Magnific · 2 references"
AVATAR_OUTFIT_VIDEO_MODEL_LABEL = "Kling O1 · 720p · ~8s · start frame"


def resolved_style_duration(style: str, selected_duration: int = 15) -> int:
    if style == "warehouse":
        return 5
    if style in ("texthook_broll", "pool"):
        return 8
    if style == "lifestyle_animation":
        return 5
    if style == "avatar_outfit":
        return 8
    return int(selected_duration)


# ═══════════════════════════════════════════════════════════════════
#  SCRAPER
# ═══════════════════════════════════════════════════════════════════

def _name_from_url(url: str) -> str:
    """Build a readable product name from a TikTok product URL slug."""
    try:
        parsed = urlparse(url)
    except Exception:
        return "Unknown Product"

    ignored = {
        "us", "uk", "ca", "au", "pdp", "dp", "ip", "product", "products",
        "shop", "t", "view", "detail", "item", "share",
    }
    candidates = []
    for raw_part in parsed.path.strip("/").split("/"):
        part = unquote(raw_part).strip()
        lowered = part.lower()
        if not part or lowered in ignored or part.isdigit():
            continue
        # Remove a trailing product ID when TikTok appends it to the slug.
        part = re.sub(r"[-_]?\d{10,}$", "", part).strip("-_")
        if len(part) < 4 or not re.search(r"[A-Za-z]", part):
            continue
        # Do not mistake TikTok short-link/share tokens for product names.
        if "-" not in part and "_" not in part and re.fullmatch(r"(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9]{6,18}", part):
            continue
        candidates.append(part)

    if not candidates:
        return "Unknown Product"

    best = max(candidates, key=lambda value: (value.count("-") + value.count("_"), len(value)))
    words = re.sub(r"[-_]+", " ", best)
    words = re.sub(r"\s+", " ", words).strip()
    words = " ".join(words.split()[:16])
    return words.title() if words else "Unknown Product"


def _extract_meta_candidates(html: str):
    """Read title-like values and canonical URLs from page metadata and image attributes."""
    names = []
    urls = []

    for tag in re.findall(r"<meta\b[^>]*>", html, flags=re.IGNORECASE):
        attrs = dict(
            (key.lower(), html_unescape(value))
            for key, _quote, value in re.findall(
                r"([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*([\"'])(.*?)\2",
                tag,
                flags=re.DOTALL,
            )
        )
        marker = (attrs.get("property") or attrs.get("name") or attrs.get("itemprop") or "").lower()
        content = re.sub(r"\s+", " ", (attrs.get("content") or "")).strip()
        if not content:
            continue
        if marker in {
            "og:title", "twitter:title", "title", "product:name", "product_name",
            "product:title", "product_title", "item:name", "item_name",
        }:
            names.append(content)
        elif marker in {"og:description", "twitter:description", "description"}:
            # TikTok's ID-only product pages sometimes expose the product title only
            # at the start of a description. Keep the first concise segment as a candidate.
            first_segment = re.split(r"[|•\n]|\s[-–—]\s|\.\s", content, maxsplit=1)[0].strip()
            first_segment = re.sub(r"^(shop|buy|discover)\s+", "", first_segment, flags=re.IGNORECASE)
            if 4 <= len(first_segment) <= 180:
                names.append(first_segment)
        elif marker in {"og:url", "twitter:url"}:
            urls.append(content)

    for tag in re.findall(r"<link\b[^>]*>", html, flags=re.IGNORECASE):
        attrs = dict(
            (key.lower(), html_unescape(value))
            for key, _quote, value in re.findall(
                r"([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*([\"'])(.*?)\2",
                tag,
                flags=re.DOTALL,
            )
        )
        if (attrs.get("rel") or "").lower() == "canonical" and attrs.get("href"):
            urls.append(attrs["href"].strip())

    # Product images frequently carry the title in alt/title/aria-label even when
    # the page's Open Graph title is generic.
    for tag in re.findall(r"<img\b[^>]*>", html, flags=re.IGNORECASE):
        attrs = dict(
            (key.lower(), html_unescape(value))
            for key, _quote, value in re.findall(
                r"([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*([\"'])(.*?)\2",
                tag,
                flags=re.DOTALL,
            )
        )
        for attr_name in ("alt", "title", "aria-label"):
            candidate = re.sub(r"\s+", " ", attrs.get(attr_name, "")).strip()
            if 4 <= len(candidate) <= 180 and candidate.lower() not in {
                "image", "product image", "tiktok shop", "shop", "photo"
            }:
                names.append(candidate)

    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if title_match:
        names.append(re.sub(r"<[^>]+>", " ", title_match.group(1)))

    return names, urls


def _extract_raw_title_candidates(html: str):
    """Find product-title fields in TikTok hydration blobs, including escaped JSON."""
    candidates = []
    keys = (
        "product_name", "productName", "product_title", "productTitle",
        "item_name", "itemName", "item_title", "itemTitle",
        "display_name", "displayName", "seo_title", "seoTitle",
        "goods_name", "goodsName", "goods_title", "goodsTitle",
        "share_title", "shareTitle", "product_display_name", "productDisplayName",
        "sku_name", "skuName", "listing_name", "listingName",
    )
    key_pattern = "|".join(re.escape(key) for key in keys)
    patterns = [
        rf'["\'](?:{key_pattern})["\']\s*:\s*["\']([^"\']{{4,220}})["\']',
        rf'\\["\'](?:{key_pattern})\\["\']\s*:\s*\\["\'](.{{4,220}}?)\\["\']',
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, html, flags=re.IGNORECASE | re.DOTALL):
            value = match.group(1)
            value = value.replace("\\u002F", "/").replace("\\/", "/")
            try:
                value = bytes(value, "utf-8").decode("unicode_escape")
            except Exception:
                pass
            value = html_unescape(value)
            value = re.sub(r"\s+", " ", value).strip()
            if value:
                candidates.append(value)
    return candidates


def _extract_visible_text_excerpt(html: str, limit: int = 2400) -> str:
    """Get a compact visible-text excerpt from a page for fallback title recovery."""
    try:
        cleaned = re.sub(r"<script\b.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"<style\b.*?</style>", " ", cleaned, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"<noscript\b.*?</noscript>", " ", cleaned, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = html_unescape(cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        noisy = [
            "tiktok", "shop", "for you", "following", "friends", "live", "upload", "search",
            "download app", "log in", "sign up", "privacy policy", "terms of service"
        ]
        parts = []
        for chunk in re.split(r"(?<=[.!?])\s+|\s+[|•]\s+", cleaned):
            chunk_clean = chunk.strip()
            if len(chunk_clean) < 3:
                continue
            lowered = chunk_clean.lower()
            if sum(marker in lowered for marker in noisy) >= 3:
                continue
            parts.append(chunk_clean)
            if len(" ".join(parts)) >= limit:
                break
        excerpt = " ".join(parts)
        return excerpt[:limit]
    except Exception:
        return ""


def recover_product_name_with_page_context(api_key: str, html: str, image_urls: list[str], page_url: str = "", product_id: str = "") -> str:
    """Fallback product-name recovery using page text plus up to 3 images."""
    if not api_key:
        return ""

    visible_text = _extract_visible_text_excerpt(html)
    image_blocks = []
    for image_url in list(image_urls or [])[:3]:
        try:
            response = requests.get(image_url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            media_type = (response.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip().lower()
            if media_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
                suffix = Path(urlparse(image_url).path).suffix.lower()
                media_type = {
                    ".png": "image/png",
                    ".webp": "image/webp",
                    ".gif": "image/gif",
                }.get(suffix, "image/jpeg")
            image_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64.b64encode(response.content).decode("ascii"),
                },
            })
        except Exception:
            continue

    if not visible_text and not image_blocks:
        return ""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        content = []
        if visible_text:
            content.append({"type": "text", "text": f"Visible page text excerpt:\n{visible_text[:2400]}"})
        content.extend(image_blocks)
        content.append({
            "type": "text",
            "text": (
                "Recover the real product name for this TikTok Shop item. Use the visible page text and listing images. "
                + (f"TikTok product ID: {product_id}. " if product_id else "")
                + (f"Page URL: {page_url}. " if page_url else "")
                + "Return the clearest concise retail product name only, based on what is actually visible. Do not invent claims, sizes, or variants that are not visible."
            ),
        })
        response = client.messages.create(
            model=MODEL,
            max_tokens=250,
            system=(
                "You identify retail product names from weak e-commerce page signals. Read only what is actually shown in the page text or images. "
                "Return ONLY JSON: {\"product_name\":\"...\",\"confidence\":\"high|medium|low\"}."
            ),
            messages=[{"role": "user", "content": content}],
        )
        text_blocks = [block.text for block in response.content if getattr(block, "type", "") == "text"]
        parsed = _extract_json_object("\n".join(text_blocks))
        candidate = _clean_product_name_candidate((parsed or {}).get("product_name", ""))
        if candidate.lower() in {"", "unknown", "unknown product", "product"}:
            return ""
        return candidate[:100]
    except Exception:
        return ""


IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".avif")
REVIEW_IMAGE_HINTS = (
    "review", "rating", "feedback", "buyer", "customer", "comment",
    "ugc", "user_content", "usercontent", "buyer_show", "buyershow",
    "review_media", "reviewmedia", "review_image", "reviewimage",
    "review_photo", "reviewphoto", "晒单", "评价",
)
NON_PRODUCT_IMAGE_HINTS = (
    "avatar", "profile", "icon", "logo", "badge", "sprite", "favicon",
)


def _looks_like_image_url(value: str) -> bool:
    """Return True for normal image URLs and common TikTok CDN image URLs."""
    if not isinstance(value, str) or not value.startswith(("http://", "https://")):
        return False
    lowered = html_unescape(value).lower()
    return (
        any(ext in lowered for ext in IMAGE_EXTENSIONS)
        or any(token in lowered for token in ("image", "img", "tos-", "p16-", "tplv-"))
    )


def _dedupe_image_urls(urls):
    seen = set()
    cleaned_urls = []
    for value in urls:
        if not value:
            continue
        cleaned = html_unescape(str(value)).replace("\\u002F", "/").replace("\\/", "/").strip()
        if cleaned and cleaned not in seen and _looks_like_image_url(cleaned):
            seen.add(cleaned)
            cleaned_urls.append(cleaned)
    return cleaned_urls


def _collect_categorized_images(obj, path=(), depth=0, max_depth=12):
    """Collect listing and review/customer images while retaining JSON path context."""
    if depth > max_depth:
        return [], []

    listing_images = []
    review_images = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            child_path = path + (str(key).lower(),)
            if isinstance(value, str) and _looks_like_image_url(value):
                context = " ".join(child_path)
                leaf = child_path[-1] if child_path else ""
                # Skip avatars, logos and UI graphics unless the path explicitly says review media/photo.
                is_review = any(token in context for token in REVIEW_IMAGE_HINTS)
                is_non_product = any(token in leaf for token in NON_PRODUCT_IMAGE_HINTS)
                if is_non_product and not is_review:
                    continue
                if is_review:
                    review_images.append(value)
                else:
                    listing_images.append(value)
            else:
                nested_listing, nested_review = _collect_categorized_images(
                    value, child_path, depth + 1, max_depth
                )
                listing_images.extend(nested_listing)
                review_images.extend(nested_review)
    elif isinstance(obj, list):
        for item in obj:
            nested_listing, nested_review = _collect_categorized_images(
                item, path, depth + 1, max_depth
            )
            listing_images.extend(nested_listing)
            review_images.extend(nested_review)

    return listing_images, review_images


def _find_images_in_dict(obj, depth=0, max_depth=8):
    """Backward-compatible helper returning all categorized images."""
    listing, review = _collect_categorized_images(obj, depth=depth, max_depth=max_depth)
    return _dedupe_image_urls(listing + review)


def _find_product_names_in_dict(obj, depth=0, max_depth=10):
    """Find likely product titles inside TikTok/commerce JSON payloads."""
    if depth > max_depth:
        return []
    names = []
    likely_keys = {
        "product_name", "productname", "product_title", "producttitle",
        "item_name", "itemname", "item_title", "itemtitle",
        "display_name", "displayname", "title", "name",
    }
    if isinstance(obj, dict):
        for key, value in obj.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if normalized in {re.sub(r"[^a-z0-9]", "", k) for k in likely_keys}:
                if isinstance(value, str):
                    candidate = html_unescape(value).strip()
                    # Reject generic page/app labels and IDs.
                    if (
                        4 <= len(candidate) <= 180
                        and not candidate.isdigit()
                        and candidate.lower() not in {
                            "tiktok", "tiktok shop", "shop", "product", "for you",
                            "log in", "sign up", "unknown product"
                        }
                        and not candidate.startswith("http")
                    ):
                        names.append(candidate)
            names.extend(_find_product_names_in_dict(value, depth + 1, max_depth))
    elif isinstance(obj, list):
        for item in obj:
            names.extend(_find_product_names_in_dict(item, depth + 1, max_depth))
    return names


def _product_id_from_url(url: str) -> str:
    """Extract the numeric TikTok Shop product identifier from ID-only share links."""
    try:
        parsed = urlparse(url)
    except Exception:
        return ""
    match = re.search(r"/(?:view/)?product/(\d{12,24})(?:/|$)", parsed.path, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def _clean_product_name_candidate(value: str) -> str:
    """Normalize a possible retail title without inventing missing wording."""
    candidate = re.sub(r"\s+", " ", html_unescape(str(value or ""))).strip(" -|–—:;,.\t\r\n")
    candidate = re.sub(
        r"\s*[|–—]\s*(TikTok(?: Shop)?|Shop|Buy Now|Free Shipping).*$",
        "",
        candidate,
        flags=re.IGNORECASE,
    ).strip()
    candidate = re.sub(r"^(product|item|shop)\s*[:|-]\s*", "", candidate, flags=re.IGNORECASE)
    return candidate[:180].strip()


def recover_product_name_from_images(api_key: str, image_urls: list[str], product_id: str = "") -> str:
    """Use Claude vision only as a fallback when an ID-only TikTok page exposes no title.

    The model is told to read visible brand/product wording and avoid fabricating a
    long marketplace title. This call runs only for an otherwise unnamed product.
    """
    if not api_key:
        return ""

    image_blocks = []
    for image_url in list(image_urls or [])[:3]:
        try:
            response = requests.get(image_url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            media_type = (response.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip().lower()
            if media_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
                suffix = Path(urlparse(image_url).path).suffix.lower()
                media_type = {
                    ".png": "image/png",
                    ".webp": "image/webp",
                    ".gif": "image/gif",
                }.get(suffix, "image/jpeg")
            image_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64.b64encode(response.content).decode("ascii"),
                },
            })
        except Exception:
            continue

    if not image_blocks:
        return ""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=MODEL,
            max_tokens=300,
            system=(
                "Identify a retail product from TikTok Shop listing images. Read only visible brand, product, variant, "
                "and packaging wording. Return a concise, useful product name. Do not invent benefits, size, flavor, "
                "model, or marketplace wording that is not visible. If the exact long listing title is unavailable, "
                "return the visible brand plus the clearest product type. Return ONLY JSON: "
                '{"product_name":"...","confidence":"high|medium|low"}'
            ),
            messages=[{
                "role": "user",
                "content": image_blocks + [{
                    "type": "text",
                    "text": (
                        "Read the product name from these listing images. "
                        + (f"TikTok product ID: {product_id}. " if product_id else "")
                        + "Do not return Unknown Product unless there is truly no readable product identity."
                    ),
                }],
            }],
        )
        text_blocks = [block.text for block in response.content if getattr(block, "type", "") == "text"]
        parsed = _extract_json_object("\n".join(text_blocks))
        candidate = _clean_product_name_candidate((parsed or {}).get("product_name", ""))
        if candidate.lower() in {"", "unknown", "unknown product", "product"}:
            return ""
        return candidate[:100]
    except Exception:
        return ""


def _best_product_name(candidates):
    """Choose the most product-like title from scraped candidates."""
    cleaned = []
    generic_markers = {
        "unknown product", "tiktok shop", "tiktok", "shop", "product", "view product",
        "log in", "sign up", "for you", "discover", "shopping made easy",
    }
    for value in candidates:
        candidate = _clean_product_name_candidate(value)
        if not candidate or candidate.lower() in generic_markers:
            continue
        if candidate.startswith(("http://", "https://")) or candidate.isdigit():
            continue
        # Reject shell-page or cookie/captcha copy rather than forwarding it as a title.
        lowered = candidate.lower()
        if any(marker in lowered for marker in (
            "enable javascript", "verify to continue", "captcha", "privacy policy",
            "terms of service", "download the app", "something went wrong",
        )):
            continue
        if len(candidate.split()) > 30:
            continue
        cleaned.append(candidate)

    if not cleaned:
        return ""

    cleaned = list(dict.fromkeys(cleaned))

    def score(candidate: str):
        words = candidate.split()
        product_word_bonus = 1 if 2 <= len(words) <= 18 else 0
        brand_title_bonus = 1 if any(char.isupper() for char in candidate) else 0
        punctuation_penalty = -1 if candidate.count(":") + candidate.count(";") > 2 else 0
        return product_word_bonus, brand_title_bonus, punctuation_penalty, min(len(words), 18), len(candidate)

    cleaned.sort(key=score, reverse=True)
    return cleaned[0][:100]


def scrape_product(url: str, api_key: str = "") -> dict | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
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

        meta_name_candidates, meta_url_candidates = _extract_meta_candidates(html)

        listing_images = []
        review_images = []
        name_candidates = list(meta_name_candidates)
        name_candidates.extend(_extract_raw_title_candidates(html))
        if img_match:
            listing_images.append(img_match.group(1))

        # JSON-LD normally contains official listing images.
        ld_blocks = re.findall(
            r'<script\s+type=["\']application/ld\+json["\']>\s*(.*?)\s*</script>',
            html, re.DOTALL | re.IGNORECASE
        )
        for block in ld_blocks:
            try:
                ld = json.loads(html_unescape(block))
                name_candidates.extend(_find_product_names_in_dict(ld))
                ld_listing, ld_review = _collect_categorized_images(ld)
                listing_images.extend(ld_listing)
                review_images.extend(ld_review)
            except (json.JSONDecodeError, TypeError):
                pass

        # Parse all hydration/application JSON payloads. TikTok often places review media
        # in these blocks even when it is not visible in the initial HTML markup.
        json_blocks = re.findall(
            r'<script[^>]*type=["\']application/json["\'][^>]*>\s*(.*?)\s*</script>',
            html, re.DOTALL | re.IGNORECASE
        )
        for block in json_blocks:
            try:
                payload = json.loads(html_unescape(block))
            except (json.JSONDecodeError, TypeError):
                continue
            name_candidates.extend(_find_product_names_in_dict(payload))
            payload_listing, payload_review = _collect_categorized_images(payload)
            listing_images.extend(payload_listing)
            review_images.extend(payload_review)

        # Image URLs in raw HTML. Nearby review-related text determines the bucket.
        raw_image_pattern = re.compile(
            r'https?://[^"\'\s<>]+(?:\.jpg|\.jpeg|\.png|\.webp|\.avif)(?:\?[^"\'\s<>]*)?',
            re.IGNORECASE,
        )
        for match in raw_image_pattern.finditer(html):
            image_url = match.group(0)
            context = html[max(0, match.start() - 450): min(len(html), match.end() + 450)].lower()
            if any(token in context for token in REVIEW_IMAGE_HINTS):
                review_images.append(image_url)
            elif any(token in image_url.lower() for token in ("product", "pdp", "origin", "large", "800", "1000", "1200")):
                listing_images.append(image_url)

        listing_images = _dedupe_image_urls(listing_images)
        review_images = _dedupe_image_urls(review_images)

        # Do not repeat official listing images inside the review-photo section.
        listing_set = set(listing_images)
        review_images = [image for image in review_images if image not in listing_set]

        if not listing_images and review_images:
            # A review photo can still be used as the primary reference if that is all TikTok exposes.
            listing_images = [review_images[0]]

        all_images = _dedupe_image_urls(listing_images + review_images)
        if not all_images:
            return None

        name = _best_product_name(name_candidates)
        name_source = "page_metadata" if name else ""
        if not name or name == "Unknown Product":
            # Slug-based PDP and short-share redirects can still expose a readable name.
            fallback_urls = [resp.url] + meta_url_candidates + [url]
            for fallback_url in fallback_urls:
                candidate_name = _name_from_url(fallback_url)
                if candidate_name and candidate_name != "Unknown Product":
                    name = candidate_name
                    name_source = "url_slug"
                    break

        product_id = _product_id_from_url(resp.url) or _product_id_from_url(url)
        if (not name or name == "Unknown Product") and api_key:
            recovered_name = recover_product_name_with_page_context(
                api_key=api_key,
                html=html,
                image_urls=all_images,
                page_url=resp.url,
                product_id=product_id,
            )
            if recovered_name:
                name = recovered_name
                name_source = "page_context_fallback"

        if (not name or name == "Unknown Product") and api_key:
            recovered_name = recover_product_name_from_images(
                api_key=api_key,
                image_urls=all_images,
                product_id=product_id,
            )
            if recovered_name:
                name = recovered_name
                name_source = "image_fallback"

        if not name:
            name = "Unknown Product"
            name_source = "unresolved"

        return {
            "name": name[:100],
            "name_source": name_source,
            "product_id": product_id,
            "images": all_images[:36],
            "listing_images": listing_images[:18],
            "review_images": review_images[:24],
            "source_url": url,
        }

    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════
#  PROMPT WRITER (Claude only — no MCP, cheap + fast)
# ═══════════════════════════════════════════════════════════════════

def _extract_json_object(raw_text: str) -> dict | None:
    cleaned = re.sub(r'```json\s*', '', raw_text)
    cleaned = re.sub(r'```\s*', '', cleaned)
    json_start = cleaned.find("{")
    json_end = cleaned.rfind("}") + 1
    if json_start < 0 or json_end <= json_start:
        return None
    try:
        return json.loads(cleaned[json_start:json_end])
    except json.JSONDecodeError:
        return None


def write_hooks(api_key: str, product_name: str, style: str = "texthook_broll") -> dict:
    """Generate five hooks from the shared library used by every workflow. Cheap/fast — no MCP."""
    system = WAREHOUSE_HOOKS_SYSTEM
    task = (
        f"Write 5 deal-drop/FOMO text hooks for this product: {product_name}. "
        f"The video style is {style}. Use the shared hook library for every workflow and choose five different angles."
    )
    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=MODEL,
            max_tokens=1400,
            system=system,
            messages=[{"role": "user", "content": task}],
        )
        parsed = _extract_json_object(response.content[0].text)
        if parsed is not None:
            return parsed
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
    broll_scene: str | None = None,
) -> dict:
    """Use Claude to write the Seedance prompt. No MCP, no Magnific."""
    if style == "shoe_video":
        vo = VOICEOVER_WITH_SCRIPT.format(script=voice_script) if voice_script else VOICEOVER_SILENT
        system = SHOE_VIDEO_SYSTEM.format(voiceover_instruction=vo)
    elif style == "warehouse":
        system = WAREHOUSE_PROMPT_SYSTEM
    elif style == "pool":
        system = POOL_PROMPT_SYSTEM
    else:
        # The selected hook is added after generation with FFmpeg.
        system = TEXTHOOK_PROMPT_SYSTEM

    dur = resolved_style_duration(style, duration)
    if style == "texthook_broll":
        chosen_broll_scene = broll_scene or choose_broll_scene()
        user_task = (
            f"Write a {dur}-second Seedance 2.0 prompt for this product: {product_name}. "
            "The generator will receive the selected reference images separately, so instruct it to match them exactly.\n\n"
            f"MANDATORY OPENING B-ROLL SCENE — USE THIS EXACT SCENE, DO NOT SUBSTITUTE WALKING:\n{chosen_broll_scene}"
        )
    else:
        chosen_broll_scene = None
        user_task = (
            f"Write a {dur}-second Seedance 2.0 prompt for this product: {product_name}. "
            "The generator will receive the selected reference images separately, so instruct it to match them exactly."
        )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user_task}],
        )

        parsed = _extract_json_object(response.content[0].text)
        if parsed is None:
            return {
                "prompt": response.content[0].text,
                "product_name": product_name,
                "error": "Couldn't parse JSON",
            }

        prompt_text = str(parsed.get("prompt") or "").strip()
        parsed["char_count"] = len(prompt_text)

        # The Warehouse skill requires a verified, actual count below 1,900 characters.
        if style == "warehouse" and prompt_text and len(prompt_text) >= 1900:
            retry = client.messages.create(
                model=MODEL,
                max_tokens=2048,
                system=system,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Rewrite this Warehouse prompt so the actual Python len() is under 1900 characters. "
                        f"Preserve every product-accuracy detail and all hard rules; trim only background wording.\n\n"
                        f"Product: {product_name}\nPrompt to shorten:\n{prompt_text}"
                    ),
                }],
            )
            retry_parsed = _extract_json_object(retry.content[0].text)
            if retry_parsed and retry_parsed.get("prompt"):
                parsed = retry_parsed
                prompt_text = str(parsed.get("prompt") or "").strip()
                parsed["char_count"] = len(prompt_text)

        if style == "warehouse" and len(prompt_text) >= 1900:
            return {
                "error": f"Warehouse prompt is {len(prompt_text)} characters; it must be under 1900.",
                "product_name": product_name,
                "prompt": prompt_text,
                "char_count": len(prompt_text),
            }

        if chosen_broll_scene:
            parsed["broll_scene"] = chosen_broll_scene
        return parsed

    except Exception as e:
        return {"error": str(e), "product_name": product_name}


# ═══════════════════════════════════════════════════════════════════
#  VIDEO GENERATOR (Claude + Magnific MCP)
# ═══════════════════════════════════════════════════════════════════

GENERATE_SYSTEM = """You are a video production assistant. You have access to Magnific tools.

Your job:
1. Upload every provided product image to Magnific using creations_upload_image.
2. Generate a video using video_generate with:
   - The prompt provided
   - EVERY uploaded image attached only as a general image/reference input for visual accuracy
   - NEVER use start_image, start frame, first frame, initial frame, end frame, or keyframe mode
   - Do not make any uploaded image the opening frame of the video
   - Reference image 1 may receive the highest packaging-accuracy priority, but it is still only a general reference
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
    image_urls: list[str] | None = None,
) -> dict:
    """Upload one or more reference images + generate video via Magnific MCP."""
    mcp_servers = [{
        "type": "url",
        "url": MAGNIFIC_MCP_URL,
        "name": MAGNIFIC_MCP_NAME,
    }]
    if magnific_token:
        mcp_servers[0]["authorization_token"] = magnific_token

    try:
        client = anthropic.Anthropic(api_key=api_key)
        refs = [u for u in (image_urls or [image_url]) if u]
        if not refs:
            refs = [image_url]
        refs_text = "\n".join(f"Reference image {i+1}: {url}" for i, url in enumerate(refs))

        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=GENERATE_SYSTEM,
            messages=[{
                "role": "user",
                "content": (
                    f"Upload every image below and generate a {duration}s video.\n"
                    f"Attach ALL uploaded images only as general image/reference inputs. "
                    f"NEVER use any image as a start frame, start_image, initial frame, end frame, or keyframe.\n"
                    f"Image 1 has the highest product-accuracy priority, but it must still remain a general reference only.\n"
                    f"{refs_text}\n\n"
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



def generate_lifestyle_image_grok(
    xai_api_key: str,
    product_name: str,
    reference_urls: list[str],
    prompt: str,
) -> dict:
    """Generate one 2K, 9:16 lifestyle approval image with the xAI Grok Imagine API."""
    if not xai_api_key:
        return {"creation_id": None, "status": "error", "error": "The xAI API key is missing."}

    # Grok multi-image editing currently accepts up to three source images.
    refs = []
    for url in reference_urls or []:
        cleaned = str(url or "").strip()
        if cleaned and cleaned not in refs:
            refs.append(cleaned)
        if len(refs) == 3:
            break

    if not refs:
        return {"creation_id": None, "status": "error", "error": "Select at least one product reference image."}

    # Multi-image edit mode allows the requested 9:16 output ratio. When only one
    # product reference is selected, repeat it as the second reference so Grok uses
    # the multi-image request shape while preserving the same product appearance.
    request_refs = refs if len(refs) >= 2 else [refs[0], refs[0]]
    payload = {
        "model": XAI_IMAGE_MODEL,
        "prompt": (
            f"Create exactly one lifestyle image for {product_name}. "
            "Treat every supplied image only as a visual reference for the same product. "
            "Preserve its packaging, colors, logos, labels, shape, material, proportions, and real-world scale exactly. "
            "Do not create multiple copies of the product merely because a reference image is repeated.\n\n"
            f"{prompt}"
        ),
        "images": [
            {"type": "image_url", "url": url}
            for url in request_refs
        ],
        "aspect_ratio": "9:16",
        "resolution": "2k",
        "response_format": "url",
        "n": 1,
    }

    try:
        response = requests.post(
            XAI_IMAGE_API_URL,
            headers={
                "Authorization": f"Bearer {xai_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=300,
        )

        if response.status_code >= 400:
            try:
                error_payload = response.json()
                if isinstance(error_payload, dict):
                    nested = error_payload.get("error")
                    if isinstance(nested, dict):
                        error_message = nested.get("message") or nested.get("code")
                    else:
                        error_message = nested
                    error_message = error_message or error_payload.get("message")
                else:
                    error_message = None
            except Exception:
                error_message = None
            error_message = error_message or (response.text or "Unknown xAI API error")
            return {
                "creation_id": None,
                "status": "error",
                "error": f"xAI image request failed ({response.status_code}): {str(error_message)[:500]}",
            }

        result_payload = response.json()
        images = result_payload.get("data") if isinstance(result_payload, dict) else None
        first_image = images[0] if isinstance(images, list) and images else {}
        image_url = first_image.get("url") if isinstance(first_image, dict) else None
        if not image_url:
            return {
                "creation_id": None,
                "status": "error",
                "error": "xAI completed the request but did not return an image URL.",
            }

        creation_id = f"grok_image_{hashlib.sha1(image_url.encode('utf-8')).hexdigest()[:16]}"
        return {
            "creation_id": creation_id,
            "status": "completed",
            "url": image_url,
            "preview_url": image_url,
            "provider": "xAI",
            "image_model": XAI_IMAGE_MODEL,
            "image_resolution": "2k",
            "image_aspect_ratio": "9:16",
            "reference_count": len(refs),
            "mime_type": first_image.get("mime_type") if isinstance(first_image, dict) else None,
            "revised_prompt": first_image.get("revised_prompt") if isinstance(first_image, dict) else None,
        }
    except requests.Timeout:
        return {"creation_id": None, "status": "error", "error": "The xAI image request timed out."}
    except Exception as exc:
        return {"creation_id": None, "status": "error", "error": f"xAI image generation failed: {exc}"}


def generate_lifestyle_kling_magnific(
    api_key: str,
    magnific_token: str,
    approved_image_url: str,
    prompt: str,
    duration: int,
) -> dict:
    """Animate an approved lifestyle still with Kling O1 through the same Magnific MCP connection."""
    duration = 5
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
            system=LIFESTYLE_KLING_GENERATE_SYSTEM,
            messages=[{
                "role": "user",
                "content": (
                    f"Approved lifestyle image: {approved_image_url}\n"
                    f"Generate a 5-second Kling O1 video with start frame behavior from the approved image, 720p resolution, 9:16 aspect ratio, and sound off.\n\nKling prompt:\n{prompt}"
                ),
            }],
            mcp_servers=mcp_servers,
            tools=[{"type": "mcp_toolset", "mcp_server_name": MAGNIFIC_MCP_NAME}],
            betas=[MCP_BETA],
        )
        return _parse_magnific_creation_response(response)
    except Exception as exc:
        return {"creation_id": None, "status": "error", "error": str(exc)}


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

def _extract_status_payload(payload, result: dict):
    """Extract status and output URLs from nested Magnific creation responses."""
    url_candidates = []

    def walk(value, path=()):
        if isinstance(value, dict):
            for key, child in value.items():
                key_text = str(key)
                key_lower = key_text.lower()
                child_path = path + (key_lower,)

                if key_lower in {"status", "state", "creation_status"} and isinstance(child, str):
                    normalized = child.strip().lower()
                    status_aliases = {
                        "succeeded": "completed",
                        "success": "completed",
                        "done": "completed",
                        "finished": "completed",
                        "pending": "queued",
                        "running": "processing",
                        "failed": "error",
                        "failure": "error",
                    }
                    result["status"] = status_aliases.get(normalized, normalized)

                if isinstance(child, str) and child.startswith(("http://", "https://")):
                    path_text = " ".join(child_path)
                    score = 0
                    if key_lower in {"videourl", "video_url", "video", "downloadurl", "download_url"}:
                        score += 120
                    elif key_lower in {"outputurl", "output_url", "resulturl", "result_url", "mediaurl", "media_url"}:
                        score += 105
                    elif key_lower in {"url", "fileurl", "file_url"}:
                        score += 75
                    elif "preview" in key_lower:
                        score += 55
                    if any(token in path_text for token in ("output", "result", "video", "media", "asset", "download")):
                        score += 25
                    if any(token in path_text for token in ("input", "reference", "source_image", "uploaded_image")):
                        score -= 80
                    if any(token in child.lower() for token in (".mp4", ".mov", ".m4v", "video")):
                        score += 30
                    url_candidates.append((score, "preview" in key_lower or "preview" in path_text, child))

                walk(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, path + (str(index),))

    walk(payload)
    if url_candidates:
        url_candidates.sort(key=lambda item: item[0], reverse=True)
        for _score, is_preview, url in url_candidates:
            if is_preview and not result.get("preview_url"):
                result["preview_url"] = url
            elif not is_preview and not result.get("url"):
                result["url"] = url
        if not result.get("url"):
            result["url"] = url_candidates[0][2]
    return result


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
                        _extract_status_payload(parsed, result)
                        for field in ("status", "url", "preview_url"):
                            if parsed.get(field):
                                result[field] = parsed[field]
                except (json.JSONDecodeError, TypeError):
                    pass

            elif block.type == "mcp_tool_result" and getattr(block, "content", None):
                for sub in block.content:
                    if not hasattr(sub, "text"):
                        continue
                    try:
                        tool_payload = json.loads(sub.text)
                        _extract_status_payload(tool_payload, result)
                    except (json.JSONDecodeError, TypeError):
                        pass

        # Never mark the job finished until an actual output URL is available.
        if result.get("status") == "completed" and not (result.get("url") or result.get("preview_url")):
            result["status"] = "processing"
        return result

    except Exception as e:
        return {"status": "error", "url": None, "error": str(e)}

def push_generated_image_to_director(
    ingest_key: str,
    ingest_url: str,
    image_url: str,
    product_name: str,
    caption: str = "",
    scene_prompt: str = "",
    meta: dict | None = None,
) -> tuple[bool, str]:
    """Send one generated image into the Momentum Academy Director ingest flow.

    Send the hosted image URL first so the request stays far below serverless payload
    limits. If Director cannot ingest the URL directly, retry once with a resized,
    compressed JPEG data URI that is intentionally kept small enough for the endpoint.
    """
    ingest_key = (ingest_key or "").strip()
    ingest_url = (ingest_url or DIRECTOR_INGEST_URL_DEFAULT).strip()
    image_url = (image_url or "").strip()

    if not ingest_key:
        return False, "DIRECTOR_INGEST_KEY is missing. Add it in Streamlit Secrets or API connection."
    if not image_url:
        return False, "No generated image URL is available to send."

    base_meta = {
        **(meta or {}),
        "source_app": "Seedance Studio",
        "generated_image_url": image_url,
        "director_delivery": "image_url",
    }
    base_payload = {
        "product_name": (product_name or "Untitled Product").strip(),
        "caption": (caption or "").strip(),
        "scene_prompt": (scene_prompt or "").strip(),
        "meta": base_meta,
    }

    def post_payload(payload: dict):
        return requests.post(
            ingest_url,
            headers={
                "Content-Type": "application/json",
                "x-ingest-key": ingest_key,
            },
            json=payload,
            timeout=120,
        )

    def response_error(response) -> str:
        try:
            error_payload = response.json()
            if isinstance(error_payload, dict):
                return str(
                    error_payload.get("message")
                    or error_payload.get("error")
                    or json.dumps(error_payload)
                )[:500]
            return str(error_payload)[:500]
        except Exception:
            return str(response.text or "Unknown Director ingest error")[:500]

    def success_message(response) -> str:
        try:
            response_payload = response.json()
        except Exception:
            response_payload = None
        if isinstance(response_payload, dict):
            director_id = (
                response_payload.get("id")
                or response_payload.get("item_id")
                or response_payload.get("inbox_id")
            )
            if director_id:
                return f"Sent to Director successfully. Item ID: {director_id}"
        return "Sent to Director successfully."

    try:
        # Preferred path: Director receives the temporary Grok URL and imports it
        # immediately. This avoids base64's ~33% size inflation and Vercel's body limit.
        url_payload = {**base_payload, "image_url": image_url}
        response = post_payload(url_payload)
        if response.status_code < 400:
            return True, success_message(response)

        first_error = response_error(response)

        # Authentication and route errors will not be fixed by retrying with bytes.
        if response.status_code in {401, 403, 404}:
            return False, f"Director ingest failed ({response.status_code}): {first_error}"

        # Compatibility fallback: compress to a modest JPEG and keep the encoded body
        # comfortably below common serverless request limits.
        image_bytes, _content_type = fetch_image_bytes(image_url)
        if not image_bytes:
            return False, (
                f"Director rejected the image URL ({response.status_code}: {first_error}), "
                "and the app could not download the image for a compressed retry."
            )

        compressed_bytes = image_bytes
        if PIL_AVAILABLE:
            try:
                source_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                source_image.thumbnail((1440, 2560), Image.Resampling.LANCZOS)

                # Keep raw JPEG under 2.25 MB so base64 + JSON remain well below 4.5 MB.
                target_bytes = 2_250_000
                for quality in (86, 80, 74, 68, 62, 56):
                    output = io.BytesIO()
                    source_image.save(
                        output,
                        format="JPEG",
                        quality=quality,
                        optimize=True,
                        progressive=True,
                    )
                    compressed_bytes = output.getvalue()
                    if len(compressed_bytes) <= target_bytes:
                        break
            except Exception:
                compressed_bytes = image_bytes

        if len(compressed_bytes) > 2_500_000:
            return False, (
                f"Director rejected the image URL ({response.status_code}: {first_error}). "
                "The fallback image is still too large to send safely."
            )

        import base64

        image_data_uri = "data:image/jpeg;base64," + base64.b64encode(compressed_bytes).decode("ascii")
        fallback_payload = {
            **base_payload,
            "meta": {
                **base_meta,
                "director_delivery": "compressed_base64_fallback",
                "compressed_image_bytes": len(compressed_bytes),
            },
            "image_base64": image_data_uri,
        }
        fallback_response = post_payload(fallback_payload)
        if fallback_response.status_code < 400:
            return True, success_message(fallback_response)

        return False, (
            f"Director ingest failed ({fallback_response.status_code}): "
            f"{response_error(fallback_response)}"
        )

    except requests.Timeout:
        return False, "Director ingest timed out before confirming the upload."
    except Exception as exc:
        return False, f"Director ingest failed: {exc}"




def _github_queue_headers(token: str) -> dict:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {(token or '').strip()}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "seedance-studio-sniper-inbox",
    }


def _github_contents_url(repo: str, path: str) -> str:
    safe_path = requests.utils.quote((path or "").strip("/"), safe="/")
    return f"https://api.github.com/repos/{(repo or '').strip().strip('/')}/contents/{safe_path}"


def fetch_seedance_queue_batch(
    token: str,
    repo: str,
    branch: str,
    file_path: str,
) -> tuple[dict | None, dict | None, str | None]:
    """Fetch and decode one Momentum Sniper queue JSON file from GitHub."""
    if not token or not repo or not file_path:
        return None, None, "The Seedance queue connection is incomplete."
    try:
        response = requests.get(
            _github_contents_url(repo, file_path),
            headers=_github_queue_headers(token),
            params={"ref": branch or "main"},
            timeout=60,
        )
        if response.status_code >= 400:
            return None, None, f"GitHub queue request failed ({response.status_code}): {response.text[:400]}"
        file_info = response.json()
        encoded = str(file_info.get("content") or "").replace("\n", "")
        if encoded:
            import base64
            raw = base64.b64decode(encoded).decode("utf-8")
        else:
            download_url = file_info.get("download_url")
            if not download_url:
                return None, file_info, "The queue file did not contain downloadable content."
            raw_response = requests.get(
                download_url,
                headers=_github_queue_headers(token),
                timeout=60,
            )
            raw_response.raise_for_status()
            raw = raw_response.text
        batch = json.loads(raw)
        if not isinstance(batch, dict):
            return None, file_info, "The queue file is not a valid batch object."
        batch["_queue_path"] = file_path
        batch["_queue_sha"] = file_info.get("sha")
        return batch, file_info, None
    except Exception as exc:
        return None, None, f"Could not read the Seedance queue: {exc}"


@st.cache_data(show_spinner=False, ttl=20)
def list_seedance_queue_batches(
    token: str,
    repo: str,
    branch: str,
    inbox_path: str,
) -> tuple[list[dict], str | None]:
    """List pending Momentum Sniper batches, newest first."""
    if not token or not repo:
        return [], "The Seedance queue token or repository is missing."
    try:
        response = requests.get(
            _github_contents_url(repo, inbox_path or SEEDANCE_QUEUE_PATH_DEFAULT),
            headers=_github_queue_headers(token),
            params={"ref": branch or "main"},
            timeout=60,
        )
        if response.status_code == 404:
            return [], None
        if response.status_code >= 400:
            return [], f"GitHub queue request failed ({response.status_code}): {response.text[:400]}"
        entries = response.json()
        if not isinstance(entries, list):
            return [], "The configured inbox path is not a GitHub directory."

        files = [
            entry for entry in entries
            if entry.get("type") == "file" and str(entry.get("name") or "").endswith(".json")
        ]
        # A normal batch is small. Limit the number of detail calls so an old queue
        # can never make the Streamlit page slow or exhaust the GitHub API quota.
        files = sorted(files, key=lambda item: item.get("name", ""), reverse=True)[:30]
        batches: list[dict] = []
        for entry in files:
            batch, _file_info, error = fetch_seedance_queue_batch(
                token, repo, branch, entry.get("path") or ""
            )
            if error or not batch:
                continue
            if batch.get("schema") != SEEDANCE_QUEUE_SCHEMA:
                continue
            if str(batch.get("status") or "pending").lower() == "imported":
                continue
            batches.append(batch)
        batches.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return batches, None
    except Exception as exc:
        return [], f"Could not list the Seedance queue: {exc}"


def mark_seedance_queue_batch_imported(
    token: str,
    repo: str,
    branch: str,
    batch: dict,
) -> tuple[bool, str | None]:
    """Update a queue file in place after Seedance imports it."""
    file_path = str(batch.get("_queue_path") or "").strip()
    file_sha = str(batch.get("_queue_sha") or "").strip()
    if not file_path or not file_sha:
        return False, "The queue file path or SHA is missing."

    cleaned = {
        key: value
        for key, value in batch.items()
        if not str(key).startswith("_queue_")
    }
    cleaned["status"] = "imported"
    cleaned["imported_at"] = datetime.utcnow().isoformat() + "Z"

    import base64
    payload = {
        "message": f"Mark Seedance batch {cleaned.get('batch_id', '')} imported",
        "content": base64.b64encode(
            json.dumps(cleaned, indent=2, ensure_ascii=False).encode("utf-8")
        ).decode("ascii"),
        "sha": file_sha,
        "branch": branch or "main",
    }
    try:
        response = requests.put(
            _github_contents_url(repo, file_path),
            headers={**_github_queue_headers(token), "Content-Type": "application/json"},
            json=payload,
            timeout=90,
        )
        if response.status_code >= 400:
            return False, f"Imported products, but could not archive the queue batch ({response.status_code}): {response.text[:400]}"
        list_seedance_queue_batches.clear()
        return True, None
    except Exception as exc:
        return False, f"Imported products, but could not archive the queue batch: {exc}"


def normalize_sniper_batch_products(
    batch: dict,
    progress_callback=None,
    api_key: str = "",
) -> tuple[list[dict], list[str]]:
    """Re-scrape Sniper TikTok links with Seedance's normal scrape flow.

    This intentionally ignores transferred image URLs whenever a TikTok product
    link is available. That gives imported products the same official listing
    photos and review/customer photos as products pasted directly into Step 1.
    Older queue batches remain compatible because queued images are used only as
    a fallback when TikTok cannot be scraped.
    """
    normalized: list[dict] = []
    skipped: list[str] = []
    raw_products = [
        product for product in list(batch.get("products") or [])
        if isinstance(product, dict)
    ]
    total = len(raw_products)

    for product_index, raw_product in enumerate(raw_products, start=1):
        sniper_name = str(raw_product.get("name") or "Unknown Product").strip()
        source_url = str(raw_product.get("source_url") or "").strip()

        if progress_callback:
            progress_callback(product_index, total, sniper_name)

        freshly_scraped = None
        if source_url.startswith(("http://", "https://")):
            freshly_scraped = scrape_product(source_url, api_key=api_key)

        if freshly_scraped and freshly_scraped.get("images"):
            scraped_name = str(freshly_scraped.get("name") or "").strip()
            product_name = sniper_name
            if not product_name or product_name == "Unknown Product":
                product_name = scraped_name or "Unknown Product"

            normalized.append({
                "name": product_name,
                "images": list(freshly_scraped.get("images") or []),
                "listing_images": list(
                    freshly_scraped.get("listing_images")
                    or freshly_scraped.get("images")
                    or []
                ),
                "review_images": list(freshly_scraped.get("review_images") or []),
                "source_url": source_url,
                "sniper_caption": str(raw_product.get("caption") or "").strip(),
                "sniper_scene_prompt": str(raw_product.get("scene_prompt") or "").strip(),
                "sniper_meta": dict(raw_product.get("sniper_meta") or {}),
                "sniper_batch_id": batch.get("batch_id"),
                "sniper_preset": batch.get("preset"),
                "sniper_transfer_mode": "tiktok_link_rescrape",
            })
            continue

        # Compatibility fallback for older batches if TikTok blocks or fails.
        fallback_urls: list[str] = []
        for value in (
            list(raw_product.get("images") or [])
            + list(raw_product.get("listing_images") or [])
            + list(raw_product.get("review_images") or [])
            + [raw_product.get("primary_image_url")]
        ):
            url = str(value or "").strip()
            if url.startswith(("http://", "https://")) and url not in fallback_urls:
                fallback_urls.append(url)

        if not fallback_urls:
            skipped.append(sniper_name or source_url or f"Product {product_index}")
            continue

        queued_listing = [
            str(url).strip() for url in list(raw_product.get("listing_images") or [])
            if str(url).strip() in fallback_urls
        ]
        queued_reviews = [
            str(url).strip() for url in list(raw_product.get("review_images") or [])
            if str(url).strip() in fallback_urls
        ]
        normalized.append({
            "name": sniper_name or "Unknown Product",
            "images": fallback_urls,
            "listing_images": queued_listing or fallback_urls,
            "review_images": queued_reviews,
            "source_url": source_url,
            "sniper_caption": str(raw_product.get("caption") or "").strip(),
            "sniper_scene_prompt": str(raw_product.get("scene_prompt") or "").strip(),
            "sniper_meta": dict(raw_product.get("sniper_meta") or {}),
            "sniper_batch_id": batch.get("batch_id"),
            "sniper_preset": batch.get("preset"),
            "sniper_transfer_mode": "queued_image_fallback",
        })

    return normalized, skipped


# ═══════════════════════════════════════════════════════════════════
#  AVATAR OUTFIT — two-skill workflow
#  Skill 1: avatar + outfit -> mirror-selfie try-on image
#  Skill 2: approved image -> Kling O1 mirror-selfie video
# ═══════════════════════════════════════════════════════════════════


def _uploaded_image_payload(uploaded_file) -> tuple[bytes, str, str]:
    """Return bytes, mime type, and a base64 data URI for a Streamlit upload."""
    if uploaded_file is None:
        return b"", "image/jpeg", ""
    data = uploaded_file.getvalue()
    mime = (getattr(uploaded_file, "type", None) or "image/jpeg").lower()
    if mime not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
        suffix = Path(getattr(uploaded_file, "name", "")).suffix.lower()
        mime = {
            ".png": "image/png",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }.get(suffix, "image/jpeg")
    data_uri = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    return data, mime, data_uri


AVATAR_LIBRARY_SEARCH_DIRS = [
    Path("avatar_library"),
    Path("avatars"),
    Path("/mnt/data/avatar_library"),
    Path("/mnt/data/avatars"),
]
AVATAR_LIBRARY_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _find_avatar_library_dir() -> Path | None:
    for folder in AVATAR_LIBRARY_SEARCH_DIRS:
        try:
            if folder.exists() and folder.is_dir():
                return folder
        except Exception:
            continue
    return None


def load_avatar_library() -> tuple[list[dict], str]:
    """Load saved avatars from a repo folder such as avatar_library/ or avatars/."""
    folder = _find_avatar_library_dir()
    if not folder:
        return [], ""

    manifest = None
    for name in ("manifest.json", "avatars.json"):
        path = folder / name
        if path.exists():
            try:
                manifest = json.loads(path.read_text())
            except Exception:
                manifest = None
            break

    records = []
    used = set()
    if isinstance(manifest, dict):
        manifest = manifest.get("avatars") or manifest.get("items") or manifest.get("data")
    if isinstance(manifest, list):
        for item in manifest:
            if not isinstance(item, dict):
                continue
            file_name = str(item.get("file") or item.get("filename") or item.get("path") or "").strip()
            if not file_name:
                continue
            img_path = (folder / file_name).resolve()
            if not img_path.exists() or img_path.suffix.lower() not in AVATAR_LIBRARY_EXTENSIONS:
                continue
            label = str(item.get("label") or item.get("name") or img_path.stem.replace("_", " ").replace("-", " ").title()).strip()
            avatar_id = str(item.get("id") or img_path.stem).strip() or img_path.stem
            records.append({"id": avatar_id, "label": label, "path": str(img_path), "file_name": img_path.name})
            used.add(img_path.resolve())

    for img_path in sorted(folder.iterdir()):
        if not img_path.is_file() or img_path.suffix.lower() not in AVATAR_LIBRARY_EXTENSIONS:
            continue
        if img_path.resolve() in used:
            continue
        records.append({
            "id": img_path.stem,
            "label": img_path.stem.replace("_", " ").replace("-", " ").title(),
            "path": str(img_path.resolve()),
            "file_name": img_path.name,
        })
    return records, str(folder)


def _local_image_payload(image_path: str) -> tuple[bytes, str, str]:
    """Return bytes, mime type, and a base64 data URI for a local image path."""
    try:
        data = Path(image_path).read_bytes()
    except Exception:
        return b"", "image/jpeg", ""
    suffix = Path(image_path).suffix.lower()
    mime = {
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(suffix, "image/jpeg")
    data_uri = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    return data, mime, data_uri


def _remote_image_payload(image_url: str) -> tuple[bytes, str, str]:
    """Return bytes, mime type, and a base64 data URI for a remote image URL."""
    data, mime = fetch_image_bytes(image_url)
    if not data:
        return b"", "image/jpeg", ""
    mime = (mime or "image/jpeg").split(";")[0].strip().lower() or "image/jpeg"
    data_uri = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    return data, mime, data_uri


def _prepare_image_for_avatar_analysis(
    image_bytes: bytes,
    mime_type: str,
    max_bytes: int = 3 * 1024 * 1024,
    max_edge: int = 1600,
) -> tuple[bytes, str]:
    """Resize/compress a reference image for Claude vision only.

    The original image bytes are left untouched elsewhere and are still used for
    Magnific GPT Image 2 generation. This only prevents oversized base64 images
    from exceeding the vision request limit during avatar/outfit analysis.
    """
    if not image_bytes:
        return b"", mime_type or "image/jpeg"

    # Already comfortably below the request limit; still normalize very large
    # pixel dimensions because camera photos can be unnecessarily expensive.
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img.load()
            width, height = img.size
            needs_resize = max(width, height) > max_edge
            needs_compress = len(image_bytes) > max_bytes
            if not needs_resize and not needs_compress:
                return image_bytes, mime_type or "image/jpeg"

            # Correct phone EXIF orientation when available without requiring ImageOps.
            try:
                exif = img.getexif()
                orientation = exif.get(274) if exif else None
                if orientation == 3:
                    img = img.rotate(180, expand=True)
                elif orientation == 6:
                    img = img.rotate(270, expand=True)
                elif orientation == 8:
                    img = img.rotate(90, expand=True)
            except Exception:
                pass

            if img.mode not in ("RGB", "L"):
                # Composite transparent images onto white so clothing/avatar edges
                # remain clean after JPEG compression.
                if "A" in img.getbands():
                    rgba = img.convert("RGBA")
                    bg = Image.new("RGB", rgba.size, "white")
                    bg.paste(rgba, mask=rgba.getchannel("A"))
                    img = bg
                else:
                    img = img.convert("RGB")
            elif img.mode == "L":
                img = img.convert("RGB")

            if max(img.size) > max_edge:
                scale = max_edge / float(max(img.size))
                img = img.resize(
                    (max(1, int(img.width * scale)), max(1, int(img.height * scale))),
                    Image.Resampling.LANCZOS,
                )

            # Try a few JPEG qualities. 3 MB leaves a comfortable margin below
            # the 10 MB per-image vision limit shown by the API error.
            for quality in (90, 85, 80, 75, 70, 65):
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=quality, optimize=True)
                output = buf.getvalue()
                if len(output) <= max_bytes:
                    return output, "image/jpeg"

            # Extremely detailed images: scale down once more and save compactly.
            scale = 0.75
            img = img.resize(
                (max(1, int(img.width * scale)), max(1, int(img.height * scale))),
                Image.Resampling.LANCZOS,
            )
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=65, optimize=True)
            return buf.getvalue(), "image/jpeg"
    except Exception:
        # If Pillow cannot decode it, return the original and let the API report
        # the actual format problem rather than silently dropping the image.
        return image_bytes, mime_type or "image/jpeg"


def _prepare_image_for_magnific_mcp_reference(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    max_bytes: int = 80 * 1024,
    max_edge: int = 900,
) -> tuple[bytes, str, str]:
    """Create a compact reference copy for Magnific MCP transport.

    Local images cannot be referenced by a public URL, so the MCP bridge needs a
    data URI. Sending the original multi-megabyte file inside the Claude message
    can blow past the prompt-token limit. This makes a small JPEG reference copy
    while leaving the original source file untouched.
    """
    if not image_bytes:
        return b"", "image/jpeg", ""

    if not PIL_AVAILABLE:
        # Last-resort fallback. The caller's prompt-budget guard will prevent an
        # enormous payload from being submitted if Pillow is unavailable.
        mime = mime_type or "image/jpeg"
        return image_bytes, mime, f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"

    try:
        with Image.open(io.BytesIO(image_bytes)) as source:
            source.load()
            try:
                exif = source.getexif()
                orientation = exif.get(274) if exif else None
                if orientation == 3:
                    source = source.rotate(180, expand=True)
                elif orientation == 6:
                    source = source.rotate(270, expand=True)
                elif orientation == 8:
                    source = source.rotate(90, expand=True)
            except Exception:
                pass

            if source.mode != "RGB":
                if "A" in source.getbands():
                    rgba = source.convert("RGBA")
                    bg = Image.new("RGB", rgba.size, "white")
                    bg.paste(rgba, mask=rgba.getchannel("A"))
                    source = bg
                else:
                    source = source.convert("RGB")

            if max(source.size) > max_edge:
                scale = max_edge / float(max(source.size))
                source = source.resize(
                    (max(1, int(source.width * scale)), max(1, int(source.height * scale))),
                    Image.Resampling.LANCZOS,
                )

            best = b""
            working = source
            for pass_index in range(4):
                for quality in (72, 64, 56, 48, 40, 34):
                    buf = io.BytesIO()
                    working.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
                    candidate = buf.getvalue()
                    best = candidate
                    if len(candidate) <= max_bytes:
                        uri = "data:image/jpeg;base64," + base64.b64encode(candidate).decode("ascii")
                        return candidate, "image/jpeg", uri
                # If quality alone is not enough, reduce dimensions and try again.
                working = working.resize(
                    (max(1, int(working.width * 0.82)), max(1, int(working.height * 0.82))),
                    Image.Resampling.LANCZOS,
                )

            uri = "data:image/jpeg;base64," + base64.b64encode(best).decode("ascii")
            return best, "image/jpeg", uri
    except Exception:
        mime = mime_type or "image/jpeg"
        return image_bytes, mime, f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"


def _trim_magnific_reference_payload(avatar_reference: str, outfit_references: list[str], max_data_uri_chars: int = 520_000) -> tuple[str, list[str], int]:
    """Keep MCP reference payload safely below Claude's prompt limit.

    Hosted HTTP(S) URLs are tiny and are always retained. Data-URI references are
    retained in priority order until the conservative character budget is reached.
    Returns avatar ref, kept outfit refs, and number of omitted outfit refs.
    """
    def is_data_uri(value: str) -> bool:
        return str(value or "").startswith("data:")

    avatar_reference = str(avatar_reference or "").strip()
    refs = [str(ref or "").strip() for ref in (outfit_references or []) if str(ref or "").strip()]
    used = len(avatar_reference) if is_data_uri(avatar_reference) else 0
    kept = []
    omitted = 0
    for ref in refs:
        cost = len(ref) if is_data_uri(ref) else 0
        if cost and used + cost > max_data_uri_chars:
            omitted += 1
            continue
        kept.append(ref)
        used += cost
    return avatar_reference, kept, omitted


def analyze_avatar_outfit_images(
    api_key: str,
    avatar_bytes: bytes,
    avatar_mime: str,
    outfit_images: list[dict],
) -> dict:
    """Analyze one avatar plus multiple outfit/listing/review references."""
    if not api_key:
        return {"error": "Anthropic API key is missing."}
    if not avatar_bytes or not outfit_images:
        return {"error": "Choose an avatar and at least one outfit image."}

    system = """You analyze images for an AI-avatar clothing try-on workflow.
Image 1 is always the AVATAR. Every later image is an OUTFIT REFERENCE. Outfit references may include official listing photos and customer review photos showing the same product from different angles or in real use.

For the avatar, describe ONLY visible physical appearance: build, descriptive skin tone, hair style/length/color, visible facial hair, visible face details, and clearly visible tattoos/piercings/features. Do NOT describe the avatar's current clothing. Do NOT use age words. Do NOT use race or ethnicity labels. Do not guess.

For the outfit, combine evidence from ALL outfit references. Describe ONLY the clothing/footwear product, never the people modeling it. Use repeated views to improve accuracy for garment pieces, silhouette/fit, neckline/collar, visible material look, colors, pattern/print, buttons/zippers/drawstrings/pockets, front/back/side construction, and footwear. If a customer review image conflicts with a clearer official listing image, prioritize the official listing image for product color/design while using review photos for real-world fit and details. Do NOT use brand names; describe visual design instead.

Determine whether shoes are visibly included in any selected outfit reference. If shoes are visible, describe them. If not, return clean white sneakers as the default. If only a top is visible across all selected references with no matching bottom, set bottom_fallback to black fitted jogger pants; otherwise leave bottom_fallback empty.

Return ONLY valid JSON:
{
  "avatar_description":"concise visible physical description",
  "outfit_description":"rich but concise combined outfit description from all selected references",
  "shoes_description":"visible shoes or clean white sneakers",
  "bottom_fallback":"black fitted jogger pants or empty string",
  "outfit_has_shoes":true,
  "outfit_has_bottom":true
}"""

    try:
        analysis_avatar_bytes, analysis_avatar_mime = _prepare_image_for_avatar_analysis(avatar_bytes, avatar_mime)
        content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": analysis_avatar_mime,
                    "data": base64.b64encode(analysis_avatar_bytes).decode("ascii"),
                },
            },
            {"type": "text", "text": "IMAGE 1 — AVATAR. Analyze identity/appearance only. Ignore current clothing."},
        ]

        usable_count = 0
        for index, item in enumerate(outfit_images[:10], start=2):
            raw_bytes = item.get("bytes") or b""
            raw_mime = item.get("mime") or "image/jpeg"
            if not raw_bytes:
                continue
            prepared_bytes, prepared_mime = _prepare_image_for_avatar_analysis(raw_bytes, raw_mime)
            if not prepared_bytes:
                continue
            usable_count += 1
            label = str(item.get("label") or f"Outfit reference {usable_count}")
            source_type = str(item.get("source_type") or "outfit reference")
            content.extend([
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": prepared_mime,
                        "data": base64.b64encode(prepared_bytes).decode("ascii"),
                    },
                },
                {
                    "type": "text",
                    "text": f"IMAGE {index} — OUTFIT REFERENCE ({source_type}): {label}. Analyze clothing/footwear only; ignore any person wearing it.",
                },
            ])

        if usable_count == 0:
            return {"error": "None of the selected outfit images could be loaded for analysis."}

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            system=system,
            messages=[{"role": "user", "content": content}],
        )
        text_blocks = [block.text for block in response.content if getattr(block, "type", "") == "text"]
        parsed = _extract_json_object("\n".join(text_blocks)) or {}
        if not parsed.get("avatar_description") or not parsed.get("outfit_description"):
            return {"error": "Could not extract both avatar and outfit descriptions."}
        parsed["shoes_description"] = (parsed.get("shoes_description") or "clean white sneakers").strip()
        parsed["bottom_fallback"] = (parsed.get("bottom_fallback") or "").strip()
        parsed["outfit_reference_count"] = usable_count
        return parsed
    except Exception as exc:
        return {"error": f"Avatar/outfit analysis failed: {exc}"}

def build_avatar_outfit_image_prompt(
    avatar_description: str,
    outfit_description: str,
    shoes_description: str,
    bottom_fallback: str = "",
) -> str:
    """Build the image prompt from the kling-tryon-image skill."""
    outfit_line = outfit_description.strip()
    if bottom_fallback:
        outfit_line += f" Pair the visible top with {bottom_fallback}."

    prompt = f"""Generate an image that looks like an authentic iPhone 15 Pro mirror selfie taken in a dimly lit room at night. Portrait orientation, 9:16 aspect ratio.

Use the person from the FIRST reference image as the subject. Preserve the exact same identity and visible appearance. Visible avatar reference: {avatar_description}. Do not preserve the avatar's original clothing.

Dress the subject in the outfit from the SECOND reference image. Replicate the clothing exactly: same colors, pattern, fit, silhouette, fabric look and visible construction details. Outfit: {outfit_line}

Shoes: {shoes_description}. Also add a thick gold Cuban link chain necklace, gold luxury wristwatch, and gold rings.

Scene: full-body head-to-toe mirror selfie inside a luxury modern penthouse at night. The subject stands before a full-length mirror and holds a black iPhone 16 in the right hand at face level so the phone partially covers the face. Slightly off-center natural handheld composition. Behind the subject: floor-to-ceiling glass windows, illuminated blue infinity pool, night city skyline and palm trees, minimalist lounge furniture, warm polished tile floor and warm recessed ceiling lights.

iPhone UGC realism is critical: slight low-light sensor grain/noise in shadows; faint cool phone-screen glow on fingers and near side of face; barely visible mirror smudge/fingerprint; natural pores and skin texture; slightly muted warm iPhone nighttime colors; sharpest focus on torso/outfit with softer frame edges; very subtle free-hand motion blur; mixed warm ceiling light and cool blue pool light; no HDR, studio fill, rim light or beauty lighting; natural shadows; realistic fabric texture and slight worn creases.

It must look like a real TikTok mirror selfie, not an AI render or polished fashion campaign. One person only. Full body entirely in frame. No extra people, pets or animals. No text, captions, prices, watermarks, logos added by the generator, or overlays."""
    return re.sub(r"\s+", " ", prompt).strip()


def build_avatar_outfit_kling_prompt(
    avatar_description: str,
    outfit_description: str,
    shoes_description: str,
) -> str:
    """Build a Kling O1 prompt from the kling-mirror-tryon skill and keep it under 1,900 chars."""
    avatar = re.sub(r"\s+", " ", avatar_description.strip())[:180]
    outfit = re.sub(r"\s+", " ", outfit_description.strip())[:330]
    shoes = re.sub(r"\s+", " ", shoes_description.strip())[:100] or "clean white sneakers"

    prompt = f"""9:16 vertical video, single continuous mirror-selfie shot, no cuts. {avatar} stands before a full-length mirror in a luxury penthouse at night, holding a smartphone at face level in the right hand. The phone partially covers the face the entire video. The subject wears {outfit}, {shoes}, a thick gold Cuban link chain, gold luxury watch, and gold rings. Behind the subject: floor-to-ceiling glass, illuminated blue infinity pool, city skyline, palm trees, night sky, warm recessed lighting, polished tile floor.

[00:00-00:02] Standing centered in mirror, full body head-to-toe, legs shoulder-width, upright and still. Outfit clearly displayed from front. Gentle handheld sway.

[00:02-00:04] Shift weight to one side. Free hand lightly touches the shirt or garment front. Slight quarter-turn showing the outfit at an angle. Phone stays at face level covering the face.

[00:04-00:06] Step back for a wider full-body view, shift between legs and turn to show the outfit from the side. Free arm gestures casually. Full outfit remains visible head-to-toe.

[00:06-00:08] Settle into a confident final pose at a slight angle and adjust the watch or chain. Outfit fully displayed. End cleanly.

Preserve the exact avatar identity, outfit colors/pattern/fit, shoes, penthouse environment and lighting from the approved start image. One person only. No animals. No voiceover, on-screen text, captions, subtitles, watermarks, music or sound. Photorealistic iPhone UGC realism."""
    prompt = re.sub(r"\s+", " ", prompt).strip()

    # The skill requires < 1,900 characters. Trim descriptions before touching the beat structure.
    if len(prompt) >= 1900:
        avatar = avatar[:110]
        outfit = outfit[:220]
        prompt = f"""9:16 vertical, single continuous mirror-selfie shot, no cuts. {avatar} stands before a full-length mirror in a luxury penthouse at night, holding a phone at face level so it partially covers the face throughout. Wearing {outfit}, {shoes}, thick gold Cuban link chain, gold watch, gold rings. Behind: floor-to-ceiling glass, illuminated blue infinity pool, city skyline, palm trees, warm recessed lights, polished tile.
[00:00-00:02] Full body head-to-toe, front view, upright and still, gentle handheld sway.
[00:02-00:04] Shift weight, free hand touches garment front, slight quarter-turn. Phone remains at face level.
[00:04-00:06] Step back, wider full-body view, turn to show the outfit from the side, casual free-arm gesture.
[00:06-00:08] Confident final pose at a slight angle, adjust watch or chain, clean ending.
Preserve exact identity, outfit, shoes, setting and lighting from the approved start image. One person only. No animals. No voiceover, text, captions, subtitles, watermarks, music or sound. Photorealistic iPhone UGC."""
        prompt = re.sub(r"\s+", " ", prompt).strip()
    return prompt[:1899]


AVATAR_OUTFIT_IMAGE_GENERATE_SYSTEM = """You are an image production assistant with access to Magnific tools.
Use the same Magnific MCP account already configured in the app.
1. Upload EVERY provided reference image to Magnific using creations_upload_image.
2. Reference image 1 is the avatar/identity reference. Preserve this exact person's appearance and identity.
3. Reference images 2+ are outfit/clothing references. They may include official listing photos and customer review photos of the same outfit from different views. Use ALL of them together for clothing, shoes, fit, color, material, and construction accuracy.
4. If references conflict, prioritize clear official listing photos for exact product design/color and use customer review photos as supporting evidence for real-world fit/details.
5. Generate EXACTLY ONE final mirror-selfie try-on image.
6. You MUST use model slug gpt_image_2.
7. You MUST use quality high.
8. You MUST use resolution 2k.
9. You MUST use aspect ratio 9:16.
10. Do not use GPT Image 1 or any default fallback image model.
11. Return ONLY valid JSON (no markdown): {"creation_id":"the magnific creation identifier","status":"queued","url":null,"preview_url":null,"error":null}
"""


def generate_avatar_outfit_image_magnific(
    api_key: str,
    magnific_token: str,
    avatar_reference: str,
    outfit_references: list[str],
    prompt: str,
) -> dict:
    """Use Magnific GPT Image 2 with one avatar plus multiple outfit references."""
    if not api_key:
        return {"creation_id": None, "status": "error", "error": "The Anthropic API key is missing."}
    if not magnific_token:
        return {"creation_id": None, "status": "error", "error": "The Magnific authorization token is missing."}
    outfit_references = [str(ref or "").strip() for ref in (outfit_references or []) if str(ref or "").strip()]
    if not avatar_reference or not outfit_references:
        return {"creation_id": None, "status": "error", "error": "Choose an avatar and at least one outfit reference."}

    # Keep the reference set practical for the MCP request while still supporting
    # multiple official + review views. Hosted TikTok URLs are tiny; local images
    # are compact data URIs. Apply a conservative prompt-payload budget as a final
    # guard so a large manual upload set cannot recreate the multi-million-token error.
    outfit_references = outfit_references[:10]
    avatar_reference, outfit_references, omitted_reference_count = _trim_magnific_reference_payload(
        avatar_reference, outfit_references
    )
    if not outfit_references:
        return {
            "creation_id": None,
            "status": "error",
            "error": "The selected local reference images are still too large for the MCP request. Try fewer manual images or use the TikTok-hosted product photos.",
        }
    mcp_servers = [{
        "type": "url",
        "url": MAGNIFIC_MCP_URL,
        "name": MAGNIFIC_MCP_NAME,
    }]
    if magnific_token:
        mcp_servers[0]["authorization_token"] = magnific_token

    try:
        client = anthropic.Anthropic(api_key=api_key)
        reference_lines = [f"Reference image 1 (AVATAR identity): {avatar_reference}"]
        for idx, ref in enumerate(outfit_references, start=2):
            reference_lines.append(f"Reference image {idx} (OUTFIT reference): {ref}")
        refs_text = "\n\n".join(reference_lines)
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=AVATAR_OUTFIT_IMAGE_GENERATE_SYSTEM,
            messages=[{
                "role": "user",
                "content": (
                    "Generate one Avatar Outfit mirror-selfie try-on image.\n"
                    "Required Magnific settings: model slug = gpt_image_2, quality = high, resolution = 2k, aspect ratio = 9:16.\n"
                    "Upload every reference below to Magnific. Reference 1 is the avatar. Every later reference is the same outfit/product from additional listing or customer-review views.\n\n"
                    f"{refs_text}\n\n"
                    f"Final image prompt:\n{prompt}"
                ),
            }],
            mcp_servers=mcp_servers,
            tools=[{"type": "mcp_toolset", "mcp_server_name": MAGNIFIC_MCP_NAME}],
            betas=[MCP_BETA],
        )
        result = _parse_magnific_creation_response(response)
        result["provider"] = "Magnific"
        result["image_model"] = "gpt_image_2"
        result["image_quality"] = "high"
        result["image_resolution"] = "2k"
        result["image_aspect_ratio"] = "9:16"
        result["reference_count"] = 1 + len(outfit_references)
        result["outfit_reference_count"] = len(outfit_references)
        result["omitted_reference_count"] = omitted_reference_count
        return result
    except Exception as exc:
        return {"creation_id": None, "status": "error", "error": f"Avatar Outfit image generation failed: {exc}"}


AVATAR_OUTFIT_KLING_SYSTEM = """You are a video production assistant with access to Magnific tools.
Use the same Magnific MCP account already configured in the app.
1. Upload the ONE approved Avatar Outfit mirror-selfie image with creations_upload_image.
2. Generate an image-to-video with video_generate using model slug kling_o1.
3. The uploaded approved image MUST be the source/start frame.
4. Use 9:16, 720p, approximately 8 seconds, sound off, and the provided Kling prompt.
5. Do not use the original avatar image or original outfit image in this video step.
6. Return the Magnific creation identifier.

Return ONLY valid JSON:
{"creation_id":"identifier","status":"queued","error":null}
"""


def generate_avatar_outfit_kling_magnific(
    api_key: str,
    magnific_token: str,
    approved_image_url: str,
    prompt: str,
) -> dict:
    """Animate the approved try-on image with Kling O1."""
    if not api_key:
        return {"creation_id": None, "status": "error", "error": "Anthropic API key is missing."}
    if not magnific_token:
        return {"creation_id": None, "status": "error", "error": "Magnific token is missing."}
    if not approved_image_url:
        return {"creation_id": None, "status": "error", "error": "Approve a generated try-on image first."}

    mcp_servers = [{
        "type": "url",
        "url": MAGNIFIC_MCP_URL,
        "name": MAGNIFIC_MCP_NAME,
        "authorization_token": magnific_token,
    }]
    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=AVATAR_OUTFIT_KLING_SYSTEM,
            messages=[{
                "role": "user",
                "content": (
                    f"Approved Avatar Outfit start image: {approved_image_url}\n"
                    "Generate a Kling O1 mirror-selfie try-on video at 720p, 9:16, approximately 8 seconds, sound off. "
                    "Use the approved image as the start frame.\n\n"
                    f"Kling prompt:\n{prompt}"
                ),
            }],
            mcp_servers=mcp_servers,
            tools=[{"type": "mcp_toolset", "mcp_server_name": MAGNIFIC_MCP_NAME}],
            betas=[MCP_BETA],
        )
        return _parse_magnific_creation_response(response)
    except Exception as exc:
        return {"creation_id": None, "status": "error", "error": str(exc)}


def _reset_avatar_outfit_generated_state() -> None:
    """Clear generated outputs but leave the uploaded input widgets alone."""
    for key in (
        "avatar_outfit_analysis",
        "avatar_outfit_image_result",
        "avatar_outfit_image_approved",
        "avatar_outfit_video_result",
        "avatar_outfit_input_signature",
    ):
        st.session_state.pop(key, None)


def render_avatar_outfit_flow(api_key: str, xai_api_key: str, magnific_token: str) -> None:
    """Avatar Outfit: saved avatar + multi-photo TikTok outfit/review references."""
    st.markdown("## 🪞 Avatar Outfit")
    st.caption(
        "Choose a saved avatar, then paste a TikTok Shop clothing link or upload outfit photos. You can select multiple official listing photos and customer review photos before generating the try-on."
    )
    st.info(
        "Selected outfit photos are analyzed together and sent to Magnific GPT Image 2 as supporting references. The Avatar Outfit video remains a clean, silent Kling O1 mirror try-on with no hook text, captions, voiceover, music, or soundtrack."
    )
    st.caption(
        "Large avatar/outfit files are optimized automatically. Claude analysis gets a resized copy, and local images get a separate compact reference copy for the Magnific MCP request so base64 data cannot overflow the prompt limit."
    )

    avatar_records, avatar_library_dir = load_avatar_library()
    outfit_mode = st.radio(
        "Outfit source",
        ["TikTok Shop link", "Upload images manually"],
        horizontal=True,
        key="avatar_outfit_source_mode",
    )

    input_col_1, input_col_2 = st.columns(2, gap="large")
    with input_col_1:
        st.markdown("### 1. Choose avatar")
        if avatar_records:
            avatar_options = {f"{item['label']} ({item['file_name']})": item for item in avatar_records}
            selected_avatar_label = st.selectbox(
                "Saved avatars",
                options=list(avatar_options.keys()),
                key="avatar_outfit_avatar_library_select",
                help="Loaded from avatar_library/ or avatars/ in the repo.",
            )
            selected_avatar = avatar_options[selected_avatar_label]
            st.image(selected_avatar["path"], caption=f"Selected avatar — {selected_avatar['label']}", use_container_width=True)
            avatar_bytes, avatar_mime, avatar_data_uri = _local_image_payload(selected_avatar["path"])
            _avatar_mcp_bytes, _avatar_mcp_mime, avatar_reference = _prepare_image_for_magnific_mcp_reference(avatar_bytes, avatar_mime)
            st.caption(f"Library folder: {avatar_library_dir}")
            avatar_source_label = selected_avatar["label"]
        else:
            st.warning("No saved avatars were found. Add images to `avatar_library/` or `avatars/` in the repo, or use the fallback uploader below.")
            avatar_file = st.file_uploader(
                "Fallback avatar image",
                type=["jpg", "jpeg", "png", "webp"],
                key="avatar_outfit_avatar_upload_fallback",
            )
            if avatar_file is not None:
                st.image(avatar_file, caption="Avatar reference — identity / appearance", use_container_width=True)
            avatar_bytes, avatar_mime, avatar_data_uri = _uploaded_image_payload(avatar_file)
            _avatar_mcp_bytes, _avatar_mcp_mime, avatar_reference = _prepare_image_for_magnific_mcp_reference(avatar_bytes, avatar_mime)
            avatar_source_label = getattr(avatar_file, "name", "Uploaded avatar") if avatar_file else ""

    outfit_analysis_images = []
    outfit_magnific_references = []
    outfit_name_prefill = ""

    with input_col_2:
        st.markdown("### 2. Choose outfit references")
        if outfit_mode == "TikTok Shop link":
            outfit_link = st.text_input(
                "TikTok Shop clothing link",
                key="avatar_outfit_tiktok_link",
                placeholder="https://www.tiktok.com/view/product/...",
                help="Scrape official product photos and customer review photos, then select multiple references below.",
            ).strip()
            if st.button(
                "🔎 Scrape outfit product",
                key="avatar_outfit_scrape_link_btn",
                use_container_width=True,
                disabled=not bool(outfit_link),
            ):
                with st.spinner("Scraping listing and customer review photos..."):
                    scraped = scrape_product(outfit_link, api_key=api_key)
                if not scraped:
                    st.error("Could not scrape that TikTok Shop outfit link.")
                else:
                    st.session_state["avatar_outfit_scraped_product"] = scraped
                    st.session_state["avatar_outfit_scraped_source_url"] = outfit_link
                    st.rerun()

            scraped = st.session_state.get("avatar_outfit_scraped_product") or {}
            scraped_source = st.session_state.get("avatar_outfit_scraped_source_url", "")
            if outfit_link and scraped and scraped_source and scraped_source != outfit_link:
                scraped = {}

            if scraped:
                outfit_name_prefill = scraped.get("name") or ""
                st.success(f"Scraped product: {scraped.get('name', 'Unknown Product')}")
                if scraped.get("name_source"):
                    st.caption(f"Name source: {scraped.get('name_source')}")
                product_name_manual = st.text_input(
                    "Outfit product name",
                    value=scraped.get("name") or "",
                    key="avatar_outfit_scraped_name_edit",
                ).strip()
                if product_name_manual:
                    outfit_name_prefill = product_name_manual

                listing_images = list(scraped.get("listing_images") or [])
                review_images = list(scraped.get("review_images") or [])
                product_key = re.sub(r"[^a-zA-Z0-9]+", "_", str(scraped.get("product_id") or hashlib.sha1((outfit_link or 'outfit').encode()).hexdigest()[:10]))

                st.markdown("**Select multiple outfit references**")
                st.caption("Choose up to 10 total. Listing photos are best for exact color/design; review photos help with real-world fit and alternate angles.")
                listing_tab, review_tab = st.tabs([
                    f"Product photos ({len(listing_images)})",
                    f"Customer reviews ({len(review_images)})",
                ])

                selected_items = []
                with listing_tab:
                    if listing_images:
                        cols = st.columns(3)
                        for idx, image_url in enumerate(listing_images[:18]):
                            with cols[idx % 3]:
                                st.image(image_url, use_container_width=True)
                                checked = st.checkbox(
                                    f"Use product photo {idx + 1}",
                                    value=(idx == 0),
                                    key=f"ao_listing_{product_key}_{idx}",
                                )
                                if checked:
                                    selected_items.append({
                                        "url": image_url,
                                        "label": f"Product photo {idx + 1}",
                                        "source_type": "official listing photo",
                                    })
                    else:
                        st.caption("No official listing photos were found.")

                with review_tab:
                    if review_images:
                        cols = st.columns(3)
                        for idx, image_url in enumerate(review_images[:24]):
                            with cols[idx % 3]:
                                st.image(image_url, use_container_width=True)
                                checked = st.checkbox(
                                    f"Use review photo {idx + 1}",
                                    value=False,
                                    key=f"ao_review_{product_key}_{idx}",
                                )
                                if checked:
                                    selected_items.append({
                                        "url": image_url,
                                        "label": f"Customer review photo {idx + 1}",
                                        "source_type": "customer review photo",
                                    })
                    else:
                        st.caption("No customer review photos were found for this product.")

                if len(selected_items) > 10:
                    st.warning(f"You selected {len(selected_items)} images. The first 10 selected references will be used.")
                    selected_items = selected_items[:10]

                if selected_items:
                    st.success(f"{len(selected_items)} outfit reference image{'s' if len(selected_items) != 1 else ''} selected")
                    preview_cols = st.columns(min(4, len(selected_items)))
                    for idx, item in enumerate(selected_items):
                        with preview_cols[idx % len(preview_cols)]:
                            st.image(item["url"], caption=item["label"], use_container_width=True)
                    for item in selected_items:
                        raw_bytes, raw_mime, _data_uri = _remote_image_payload(item["url"])
                        if raw_bytes:
                            outfit_analysis_images.append({
                                "bytes": raw_bytes,
                                "mime": raw_mime,
                                "label": item["label"],
                                "source_type": item["source_type"],
                            })
                            # Use the hosted TikTok CDN URL for Magnific; this keeps the MCP request much smaller than embedding base64.
                            outfit_magnific_references.append(item["url"])
                else:
                    st.warning("Select at least one product or customer-review photo.")
            else:
                st.caption("Paste a clothing product link and scrape it to choose images.")
        else:
            manual_name = st.text_input(
                "Outfit name (optional)",
                key="avatar_outfit_manual_name",
                placeholder="Blue hoodie and black joggers",
            ).strip()
            if manual_name:
                outfit_name_prefill = manual_name
            outfit_files = st.file_uploader(
                "Outfit images",
                type=["jpg", "jpeg", "png", "webp"],
                accept_multiple_files=True,
                key="avatar_outfit_outfit_upload_multi",
                help="Upload multiple listing, flat-lay, modeled, detail, or customer-review images of the same outfit.",
            )
            if outfit_files:
                if len(outfit_files) > 10:
                    st.warning(f"You uploaded {len(outfit_files)} images. The first 10 will be used.")
                outfit_files = outfit_files[:10]
                cols = st.columns(min(4, len(outfit_files)))
                for idx, outfit_file in enumerate(outfit_files):
                    with cols[idx % len(cols)]:
                        st.image(outfit_file, caption=outfit_file.name, use_container_width=True)
                    raw_bytes, raw_mime, raw_uri = _uploaded_image_payload(outfit_file)
                    if raw_bytes:
                        outfit_analysis_images.append({
                            "bytes": raw_bytes,
                            "mime": raw_mime,
                            "label": outfit_file.name,
                            "source_type": "uploaded outfit reference",
                        })
                        _mcp_bytes, _mcp_mime, compact_mcp_uri = _prepare_image_for_magnific_mcp_reference(raw_bytes, raw_mime)
                        if compact_mcp_uri:
                            outfit_magnific_references.append(compact_mcp_uri)
                st.success(f"{len(outfit_analysis_images)} outfit reference image{'s' if len(outfit_analysis_images) != 1 else ''} selected")

    # Track the exact avatar + selected outfit set so changing references clears stale generations.
    if avatar_bytes and outfit_analysis_images:
        signature_hasher = hashlib.sha1()
        signature_hasher.update(avatar_bytes)
        signature_hasher.update(b"|AVATAR_OUTFIT_MULTI|")
        for item in outfit_analysis_images:
            signature_hasher.update(item.get("bytes") or b"")
        signature_hasher.update((outfit_name_prefill or "").encode("utf-8", "ignore"))
        input_signature = signature_hasher.hexdigest()
        previous_signature = st.session_state.get("avatar_outfit_input_signature")
        if previous_signature and previous_signature != input_signature:
            for key in (
                "avatar_outfit_analysis",
                "avatar_outfit_image_result",
                "avatar_outfit_image_approved",
                "avatar_outfit_video_result",
            ):
                st.session_state.pop(key, None)
        st.session_state["avatar_outfit_input_signature"] = input_signature

    analyze_disabled = not (avatar_bytes and outfit_analysis_images and api_key)
    if st.button(
        "🔎 Step 1 — Analyze Avatar + Selected Outfit Photos",
        type="primary",
        use_container_width=True,
        key="avatar_outfit_analyze_btn",
        disabled=analyze_disabled,
    ):
        with st.spinner(f"Analyzing the avatar plus {len(outfit_analysis_images)} selected outfit reference(s)..."):
            analysis = analyze_avatar_outfit_images(
                api_key=api_key,
                avatar_bytes=avatar_bytes,
                avatar_mime=avatar_mime,
                outfit_images=outfit_analysis_images,
            )
        if analysis.get("error"):
            st.error(analysis["error"])
        else:
            if outfit_name_prefill:
                analysis["product_name"] = outfit_name_prefill[:100]
            if avatar_source_label:
                analysis["avatar_label"] = avatar_source_label
            # Save current references so reruns after analysis/approval still know exactly what to send to Magnific.
            st.session_state["avatar_outfit_analysis"] = analysis
            st.session_state["avatar_outfit_magnific_references"] = list(outfit_magnific_references)
            st.session_state["avatar_outfit_avatar_reference"] = avatar_reference
            st.session_state.pop("avatar_outfit_image_result", None)
            st.session_state.pop("avatar_outfit_image_approved", None)
            st.session_state.pop("avatar_outfit_video_result", None)
            st.rerun()

    if not api_key:
        st.warning("Connect the Anthropic API key above to analyze the avatar and outfit references.")
    if not magnific_token:
        st.warning("Connect Magnific above to generate the Avatar Outfit try-on image and run the Kling O1 video step.")

    analysis = st.session_state.get("avatar_outfit_analysis") or {}
    if not analysis:
        st.caption("Tip: select several angles or detail shots when the clothing has important front/back details, matching pieces, or shoes.")
        return

    saved_outfit_refs = st.session_state.get("avatar_outfit_magnific_references") or outfit_magnific_references
    saved_avatar_ref = st.session_state.get("avatar_outfit_avatar_reference") or avatar_reference

    st.markdown("### Reference analysis")
    if analysis.get("product_name"):
        st.caption(f"Outfit product: **{analysis.get('product_name')}**")
    if analysis.get("avatar_label"):
        st.caption(f"Avatar: **{analysis.get('avatar_label')}**")
    if analysis.get("outfit_reference_count"):
        st.caption(f"Outfit references analyzed: **{analysis.get('outfit_reference_count')}**")
    avatar_desc = st.text_area(
        "Avatar description",
        value=analysis.get("avatar_description", ""),
        height=90,
        key="avatar_outfit_avatar_description",
    ).strip()
    outfit_desc = st.text_area(
        "Combined outfit description",
        value=analysis.get("outfit_description", ""),
        height=130,
        key="avatar_outfit_outfit_description",
        help="This description combines all selected listing and customer-review images.",
    ).strip()
    shoes_desc = st.text_input(
        "Shoes",
        value=analysis.get("shoes_description") or "clean white sneakers",
        key="avatar_outfit_shoes_description",
    ).strip() or "clean white sneakers"
    bottom_fallback = analysis.get("bottom_fallback", "")
    if bottom_fallback:
        st.caption(f"Only a top was detected, so the image skill will pair it with: **{bottom_fallback}**")

    image_prompt = build_avatar_outfit_image_prompt(
        avatar_description=avatar_desc,
        outfit_description=outfit_desc,
        shoes_description=shoes_desc,
        bottom_fallback=bottom_fallback,
    )
    kling_prompt = build_avatar_outfit_kling_prompt(
        avatar_description=avatar_desc,
        outfit_description=outfit_desc,
        shoes_description=shoes_desc,
    )

    with st.expander("📋 Skill prompts", expanded=False):
        st.markdown("**Try-on image prompt**")
        st.code(image_prompt, language=None)
        st.caption(f"Image model: {AVATAR_OUTFIT_IMAGE_MODEL_LABEL} · Outfit refs: {len(saved_outfit_refs)}")
        st.markdown("**Kling O1 mirror prompt**")
        st.code(kling_prompt, language=None)
        st.caption(f"Kling prompt characters: {len(kling_prompt)}/1900 · {AVATAR_OUTFIT_VIDEO_MODEL_LABEL}")

    image_result = st.session_state.get("avatar_outfit_image_result") or {}
    generated_image_url = image_result.get("url") or image_result.get("preview_url")

    if not generated_image_url:
        status = (image_result.get("status") or "").lower().strip()
        creation_id = image_result.get("creation_id")
        if creation_id and status in {"queued", "processing", "running", "unknown"}:
            st.info(f"Avatar Outfit image status: **{status or 'processing'}**")
            if st.button(
                "🔄 Check image status",
                use_container_width=True,
                key="avatar_outfit_check_image_status",
                disabled=not bool(api_key and magnific_token and creation_id),
            ):
                with st.spinner("Checking Magnific image status..."):
                    refreshed = check_creation_status(api_key=api_key, magnific_token=magnific_token, creation_id=creation_id)
                merged = {**image_result, **{k: v for k, v in refreshed.items() if v is not None}}
                st.session_state["avatar_outfit_image_result"] = merged
                if merged.get("status") == "error" and merged.get("error"):
                    st.error(merged["error"])
                st.rerun()
        if st.button(
            "🖼️ Step 2 — Generate Avatar Outfit Image",
            type="primary",
            use_container_width=True,
            key="avatar_outfit_generate_image",
            disabled=not bool(api_key and magnific_token and saved_avatar_ref and saved_outfit_refs),
        ):
            with st.spinner(f"Generating with Magnific GPT Image 2 using {len(saved_outfit_refs)} outfit reference(s)..."):
                result = generate_avatar_outfit_image_magnific(
                    api_key=api_key,
                    magnific_token=magnific_token,
                    avatar_reference=saved_avatar_ref,
                    outfit_references=saved_outfit_refs,
                    prompt=image_prompt,
                )
            if result.get("error"):
                st.error(result["error"])
            else:
                st.session_state["avatar_outfit_image_result"] = result
                if result.get("omitted_reference_count"):
                    st.warning(f"{result.get('omitted_reference_count')} oversized local outfit reference(s) were skipped to keep the MCP request within its prompt limit. All hosted TikTok references were retained.")
                st.session_state["avatar_outfit_image_approved"] = False
                st.session_state.pop("avatar_outfit_video_result", None)
                st.rerun()
        return

    st.markdown("### Generated try-on image")
    image_col, action_col = st.columns([1.15, 1], gap="large")
    with image_col:
        st.image(generated_image_url, use_container_width=True)
        image_bytes, image_content_type = fetch_image_bytes(generated_image_url)
        if image_bytes:
            st.download_button(
                "⬇️ Download try-on image",
                data=image_bytes,
                file_name=f"avatar_outfit_{image_result.get('creation_id', 'image')}.jpg",
                mime=image_content_type or "image/jpeg",
                key="avatar_outfit_download_image",
                use_container_width=True,
            )
    with action_col:
        st.success("Review identity, outfit accuracy, shoes, full-body framing, and mirror realism before approving.")
        st.caption(f"Magnific used {image_result.get('outfit_reference_count', len(saved_outfit_refs))} outfit reference(s).")
        regen_col, approve_col = st.columns(2)
        if regen_col.button(
            "🔁 Regenerate image",
            use_container_width=True,
            key="avatar_outfit_regen_image",
            disabled=not bool(api_key and magnific_token and saved_avatar_ref and saved_outfit_refs),
        ):
            with st.spinner("Generating another GPT Image 2 try-on with the same selected references..."):
                result = generate_avatar_outfit_image_magnific(
                    api_key=api_key,
                    magnific_token=magnific_token,
                    avatar_reference=saved_avatar_ref,
                    outfit_references=saved_outfit_refs,
                    prompt=image_prompt,
                )
            if result.get("error"):
                st.error(result["error"])
            else:
                st.session_state["avatar_outfit_image_result"] = result
                if result.get("omitted_reference_count"):
                    st.warning(f"{result.get('omitted_reference_count')} oversized local outfit reference(s) were skipped to keep the MCP request within its prompt limit. All hosted TikTok references were retained.")
                st.session_state["avatar_outfit_image_approved"] = False
                st.session_state.pop("avatar_outfit_video_result", None)
                st.rerun()
        if approve_col.button(
            "✅ Approve image",
            type="primary",
            use_container_width=True,
            key="avatar_outfit_approve_image",
        ):
            st.session_state["avatar_outfit_image_approved"] = True
            st.rerun()

    if not st.session_state.get("avatar_outfit_image_approved"):
        st.info("Approve the generated image before sending it to Kling O1.")
        return

    st.success("Image approved. This exact image will be used as the Kling O1 start frame.")
    video_result = st.session_state.get("avatar_outfit_video_result") or {}
    creation_id = video_result.get("creation_id")
    video_status = video_result.get("status", "")

    if not creation_id:
        if st.button(
            "🎬 Step 3 — Generate Kling O1 Mirror Video",
            type="primary",
            use_container_width=True,
            key="avatar_outfit_generate_video",
            disabled=not bool(api_key and magnific_token and generated_image_url),
        ):
            with st.spinner("Sending the approved mirror image to Kling O1 as the start frame..."):
                result = generate_avatar_outfit_kling_video(
                    api_key=api_key,
                    magnific_token=magnific_token,
                    approved_image_url=generated_image_url,
                    prompt=kling_prompt,
                )
            if result.get("error"):
                st.error(result["error"])
            else:
                result["avatar_label"] = analysis.get("avatar_label")
                result["product_name"] = analysis.get("product_name")
                st.session_state["avatar_outfit_video_result"] = result
                st.rerun()
        return

    st.markdown("### Kling O1 mirror video")
    if video_status in {"queued", "processing", "running", "unknown"}:
        st.info(f"Current video status: **{video_status or 'processing'}**")
        if st.button(
            "🔄 Check video status",
            key="avatar_outfit_check_video_status",
            use_container_width=True,
            disabled=not bool(api_key and magnific_token and creation_id),
        ):
            with st.spinner("Checking Kling O1 video status..."):
                refreshed = check_creation_status(api_key=api_key, magnific_token=magnific_token, creation_id=creation_id)
            merged = {**video_result, **{k: v for k, v in refreshed.items() if v is not None}}
            st.session_state["avatar_outfit_video_result"] = merged
            st.rerun()
        return

    video_url = video_result.get("url") or video_result.get("preview_url")
    if video_status == "completed" and video_url:
        refreshed_key = f"{creation_id}_{hashlib.sha1(video_url.encode('utf-8')).hexdigest()[:12]}"
        st.video(video_url)
        video_bytes = fetch_video_bytes(f"{video_url}#avatar_outfit={refreshed_key}")
        if video_bytes:
            st.download_button(
                "⬇️ Download Avatar Outfit video",
                data=video_bytes,
                file_name=f"avatar_outfit_{creation_id}.mp4",
                mime="video/mp4",
                key="avatar_outfit_download_video",
                use_container_width=True,
            )
        regen_cols = st.columns(2)
        if regen_cols[0].button(
            "🎬 Regenerate Kling O1 video",
            key="avatar_outfit_regen_video",
            use_container_width=True,
            disabled=not bool(api_key and magnific_token and generated_image_url),
        ):
            with st.spinner("Generating a fresh Kling O1 mirror video from the approved image..."):
                result = generate_avatar_outfit_kling_video(
                    api_key=api_key,
                    magnific_token=magnific_token,
                    approved_image_url=generated_image_url,
                    prompt=kling_prompt,
                )
            if result.get("error"):
                st.error(result["error"])
            else:
                result["avatar_label"] = analysis.get("avatar_label")
                result["product_name"] = analysis.get("product_name")
                st.session_state["avatar_outfit_video_result"] = result
                st.rerun()
        if regen_cols[1].button(
            "🧹 Start over",
            key="avatar_outfit_start_over",
            use_container_width=True,
        ):
            _reset_avatar_outfit_generated_state()
            for key in (
                "avatar_outfit_scraped_product",
                "avatar_outfit_scraped_source_url",
                "avatar_outfit_magnific_references",
                "avatar_outfit_avatar_reference",
            ):
                st.session_state.pop(key, None)
            st.rerun()
        return

    if video_status == "error":
        st.error(video_result.get("error") or "Kling O1 failed.")
    else:
        st.warning("No finished video URL is available yet.")


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
            <p>Turn TikTok Shop products into multiple video formats, or create Avatar Outfit mirror try-ons from an avatar + clothing reference using Magnific GPT Image 2 + Kling O1, then refine supported workflows with the existing editor.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    # ── Always-visible video setup ──
    api_key_from_secrets = get_secret("ANTHROPIC_API_KEY")
    token_from_secrets = get_secret("MAGNIFIC_AUTH_TOKEN")
    xai_key_from_secrets = get_secret("XAI_API_KEY")
    director_key_from_secrets = get_secret("DIRECTOR_INGEST_KEY")
    director_url_from_secrets = get_secret("DIRECTOR_INGEST_URL") or DIRECTOR_INGEST_URL_DEFAULT
    queue_token_from_secrets = get_secret("SEEDANCE_QUEUE_GITHUB_TOKEN")
    queue_repo_from_secrets = get_secret("SEEDANCE_QUEUE_REPO")
    queue_branch_from_secrets = get_secret("SEEDANCE_QUEUE_BRANCH") or "main"
    queue_path_from_secrets = get_secret("SEEDANCE_QUEUE_PATH") or SEEDANCE_QUEUE_PATH_DEFAULT

    if "runtime_anthropic_api_key" not in st.session_state:
        st.session_state["runtime_anthropic_api_key"] = api_key_from_secrets
    if "runtime_magnific_token" not in st.session_state:
        st.session_state["runtime_magnific_token"] = token_from_secrets
    if "runtime_xai_api_key" not in st.session_state:
        st.session_state["runtime_xai_api_key"] = xai_key_from_secrets
    if "runtime_director_ingest_key" not in st.session_state:
        st.session_state["runtime_director_ingest_key"] = director_key_from_secrets
    if "runtime_director_ingest_url" not in st.session_state:
        st.session_state["runtime_director_ingest_url"] = director_url_from_secrets
    if "runtime_seedance_queue_token" not in st.session_state:
        st.session_state["runtime_seedance_queue_token"] = queue_token_from_secrets
    if "runtime_seedance_queue_repo" not in st.session_state:
        st.session_state["runtime_seedance_queue_repo"] = queue_repo_from_secrets
    if "runtime_seedance_queue_branch" not in st.session_state:
        st.session_state["runtime_seedance_queue_branch"] = queue_branch_from_secrets
    if "runtime_seedance_queue_path" not in st.session_state:
        st.session_state["runtime_seedance_queue_path"] = queue_path_from_secrets

    with st.container(border=True):
        st.markdown("### Video setup")
        st.caption("Choose the format first. API controls stay below in the same dark workspace—no hidden sidebar or white popover.")

        style = st.radio(
            "Video style",
            options=["shoe_video", "texthook_broll", "warehouse", "pool", "lifestyle_animation", "avatar_outfit"],
            format_func=lambda value: STYLE_LABELS[value],
            key="main_video_style",
            horizontal=True,
            label_visibility="collapsed",
        )

        if style == "shoe_video":
            duration_col, voice_col = st.columns([1, 3], vertical_alignment="top")
            with duration_col:
                duration = st.select_slider(
                    "Duration",
                    options=[5, 10, 15],
                    value=15,
                    key="main_video_duration",
                )
            with voice_col:
                voice_script = st.text_area(
                    "Voiceover (optional)",
                    placeholder="Leave empty for a silent video",
                    height=82,
                    key="main_voice_script",
                )
        elif style == "warehouse":
            duration = 5
            voice_script = None
            st.info(
                "Warehouse is fixed at 5 seconds and silent: one continuous first-person move beside a bulk pallet display. "
                "No people, hands, cuts, or rendered text."
            )
        elif style == "pool":
            duration = 8
            voice_script = None
            st.info(
                "Pool is fixed at 8 seconds and silent: handheld poolside product close-up → patio table beauty shot → poolside close-up. "
                "The chosen hook is added afterward with FFmpeg."
            )
        elif style == "lifestyle_animation":
            duration_col, info_col = st.columns([1, 3], vertical_alignment="top")
            with duration_col:
                duration = st.select_slider(
                    "Kling duration (fixed)",
                    options=[5],
                    value=5,
                    key="main_lifestyle_duration",
                )
            with info_col:
                st.info(
                    "Lifestyle Animation generates the approval image with the xAI Grok Imagine API in 2k at 9:16, then sends the approved image to Magnific for a 5-second Kling O1 animation at 720p using it as the start frame. "
                    "Choose a product size/type so the scene works for anything from supplements to vacuums, couches, appliances, electronics, fitness gear, and outdoor items. The selected deal/FOMO hook is added afterward with FFmpeg."
                )
                st.caption(f"Image model: {LIFESTYLE_IMAGE_MODEL_LABEL}  |  Video model: {LIFESTYLE_VIDEO_MODEL_LABEL}")
            voice_script = None
        elif style == "avatar_outfit":
            duration = 8
            voice_script = None
            st.info(
                "Avatar Outfit uses the two uploaded try-on skills as one workflow: upload the avatar and outfit separately, analyze both, generate a 9:16 iPhone-style penthouse mirror selfie with Magnific GPT Image 2, approve it, then use that exact image as the Kling O1 start frame for the silent mirror try-on video."
            )
            st.caption(f"Image model: {AVATAR_OUTFIT_IMAGE_MODEL_LABEL}  |  Video model: {AVATAR_OUTFIT_VIDEO_MODEL_LABEL}")
        else:
            duration = 8
            voice_script = None
            st.info("Text-Hook B-Roll is fixed at 8 seconds and silent. Python selects a concrete unrelated opening scene for every generation, and regeneration avoids the previous scene. B-Roll now uses the same deal/FOMO hook library as Warehouse and Pool.")

        api_key = st.session_state.get("runtime_anthropic_api_key", "")
        magnific_token = st.session_state.get("runtime_magnific_token", "")
        xai_api_key = st.session_state.get("runtime_xai_api_key", "")
        director_ingest_key = st.session_state.get("runtime_director_ingest_key", "")
        director_ingest_url = st.session_state.get("runtime_director_ingest_url", DIRECTOR_INGEST_URL_DEFAULT)
        queue_token = st.session_state.get("runtime_seedance_queue_token", "")
        queue_repo = st.session_state.get("runtime_seedance_queue_repo", "")
        queue_branch = st.session_state.get("runtime_seedance_queue_branch", "main") or "main"
        queue_path = st.session_state.get("runtime_seedance_queue_path", SEEDANCE_QUEUE_PATH_DEFAULT) or SEEDANCE_QUEUE_PATH_DEFAULT
        status_col_1, status_col_2, status_col_3, status_col_4, status_col_5, status_col_6 = st.columns(6)
        if api_key:
            status_col_1.success("Anthropic connected")
        else:
            status_col_1.warning("Anthropic key needed")
        if magnific_token:
            status_col_2.success("Magnific connected")
        else:
            status_col_2.info("Magnific needed for video")
        if xai_api_key:
            status_col_3.success("Grok images connected")
        else:
            status_col_3.info("Grok key needed for image workflows")
        if director_ingest_key:
            status_col_4.success("Director connected")
        else:
            status_col_4.info("Director key optional")
        if queue_token and queue_repo:
            status_col_5.success("Sniper inbox connected")
        else:
            status_col_5.info("Sniper inbox optional")
        status_col_6.info(f"{STYLE_LABELS[style]} · {resolved_style_duration(style, duration)}s")

        required_connections_ready = bool(api_key and magnific_token and (xai_api_key if style in ("lifestyle_animation", "avatar_outfit") else True))
        with st.expander("API connection", expanded=not required_connections_ready):
            if api_key_from_secrets:
                st.success("Anthropic API key loaded from Streamlit secrets.")
            else:
                st.session_state["runtime_anthropic_api_key"] = st.text_input(
                    "Anthropic API Key",
                    type="password",
                    value=st.session_state.get("runtime_anthropic_api_key", ""),
                    key="runtime_anthropic_api_key_input",
                )

            if xai_key_from_secrets:
                st.success("xAI API key loaded from Streamlit secrets.")
            else:
                st.session_state["runtime_xai_api_key"] = st.text_input(
                    "xAI API Key",
                    type="password",
                    value=st.session_state.get("runtime_xai_api_key", ""),
                    key="runtime_xai_api_key_input",
                    help="Used to generate Lifestyle approval images with Grok Imagine.",
                )

            st.session_state["runtime_magnific_token"] = st.text_input(
                "Magnific token",
                type="password",
                value=st.session_state.get("runtime_magnific_token", ""),
                key="runtime_magnific_token_input",
                help="Paste a refreshed token here whenever Magnific authentication expires.",
            )

            if director_key_from_secrets:
                st.success("Momentum Director ingest key loaded from Streamlit secrets.")
            else:
                st.session_state["runtime_director_ingest_key"] = st.text_input(
                    "Momentum Director ingest key",
                    type="password",
                    value=st.session_state.get("runtime_director_ingest_key", ""),
                    key="runtime_director_ingest_key_input",
                    help="Used by the Send to Director button for generated Lifestyle images.",
                )
            st.session_state["runtime_director_ingest_url"] = st.text_input(
                "Momentum Director ingest URL",
                value=st.session_state.get("runtime_director_ingest_url", DIRECTOR_INGEST_URL_DEFAULT),
                key="runtime_director_ingest_url_input",
                help="Leave this at the default unless the Momentum Academy Director endpoint changes.",
            ).strip() or DIRECTOR_INGEST_URL_DEFAULT

            st.markdown("**Momentum Sniper inbox connection**")
            if queue_token_from_secrets and queue_repo_from_secrets:
                st.success("Seedance queue repository loaded from Streamlit secrets.")
            else:
                queue_connection_col_1, queue_connection_col_2 = st.columns(2)
                with queue_connection_col_1:
                    st.session_state["runtime_seedance_queue_token"] = st.text_input(
                        "Seedance queue GitHub token",
                        type="password",
                        value=st.session_state.get("runtime_seedance_queue_token", ""),
                        key="runtime_seedance_queue_token_input",
                        help="A fine-grained GitHub token with Contents read/write access to the dedicated queue repository.",
                    )
                with queue_connection_col_2:
                    st.session_state["runtime_seedance_queue_repo"] = st.text_input(
                        "Seedance queue repository",
                        value=st.session_state.get("runtime_seedance_queue_repo", ""),
                        key="runtime_seedance_queue_repo_input",
                        placeholder="owner/seedance-queue",
                    )
            queue_settings_col_1, queue_settings_col_2 = st.columns(2)
            with queue_settings_col_1:
                st.session_state["runtime_seedance_queue_branch"] = st.text_input(
                    "Queue branch",
                    value=st.session_state.get("runtime_seedance_queue_branch", "main"),
                    key="runtime_seedance_queue_branch_input",
                ).strip() or "main"
            with queue_settings_col_2:
                st.session_state["runtime_seedance_queue_path"] = st.text_input(
                    "Queue inbox folder",
                    value=st.session_state.get("runtime_seedance_queue_path", SEEDANCE_QUEUE_PATH_DEFAULT),
                    key="runtime_seedance_queue_path_input",
                ).strip().strip("/") or SEEDANCE_QUEUE_PATH_DEFAULT

            magnific_token = st.session_state.get("runtime_magnific_token", "")
            api_key = st.session_state.get("runtime_anthropic_api_key", "")
            xai_api_key = st.session_state.get("runtime_xai_api_key", "")
            director_ingest_key = st.session_state.get("runtime_director_ingest_key", "")
            director_ingest_url = st.session_state.get("runtime_director_ingest_url", DIRECTOR_INGEST_URL_DEFAULT)
            queue_token = st.session_state.get("runtime_seedance_queue_token", "")
            queue_repo = st.session_state.get("runtime_seedance_queue_repo", "")
            queue_branch = st.session_state.get("runtime_seedance_queue_branch", "main") or "main"
            queue_path = st.session_state.get("runtime_seedance_queue_path", SEEDANCE_QUEUE_PATH_DEFAULT) or SEEDANCE_QUEUE_PATH_DEFAULT

            st.markdown("**Momentum Director connection**")
            st.markdown(
                'Add `DIRECTOR_INGEST_KEY = "your-key"` to Streamlit secrets. '
                '`DIRECTOR_INGEST_URL` is optional and defaults to the existing Momentum Academy Director ingest endpoint.'
            )

            st.markdown("**Momentum Sniper queue secrets**")
            st.markdown(
                'Add `SEEDANCE_QUEUE_GITHUB_TOKEN` and `SEEDANCE_QUEUE_REPO = "owner/seedance-queue"` to both apps. '
                '`SEEDANCE_QUEUE_BRANCH` and `SEEDANCE_QUEUE_PATH` are optional.'
            )

            st.markdown("**xAI key for image workflows**")
            st.markdown('Add `XAI_API_KEY = "your-key"` to Streamlit secrets, or paste the key in the field above. Grok is used for Lifestyle approval images.')

            st.markdown("**How to refresh the Magnific token**")
            st.markdown("""
1. Run `npx @modelcontextprotocol/inspector` on a computer with Node.js.
2. Set **Transport Type** to `Streamable HTTP`.
3. Set the URL to `https://mcp.magnific.com`.
4. Connect, open Auth Settings, and complete the Quick OAuth Flow.
5. Copy the `access_token` and paste it above.
            """)


    if style == "avatar_outfit":
        render_avatar_outfit_flow(
            api_key=st.session_state.get("runtime_anthropic_api_key", ""),
            xai_api_key=st.session_state.get("runtime_xai_api_key", ""),
            magnific_token=st.session_state.get("runtime_magnific_token", ""),
        )
        return

    # ════════════════════════════════════════════════════════════════
    #  MOMENTUM SNIPER INBOX
    # ════════════════════════════════════════════════════════════════
    imported_message = st.session_state.pop("sniper_import_message", None)
    if imported_message:
        st.success(imported_message)

    with st.container(border=True):
        inbox_header_col, inbox_refresh_col = st.columns([4, 1], vertical_alignment="center")
        with inbox_header_col:
            st.markdown("### 📥 Momentum Sniper Inbox")
            st.caption(
                "Momentum Sniper sends the TikTok links and research data. When you import a batch, "
                "Seedance re-scrapes every TikTok page using the same flow as pasted links so you get "
                "official listing photos and customer review photos."
            )
        with inbox_refresh_col:
            if st.button(
                "🔄 Refresh inbox",
                key="refresh_sniper_inbox",
                use_container_width=True,
                disabled=not bool(queue_token and queue_repo),
            ):
                list_seedance_queue_batches.clear()
                st.rerun()

        if not (queue_token and queue_repo):
            st.info(
                "Connect the shared GitHub queue in **API connection** to receive Momentum Sniper batches."
            )
        else:
            pending_batches, queue_error = list_seedance_queue_batches(
                queue_token,
                queue_repo,
                queue_branch,
                queue_path,
            )
            if queue_error:
                st.error(queue_error)

            try:
                requested_batch_path = st.query_params.get("sniper_batch", "")
                if isinstance(requested_batch_path, list):
                    requested_batch_path = requested_batch_path[0] if requested_batch_path else ""
                requested_batch_path = str(requested_batch_path or "").strip()
            except Exception:
                requested_batch_path = ""

            if requested_batch_path and not any(
                batch.get("_queue_path") == requested_batch_path for batch in pending_batches
            ):
                requested_batch, _file_info, requested_error = fetch_seedance_queue_batch(
                    queue_token,
                    queue_repo,
                    queue_branch,
                    requested_batch_path,
                )
                if requested_batch and str(requested_batch.get("status") or "pending").lower() != "imported":
                    pending_batches.insert(0, requested_batch)
                elif requested_error:
                    st.warning(f"The linked Momentum Sniper batch could not be opened: {requested_error}")

            if not pending_batches:
                st.info("No pending Momentum Sniper batches are waiting.")
            else:
                batch_paths = [str(batch.get("_queue_path") or "") for batch in pending_batches]
                default_batch_index = 0
                if requested_batch_path in batch_paths:
                    default_batch_index = batch_paths.index(requested_batch_path)

                batch_by_path = {
                    str(batch.get("_queue_path") or ""): batch
                    for batch in pending_batches
                }

                def sniper_batch_label(file_path: str) -> str:
                    batch = batch_by_path[file_path]
                    preset_label = str(batch.get("preset") or "Custom")
                    product_count = int(batch.get("product_count") or len(batch.get("products") or []))
                    created_at = str(batch.get("created_at") or "")
                    created_label = created_at.replace("T", " ")[:16] if created_at else ""
                    return f"{preset_label} · {product_count} products" + (f" · {created_label}" if created_label else "")

                selected_batch_path = st.selectbox(
                    "Pending batch",
                    options=batch_paths,
                    index=default_batch_index,
                    format_func=sniper_batch_label,
                    key="selected_sniper_batch_path",
                )
                selected_batch = batch_by_path[selected_batch_path]
                preview_rows = []
                for product in list(selected_batch.get("products") or []):
                    if not isinstance(product, dict):
                        continue
                    meta = dict(product.get("sniper_meta") or {})
                    preview_rows.append({
                        "Product": product.get("name", "Unknown Product"),
                        "Price": meta.get("avg_price"),
                        "Revenue 7d": meta.get("revenue_7d"),
                        "Ads": meta.get("ads_top10"),
                        "Photos": "Scrape on import",
                        "TikTok link": product.get("source_url", ""),
                    })
                if preview_rows:
                    st.dataframe(preview_rows, use_container_width=True, hide_index=True)

                import_batch_clicked = st.button(
                    f"🔍 Scrape TikTok links & import {len(preview_rows)} product(s)",
                    type="primary",
                    use_container_width=True,
                    key="import_selected_sniper_batch",
                    help=(
                        "Runs every TikTok link through Seedance's normal scraper to collect "
                        "official listing photos and customer review photos before importing."
                    ),
                )
                if import_batch_clicked:
                    scrape_progress = st.progress(0, text="Preparing TikTok photo scrape…")

                    def update_sniper_scrape_progress(current, total, product_name):
                        denominator = max(total, 1)
                        scrape_progress.progress(
                            max(0.0, min(0.95, (current - 1) / denominator)),
                            text=f"Scraping TikTok {current}/{total}: {product_name[:55]}…",
                        )

                    with st.spinner("Scraping TikTok listing and review photos…"):
                        imported_products, skipped_products = normalize_sniper_batch_products(
                            selected_batch,
                            progress_callback=update_sniper_scrape_progress,
                            api_key=api_key,
                        )
                    scrape_progress.progress(1.0, text="TikTok photo scrape complete.")

                    if not imported_products:
                        st.error(
                            "Seedance could not collect usable photos from any TikTok link in this batch."
                        )
                    else:
                        st.session_state["scraped"] = imported_products
                        st.session_state["product_hooks"] = {}
                        st.session_state.pop("product_hooks_style", None)
                        archived, archive_warning = mark_seedance_queue_batch_imported(
                            queue_token,
                            queue_repo,
                            queue_branch,
                            selected_batch,
                        )
                        listing_count = sum(
                            len(product.get("listing_images") or [])
                            for product in imported_products
                        )
                        review_count = sum(
                            len(product.get("review_images") or [])
                            for product in imported_products
                        )
                        message = (
                            f"Scraped and imported {len(imported_products)} Momentum Sniper product(s) "
                            f"with {listing_count} listing photo(s) and {review_count} review photo(s)."
                        )
                        if skipped_products:
                            message += f" Skipped {len(skipped_products)} link(s) with no usable photos."
                        if archive_warning:
                            st.session_state["sniper_import_archive_warning"] = archive_warning
                        st.session_state["sniper_import_message"] = message
                        try:
                            if "sniper_batch" in st.query_params:
                                del st.query_params["sniper_batch"]
                        except Exception:
                            pass
                        st.rerun()

        archive_warning = st.session_state.pop("sniper_import_archive_warning", None)
        if archive_warning:
            st.warning(archive_warning)

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

    scrape_btn = st.button("🔍 Scrape Product & Review Photos", use_container_width=True)

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
        st.subheader("② Select Product References")
        st.caption("Choose official listing photos, customer review photos, or both. Multiple references improve product accuracy.")

        scraped_products = []
        progress = st.progress(0, text="Scraping...")

        for i, url in enumerate(links):
            progress.progress(i / len(links), text=f"Scraping {i+1}/{len(links)}...")
            scraped = scrape_product(url, api_key=api_key)

            if scraped and scraped["images"]:
                scraped_products.append(scraped)
            else:
                st.error(f"❌ Couldn't scrape: {url[:70]}...")

        progress.progress(1.0, text=f"Found {len(scraped_products)} product(s)")

        if scraped_products:
            # Store in session state so selections persist. A fresh scrape starts a
            # fresh hook batch so old index-based hook choices cannot attach to new products.
            st.session_state["scraped"] = scraped_products
            st.session_state["product_hooks"] = {}
        else:
            st.error("No products could be scraped. Check your links.")

    # ── Show image selection if we have scraped data (doesn't block the rest of the page) ──
    if "scraped" in st.session_state:
        scraped_products = st.session_state["scraped"]
        selections = {}  # product_index → selected image URL list
        edited_names = {}
        lifestyle_settings = {}

        st.caption("Remove any product you do not want before generating hooks. Removed products are excluded from every later step.")

        for idx, product in enumerate(scraped_products):
            st.markdown("---")

            detected_name = product.get("name") or "Unknown Product"
            product_fingerprint = hashlib.sha1(
                product.get("source_url", str(idx)).encode("utf-8")
            ).hexdigest()[:10]
            product_name_key = f"product_name_{product_fingerprint}"
            if product_name_key not in st.session_state:
                st.session_state[product_name_key] = "" if detected_name == "Unknown Product" else detected_name

            product_name_col, remove_product_col = st.columns([5, 1], vertical_alignment="bottom")
            with product_name_col:
                edited_name = st.text_input(
                    "Product name",
                    placeholder="Type the product name if TikTok did not provide it",
                    key=product_name_key,
                    help="The app fills this automatically when TikTok exposes a title. You can still correct it here.",
                ).strip()
            with remove_product_col:
                if st.button(
                    "🗑️ Remove",
                    key=f"remove_product_{product_fingerprint}",
                    use_container_width=True,
                    help="Remove this product from the current batch.",
                ):
                    remaining_products = [
                        saved_product
                        for saved_index, saved_product in enumerate(st.session_state.get("scraped", []))
                        if saved_index != idx
                    ]
                    if remaining_products:
                        st.session_state["scraped"] = remaining_products
                    else:
                        st.session_state.pop("scraped", None)

                    # Hooks are indexed by the active product order, so reset them after removal.
                    # Product widgets use stable URL fingerprints, so the remaining products keep
                    # their names, selected references, and Lifestyle settings after the rerun.
                    st.session_state["product_hooks"] = {}
                    st.rerun()
            if not edited_name:
                edited_name = detected_name
            edited_names[idx] = edited_name
            product["name"] = edited_name

            if edited_name == "Unknown Product":
                st.warning("TikTok did not expose a product title. Enter the product name above before generating hooks.")
            elif product.get("name_source") == "image_fallback":
                st.caption("Product name recovered from the listing image because this TikTok ID-only link did not expose a readable title.")

            st.caption(f"Source: {product['source_url'][:100]}...")
            if product.get("sniper_caption"):
                st.caption(f"Momentum Sniper hook: {product['sniper_caption']}")
            if product.get("sniper_preset"):
                st.caption(f"Imported from Momentum Sniper preset: {product['sniper_preset']}")

            listing_images = product.get("listing_images") or product.get("images", [])
            review_images = product.get("review_images") or []

            listing_tab, review_tab = st.tabs([
                f"Listing photos ({len(listing_images)})",
                f"Review/customer photos ({len(review_images)})",
            ])

            listing_state_key = f"listing_refs_{product_fingerprint}"
            review_state_key = f"review_refs_{product_fingerprint}"
            primary_state_key = f"primary_reference_url_{product_fingerprint}"

            if listing_state_key not in st.session_state:
                st.session_state[listing_state_key] = [0] if listing_images else []
            if review_state_key not in st.session_state:
                st.session_state[review_state_key] = []

            st.caption("Click **Select** on any images you want to use. Click **Make primary** on the main image you want Seedance to follow most closely.")

            with listing_tab:
                if listing_images:
                    listing_cols = st.columns(4)
                    for image_index, image_url in enumerate(listing_images):
                        with listing_cols[image_index % 4]:
                            try:
                                st.image(image_url, use_container_width=True, caption=f"Listing {image_index + 1}")
                            except Exception:
                                st.caption(f"Listing {image_index + 1}: {image_url[:45]}...")

                            is_selected = image_index in st.session_state.get(listing_state_key, [])
                            is_primary = st.session_state.get(primary_state_key) == image_url
                            if is_primary:
                                st.success("Primary reference")
                            elif is_selected:
                                st.info("Selected")
                            else:
                                st.caption("Not selected")

                            select_col, primary_col = st.columns(2)
                            with select_col:
                                if st.button(
                                    "Deselect" if is_selected else "Select",
                                    key=f"listing_toggle_{product_fingerprint}_{image_index}",
                                    use_container_width=True,
                                ):
                                    selected_items = list(st.session_state.get(listing_state_key, []))
                                    if image_index in selected_items:
                                        selected_items.remove(image_index)
                                        if st.session_state.get(primary_state_key) == image_url:
                                            st.session_state[primary_state_key] = None
                                    else:
                                        selected_items.append(image_index)
                                        if not st.session_state.get(primary_state_key):
                                            st.session_state[primary_state_key] = image_url
                                    st.session_state[listing_state_key] = selected_items
                                    st.rerun()
                            with primary_col:
                                if st.button(
                                    "Make primary",
                                    key=f"listing_primary_{product_fingerprint}_{image_index}",
                                    disabled=not is_selected or is_primary,
                                    use_container_width=True,
                                ):
                                    st.session_state[primary_state_key] = image_url
                                    st.rerun()
                else:
                    st.info("No official listing photos were exposed by this page.")

            with review_tab:
                if review_images:
                    review_cols = st.columns(4)
                    for image_index, image_url in enumerate(review_images):
                        with review_cols[image_index % 4]:
                            try:
                                st.image(image_url, use_container_width=True, caption=f"Review {image_index + 1}")
                            except Exception:
                                st.caption(f"Review {image_index + 1}: {image_url[:45]}...")

                            is_selected = image_index in st.session_state.get(review_state_key, [])
                            is_primary = st.session_state.get(primary_state_key) == image_url
                            if is_primary:
                                st.success("Primary reference")
                            elif is_selected:
                                st.info("Selected")
                            else:
                                st.caption("Not selected")

                            select_col, primary_col = st.columns(2)
                            with select_col:
                                if st.button(
                                    "Deselect" if is_selected else "Select",
                                    key=f"review_toggle_{product_fingerprint}_{image_index}",
                                    use_container_width=True,
                                ):
                                    selected_items = list(st.session_state.get(review_state_key, []))
                                    if image_index in selected_items:
                                        selected_items.remove(image_index)
                                        if st.session_state.get(primary_state_key) == image_url:
                                            st.session_state[primary_state_key] = None
                                    else:
                                        selected_items.append(image_index)
                                        if not st.session_state.get(primary_state_key):
                                            st.session_state[primary_state_key] = image_url
                                    st.session_state[review_state_key] = selected_items
                                    st.rerun()
                            with primary_col:
                                if st.button(
                                    "Make primary",
                                    key=f"review_primary_{product_fingerprint}_{image_index}",
                                    disabled=not is_selected or is_primary,
                                    use_container_width=True,
                                ):
                                    st.session_state[primary_state_key] = image_url
                                    st.rerun()
                else:
                    st.info("TikTok did not expose review photos in the public page data. You can paste direct review-photo URLs below.")

                manual_review_urls_text = st.text_area(
                    "Add review-photo URLs manually (optional)",
                    placeholder="Paste one direct image URL per line",
                    height=90,
                    key=f"manual_review_urls_{product_fingerprint}",
                )

            selected_listing_indices = [
                image_index for image_index in st.session_state.get(listing_state_key, [])
                if 0 <= image_index < len(listing_images)
            ]
            selected_review_indices = [
                image_index for image_index in st.session_state.get(review_state_key, [])
                if 0 <= image_index < len(review_images)
            ]

            selected_candidates = []
            for image_index in selected_listing_indices:
                selected_candidates.append((f"Listing {image_index + 1}", listing_images[image_index]))
            for image_index in selected_review_indices:
                selected_candidates.append((f"Review {image_index + 1}", review_images[image_index]))

            manual_review_urls = _dedupe_image_urls([
                line.strip()
                for line in manual_review_urls_text.splitlines()
                if line.strip()
            ])
            for manual_index, image_url in enumerate(manual_review_urls, start=1):
                selected_candidates.append((f"Manual review {manual_index}", image_url))

            if not selected_candidates:
                fallback_images = listing_images or review_images or product.get("images", [])
                if fallback_images:
                    selected_candidates = [("Automatic fallback", fallback_images[0])]
                    st.session_state[primary_state_key] = fallback_images[0]
                    st.info("No references were selected, so the first available image will be used.")

            if selected_candidates:
                primary_reference_url = st.session_state.get(primary_state_key)
                if not any(url == primary_reference_url for _label, url in selected_candidates):
                    primary_reference_url = selected_candidates[0][1]
                    st.session_state[primary_state_key] = primary_reference_url

                ordered_candidates = [
                    candidate for candidate in selected_candidates
                    if candidate[1] == primary_reference_url
                ] + [
                    candidate for candidate in selected_candidates
                    if candidate[1] != primary_reference_url
                ]
                selections[idx] = [url for _label, url in ordered_candidates]
                st.caption(f"Using {len(selections[idx])} reference image(s). Primary: {ordered_candidates[0][0]}")
            else:
                selections[idx] = []


            if style == "lifestyle_animation":
                st.markdown("##### Lifestyle image setup")
                inferred_product_type = infer_lifestyle_product_type(edited_name)
                type_widget_key = f"lifestyle_product_type_{product_fingerprint}"
                if type_widget_key not in st.session_state:
                    st.session_state[type_widget_key] = "auto"

                product_type_choice = st.selectbox(
                    "Product size / type",
                    options=LIFESTYLE_PRODUCT_TYPE_OPTIONS,
                    format_func=lambda value: LIFESTYLE_PRODUCT_TYPE_LABELS[value],
                    key=type_widget_key,
                    help="Auto-detect works from the product name, but you can override it for couches, vacuums, appliances, electronics, fitness gear, outdoor items, and other products.",
                )
                resolved_product_type = (
                    inferred_product_type if product_type_choice == "auto" else product_type_choice
                )
                st.caption(
                    f"Using profile: {LIFESTYLE_PRODUCT_TYPES[resolved_product_type]['label']}"
                    + (" · detected automatically" if product_type_choice == "auto" else " · manual override")
                )

                scene_options = lifestyle_scene_options(resolved_product_type)
                preferred_scene = infer_lifestyle_default_scene(edited_name, resolved_product_type)
                if preferred_scene in scene_options:
                    scene_options.remove(preferred_scene)
                    scene_options.insert(0, preferred_scene)
                scene_widget_key = f"lifestyle_scene_{product_fingerprint}"
                if st.session_state.get(scene_widget_key) not in scene_options:
                    st.session_state[scene_widget_key] = scene_options[0]
                scene_key = st.selectbox(
                    "Lifestyle scene",
                    options=scene_options,
                    format_func=lambda value: LIFESTYLE_SCENES[value]["label"],
                    key=scene_widget_key,
                    help="The scene list changes to match the selected product size/type.",
                )

                custom_scene = ""
                if scene_key == "custom":
                    custom_scene = st.text_area(
                        "Custom lifestyle scene",
                        placeholder="Example: a cream sectional couch in a small lived-in apartment living room beside a rug and floor lamp",
                        height=90,
                        key=f"lifestyle_custom_scene_{product_fingerprint}",
                        help="Describe where the product should realistically be placed. Include the room or outdoor setting and useful scale references.",
                    ).strip()
                    if not custom_scene:
                        st.info("Describe the custom scene before generating so Grok knows the correct environment and scale.")

                appearance_details = st.text_area(
                    "Product appearance and scale details",
                    placeholder=LIFESTYLE_PRODUCT_TYPES[resolved_product_type]["appearance_help"],
                    height=92,
                    key=f"lifestyle_appearance_{product_fingerprint}",
                    help="Kling uses this after image approval. Include every feature that must stay unchanged, especially overall size, materials, controls, accessories, and proportions.",
                ).strip()
                default_appearance = (
                    "the exact real-world size, silhouette, construction, colors, materials, controls, accessories, branding, "
                    "and proportions shown in the approved image"
                )
                lifestyle_settings[idx] = {
                    "product_type_choice": product_type_choice,
                    "product_type": resolved_product_type,
                    "scene_key": scene_key,
                    "custom_scene": custom_scene,
                    "appearance_details": appearance_details or default_appearance,
                }


        # ════════════════════════════════════════════════════════════════
        #  STEP 3 — GENERATE OR GET PROMPTS
        # ════════════════════════════════════════════════════════════════
        st.divider()
        st.subheader("③ Generate")

        has_token = bool(xai_api_key) if style == "lifestyle_animation" else bool(magnific_token)

        # ── Build final product list with selected images ──
        final_products = []
        for idx, product in enumerate(scraped_products):
            selected_refs = selections.get(idx) or [product["images"][0]]
            product_entry = {
                "name": product["name"],
                "image_url": selected_refs[0],
                "image_urls": selected_refs,
                "source_url": product["source_url"],
                "sniper_caption": product.get("sniper_caption", ""),
                "sniper_scene_prompt": product.get("sniper_scene_prompt", ""),
                "sniper_meta": product.get("sniper_meta", {}),
                "sniper_batch_id": product.get("sniper_batch_id"),
                "sniper_preset": product.get("sniper_preset"),
            }
            if style == "lifestyle_animation":
                lifestyle_config = lifestyle_settings.get(idx, {})
                product_type = lifestyle_config.get(
                    "product_type",
                    infer_lifestyle_product_type(product["name"]),
                )
                scene_key = lifestyle_config.get(
                    "scene_key",
                    infer_lifestyle_default_scene(product["name"], product_type),
                )
                custom_scene = lifestyle_config.get("custom_scene", "")
                appearance_details = lifestyle_config.get(
                    "appearance_details",
                    "the exact real-world size, silhouette, construction, colors, materials, controls, accessories, branding, and proportions shown in the approved image",
                )
                product_entry.update({
                    "product_type_choice": lifestyle_config.get("product_type_choice", "auto"),
                    "product_type": product_type,
                    "scene_key": scene_key,
                    "custom_scene": custom_scene,
                    "appearance_details": appearance_details,
                    "lifestyle_prompt": build_lifestyle_image_prompt(
                        product["name"], scene_key, product_type, custom_scene
                    ),
                    "kling_prompt": build_lifestyle_kling_prompt(
                        product["name"], appearance_details, scene_key, product_type, custom_scene
                    ),
                })
            final_products.append(product_entry)

        # ── Pick hooks FIRST, then generate ──
        hooks_ready = False

        # Hook voice changes by style. Clear old options when the selected style changes
        # so Warehouse hooks can never be mixed with B-roll/Shoe hooks.
        if st.session_state.get("product_hooks_style") != style:
            st.session_state["product_hooks"] = {}
            st.session_state["product_hooks_style"] = style

        # All three styles use generated on-screen text hooks.
        # The selected hook is stored now and burned onto the finished video later with FFmpeg.
        if style in ("texthook_broll", "shoe_video", "warehouse", "pool", "lifestyle_animation"):
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
                        hook_result = write_hooks(api_key, product["name"], style=style)
                    generated_hook_options = list(hook_result.get("hook_options", []) or [])
                    sniper_hook = str(product.get("sniper_caption") or "").strip()
                    if sniper_hook:
                        generated_hook_options = [sniper_hook] + [
                            hook for hook in generated_hook_options if hook.strip() != sniper_hook
                        ]
                        generated_hook_options = generated_hook_options[:5]
                    st.session_state["product_hooks"][i] = {
                        "product_name": product["name"],
                        "hook_options": generated_hook_options,
                        "caption": hook_result.get("caption", ""),
                        "hashtags": hook_result.get("hashtags", ""),
                        "sound_tip": hook_result.get("sound_tip", ""),
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
                    if hook_data.get("sound_tip"):
                        st.caption(f"Sound tip: {hook_data['sound_tip']}")

                st.markdown("---")
                bulk_hook_col, bulk_hook_note_col = st.columns([1.35, 2.65], vertical_alignment="center")
                with bulk_hook_col:
                    keep_all_hooks = st.button(
                        "✅ Keep All Selected Hooks",
                        key="keep_all_selected_hooks",
                        type="primary",
                        use_container_width=True,
                        help="Accept the currently selected hook for every product in this batch.",
                    )
                with bulk_hook_note_col:
                    st.caption(
                        "Choose an option for each product, then click once here. "
                        "Any product you did not change will keep its first hook option."
                    )

                if keep_all_hooks:
                    accepted_count = 0
                    for hook_index, _product in enumerate(final_products):
                        hook_entry = st.session_state["product_hooks"].get(hook_index)
                        hook_options = list((hook_entry or {}).get("hook_options") or [])
                        if not hook_entry or not hook_options:
                            continue
                        selected_option_index = int(st.session_state.get(f"hookpick_{hook_index}", 0) or 0)
                        selected_option_index = max(0, min(selected_option_index, len(hook_options) - 1))
                        hook_entry["accepted_hook"] = hook_options[selected_option_index]
                        accepted_count += 1
                    if accepted_count:
                        st.session_state["bulk_hooks_saved_message"] = f"Kept {accepted_count} selected hook(s)."
                        st.rerun()

                if st.session_state.pop("bulk_hooks_saved_message", None):
                    st.success("✅ All selected hooks were saved for this batch.")

                hooks_ready = all(
                    bool((st.session_state["product_hooks"].get(hook_index) or {}).get("accepted_hook"))
                    for hook_index in range(len(final_products))
                )
                if not hooks_ready:
                    st.info("Choose the hooks you want, then click **Keep All Selected Hooks** once.")
                else:
                    st.success("✅ All hooks accepted! Ready to generate.")

        # ── Step 3c: Generate buttons (only appear when hooks are ready) ──
        auto_btn = False
        prompt_btn = False
        if hooks_ready:
            st.markdown("---")
            if has_token:
                col1, col2 = st.columns(2)
                auto_label = "🖼️ Step 2 — Generate Lifestyle Image" if style == "lifestyle_animation" else "🎬 Step 2 — Auto-Generate Videos"
                prompt_label = "📝 Get Grok + Kling Prompts" if style == "lifestyle_animation" else "📝 Just Get Prompts"
                auto_btn = col1.button(auto_label, type="primary", use_container_width=True)
                prompt_btn = col2.button(prompt_label, use_container_width=True)
            else:
                prompt_label = "📝 Get Grok + Kling Prompts" if style == "lifestyle_animation" else "📝 Get Prompts + Images (generate manually in Magnific)"
                prompt_btn = st.button(prompt_label, type="primary", use_container_width=True)

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
            if style in ("texthook_broll", "shoe_video", "warehouse", "pool", "lifestyle_animation"):
                hook_data_for_product = st.session_state.get("product_hooks", {}).get(i)
                if hook_data_for_product:
                    selected_hook = hook_data_for_product.get("accepted_hook")

            with st.spinner(f"Writing prompt for {product['name'][:30]}..."):
                if style == "lifestyle_animation":
                    result = {
                        "prompt": product["lifestyle_prompt"],
                        "lifestyle_prompt": product["lifestyle_prompt"],
                        "kling_prompt": product["kling_prompt"],
                        "char_count": len(product["lifestyle_prompt"]),
                    }
                else:
                    selected_broll_scene = choose_broll_scene() if style == "texthook_broll" else None
                    result = write_prompt(
                        api_key=api_key,
                        product_name=product["name"],
                        style=style,
                        duration=duration,
                        voice_script=voice_script if voice_script else None,
                        selected_hook=selected_hook,
                        broll_scene=selected_broll_scene,
                    )

            # Carry over hook data into result for persistence
            if hook_data_for_product:
                result["accepted_hook"] = selected_hook
                result["hook_options"] = hook_data_for_product.get("hook_options", [])
                result["caption"] = hook_data_for_product.get("caption")
                result["hashtags"] = hook_data_for_product.get("hashtags")
                result["sound_tip"] = hook_data_for_product.get("sound_tip")

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
                if style == "lifestyle_animation":
                    st.text_area(
                        "Grok lifestyle image prompt",
                        value=result["lifestyle_prompt"],
                        height=210,
                        key=f"lifestyle_prompt_{i}",
                    )
                    st.text_area(
                        "Kling O1 animation prompt",
                        value=result["kling_prompt"],
                        height=240,
                        key=f"kling_prompt_{i}",
                    )
                    st.caption(f"Scene: {LIFESTYLE_SCENES[product['scene_key']]['label']} · Kling duration: 5s · Resolution: 720p · Start frame")
                    st.caption(f"Product profile: {LIFESTYLE_PRODUCT_TYPES[product.get('product_type', 'other')]['label']}")
                    if product.get("custom_scene"):
                        st.caption(f"Custom scene: {product['custom_scene']}")
                    st.caption(f"Image model: {LIFESTYLE_IMAGE_MODEL_LABEL}  |  Video model: {LIFESTYLE_VIDEO_MODEL_LABEL}")
                elif result.get("prompt"):
                    st.text_area(
                        "Seedance Prompt (copy this):",
                        value=result["prompt"],
                        height=250,
                        key=f"prompt_{i}",
                    )
                    char_count = result.get("char_count", len(result["prompt"]))
                    st.caption(f"Characters: {char_count}")
                    if style == "texthook_broll" and result.get("broll_scene"):
                        st.info(f"Random opening scene: {result['broll_scene']}")
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
            entry["image_urls"] = fp.get("image_urls", [fp["image_url"]])
            entry["source_url"] = fp["source_url"]
            entry["sniper_caption"] = fp.get("sniper_caption", "")
            entry["sniper_scene_prompt"] = fp.get("sniper_scene_prompt", "")
            entry["sniper_meta"] = fp.get("sniper_meta", {})
            entry["sniper_batch_id"] = fp.get("sniper_batch_id")
            entry["sniper_preset"] = fp.get("sniper_preset")
            entry["style"] = style
            entry["duration"] = resolved_style_duration(style, duration)
            entry["voice_script"] = voice_script or ""
            entry["status"] = "prompt_only"
            entry["generated_at"] = datetime.now().isoformat()
            if style == "lifestyle_animation":
                entry["product_type_choice"] = fp.get("product_type_choice", "auto")
                entry["product_type"] = fp.get("product_type", "other")
                entry["scene_key"] = fp.get("scene_key")
                entry["custom_scene"] = fp.get("custom_scene", "")
                entry["appearance_details"] = fp.get("appearance_details")
                entry["lifestyle_prompt"] = fp.get("lifestyle_prompt")
                entry["kling_prompt"] = fp.get("kling_prompt")
                entry["pipeline_stage"] = "prompt"
            add_generation(entry)

        # Manual generation instructions
        st.divider()
        if style == "lifestyle_animation":
            st.info("""
**Manual Lifestyle workflow:**
1. Generate the approval image with xAI Grok Imagine using **grok-imagine-image-quality**.
2. Use up to three selected product references, the Grok lifestyle prompt, **9:16**, and **2k**.
3. Approve and download the resulting image.
4. Upload that approved image to Magnific as the **start frame** for **Kling O1**.
5. Set Kling to **720p**, **5 seconds**, **9:16**, and sound off.
            """)
        else:
            st.info("""
**How to generate manually in Magnific:**
1. Open the Magnific video generator.
2. Select model **Seedance 2.0 Fast**.
3. Upload the product image.
4. Paste the prompt.
5. Set aspect ratio to **9:16** and resolution to **720p**.
6. Click **Generate**.
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
                        "image_urls": fp.get("image_urls", [fp["image_url"]]),
                        "source_url": fp["source_url"],
                        "prompt": r.get("prompt", ""),
                        "accepted_hook": r.get("accepted_hook"),
                        "hook_options": r.get("hook_options"),
                        "caption": r.get("caption"),
                        "hashtags": r.get("hashtags"),
                        "sound_tip": r.get("sound_tip"),
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

            progress.progress(
                i / len(final_products),
                text=f"Processing {i+1}/{len(final_products)}: {product['name'][:30]}...",
            )

            selected_hook = None
            hook_data_for_product = st.session_state.get("product_hooks", {}).get(i)
            if hook_data_for_product:
                selected_hook = hook_data_for_product.get("accepted_hook")

            if style == "lifestyle_animation":
                prompt_text = product["lifestyle_prompt"]
                with st.spinner(f"Generating lifestyle image for {product['name'][:30]} with Grok Imagine..."):
                    gen_result = generate_lifestyle_image_grok(
                        xai_api_key=xai_api_key,
                        product_name=product["name"],
                        reference_urls=product.get("image_urls", [product["image_url"]]),
                        prompt=prompt_text,
                    )

                gen_result["product_name"] = product["name"]
                gen_result["prompt"] = prompt_text
                gen_result["prompt_used"] = prompt_text
                gen_result["lifestyle_prompt"] = prompt_text
                gen_result["kling_prompt"] = product["kling_prompt"]
                gen_result["product_type_choice"] = product.get("product_type_choice", "auto")
                gen_result["product_type"] = product.get("product_type", "other")
                gen_result["scene_key"] = product["scene_key"]
                gen_result["custom_scene"] = product.get("custom_scene", "")
                gen_result["appearance_details"] = product["appearance_details"]
                gen_result["pipeline_stage"] = "image"
                gen_result["lifestyle_creation_id"] = gen_result.get("creation_id")
                if gen_result.get("status") == "completed":
                    gen_result["status"] = "image_completed"
                    gen_result["lifestyle_image_url"] = gen_result.get("url") or gen_result.get("preview_url")
                    st.success(f"✅ **{product['name']}** — Grok lifestyle image is ready for approval")
                elif gen_result.get("status") == "error":
                    error_msg = gen_result.get("error", "")
                    st.error(f"❌ **{product['name']}** — {error_msg}")
                    if any(keyword in error_msg.lower() for keyword in ['401', 'unauthorized', 'auth', 'api key', 'forbidden', '403']):
                        st.warning("🔄 xAI authentication failed. Add or refresh the XAI_API_KEY in the API connection section.")
                        token_expired = True
                else:
                    st.warning(f"⚠️ **{product['name']}** — Status: {gen_result.get('status')}")
            else:
                selected_broll_scene = choose_broll_scene() if style == "texthook_broll" else None
                with st.spinner(f"Writing prompt for {product['name'][:30]}..."):
                    prompt_result = write_prompt(
                        api_key=api_key,
                        product_name=product["name"],
                        style=style,
                        duration=duration,
                        voice_script=voice_script if voice_script else None,
                        selected_hook=selected_hook,
                        broll_scene=selected_broll_scene,
                    )

                if prompt_result.get("error") or not prompt_result.get("prompt"):
                    st.error(f"❌ **{product['name']}** — Prompt error: {prompt_result.get('error', 'No prompt')}")
                    results.append({
                        "product_name": product["name"],
                        "status": "error",
                        "error": prompt_result.get("error"),
                        "creation_id": None,
                    })
                    continue

                prompt_text = prompt_result["prompt"]
                with st.spinner(f"Generating video for {product['name'][:30]}... (may take a minute)"):
                    gen_result = generate_video(
                        api_key=api_key,
                        magnific_token=magnific_token,
                        image_url=product["image_url"],
                        image_urls=product.get("image_urls"),
                        prompt=prompt_text,
                        duration=resolved_style_duration(style, duration),
                    )

                gen_result["product_name"] = product["name"]
                gen_result["prompt_used"] = prompt_text
                if style == "texthook_broll":
                    gen_result["broll_scene"] = prompt_result.get("broll_scene") or selected_broll_scene
                if gen_result.get("creation_id") and gen_result.get("status") == "queued":
                    st.success(f"✅ **{product['name']}** — Creation ID: `{gen_result['creation_id']}`")
                elif gen_result.get("status") == "error":
                    error_msg = gen_result.get("error", "")
                    st.error(f"❌ **{product['name']}** — {error_msg}")
                    if any(keyword in error_msg.lower() for keyword in ['401', 'unauthorized', 'auth', 'token', 'forbidden', '403']):
                        st.warning("🔄 **Token expired.** Paste a fresh token in the API connection section and re-run.")
                        token_expired = True
                else:
                    st.warning(f"⚠️ **{product['name']}** — Status: {gen_result.get('status')}")

            if available_audio_tracks() and not gen_result.get("audio_track"):
                gen_result["audio_track"] = choose_random_audio_track()
                gen_result["audio_volume_pct"] = 100

            if hook_data_for_product:
                gen_result["accepted_hook"] = selected_hook
                gen_result["hook_options"] = hook_data_for_product.get("hook_options", [])
                gen_result["caption"] = hook_data_for_product.get("caption")
                gen_result["hashtags"] = hook_data_for_product.get("hashtags")
                gen_result["sound_tip"] = hook_data_for_product.get("sound_tip")
                if selected_hook:
                    st.info(f"📝 Hook saved for the text editor: {selected_hook}")

            results.append(gen_result)
            if i < len(final_products) - 1:
                time.sleep(5)

        progress.progress(1.0, text="Done!")

        # Save each result to persistent file
        for r, fp in zip(results, final_products):
            r["image_url"] = fp["image_url"]
            r["image_urls"] = fp.get("image_urls", [fp["image_url"]])
            r["source_url"] = fp["source_url"]
            r["sniper_caption"] = fp.get("sniper_caption", "")
            r["sniper_scene_prompt"] = fp.get("sniper_scene_prompt", "")
            r["sniper_meta"] = fp.get("sniper_meta", {})
            r["sniper_batch_id"] = fp.get("sniper_batch_id")
            r["sniper_preset"] = fp.get("sniper_preset")
            r["style"] = style
            r["duration"] = resolved_style_duration(style, duration)
            r["voice_script"] = voice_script or ""
            r["generated_at"] = datetime.now().isoformat()
            if style == "lifestyle_animation":
                r["product_type_choice"] = fp.get("product_type_choice", "auto")
                r["product_type"] = fp.get("product_type", "other")
                r["scene_key"] = fp.get("scene_key")
                r["custom_scene"] = fp.get("custom_scene", "")
                r["appearance_details"] = fp.get("appearance_details")
                r["lifestyle_prompt"] = fp.get("lifestyle_prompt")
                r["kling_prompt"] = fp.get("kling_prompt")
            add_generation(r)

        # Summary
        st.divider()
        queued = sum(1 for r in results if r.get("status") in ("queued", "image_queued", "image_processing"))
        errors = sum(1 for r in results if r.get("status") == "error")

        col1, col2, col3 = st.columns(3)
        col1.metric("Total", len(results))
        col2.metric("Queued ✅", queued)
        col3.metric("Errors ❌", errors)

    # ════════════════════════════════════════════════════════════════
    #  UPLOAD A VIDEO AND ADD TEXT
    # ════════════════════════════════════════════════════════════════
    st.divider()
    st.subheader("④ Upload a Video & Add Text")
    st.caption("Use this for an original video that was downloaded without its hook. The uploaded file stays unchanged; the app creates a separate text version.")

    uploaded_video = st.file_uploader(
        "Upload an MP4, MOV, or M4V",
        type=["mp4", "mov", "m4v"],
        key="standalone_video_upload",
    )

    if uploaded_video is not None:
        uploaded_bytes = uploaded_video.getvalue()
        uploaded_signature = hashlib.sha1(uploaded_bytes).hexdigest()
        if st.session_state.get("uploaded_video_signature") != uploaded_signature:
            st.session_state["uploaded_video_signature"] = uploaded_signature
            st.session_state.pop("uploaded_text_output", None)
            random_uploaded_track = choose_random_audio_track()
            if random_uploaded_track:
                st.session_state["upload_audio_track_select"] = random_uploaded_track
            st.session_state["upload_audio_volume"] = 100

        uploaded_output_path = st.session_state.get("uploaded_text_output")
        uploaded_output_bytes = read_local_video(uploaded_output_path)

        upload_original_col, upload_finished_col = st.columns(2, gap="large")
        with upload_original_col:
            st.markdown("#### Original uploaded video")
            st.video(uploaded_bytes)

        with upload_finished_col:
            st.markdown("#### Finished text version")
            if uploaded_output_bytes:
                st.video(uploaded_output_bytes)
                output_name = f"{safe_export_filename(Path(uploaded_video.name).stem)}_with_text.mp4"
                st.download_button(
                    "⬇️ Download text version",
                    data=uploaded_output_bytes,
                    file_name=output_name,
                    mime="video/mp4",
                    use_container_width=True,
                    key="download_uploaded_text_video",
                )
            else:
                st.info("Your finished version will appear here after you apply the hook.")

        with st.expander("✍️ Text editor", expanded=True):
            upload_base = dict(DEFAULT_TEXT_SETTINGS)
            st.caption("Default text style: size 48 · width 89 · position 12 · outline 4 · spacing 99 · emoji 50")
            upload_font_options = available_overlay_fonts()
            upload_default_font = upload_base.get("font_name", "TikTok Sans")
            if upload_default_font not in upload_font_options:
                upload_default_font = upload_font_options[0]

            upload_font_col, upload_hook_col = st.columns([1.15, 2.85])
            with upload_font_col:
                upload_font_name = st.selectbox(
                    "Font",
                    options=upload_font_options,
                    index=upload_font_options.index(upload_default_font),
                    key="upload_font_name",
                )
            with upload_hook_col:
                upload_hook = st.text_area(
                    "On-screen text hook",
                    placeholder="Paste a past hook here, or write a new one",
                    height=100,
                    key="upload_hook_text",
                )

            up_size_col, up_width_col, up_position_col = st.columns(3)
            with up_size_col:
                up_font_size = st.slider("Text size", 16, 48, int(upload_base["font_size"]), key="upload_font_size")
            with up_width_col:
                up_max_width = st.slider("Text width", 45, 92, int(upload_base["max_width_pct"]), key="upload_max_width")
            with up_position_col:
                up_position = st.slider("Vertical position", 8, 60, int(upload_base["vertical_position_pct"]), key="upload_position")

            up_outline_col, up_spacing_col, up_emoji_col = st.columns(3)
            with up_outline_col:
                up_outline = st.slider("Outline thickness", 1, 5, int(upload_base["outline_width"]), key="upload_outline")
            with up_spacing_col:
                up_spacing = st.slider("Line spacing", 95, 145, int(upload_base["line_spacing_pct"]), key="upload_spacing")
            with up_emoji_col:
                up_emoji = st.slider("Emoji size", 18, 90, int(upload_base["emoji_size_px"]), step=2, key="upload_emoji")

            upload_settings = normalize_text_settings({
                "font_name": upload_font_name,
                "font_size": up_font_size,
                "max_width_pct": up_max_width,
                "vertical_position_pct": up_position,
                "outline_width": up_outline,
                "line_spacing_pct": up_spacing,
                "emoji_size_px": up_emoji,
            })

            st.markdown('<span class="preset-pill">RANDOM SOUNDTRACK</span>', unsafe_allow_html=True)
            uploaded_soundtrack_files = available_audio_tracks()
            upload_selected_audio_track = ""
            upload_audio_volume_pct = int(st.session_state.get("upload_audio_volume", 100) or 100)
            if uploaded_soundtrack_files:
                uploaded_soundtrack_names = [track.name for track in uploaded_soundtrack_files]
                if st.session_state.get("upload_audio_track_select") not in uploaded_soundtrack_names:
                    st.session_state["upload_audio_track_select"] = choose_random_audio_track()

                up_audio_col, up_random_col, up_volume_col = st.columns([2.5, 1, 1.25])
                with up_audio_col:
                    upload_selected_audio_track = st.selectbox(
                        "Audio track",
                        options=uploaded_soundtrack_names,
                        key="upload_audio_track_select",
                    )
                with up_random_col:
                    st.write("")
                    if st.button("🎲 Randomize", key="upload_random_audio", use_container_width=True):
                        new_upload_audio_track = choose_random_audio_track(exclude=upload_selected_audio_track)
                        if new_upload_audio_track:
                            st.session_state["upload_audio_track_select"] = new_upload_audio_track
                            st.session_state["upload_audio_volume"] = 100
                            st.rerun()
                with up_volume_col:
                    upload_audio_volume_pct = st.slider(
                        "Volume",
                        min_value=0,
                        max_value=100,
                        step=5,
                        key="upload_audio_volume",
                    )

                upload_selected_audio_path = resolve_audio_track(upload_selected_audio_track)
                if upload_selected_audio_path:
                    try:
                        st.audio(upload_selected_audio_path.read_bytes())
                    except Exception:
                        st.caption(f"Selected soundtrack: {upload_selected_audio_track}")
                st.caption(f"{len(uploaded_soundtrack_files)} soundtrack(s) found. A random track is assigned when you upload a video.")
            else:
                st.warning("No audio tracks found. Add your 14 files to the `audio_tracks/` folder in GitHub.")

            st.markdown('<span class="preset-pill">COLOR FILTER</span>', unsafe_allow_html=True)
            upload_apply_color_filter = st.toggle(
                "Apply saved color filter",
                value=bool(st.session_state.get("upload_apply_color_filter", False)),
                key="upload_apply_color_filter",
                help="Applies the fixed FFmpeg color preset when creating the finished video.",
            )
            st.caption(VIDEO_COLOR_FILTER_LABEL)

            if st.button("🎨 Add / Update Text", type="primary", use_container_width=True, key="process_uploaded_video"):
                with st.spinner("Applying text with FFmpeg..."):
                    upload_output, upload_warning = apply_text_to_uploaded_video(
                        video_bytes=uploaded_bytes,
                        original_filename=uploaded_video.name,
                        hook=upload_hook.strip(),
                        settings=upload_settings,
                        audio_track=upload_selected_audio_track,
                        audio_volume_pct=upload_audio_volume_pct,
                        apply_color_filter=upload_apply_color_filter,
                    )
                if upload_output:
                    st.session_state["uploaded_text_output"] = str(upload_output)
                    if upload_warning:
                        st.warning(upload_warning)
                    st.rerun()
                else:
                    st.error(upload_warning or "Could not create the text version.")

    # ════════════════════════════════════════════════════════════════
    #  STEP 4 — PAST GENERATIONS (persisted to file, survives refresh)
    # ════════════════════════════════════════════════════════════════
    saved_gens = load_generations()

    if saved_gens:
        st.divider()
        st.subheader("⑤ Past Generations")
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

        # Refresh every pending generation before rendering the workspace.
        if check_all:
            refreshed_any = False
            for refresh_index, refresh_result in enumerate(saved_gens):
                refresh_creation_id = refresh_result.get("creation_id")
                refresh_status = refresh_result.get("status", "unknown")
                is_lifestyle_image = (
                    refresh_result.get("style") == "lifestyle_animation"
                    and refresh_result.get("pipeline_stage") == "image"
                )
                terminal_statuses = {"completed", "error", "prompt_only", "image_approved"}
                if refresh_status == "image_completed" and refresh_result.get("lifestyle_image_url"):
                    terminal_statuses.add("image_completed")
                if refresh_creation_id and refresh_status not in terminal_statuses:
                    with st.spinner(f"Checking {refresh_result.get('product_name', 'video')}..."):
                        status_result = check_creation_status(api_key, magnific_token, refresh_creation_id)
                    if is_lifestyle_image:
                        raw_status = status_result.get("status", refresh_status)
                        mapped = {
                            "queued": "image_queued",
                            "processing": "image_processing",
                            "completed": "image_completed",
                            "error": "error",
                        }.get(raw_status, raw_status)
                        saved_gens[refresh_index]["status"] = mapped
                        approved_image_url = status_result.get("url") or status_result.get("preview_url")
                        if approved_image_url:
                            saved_gens[refresh_index]["lifestyle_image_url"] = approved_image_url
                    else:
                        refreshed_status = status_result.get("status", refresh_status)
                        saved_gens[refresh_index]["status"] = refreshed_status
                        if status_result.get("url"):
                            saved_gens[refresh_index]["url"] = status_result["url"]
                        if status_result.get("preview_url"):
                            saved_gens[refresh_index]["preview_url"] = status_result["preview_url"]
                        if refreshed_status == "completed" and (status_result.get("url") or status_result.get("preview_url")):
                            saved_gens[refresh_index]["completed_at"] = datetime.now().isoformat()
                            saved_gens[refresh_index]["video_refresh_key"] = f"{refresh_creation_id}-{time.time_ns()}"
                    refreshed_any = True
            if refreshed_any:
                save_generations(saved_gens)
                st.rerun()

        # Master-detail workspace: compact list on the left, selected video on the right.
        # Only one editor is rendered at a time, which keeps the page short and readable.
        def generation_identity(generation, generation_index):
            return str(
                generation.get("creation_id")
                or generation.get("generated_at")
                or f"generation-{generation_index}"
            )

        all_generation_keys = [
            generation_identity(generation, generation_index)
            for generation_index, generation in enumerate(saved_gens)
        ]
        selected_generation_key = st.session_state.get("selected_generation_key")
        if selected_generation_key not in all_generation_keys:
            selected_generation_key = all_generation_keys[0]
            st.session_state["selected_generation_key"] = selected_generation_key

        list_panel, detail_panel = st.columns([1.05, 2.35], gap="large")

        with list_panel:
            st.markdown("#### Video Library")
            generation_search = st.text_input(
                "Search videos",
                placeholder="Search product, hook, or status",
                label_visibility="collapsed",
                key="generation_library_search",
            ).strip().lower()

            with st.container(height=760, border=True):
                visible_count = 0
                for list_index, list_result in enumerate(saved_gens):
                    list_product_name = list_result.get("product_name", "Unknown Product")
                    list_status = list_result.get("status", "unknown")
                    list_hook = list_result.get("accepted_hook", "") or ""
                    list_style = list_result.get("style", "texthook_broll")
                    search_haystack = f"{list_product_name} {list_status} {list_hook} {list_style}".lower()
                    if generation_search and generation_search not in search_haystack:
                        continue

                    visible_count += 1
                    list_key = generation_identity(list_result, list_index)
                    list_selected = list_key == selected_generation_key
                    list_generated_at = list_result.get("generated_at", "")
                    list_time = ""
                    if list_generated_at:
                        try:
                            list_dt = datetime.fromisoformat(list_generated_at)
                            list_time = list_dt.strftime("%b %d · %I:%M %p")
                        except Exception:
                            list_time = ""

                    list_status_badges = {
                        "queued": "🟡 Queued",
                        "processing": "🟠 Processing",
                        "completed": "🟢 Completed",
                        "error": "🔴 Error",
                        "prompt_only": "📝 Prompt only",
                        "image_queued": "🟡 Image queued",
                        "image_processing": "🟠 Image processing",
                        "image_completed": "🖼️ Awaiting approval",
                        "image_approved": "✅ Image approved",
                    }
                    list_badge = list_status_badges.get(list_status, f"⚪ {list_status}")
                    text_marker = " · ✍️ Text ready" if read_local_video(list_result.get("processed_path")) else ""

                    with st.container(border=True):
                        st.markdown(f"**{list_product_name}**")
                        st.caption(f"{STYLE_LABELS.get(list_style, list_style)} · {list_badge}{text_marker}")
                        if list_time:
                            st.caption(list_time)
                        if list_hook:
                            compact_hook = list_hook if len(list_hook) <= 72 else f"{list_hook[:69]}..."
                            st.caption(f"“{compact_hook}”")

                        if st.button(
                            "Viewing" if list_selected else "Open",
                            key=f"open_generation_{list_index}",
                            type="primary" if list_selected else "secondary",
                            disabled=list_selected,
                            use_container_width=True,
                        ):
                            st.session_state["selected_generation_key"] = list_key
                            st.rerun()

                if visible_count == 0:
                    st.info("No saved videos match that search.")

        with detail_panel:
            selected_index = all_generation_keys.index(selected_generation_key)
            result = saved_gens[selected_index]
            i = selected_index

            with st.container(border=True):
                creation_id = result.get("creation_id")
                product_name = result.get("product_name", "Unknown Product")
                status = result.get("status", "unknown")
                generated_at = result.get("generated_at", "")

                status_badges = {
                    "queued": "🟡 Queued",
                    "processing": "🟠 Processing",
                    "completed": "🟢 Completed",
                    "error": "🔴 Error",
                    "prompt_only": "📝 Prompt Only",
                    "image_queued": "🟡 Image queued",
                    "image_processing": "🟠 Image processing",
                    "image_completed": "🖼️ Awaiting approval",
                    "image_approved": "✅ Image approved",
                }
                badge = status_badges.get(status, f"⚪ {status}")

                time_str = ""
                if generated_at:
                    try:
                        dt = datetime.fromisoformat(generated_at)
                        time_str = f" · {dt.strftime('%b %d, %I:%M %p')}"
                    except Exception:
                        pass

                header_info, header_actions = st.columns([3.4, 1.6], vertical_alignment="center")
                with header_info:
                    st.markdown(f"### {product_name}")
                    st.caption(f"{STYLE_LABELS.get(result.get('style', 'texthook_broll'), result.get('style', ''))} · {badge}{time_str}")
                    if result.get("style") == "lifestyle_animation":
                        st.caption(f"Image model: {LIFESTYLE_IMAGE_MODEL_LABEL}  |  Video model: {LIFESTYLE_VIDEO_MODEL_LABEL}")
                    if creation_id:
                        st.caption(f"Creation ID: `{creation_id}`")

                with header_actions:
                    stored_style = result.get("style") or "texthook_broll"
                    is_lifestyle = stored_style == "lifestyle_animation"
                    is_lifestyle_image_stage = is_lifestyle and result.get("pipeline_stage") == "image"

                    terminal_statuses = {"completed", "error", "prompt_only", "image_approved"}
                    if status == "image_completed" and result.get("lifestyle_image_url"):
                        terminal_statuses.add("image_completed")
                    if creation_id and status not in terminal_statuses and magnific_token and api_key:
                        if st.button("🔄 Check status", key=f"chk_{i}", use_container_width=True):
                            with st.spinner("Checking..."):
                                status_result = check_creation_status(api_key, magnific_token, creation_id)
                            if is_lifestyle_image_stage:
                                raw_status = status_result.get("status", status)
                                saved_gens[i]["status"] = {
                                    "queued": "image_queued",
                                    "processing": "image_processing",
                                    "completed": "image_completed",
                                    "error": "error",
                                }.get(raw_status, raw_status)
                                lifestyle_url = status_result.get("url") or status_result.get("preview_url")
                                if lifestyle_url:
                                    saved_gens[i]["lifestyle_image_url"] = lifestyle_url
                            else:
                                refreshed_status = status_result.get("status", status)
                                saved_gens[i]["status"] = refreshed_status
                                if status_result.get("url"):
                                    saved_gens[i]["url"] = status_result["url"]
                                if status_result.get("preview_url"):
                                    saved_gens[i]["preview_url"] = status_result["preview_url"]
                                if refreshed_status == "completed" and (status_result.get("url") or status_result.get("preview_url")):
                                    saved_gens[i]["completed_at"] = datetime.now().isoformat()
                                    saved_gens[i]["video_refresh_key"] = f"{creation_id}-{time.time_ns()}"
                            st.session_state["selected_generation_key"] = str(creation_id)
                            st.session_state["video_refresh_nonce"] = time.time_ns()
                            save_generations(saved_gens)
                            st.rerun()

                    if is_lifestyle:
                        if status == "image_completed":
                            if st.button("✅ Approve image", key=f"approve_lifestyle_{i}", type="primary", use_container_width=True):
                                saved_gens[i]["status"] = "image_approved"
                                saved_gens[i]["approved_at"] = datetime.now().isoformat()
                                save_generations(saved_gens)
                                st.rerun()

                        if status == "image_approved" and result.get("lifestyle_image_url") and magnific_token and api_key:
                            if st.button("🎬 Generate Kling video", key=f"generate_kling_{i}", type="primary", use_container_width=True):
                                with st.spinner("Animating the approved image with Kling through Magnific..."):
                                    kling_result = generate_lifestyle_kling_magnific(
                                        api_key=api_key,
                                        magnific_token=magnific_token,
                                        approved_image_url=result["lifestyle_image_url"],
                                        prompt=result.get("kling_prompt") or "",
                                        duration=int(result.get("duration") or 5),
                                    )
                                if kling_result.get("creation_id"):
                                    saved_gens[i]["video_creation_id"] = kling_result["creation_id"]
                                    saved_gens[i]["creation_id"] = kling_result["creation_id"]
                                    saved_gens[i]["pipeline_stage"] = "video"
                                    saved_gens[i]["status"] = kling_result.get("status", "queued")
                                    saved_gens[i]["audio_track"] = choose_random_audio_track(
                                        exclude=result.get("audio_track")
                                    ) or result.get("audio_track", "")
                                    saved_gens[i]["audio_volume_pct"] = 100
                                    saved_gens[i]["kling_started_at"] = datetime.now().isoformat()
                                    st.session_state["selected_generation_key"] = str(kling_result["creation_id"])
                                    save_generations(saved_gens)
                                    st.rerun()
                                else:
                                    st.error(kling_result.get("error", "Magnific did not return a Kling creation ID."))

                        if status in ("image_completed", "image_approved"):
                            if st.button(
                                "🖼️ Regenerate lifestyle image",
                                key=f"regen_lifestyle_{i}",
                                use_container_width=True,
                                disabled=not bool(api_key and magnific_token),
                            ):
                                with st.spinner("Generating another lifestyle image with Grok Imagine..."):
                                    image_result = generate_lifestyle_image_grok(
                                        xai_api_key=xai_api_key,
                                        product_name=product_name,
                                        reference_urls=result.get("image_urls", [result.get("image_url")]),
                                        prompt=result.get("lifestyle_prompt") or result.get("prompt_used") or result.get("prompt") or "",
                                    )
                                if image_result.get("creation_id") and image_result.get("url"):
                                    saved_gens[i]["creation_id"] = image_result["creation_id"]
                                    saved_gens[i]["lifestyle_creation_id"] = image_result["creation_id"]
                                    saved_gens[i]["pipeline_stage"] = "image"
                                    saved_gens[i]["status"] = "image_completed"
                                    saved_gens[i]["lifestyle_image_url"] = image_result["url"]
                                    saved_gens[i]["provider"] = "xAI"
                                    saved_gens[i]["image_model"] = image_result.get("image_model", XAI_IMAGE_MODEL)
                                    saved_gens[i]["image_resolution"] = "2k"
                                    saved_gens[i]["image_aspect_ratio"] = "9:16"
                                    saved_gens[i].pop("approved_at", None)
                                    st.session_state["selected_generation_key"] = str(image_result["creation_id"])
                                    save_generations(saved_gens)
                                    st.rerun()
                                else:
                                    st.error(image_result.get("error", "xAI did not return a lifestyle image."))
                    else:
                        current_prompt = result.get("prompt_used") or result.get("prompt")
                        if current_prompt and api_key:
                            if st.button("🪄 Regenerate prompt", key=f"regen_prompt_{i}", use_container_width=True):
                                stored_duration = int(result.get("duration") or resolved_style_duration(stored_style, 15))
                                regenerated_broll_scene = (
                                    choose_broll_scene(result.get("broll_scene"))
                                    if stored_style == "texthook_broll"
                                    else None
                                )
                                with st.spinner("Writing a new prompt..."):
                                    regenerated_prompt = write_prompt(
                                        api_key=api_key,
                                        product_name=product_name,
                                        style=stored_style,
                                        duration=stored_duration,
                                        voice_script=result.get("voice_script") or None,
                                        selected_hook=result.get("accepted_hook") or None,
                                        broll_scene=regenerated_broll_scene,
                                    )
                                if regenerated_prompt.get("prompt"):
                                    result["prompt"] = regenerated_prompt["prompt"]
                                    result["prompt_used"] = regenerated_prompt["prompt"]
                                    if stored_style == "texthook_broll":
                                        result["broll_scene"] = regenerated_prompt.get("broll_scene") or regenerated_broll_scene
                                    result["prompt_regenerated_at"] = datetime.now().isoformat()
                                    saved_gens[i] = result
                                    save_generations(saved_gens)
                                    st.success("New prompt saved. Use Generate/Regenerate video when ready.")
                                else:
                                    st.error(regenerated_prompt.get("error", "The prompt could not be regenerated."))

                        current_prompt = result.get("prompt_used") or result.get("prompt")
                        if current_prompt and result.get("image_url") and magnific_token and api_key:
                            video_button_label = "🎬 Generate video" if status == "prompt_only" else "🎬 Regenerate video"
                            if st.button(video_button_label, key=f"regen_{i}", use_container_width=True):
                                stored_duration = int(result.get("duration") or resolved_style_duration(stored_style, 15))
                                prompt_for_regeneration = current_prompt
                                regenerated_broll_scene = result.get("broll_scene")

                                if stored_style == "texthook_broll":
                                    regenerated_broll_scene = choose_broll_scene(result.get("broll_scene"))
                                    with st.spinner("Choosing a different opening scene and writing a fresh B-roll prompt..."):
                                        refreshed_prompt = write_prompt(
                                            api_key=api_key,
                                            product_name=product_name,
                                            style=stored_style,
                                            duration=stored_duration,
                                            voice_script=result.get("voice_script") or None,
                                            selected_hook=result.get("accepted_hook") or None,
                                            broll_scene=regenerated_broll_scene,
                                        )
                                    if not refreshed_prompt.get("prompt"):
                                        st.error(refreshed_prompt.get("error", "Could not create a new B-roll prompt."))
                                        st.stop()
                                    prompt_for_regeneration = refreshed_prompt["prompt"]
                                    regenerated_broll_scene = refreshed_prompt.get("broll_scene") or regenerated_broll_scene

                                with st.spinner("Sending the updated prompt and references to Magnific..."):
                                    new_result = generate_video(
                                        api_key=api_key,
                                        magnific_token=magnific_token,
                                        image_url=result["image_url"],
                                        image_urls=result.get("image_urls", [result["image_url"]]),
                                        prompt=prompt_for_regeneration,
                                        duration=stored_duration,
                                    )
                                new_result["product_name"] = product_name
                                new_result["prompt_used"] = prompt_for_regeneration
                                new_result["prompt"] = prompt_for_regeneration
                                if stored_style == "texthook_broll":
                                    new_result["broll_scene"] = regenerated_broll_scene
                                new_result["image_url"] = result["image_url"]
                                new_result["image_urls"] = result.get("image_urls", [result["image_url"]])
                                new_result["source_url"] = result.get("source_url", "")
                                new_result["style"] = stored_style
                                new_result["duration"] = stored_duration
                                new_result["voice_script"] = result.get("voice_script", "")
                                new_result["accepted_hook"] = result.get("accepted_hook")
                                new_result["hook_options"] = result.get("hook_options", [])
                                new_result["caption"] = result.get("caption")
                                new_result["hashtags"] = result.get("hashtags")
                                new_result["sound_tip"] = result.get("sound_tip")
                                new_result["audio_track"] = choose_random_audio_track(
                                    exclude=result.get("audio_track")
                                ) or result.get("audio_track", "")
                                new_result["audio_volume_pct"] = 100
                                new_result["generated_at"] = datetime.now().isoformat()
                                new_result["regenerated_from_creation_id"] = creation_id
                                new_result.pop("processed_path", None)
                                new_result.pop("processed_at", None)
                                new_creation_id = new_result.get("creation_id")
                                if not new_creation_id:
                                    st.error(new_result.get("error") or "Magnific did not return a new creation ID, so the old video was left selected.")
                                else:
                                    new_generation_key = str(new_creation_id)
                                    add_generation(new_result)
                                    st.session_state["selected_generation_key"] = new_generation_key
                                    st.session_state["video_refresh_nonce"] = time.time_ns()
                                    st.rerun()

                is_lifestyle_result = result.get("style") == "lifestyle_animation"
                is_image_stage = is_lifestyle_result and result.get("pipeline_stage") == "image"
                video_url = result.get("url") or (None if is_image_stage else result.get("preview_url"))
                lifestyle_image_url = result.get("lifestyle_image_url")
                processed_bytes = read_local_video(result.get("processed_path"))
                original_bytes = None
                safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", product_name)[:40]

                if video_url and status == "completed":
                    original_preview_col, edited_preview_col = st.columns(2, gap="large")

                    with original_preview_col:
                        st.markdown("#### Original video")
                        preview_cache_key = str(
                            result.get("video_refresh_key")
                            or result.get("creation_id")
                            or result.get("completed_at")
                            or result.get("generated_at")
                            or i
                        )
                        original_bytes = fetch_video_bytes(video_url, preview_cache_key)
                        try:
                            st.video(original_bytes if original_bytes else video_url)
                        except Exception:
                            st.markdown(f"🎬 [Watch original video]({video_url})")
                        if original_bytes:
                            st.download_button(
                                "⬇️ Download original",
                                data=original_bytes,
                                file_name=f"{safe_name}_{creation_id or i}_original.mp4",
                                mime="video/mp4",
                                key=f"dl_original_{i}",
                                use_container_width=True,
                            )

                    with edited_preview_col:
                        st.markdown("#### Text version")
                        if processed_bytes:
                            st.video(processed_bytes)
                            st.download_button(
                                "⬇️ Download text version",
                                data=processed_bytes,
                                file_name=f"{safe_name}_{creation_id or i}_with_text.mp4",
                                mime="video/mp4",
                                key=f"dl_processed_{i}",
                                use_container_width=True,
                            )
                        else:
                            st.info("Your edited text version will appear here after you click Apply text below.")
                elif is_lifestyle_result and lifestyle_image_url:
                    image_col, approval_col = st.columns([1.15, 1.35], gap="large")
                    with image_col:
                        st.markdown("#### Generated lifestyle image")
                        st.image(lifestyle_image_url, use_container_width=True)
                        image_bytes, image_content_type = fetch_image_bytes(lifestyle_image_url)
                        if image_bytes:
                            ext_map = {
                                "image/jpeg": ".jpg",
                                "image/jpg": ".jpg",
                                "image/png": ".png",
                                "image/webp": ".webp",
                            }
                            image_ext = ext_map.get((image_content_type or "").lower(), ".jpg")
                            st.download_button(
                                "⬇️ Download lifestyle image",
                                data=image_bytes,
                                file_name=f"{safe_name}_{creation_id or i}_lifestyle{image_ext}",
                                mime=image_content_type or "image/jpeg",
                                key=f"dl_lifestyle_image_{i}",
                                use_container_width=True,
                            )
                    with approval_col:
                        if status == "image_completed":
                            st.success("Review this image carefully. Click **Approve image** only when the product and scene look right.")
                        elif status == "image_approved":
                            st.success("Approved. You can now generate the Kling O1 animation from this exact image using it as the start frame.")
                        else:
                            st.info("The image step is still processing.")
                        product_type = result.get("product_type", "other")
                        if product_type in LIFESTYLE_PRODUCT_TYPES:
                            st.caption(f"Product profile: {LIFESTYLE_PRODUCT_TYPES[product_type]['label']}")
                        scene_key = result.get("scene_key")
                        if scene_key in LIFESTYLE_SCENES:
                            st.caption(f"Scene: {LIFESTYLE_SCENES[scene_key]['label']}")
                        if result.get("custom_scene"):
                            st.caption(f"Custom scene: {result['custom_scene']}")
                        if result.get("appearance_details"):
                            st.caption(f"Product details: {result['appearance_details']}")

                        st.markdown("---")
                        if result.get("director_pushed_at"):
                            st.success(f"Already sent to Director: {result['director_pushed_at']}")

                        director_button_label = (
                            "↗️ Send image to Director again"
                            if result.get("director_pushed_at")
                            else "↗️ Send image to Director"
                        )
                        send_to_director = st.button(
                            director_button_label,
                            key=f"send_lifestyle_to_director_{i}",
                            type="primary" if not result.get("director_pushed_at") else "secondary",
                            use_container_width=True,
                            disabled=not bool(director_ingest_key),
                            help=(
                                "Push this generated Lifestyle image into the Momentum Academy Director flow."
                                if director_ingest_key
                                else "Add DIRECTOR_INGEST_KEY in API connection or Streamlit Secrets first."
                            ),
                        )
                        if not director_ingest_key:
                            st.caption("Connect the Momentum Director ingest key above to enable this button.")

                        if send_to_director:
                            with st.spinner("Sending the generated image to Momentum Director..."):
                                director_ok, director_message = push_generated_image_to_director(
                                    ingest_key=director_ingest_key,
                                    ingest_url=director_ingest_url,
                                    image_url=lifestyle_image_url,
                                    product_name=product_name,
                                    caption=result.get("caption") or result.get("accepted_hook") or "",
                                    scene_prompt=result.get("lifestyle_prompt") or result.get("prompt_used") or result.get("prompt") or "",
                                    meta={
                                        "source_url": result.get("source_url", ""),
                                        "style": result.get("style", "lifestyle_animation"),
                                        "scene_key": result.get("scene_key"),
                                        "custom_scene": result.get("custom_scene", ""),
                                        "product_type": result.get("product_type"),
                                        "appearance_details": result.get("appearance_details", ""),
                                        "image_model": result.get("image_model", XAI_IMAGE_MODEL),
                                        "image_resolution": result.get("image_resolution", "2k"),
                                        "image_aspect_ratio": result.get("image_aspect_ratio", "9:16"),
                                        "creation_id": result.get("lifestyle_creation_id") or result.get("creation_id"),
                                        "generated_at": result.get("generated_at", ""),
                                        "accepted_hook": result.get("accepted_hook", ""),
                                        "hashtags": result.get("hashtags", ""),
                                    },
                                )
                            if director_ok:
                                saved_gens[i]["director_pushed_at"] = datetime.now().isoformat(timespec="seconds")
                                saved_gens[i]["director_ingest_status"] = "sent"
                                saved_gens[i]["director_ingest_message"] = director_message
                                save_generations(saved_gens)
                                st.success(director_message)
                                st.rerun()
                            else:
                                saved_gens[i]["director_ingest_status"] = "error"
                                saved_gens[i]["director_ingest_message"] = director_message
                                save_generations(saved_gens)
                                st.error(director_message)
                elif result.get("image_url"):
                    preview_image_col, preview_message_col = st.columns([1, 1.5])
                    with preview_image_col:
                        try:
                            st.image(result["image_url"], use_container_width=True)
                        except Exception:
                            pass
                    with preview_message_col:
                        if is_lifestyle_result:
                            st.info("The lifestyle image is not ready yet. Check its status when Magnific is connected.")
                        else:
                            st.info("This generation is not finished yet. Check its status when Magnific is connected.")

                prompt_text_field = result.get("prompt_used") or result.get("prompt")
                if prompt_text_field:
                    with st.expander("📋 Generation prompt", expanded=False):
                        if is_lifestyle_result:
                            st.markdown("**Grok lifestyle image prompt**")
                            st.code(result.get("lifestyle_prompt") or prompt_text_field, language=None)
                            st.markdown("**Kling O1 animation prompt**")
                            st.code(result.get("kling_prompt") or "", language=None)
                        else:
                            st.code(prompt_text_field, language=None)
                            if result.get("style") == "texthook_broll" and result.get("broll_scene"):
                                st.caption(f"Opening scene selected by app: {result['broll_scene']}")
                        reference_urls = result.get("image_urls") or ([result.get("image_url")] if result.get("image_url") else [])
                        if reference_urls:
                            st.caption(f"Reference images: {len(reference_urls)}")
                            for reference_number, reference_url in enumerate(reference_urls, start=1):
                                st.text_input(
                                    f"Reference {reference_number}",
                                    value=reference_url,
                                    key=f"detail_reference_{i}_{reference_number}",
                                )

                if video_url and status == "completed":
                    has_processed_version = bool(processed_bytes)
                    editor_title = "✍️ Modify on-screen text" if has_processed_version else "✍️ Add on-screen text"

                    with st.expander(editor_title, expanded=True):
                        st.caption(
                            "The original stays untouched. The final version combines your hook styling with the assigned soundtrack."
                        )

                        # Unedited videos always open with the fixed default style.
                        # Existing processed versions keep their saved settings until changed.
                        if has_processed_version and result.get("text_settings"):
                            stored_settings = normalize_text_settings(result.get("text_settings"))
                        else:
                            stored_settings = dict(DEFAULT_TEXT_SETTINGS)

                        widget_keys = [
                            f"editor_font_{i}",
                            f"editor_size_{i}",
                            f"editor_width_{i}",
                            f"editor_position_{i}",
                            f"editor_outline_{i}",
                            f"editor_spacing_{i}",
                            f"editor_emoji_{i}",
                        ]
                        if not any(key in st.session_state for key in widget_keys):
                            set_editor_widget_values(i, stored_settings)

                        st.caption("Default text style: size 48 · width 89 · position 12 · outline 4 · spacing 99 · emoji 50")

                        editor_font_options = available_overlay_fonts()
                        editor_default_font = stored_settings.get("font_name", "TikTok Sans")
                        if editor_default_font not in editor_font_options:
                            editor_default_font = editor_font_options[0]

                        font_col, hook_col = st.columns([1.15, 2.85])
                        with font_col:
                            editor_font_name = st.selectbox(
                                "Font",
                                options=editor_font_options,
                                index=editor_font_options.index(editor_default_font),
                                key=f"editor_font_{i}",
                            )
                        with hook_col:
                            edited_hook = st.text_area(
                                "Hook text",
                                value=result.get("accepted_hook", ""),
                                key=f"editor_hook_{i}",
                                height=100,
                            )

                        row_one_col1, row_one_col2, row_one_col3 = st.columns(3)
                        with row_one_col1:
                            font_size = st.slider(
                                "Text size",
                                min_value=16,
                                max_value=48,
                                step=1,
                                key=f"editor_size_{i}",
                            )
                        with row_one_col2:
                            max_width_pct = st.slider(
                                "Text width",
                                min_value=45,
                                max_value=92,
                                step=1,
                                key=f"editor_width_{i}",
                            )
                        with row_one_col3:
                            vertical_position_pct = st.slider(
                                "Vertical position",
                                min_value=8,
                                max_value=60,
                                step=1,
                                key=f"editor_position_{i}",
                            )

                        row_two_col1, row_two_col2, row_two_col3 = st.columns(3)
                        with row_two_col1:
                            outline_width = st.slider(
                                "Outline thickness",
                                min_value=1,
                                max_value=5,
                                step=1,
                                key=f"editor_outline_{i}",
                            )
                        with row_two_col2:
                            line_spacing_pct = st.slider(
                                "Line spacing",
                                min_value=95,
                                max_value=145,
                                step=1,
                                key=f"editor_spacing_{i}",
                            )
                        with row_two_col3:
                            emoji_size_px = st.slider(
                                "Emoji size",
                                min_value=18,
                                max_value=90,
                                step=2,
                                key=f"editor_emoji_{i}",
                            )

                        editor_settings = normalize_text_settings({
                            "font_name": editor_font_name,
                            "font_size": font_size,
                            "max_width_pct": max_width_pct,
                            "vertical_position_pct": vertical_position_pct,
                            "outline_width": outline_width,
                            "line_spacing_pct": line_spacing_pct,
                            "emoji_size_px": emoji_size_px,
                        })

                        available_assets = sum(
                            1 for filename in EMOJI_ASSET_MAP.values()
                            if (EMOJI_ASSET_DIR / filename).exists()
                        )
                        st.caption(
                            f"Apple-style emoji PNGs found: {available_assets}/{len(EMOJI_ASSET_MAP)}."
                        )

                        st.markdown('<span class="preset-pill">RANDOM SOUNDTRACK</span>', unsafe_allow_html=True)
                        soundtrack_files = available_audio_tracks()
                        selected_audio_track = ""
                        audio_volume_pct = int(result.get("audio_volume_pct", 100) or 100)
                        if soundtrack_files:
                            soundtrack_names = [track.name for track in soundtrack_files]
                            stored_audio_track = result.get("audio_track")
                            if stored_audio_track not in soundtrack_names:
                                stored_audio_track = choose_random_audio_track()
                                saved_gens[i]["audio_track"] = stored_audio_track
                                saved_gens[i]["audio_volume_pct"] = audio_volume_pct
                                save_generations(saved_gens)

                            audio_widget_key = f"audio_track_select_{i}"
                            if st.session_state.get(audio_widget_key) not in soundtrack_names:
                                st.session_state[audio_widget_key] = stored_audio_track

                            audio_track_col, audio_random_col, audio_volume_col = st.columns([2.5, 1, 1.25])
                            with audio_track_col:
                                selected_audio_track = st.selectbox(
                                    "Audio track",
                                    options=soundtrack_names,
                                    key=audio_widget_key,
                                )
                            with audio_random_col:
                                st.write("")
                                if st.button("🎲 Randomize", key=f"random_audio_{i}", use_container_width=True):
                                    new_audio_track = choose_random_audio_track(exclude=selected_audio_track)
                                    if new_audio_track:
                                        saved_gens[i]["audio_track"] = new_audio_track
                                        saved_gens[i]["audio_volume_pct"] = 100
                                        save_generations(saved_gens)
                                        st.session_state[audio_widget_key] = new_audio_track
                                        st.rerun()
                            with audio_volume_col:
                                audio_volume_key = f"audio_volume_{i}"
                                if audio_volume_key not in st.session_state:
                                    st.session_state[audio_volume_key] = audio_volume_pct
                                audio_volume_pct = st.slider(
                                    "Volume",
                                    min_value=0,
                                    max_value=100,
                                    step=5,
                                    key=audio_volume_key,
                                )

                            selected_audio_path = resolve_audio_track(selected_audio_track)
                            if selected_audio_path:
                                try:
                                    st.audio(selected_audio_path.read_bytes())
                                except Exception:
                                    st.caption(f"Selected soundtrack: {selected_audio_track}")
                            st.caption(f"{len(soundtrack_files)} soundtrack(s) found. A random track is assigned to each new or regenerated video.")
                        else:
                            st.warning("No audio tracks found. Add your 14 files to the `audio_tracks/` folder in GitHub.")

                        st.markdown('<span class="preset-pill">COLOR FILTER</span>', unsafe_allow_html=True)
                        filter_widget_key = f"apply_color_filter_{i}"
                        if filter_widget_key not in st.session_state:
                            st.session_state[filter_widget_key] = bool(result.get("apply_color_filter", False))
                        apply_color_filter = st.toggle(
                            "Apply saved color filter",
                            key=filter_widget_key,
                            help="Applies the fixed FFmpeg color preset to the final video while keeping the original untouched.",
                        )
                        st.caption(VIDEO_COLOR_FILTER_LABEL)

                        apply_col, remove_col = st.columns([1.5, 1])
                        apply_label = "🎬 Update final video" if has_processed_version else "🎬 Create final video"

                        if apply_col.button(
                            apply_label,
                            key=f"apply_text_{i}",
                            type="primary",
                            use_container_width=True,
                        ):
                            with st.spinner("Applying your text settings with FFmpeg..."):
                                output_path, editor_warning = apply_text_with_ffmpeg(
                                    video_url=video_url,
                                    creation_id=creation_id,
                                    hook=edited_hook.strip(),
                                    settings=editor_settings,
                                    audio_track=selected_audio_track or None,
                                    audio_volume_pct=audio_volume_pct,
                                    apply_color_filter=apply_color_filter,
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
                                saved_gens[i]["text_preset_name"] = "Default"
                                saved_gens[i]["audio_track"] = selected_audio_track
                                saved_gens[i]["audio_volume_pct"] = audio_volume_pct
                                saved_gens[i]["apply_color_filter"] = bool(apply_color_filter)
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

                        with st.expander("Past hooks and caption", expanded=False):
                            if result.get("hook_options"):
                                st.caption("Other generated hook options:")
                                for hook_option in result["hook_options"]:
                                    st.caption(f"• {hook_option}")
                            if result.get("caption"):
                                st.caption(f"Caption: {result['caption']}")
                            if result.get("hashtags"):
                                st.caption(f"Hashtags: {result['hashtags']}")
                            if result.get("sound_tip"):
                                st.caption(f"Sound tip: {result['sound_tip']}")

        # Bulk downloads
        st.divider()
        st.subheader("📦 Bulk Downloads")
        export_stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        csv_data = generations_csv_bytes(saved_gens)

        download_col1, download_col2, download_col3, download_col4, download_col5 = st.columns(5)
        download_col1.download_button(
            "📥 Download CSV",
            data=csv_data,
            file_name=f"captions_{export_stamp}.csv",
            mime="text/csv",
            use_container_width=True,
        )

        zip_data, zip_video_count, zip_skipped = generations_zip_bytes(saved_gens)
        download_col2.download_button(
            f"⬇️ Download Videos ZIP ({zip_video_count})",
            data=zip_data,
            file_name=f"seedance_videos_{export_stamp}.zip",
            mime="application/zip",
            use_container_width=True,
            disabled=zip_video_count == 0,
        )

        lifestyle_zip_data, lifestyle_zip_count, lifestyle_zip_skipped = lifestyle_images_zip_bytes(saved_gens)
        download_col3.download_button(
            f"🖼️ Download Lifestyle Images ({lifestyle_zip_count})",
            data=lifestyle_zip_data,
            file_name=f"lifestyle_images_{export_stamp}.zip",
            mime="application/zip",
            use_container_width=True,
            disabled=lifestyle_zip_count == 0,
        )

        download_col4.download_button(
            "📝 Download Past Hooks",
            data=past_hooks_csv_bytes(saved_gens),
            file_name=f"past_text_hooks_{export_stamp}.csv",
            mime="text/csv",
            use_container_width=True,
        )

        download_col5.download_button(
            "📥 Download JSON",
            data=json.dumps(saved_gens, indent=2, default=str),
            file_name=f"generations_{export_stamp}.json",
            mime="application/json",
            use_container_width=True,
        )

        # Bulk Director push: send every available Lifestyle image that has not
        # already been delivered. Successful items are marked immediately so a
        # later retry only attempts the remaining failures and never duplicates
        # images that were already accepted by Director.
        bulk_director_available = []
        bulk_director_pending = []
        for bulk_index, bulk_result in enumerate(saved_gens):
            if bulk_result.get("style") != "lifestyle_animation":
                continue
            bulk_image_url = (
                bulk_result.get("lifestyle_image_url")
                or (
                    bulk_result.get("url")
                    if str(bulk_result.get("url") or "").lower().split("?")[0].endswith(
                        (".jpg", ".jpeg", ".png", ".webp", ".avif")
                    )
                    else ""
                )
            )
            if not bulk_image_url:
                continue
            bulk_director_available.append((bulk_index, bulk_result, bulk_image_url))
            if not bulk_result.get("director_pushed_at"):
                bulk_director_pending.append((bulk_index, bulk_result, bulk_image_url))

        bulk_summary = st.session_state.pop("bulk_director_summary", None)
        if isinstance(bulk_summary, dict):
            success_count = int(bulk_summary.get("success", 0) or 0)
            failure_count = int(bulk_summary.get("failed", 0) or 0)
            if success_count:
                st.success(f"Sent {success_count} Lifestyle image(s) to Director.")
            if failure_count:
                st.error(f"{failure_count} Lifestyle image(s) could not be sent. Click the bulk button again to retry only those items.")
                failure_messages = bulk_summary.get("messages") or []
                if failure_messages:
                    with st.expander("Director errors", expanded=False):
                        for failure_message in failure_messages:
                            st.caption(f"• {failure_message}")

        bulk_director_label = f"↗️ Send to Director ({len(bulk_director_pending)})"
        bulk_send_to_director = st.button(
            bulk_director_label,
            key="bulk_send_lifestyle_to_director",
            type="primary",
            use_container_width=True,
            disabled=(not bool(director_ingest_key) or not bulk_director_pending),
            help=(
                "Send every available Lifestyle image that has not already been sent into the Momentum Academy Director flow."
                if director_ingest_key
                else "Add DIRECTOR_INGEST_KEY in API connection or Streamlit Secrets first."
            ),
        )

        if not director_ingest_key:
            st.caption("Connect the Momentum Director ingest key above to enable bulk sending.")
        elif not bulk_director_available:
            st.caption("No generated Lifestyle images are available to send yet.")
        elif not bulk_director_pending:
            st.caption(f"All {len(bulk_director_available)} available Lifestyle image(s) have already been sent to Director.")
        else:
            already_sent_count = len(bulk_director_available) - len(bulk_director_pending)
            sent_note = f" {already_sent_count} already-sent image(s) will be skipped." if already_sent_count else ""
            st.caption(
                f"This sends {len(bulk_director_pending)} pending Lifestyle image(s)."
                f"{sent_note} Successful items are marked immediately, so retries only send failures."
            )

        if bulk_send_to_director:
            bulk_progress = st.progress(0, text="Preparing Lifestyle images for Director...")
            bulk_success_count = 0
            bulk_failure_count = 0
            bulk_failure_messages = []
            bulk_total = len(bulk_director_pending)
            bulk_batch_id = f"director_bulk_{export_stamp}"

            for bulk_position, (bulk_index, bulk_result, bulk_image_url) in enumerate(
                bulk_director_pending,
                start=1,
            ):
                bulk_product_name = bulk_result.get("product_name", "Untitled Product")
                bulk_progress.progress(
                    (bulk_position - 1) / max(1, bulk_total),
                    text=f"Sending {bulk_position}/{bulk_total}: {bulk_product_name[:55]}...",
                )

                director_ok, director_message = push_generated_image_to_director(
                    ingest_key=director_ingest_key,
                    ingest_url=director_ingest_url,
                    image_url=bulk_image_url,
                    product_name=bulk_product_name,
                    caption=bulk_result.get("caption") or bulk_result.get("accepted_hook") or "",
                    scene_prompt=(
                        bulk_result.get("lifestyle_prompt")
                        or bulk_result.get("prompt_used")
                        or bulk_result.get("prompt")
                        or ""
                    ),
                    meta={
                        "source_url": bulk_result.get("source_url", ""),
                        "style": bulk_result.get("style", "lifestyle_animation"),
                        "scene_key": bulk_result.get("scene_key"),
                        "custom_scene": bulk_result.get("custom_scene", ""),
                        "product_type": bulk_result.get("product_type"),
                        "appearance_details": bulk_result.get("appearance_details", ""),
                        "image_model": bulk_result.get("image_model", XAI_IMAGE_MODEL),
                        "image_resolution": bulk_result.get("image_resolution", "2k"),
                        "image_aspect_ratio": bulk_result.get("image_aspect_ratio", "9:16"),
                        "creation_id": bulk_result.get("lifestyle_creation_id") or bulk_result.get("creation_id"),
                        "generated_at": bulk_result.get("generated_at", ""),
                        "accepted_hook": bulk_result.get("accepted_hook", ""),
                        "hashtags": bulk_result.get("hashtags", ""),
                        "director_bulk_batch_id": bulk_batch_id,
                    },
                )

                attempt_time = datetime.now().isoformat(timespec="seconds")
                saved_gens[bulk_index]["director_last_attempt_at"] = attempt_time
                saved_gens[bulk_index]["director_ingest_message"] = director_message
                saved_gens[bulk_index]["director_bulk_batch_id"] = bulk_batch_id

                if director_ok:
                    saved_gens[bulk_index]["director_pushed_at"] = attempt_time
                    saved_gens[bulk_index]["director_ingest_status"] = "sent"
                    bulk_success_count += 1
                else:
                    saved_gens[bulk_index]["director_ingest_status"] = "error"
                    bulk_failure_count += 1
                    bulk_failure_messages.append(f"{bulk_product_name}: {director_message}")

                # Save after every item so progress survives a browser refresh or a
                # later request failure during a larger batch.
                save_generations(saved_gens)
                bulk_progress.progress(
                    bulk_position / max(1, bulk_total),
                    text=f"Processed {bulk_position}/{bulk_total} Lifestyle image(s)",
                )
                if bulk_position < bulk_total:
                    time.sleep(0.35)

            st.session_state["bulk_director_summary"] = {
                "success": bulk_success_count,
                "failed": bulk_failure_count,
                "messages": bulk_failure_messages,
            }
            st.rerun()

        st.caption(
            f"The video ZIP contains {zip_video_count} available video(s) plus captions.csv. "
            "Edited text versions are used first; otherwise the original completed video is included."
        )
        if zip_skipped:
            st.caption(f"Skipped {len(zip_skipped)} item(s) that do not have an available finished video yet.")
        if lifestyle_zip_count:
            st.caption(f"The lifestyle image ZIP contains {lifestyle_zip_count} generated lifestyle image(s).")
        if lifestyle_zip_skipped:
            st.caption(f"Skipped {len(lifestyle_zip_skipped)} lifestyle image(s) that are not available yet.")


if __name__ == "__main__":
    main()