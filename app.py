"""
Seedance Video Generator — Streamlit App (v2)
==============================================
Paste TikTok Shop links → pick a style → select the right product photo →
generate videos automatically OR get prompts to generate manually.
"""

import streamlit as st
import anthropic
import csv
import hashlib
import io
import zipfile
import json
import os
import re
import time
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

FONT_FILES = {
    "TikTok Sans": ["TikTokSans.ttf", "/mnt/data/TikTokSans.ttf"],
    "DejaVu Sans Bold": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "Liberation Sans Bold": ["/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"],
    "Arial Bold": ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "C:/Windows/Fonts/arialbd.ttf"],
}

FONT_CANDIDATES = [
    "TikTokSans.ttf",
    "/mnt/data/TikTokSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]

DEFAULT_TEXT_SETTINGS = {
    "font_name": "TikTok Sans",
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
            min-height: 42px;
            border-radius: 14px !important;
            border: 1px solid var(--glass-border) !important;
            background: linear-gradient(145deg, rgba(33,39,53,.96), rgba(20,24,34,.96)) !important;
            color: #eef2f8 !important;
            box-shadow: 0 10px 26px rgba(0,0,0,.24) !important;
            backdrop-filter: blur(16px);
            font-weight: 700 !important;
            transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease, background .16s ease;
        }

        .stButton > button p,
        .stDownloadButton > button p,
        .stButton > button span,
        .stDownloadButton > button span {
            color: #eef2f8 !important;
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover {
            transform: translateY(-1px);
            border-color: var(--glass-border-hover) !important;
            background: linear-gradient(145deg, rgba(43,50,67,.98), rgba(26,31,43,.98)) !important;
            box-shadow: 0 14px 34px rgba(0,0,0,.34) !important;
        }

        .stButton > button[kind="primary"] {
            color: white !important;
            background: linear-gradient(135deg, #247ff0, #7658e8) !important;
            border: 1px solid rgba(255,255,255,.12) !important;
            box-shadow: 0 14px 34px rgba(35, 103, 226, .30) !important;
        }

        .stButton > button[kind="primary"]:hover {
            background: linear-gradient(135deg, #348cff, #8668f8) !important;
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
        "product_name", "product_link", "caption", "hashtags", "sound_tip", "full_caption",
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
) -> tuple[Path | None, str | None]:
    """Apply an overlay to a user-uploaded MP4 using the same renderer as generated videos."""
    if not video_bytes:
        return None, "Upload a video first."
    if not hook.strip():
        return None, "Enter text before applying the overlay."

    ffmpeg_path = get_ffmpeg_executable()
    if not ffmpeg_path:
        return None, "FFmpeg is not installed. Keep `ffmpeg` in packages.txt."

    digest_data = video_bytes[:1048576] + hook.encode("utf-8") + json.dumps(
        settings, sort_keys=True, ensure_ascii=False
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

            command = [
                ffmpeg_path, "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(input_path), "-loop", "1", "-framerate", "30",
                "-i", str(overlay_path),
                "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto:shortest=1[v]",
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
            return final_path, overlay_warning
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
on-screen text hooks for a silent warehouse walk-up deal video.

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

Rules:
- Casual, chaotic, sassy deal-drop/FOMO voice; never polished corporate copy.
- No link in bio and no formal CTA.
- Do not claim an exact price or percentage unless the template already uses broad sale wording.
- The render is silent; this hook is burned in later with FFmpeg.
- Caption: one short warehouse-find line in the same voice.
- Hashtags: 8-12 tags including #tiktokshop #tiktokmademebuyit #costcofinds #warehousedeals plus product/category tags.
- Sound tip: short reminder to add an upbeat trending TikTok sound in-app.

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


STYLE_LABELS = {
    "shoe_video": "👟 Shoe Video (feet-only)",
    "texthook_broll": "📱 Text-Hook B-Roll",
    "warehouse": "🏬 Warehouse",
    "pool": "🏝️ Pool",
}


def resolved_style_duration(style: str, selected_duration: int = 15) -> int:
    if style == "warehouse":
        return 5
    if style in ("texthook_broll", "pool"):
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
    """Read title-like values from meta/link tags regardless of attribute order."""
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
        content = (attrs.get("content") or "").strip()
        if not content:
            continue
        if marker in {"og:title", "twitter:title", "title", "product:name", "product_title"}:
            names.append(content)
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


def _best_product_name(candidates):
    """Choose the most product-like title from scraped candidates."""
    cleaned = []
    for value in candidates:
        if not value:
            continue
        value = re.sub(r"\s+", " ", html_unescape(str(value))).strip()
        value = re.sub(r'\s*[|\-–—]\s*(TikTok|Shop|Amazon|Walmart).*$', '', value, flags=re.IGNORECASE)
        if value and value.lower() not in {"unknown product", "tiktok shop", "tiktok", "shop"}:
            cleaned.append(value)
    if not cleaned:
        return ""
    # Prefer descriptive titles with several words, without choosing huge page blobs.
    cleaned = list(dict.fromkeys(cleaned))
    cleaned.sort(key=lambda x: (2 <= len(x.split()) <= 14, len(x.split()), len(x)), reverse=True)
    return cleaned[0][:100]


def scrape_product(url: str) -> dict | None:
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
        if not name or name == "Unknown Product":
            # Short share links often redirect to a full PDP URL containing the product slug.
            fallback_urls = [resp.url] + meta_url_candidates + [url]
            for fallback_url in fallback_urls:
                candidate_name = _name_from_url(fallback_url)
                if candidate_name and candidate_name != "Unknown Product":
                    name = candidate_name
                    break
        if not name:
            name = "Unknown Product"

        return {
            "name": name[:100],
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
    """Generate five style-matched hook options for a product. Cheap/fast — no MCP."""
    system = WAREHOUSE_HOOKS_SYSTEM if style == "warehouse" else TEXTHOOK_HOOKS_SYSTEM
    task = (
        f"Write 5 warehouse deal-drop text hooks for this product: {product_name}"
        if style == "warehouse"
        else f"Write 5 text hook options for this product: {product_name}"
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
            <p>Turn TikTok Shop products into Shoe, B-Roll, or Warehouse walk-up videos, then refine the text styling with reusable presets and Apple-style emoji overlays.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    # ── Always-visible video setup ──
    api_key_from_secrets = get_secret("ANTHROPIC_API_KEY")
    token_from_secrets = get_secret("MAGNIFIC_AUTH_TOKEN")

    if "runtime_anthropic_api_key" not in st.session_state:
        st.session_state["runtime_anthropic_api_key"] = api_key_from_secrets
    if "runtime_magnific_token" not in st.session_state:
        st.session_state["runtime_magnific_token"] = token_from_secrets

    with st.container(border=True):
        st.markdown("### Video setup")
        st.caption("Choose the format first. API controls stay below in the same dark workspace—no hidden sidebar or white popover.")

        style = st.radio(
            "Video style",
            options=["shoe_video", "texthook_broll", "warehouse", "pool"],
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
        else:
            duration = 8
            voice_script = None
            st.info("Text-Hook B-Roll is fixed at 8 seconds and silent. The chosen hook is added afterward with FFmpeg.")

        api_key = st.session_state.get("runtime_anthropic_api_key", "")
        magnific_token = st.session_state.get("runtime_magnific_token", "")
        status_col_1, status_col_2, status_col_3 = st.columns(3)
        if api_key:
            status_col_1.success("Anthropic connected")
        else:
            status_col_1.warning("Anthropic key needed")
        if magnific_token:
            status_col_2.success("Magnific connected")
        else:
            status_col_2.info("Prompt-only mode")
        status_col_3.info(f"{STYLE_LABELS[style]} · {resolved_style_duration(style, duration)}s")

        with st.expander("API connection", expanded=not bool(api_key and magnific_token)):
            if api_key_from_secrets:
                st.success("Anthropic API key loaded from Streamlit secrets.")
            else:
                st.session_state["runtime_anthropic_api_key"] = st.text_input(
                    "Anthropic API Key",
                    type="password",
                    value=st.session_state.get("runtime_anthropic_api_key", ""),
                    key="runtime_anthropic_api_key_input",
                )

            st.session_state["runtime_magnific_token"] = st.text_input(
                "Magnific token",
                type="password",
                value=st.session_state.get("runtime_magnific_token", ""),
                key="runtime_magnific_token_input",
                help="Paste a refreshed token here whenever Magnific authentication expires.",
            )
            magnific_token = st.session_state.get("runtime_magnific_token", "")
            api_key = st.session_state.get("runtime_anthropic_api_key", "")

            st.markdown("**How to refresh the Magnific token**")
            st.markdown("""
1. Run `npx @modelcontextprotocol/inspector` on a computer with Node.js.
2. Set **Transport Type** to `Streamable HTTP`.
3. Set the URL to `https://mcp.magnific.com`.
4. Connect, open Auth Settings, and complete the Quick OAuth Flow.
5. Copy the `access_token` and paste it above.
            """)

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
        selections = {}  # product_index → selected image URL list
        edited_names = {}

        for idx, product in enumerate(scraped_products):
            st.markdown("---")

            detected_name = product.get("name") or "Unknown Product"
            product_fingerprint = hashlib.sha1(
                product.get("source_url", str(idx)).encode("utf-8")
            ).hexdigest()[:10]
            product_name_key = f"product_name_{idx}_{product_fingerprint}"
            if product_name_key not in st.session_state:
                st.session_state[product_name_key] = "" if detected_name == "Unknown Product" else detected_name
            edited_name = st.text_input(
                "Product name",
                placeholder="Type the product name if TikTok did not provide it",
                key=product_name_key,
                help="The app fills this automatically when TikTok exposes a title. You can still correct it here.",
            ).strip()
            if not edited_name:
                edited_name = detected_name
            edited_names[idx] = edited_name
            product["name"] = edited_name

            if edited_name == "Unknown Product":
                st.warning("TikTok did not expose a product title. Enter the product name above before generating hooks.")

            st.caption(f"Source: {product['source_url'][:100]}...")

            listing_images = product.get("listing_images") or product.get("images", [])
            review_images = product.get("review_images") or []

            listing_tab, review_tab = st.tabs([
                f"Listing photos ({len(listing_images)})",
                f"Review/customer photos ({len(review_images)})",
            ])

            listing_state_key = f"listing_refs_{idx}"
            review_state_key = f"review_refs_{idx}"
            primary_state_key = f"primary_reference_url_{idx}"

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
                                    key=f"listing_toggle_{idx}_{image_index}",
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
                                    key=f"listing_primary_{idx}_{image_index}",
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
                                    key=f"review_toggle_{idx}_{image_index}",
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
                                    key=f"review_primary_{idx}_{image_index}",
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
                    key=f"manual_review_urls_{idx}",
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


        # ════════════════════════════════════════════════════════════════
        #  STEP 3 — GENERATE OR GET PROMPTS
        # ════════════════════════════════════════════════════════════════
        st.divider()
        st.subheader("③ Generate")

        has_token = bool(magnific_token)

        # ── Build final product list with selected images ──
        final_products = []
        for idx, product in enumerate(scraped_products):
            selected_refs = selections.get(idx) or [product["images"][0]]
            final_products.append({
                "name": product["name"],
                "image_url": selected_refs[0],
                "image_urls": selected_refs,
                "source_url": product["source_url"],
            })

        # ── Pick hooks FIRST, then generate ──
        hooks_ready = False

        # Hook voice changes by style. Clear old options when the selected style changes
        # so Warehouse hooks can never be mixed with B-roll/Shoe hooks.
        if st.session_state.get("product_hooks_style") != style:
            st.session_state["product_hooks"] = {}
            st.session_state["product_hooks_style"] = style

        # All three styles use generated on-screen text hooks.
        # The selected hook is stored now and burned onto the finished video later with FFmpeg.
        if style in ("texthook_broll", "shoe_video", "warehouse", "pool"):
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
                    st.session_state["product_hooks"][i] = {
                        "product_name": product["name"],
                        "hook_options": hook_result.get("hook_options", []),
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
                auto_btn = col1.button("🎬 Step 2 — Auto-Generate Videos",
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
            if style in ("texthook_broll", "shoe_video", "warehouse", "pool"):
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
            entry["image_urls"] = fp.get("image_urls", [fp["image_url"]])
            entry["source_url"] = fp["source_url"]
            entry["style"] = style
            entry["duration"] = resolved_style_duration(style, duration)
            entry["voice_script"] = voice_script or ""
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

            progress.progress(i / len(final_products),
                              text=f"Processing {i+1}/{len(final_products)}: {product['name'][:30]}...")

            # Step A: Write the prompt (cheap, no MCP)
            selected_hook = None
            hook_data_for_product = None
            if style in ("texthook_broll", "shoe_video", "warehouse", "pool"):
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
                    image_urls=product.get("image_urls"),
                    prompt=prompt_text,
                    duration=resolved_style_duration(style, duration),
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
                    st.warning("🔄 **Token expired.** Paste a fresh token in the API connection section and re-run.")
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
                gen_result["sound_tip"] = hook_data_for_product.get("sound_tip")
                if selected_hook:
                    st.info(f"📝 Hook saved for the text editor: {selected_hook}")
                if hook_data_for_product.get("caption"):
                    st.caption(f"Caption: {hook_data_for_product['caption']}")
                if hook_data_for_product.get("hashtags"):
                    st.caption(f"Hashtags: {hook_data_for_product['hashtags']}")
                if hook_data_for_product.get("sound_tip"):
                    st.caption(f"Sound tip: {hook_data_for_product['sound_tip']}")

            if i < len(final_products) - 1:
                time.sleep(5)

        progress.progress(1.0, text="Done!")

        # Save each result to persistent file
        for r, fp in zip(results, final_products):
            r["image_url"] = fp["image_url"]
            r["image_urls"] = fp.get("image_urls", [fp["image_url"]])
            r["source_url"] = fp["source_url"]
            r["style"] = style
            r["duration"] = resolved_style_duration(style, duration)
            r["voice_script"] = voice_script or ""
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
            upload_presets, _upload_preset_data = all_text_presets()
            upload_default_settings, upload_default_name = default_text_settings_from_presets()
            upload_preset_name = st.selectbox(
                "Text preset",
                options=list(upload_presets.keys()),
                index=list(upload_presets.keys()).index(upload_default_name),
                key="upload_text_preset",
            )
            upload_base = normalize_text_settings(upload_presets[upload_preset_name])
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

            if st.button("🎨 Add / Update Text", type="primary", use_container_width=True, key="process_uploaded_video"):
                with st.spinner("Applying text with FFmpeg..."):
                    upload_output, upload_warning = apply_text_to_uploaded_video(
                        video_bytes=uploaded_bytes,
                        original_filename=uploaded_video.name,
                        hook=upload_hook.strip(),
                        settings=upload_settings,
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
                if refresh_creation_id and refresh_status not in ("completed", "error"):
                    with st.spinner(f"Checking {refresh_result.get('product_name', 'video')}..."):
                        status_result = check_creation_status(
                            api_key, magnific_token, refresh_creation_id
                        )
                    saved_gens[refresh_index]["status"] = status_result.get("status", refresh_status)
                    if status_result.get("url"):
                        saved_gens[refresh_index]["url"] = status_result["url"]
                    if status_result.get("preview_url"):
                        saved_gens[refresh_index]["preview_url"] = status_result["preview_url"]
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
                    if creation_id:
                        st.caption(f"Creation ID: `{creation_id}`")

                with header_actions:
                    if creation_id and status not in ("completed", "error") and magnific_token and api_key:
                        if st.button("🔄 Check status", key=f"chk_{i}", use_container_width=True):
                            with st.spinner("Checking..."):
                                status_result = check_creation_status(
                                    api_key, magnific_token, creation_id
                                )
                            saved_gens[i]["status"] = status_result.get("status", status)
                            if status_result.get("url"):
                                saved_gens[i]["url"] = status_result["url"]
                            if status_result.get("preview_url"):
                                saved_gens[i]["preview_url"] = status_result["preview_url"]
                            save_generations(saved_gens)
                            st.rerun()

                    current_prompt = result.get("prompt_used") or result.get("prompt")
                    if current_prompt and api_key:
                        if st.button("🪄 Regenerate prompt", key=f"regen_prompt_{i}", use_container_width=True):
                            stored_style = result.get("style") or "texthook_broll"
                            stored_duration = int(result.get("duration") or resolved_style_duration(stored_style, 15))
                            with st.spinner("Writing a new prompt..."):
                                regenerated_prompt = write_prompt(
                                    api_key=api_key,
                                    product_name=product_name,
                                    style=stored_style,
                                    duration=stored_duration,
                                    voice_script=result.get("voice_script") or None,
                                    selected_hook=result.get("accepted_hook") or None,
                                )
                            if regenerated_prompt.get("prompt"):
                                result["prompt"] = regenerated_prompt["prompt"]
                                result["prompt_used"] = regenerated_prompt["prompt"]
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
                            stored_style = result.get("style") or "texthook_broll"
                            stored_duration = int(result.get("duration") or resolved_style_duration(stored_style, 15))
                            with st.spinner("Sending the current prompt and references to Magnific..."):
                                new_result = generate_video(
                                    api_key=api_key,
                                    magnific_token=magnific_token,
                                    image_url=result["image_url"],
                                    image_urls=result.get("image_urls", [result["image_url"]]),
                                    prompt=current_prompt,
                                    duration=stored_duration,
                                )
                            new_result["product_name"] = product_name
                            new_result["prompt_used"] = current_prompt
                            new_result["prompt"] = current_prompt
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
                            new_result["generated_at"] = datetime.now().isoformat()
                            add_generation(new_result)
                            st.rerun()

                video_url = result.get("url") or result.get("preview_url")
                processed_bytes = read_local_video(result.get("processed_path"))
                original_bytes = None
                safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", product_name)[:40]

                if video_url and status == "completed":
                    original_preview_col, edited_preview_col = st.columns(2, gap="large")

                    with original_preview_col:
                        st.markdown("#### Original video")
                        try:
                            st.video(video_url)
                        except Exception:
                            st.markdown(f"🎬 [Watch original video]({video_url})")
                        original_bytes = fetch_video_bytes(video_url)
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
                elif result.get("image_url"):
                    preview_image_col, preview_message_col = st.columns([1, 1.5])
                    with preview_image_col:
                        try:
                            st.image(result["image_url"], use_container_width=True)
                        except Exception:
                            pass
                    with preview_message_col:
                        st.info("This generation is not finished yet. Check its status when Magnific is connected.")

                prompt_text_field = result.get("prompt_used") or result.get("prompt")
                if prompt_text_field:
                    with st.expander("📋 Generation prompt", expanded=False):
                        st.code(prompt_text_field, language=None)
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
                            "The original stays untouched. The updated version appears beside it in the Text version panel."
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

                        st.markdown('<span class="preset-pill">TEXT STYLE PRESETS</span>', unsafe_allow_html=True)
                        preset_col, load_col, default_col = st.columns([2.5, 1, 1.35])
                        with preset_col:
                            selected_preset = st.selectbox(
                                "Preset",
                                options=list(presets.keys()),
                                index=list(presets.keys()).index(active_preset_name),
                                key=f"preset_select_{i}",
                            )
                        with load_col:
                            st.write("")
                            if st.button("Load", key=f"load_preset_{i}", use_container_width=True):
                                set_editor_widget_values(i, presets[selected_preset])
                                saved_gens[i]["text_preset_name"] = selected_preset
                                save_generations(saved_gens)
                                st.rerun()
                        with default_col:
                            st.write("")
                            if st.button(
                                "Set default",
                                key=f"default_preset_{i}",
                                use_container_width=True,
                            ):
                                preset_data["default"] = selected_preset
                                save_text_presets_data(preset_data)
                                st.success(f"{selected_preset} is now your default preset.")

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

                        st.markdown('<span class="preset-pill">SAVE THIS STYLE</span>', unsafe_allow_html=True)
                        preset_name_col, preset_save_col, preset_delete_col = st.columns([2.2, 1, 1])
                        with preset_name_col:
                            custom_preset_name = st.text_input(
                                "Preset name",
                                placeholder="My favorite style",
                                key=f"custom_preset_name_{i}",
                                label_visibility="collapsed",
                            )
                        with preset_save_col:
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
                                    st.error("Built-in presets cannot be overwritten.")
                                else:
                                    preset_data.setdefault("presets", {})[cleaned_name] = editor_settings
                                    save_text_presets_data(preset_data)
                                    saved_gens[i]["text_preset_name"] = cleaned_name
                                    save_generations(saved_gens)
                                    st.success(f"Saved preset: {cleaned_name}")
                                    st.rerun()
                        with preset_delete_col:
                            can_delete_preset = selected_preset not in BUILT_IN_TEXT_PRESETS
                            if st.button(
                                "Delete preset",
                                key=f"delete_preset_{i}",
                                disabled=not can_delete_preset,
                                use_container_width=True,
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
                            f"Apple-style emoji PNGs found: {available_assets}/{len(EMOJI_ASSET_MAP)}."
                        )

                        apply_col, remove_col = st.columns([1.5, 1])
                        apply_label = "🎨 Update text version" if has_processed_version else "🎨 Apply text"

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

        download_col1, download_col2, download_col3, download_col4 = st.columns(4)
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

        download_col3.download_button(
            "📝 Download Past Hooks",
            data=past_hooks_csv_bytes(saved_gens),
            file_name=f"past_text_hooks_{export_stamp}.csv",
            mime="text/csv",
            use_container_width=True,
        )

        download_col4.download_button(
            "📥 Download JSON",
            data=json.dumps(saved_gens, indent=2, default=str),
            file_name=f"generations_{export_stamp}.json",
            mime="application/json",
            use_container_width=True,
        )

        st.caption(
            f"The ZIP contains {zip_video_count} available video(s) plus captions.csv. "
            "Edited text versions are used first; otherwise the original completed video is included."
        )
        if zip_skipped:
            st.caption(f"Skipped {len(zip_skipped)} item(s) that do not have an available finished video yet.")


if __name__ == "__main__":
    main()