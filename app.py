"""
Seedance Video Generator — Streamlit App (v2)
==============================================
Paste TikTok Shop links → pick a style → select the right product photo →
generate videos automatically OR get prompts to generate manually.
"""

import streamlit as st
import anthropic
import json
import os
import re
import time
import requests
from datetime import datetime
from urllib.parse import urlparse
from html import unescape as html_unescape
from pathlib import Path


# ── Page config ─────────────────────────────────────────────────────
st.set_page_config(
    page_title="Seedance Video Generator",
    page_icon="🎬",
    layout="wide",
)

# ── Persistent storage ─────────────────────────────────────────────
SAVE_FILE = Path("generations.json")


def load_generations() -> list[dict]:
    """Load saved generations from disk."""
    if SAVE_FILE.exists():
        try:
            with open(SAVE_FILE) as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_generations(generations: list[dict]):
    """Save generations to disk."""
    try:
        with open(SAVE_FILE, "w") as f:
            json.dump(generations, f, indent=2, default=str)
    except IOError:
        pass


def add_generation(result: dict):
    """Append a single generation result to the saved file."""
    gens = load_generations()
    gens.insert(0, result)  # Newest first
    # Keep last 200 entries
    save_generations(gens[:200])


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_video_bytes(video_url: str) -> bytes | None:
    """Download video bytes for the download button. Cached so repeated
    reruns (e.g. clicking other buttons on the page) don't re-fetch."""
    try:
        resp = requests.get(video_url, timeout=60)
        resp.raise_for_status()
        return resp.content
    except Exception:
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
Seedance 2.0 video prompt that BURNS IN on-screen text as part of the AI render.

The selected text hook to burn in: {selected_hook}

HARD RULES:
- SILENT video — NO audio, NO voiceover
- The text hook MUST appear as large bold white text with a subtle dark drop shadow,
  centered in the upper third of the frame. The text appears at 00:00 and stays on
  screen for the entire video. It looks like a native TikTok text overlay.
- No face, no person, no character — only a hand in the reveal shot
- Two acts: random b-roll (~3s) → hard cut to product reveal (~5s)
- ~8 seconds total, 9:16 vertical
- Under 1,900 characters

CRITICAL — B-ROLL RULES:
The opening b-roll must be a RANDOM mundane real-life scene. It must NOT relate to the
product in any way. Pick from scenes like:
- Person's feet walking on a sidewalk
- Cars driving on a highway at golden hour
- Coffee being poured into a mug
- Rain droplets on a window
- Hand pushing a grocery cart down an aisle
- Laundry tumbling in a dryer
- Dog trotting ahead on a leash (shot from behind)
- Crosswalk signal changing, crowd crossing
- Leaves blowing across a parking lot
- Steam rising off pavement after rain
Pick ONE at random. The more unrelated to the product, the better — that's the style.

Prompt template:
9:16 vertical, TikTok UGC aesthetic, silent, no audio, no voiceover. Handheld phone-camera
feel with natural micro-shake. Warm bright daylight, slightly saturated. No face, no person,
no character — only a hand in the second half.

Large bold white text with subtle dark drop shadow centered in the upper third of the frame
reads: "{selected_hook}" — the text appears immediately and stays on screen the entire video.

[00:00-00:03] Establishing b-roll: first-person POV [RANDOM MUNDANE SCENE — NOT related to
the product]. Casual handheld drift. No product on screen. The white text hook is visible
in the upper third.

[00:03-00:08] Hard cut to outdoors on a surface. A single medium-brown-skinned hand holds up
[PRODUCT + visual detail] toward camera, slowly rotating and tilting so the detail catches
warm light. Hand fills lower half. Soft blurred background. The white text hook remains
visible in the upper third.

No face. No person above the wrist.

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
        system = TEXTHOOK_PROMPT_SYSTEM.format(selected_hook=selected_hook or "")
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
    # ── Header ──
    st.title("🎬 Seedance Video Generator")
    st.caption("Paste product links → pick photos → generate videos (or get prompts)")

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
            st.caption("Always 8s, silent. You'll get the text hook to burn in via CapCut.")

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

                # Show which hook was burned in
                if result.get("accepted_hook"):
                    st.success(f"🔥 Burned-in hook: {result['accepted_hook']}")
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

            # Show which hook was burned into the video
            if hook_data_for_product:
                gen_result["accepted_hook"] = selected_hook
                gen_result["hook_options"] = hook_data_for_product.get("hook_options", [])
                gen_result["caption"] = hook_data_for_product.get("caption")
                gen_result["hashtags"] = hook_data_for_product.get("hashtags")
                if selected_hook:
                    st.info(f"🔥 Burned-in hook: {selected_hook}")
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
        st.caption(f"{len(saved_gens)} saved — survives page refreshes. Check status, watch videos, or regenerate.")

        # Bulk actions
        action_col1, action_col2, action_col3 = st.columns(3)
        if magnific_token and api_key:
            check_all = action_col1.button("🔄 Check All Statuses", use_container_width=True)
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

                # Show video if completed and we have a URL — kept small so
                # multiple videos fit comfortably on the page
                video_url = result.get("url") or result.get("preview_url")
                if video_url and status == "completed":
                    video_col, _spacer = st.columns([1, 2])
                    with video_col:
                        try:
                            st.video(video_url)
                        except Exception:
                            st.markdown(f"🎬 [Watch video]({video_url})")

                        video_bytes = fetch_video_bytes(video_url)
                        if video_bytes:
                            safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', product_name)[:40]
                            st.download_button(
                                "⬇️ Download video",
                                data=video_bytes,
                                file_name=f"{safe_name}_{creation_id or i}.mp4",
                                mime="video/mp4",
                                key=f"dl_{i}",
                                use_container_width=True,
                            )
                        else:
                            st.caption("⚠️ Couldn't fetch video for download — use the player above or the link.")

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

            # Show which hook was burned into this video
            if result.get("accepted_hook"):
                with st.expander(f"📝 Text Hook — {product_name}", expanded=False):
                    st.success(f"🔥 Burned-in hook: {result['accepted_hook']}")
                    if result.get("hook_options"):
                        st.caption("Other options that were available:")
                        for h in result["hook_options"]:
                            if h != result["accepted_hook"]:
                                st.caption(f"  • {h}")
                    if result.get("caption"):
                        st.caption(f"Caption: {result['caption']}")
                    if result.get("hashtags"):
                        st.caption(f"Hashtags: {result['hashtags']}")
            elif result.get("hook_options"):
                # Legacy entries from before hook-first flow
                with st.expander(f"📝 Hook options — {product_name}"):
                    for h in result["hook_options"]:
                        st.code(h, language=None)
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
