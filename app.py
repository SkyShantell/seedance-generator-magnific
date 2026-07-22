"""
Seedance Video Generator — Streamlit App
=========================================
Paste TikTok Shop links → pick a video style → hit Generate.
Built for VAs who don't touch the terminal.
"""

import streamlit as st
import anthropic
import base64
import json
import os
import re
import time
import requests
from datetime import datetime
from urllib.parse import urlparse
from html import unescape as html_unescape


# ── Page config ─────────────────────────────────────────────────────
st.set_page_config(
    page_title="Seedance Video Generator",
    page_icon="🎬",
    layout="wide",
)

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
#  SYSTEM PROMPTS — one per video style
# ═══════════════════════════════════════════════════════════════════

SHOE_VIDEO_PROMPT = """You are a TikTok Shop affiliate content producer specializing in
shoe/footwear product videos. You generate Seedance 2.0 video prompts and use
Magnific tools to create the videos.

## Your workflow:

1. ANALYZE the product — identify: shoe type, color, pattern, material, sole
   type, standout features (buckles, bows, straps, cushioning, etc.)

2. WRITE a Seedance 2.0 prompt following these HARD RULES:
   - 9:16 vertical, TikTok UGC aesthetic
   - NO person above the ankle — EVER
   - NO on-screen text, captions, subtitles, overlays, signs, logos
   - Max duration as specified
   - Feet-and-shoes ONLY — the shoe IS the star
   - Warm natural lighting, phone-camera handheld feel
   - 3 timecoded shots (looking-down POV → low side-angle → back to overhead)

3. UPLOAD the product image to Magnific using creations_upload_image with the
   provided URL

4. GENERATE the video using video_generate with:
   - The Seedance prompt you wrote
   - The uploaded creation as a reference
   - Model slug: bytedance-seedance-fast-2.0
   - Aspect ratio: 9:16, resolution: 720p
   - Duration as specified

## Shot structure:
[00:00-00:05] Looking-down POV. Feet in [product] on [surface]. [Opening movement].
[00:05-00:10] Low side-angle. Camera tilts to reveal [feature]. Foot lifts, sets down.
[00:10-00:15] Overhead POV. [Natural movement]. [Product detail] catches warm light.

## Surface matching:
- Sandals/flip-flops → light hardwood, tile, poolside concrete
- Sneakers → pavement, gym floor, clean concrete
- Boots → wood floor, outdoor path, autumn leaves
- Heels → marble, polished tile
- Slippers → carpet, rug, cozy indoor floor

{voiceover_instruction}

IMPORTANT: Return ONLY valid JSON (no markdown, no backticks, no extra text):
{{"product_name": "...", "prompt_used": "the full seedance prompt", "creation_id": "the magnific creation identifier for the video", "status": "queued", "error": null}}
"""

TEXTHOOK_BROLL_PROMPT = """You are a TikTok Shop affiliate content producer. You generate
"text-hook + vibey b-roll → product reveal" style videos using Seedance 2.0 via Magnific.

## Style rules:
This is a SILENT video — NO audio, NO voiceover. The "script" is a written text hook
the user burns in later via CapCut/TikTok. The AI render must contain ZERO on-screen text.

## Structure (~8 seconds):
Two acts:
1. VIBEY B-ROLL (00:00-00:03) — mundane real-life establishing shot (sunny street, park,
   sky). Has NOTHING to do with the product. Sets a relatable "my real life" mood.
2. PRODUCT REVEAL (00:03-00:08) — hard cut. A single hand holds the product up outdoors,
   slowly rotating/tilting so it catches warm light. Soft blurred background.

## Hard rules:
- SILENT. No audio, no voiceover, no Seedance audio generation
- Zero rendered on-screen text — no captions, subtitles, overlays, signs, logos
- No face, no person, no character — only a hand appears, and ONLY in the reveal
- No arm above the wrist
- ~8 seconds, 9:16 vertical
- Under 1,900 characters for the prompt

## Prompt template:
9:16 vertical, TikTok UGC aesthetic, silent, no audio, no voiceover. Handheld one-hand
phone-camera feel with natural micro-shake. Warm bright natural daylight, slightly
saturated. No face, no person, no character — only a hand appears in the second half.

[00:00-00:03] Establishing b-roll: first-person POV [SCENE]. Mundane real-life vibe,
slow handheld drift. No product on screen.

[00:03-00:08] Hard cut to outdoors on [SURFACE]. A single hand holds up [PRODUCT +
visual detail] toward the camera, slowly rotating and tilting it so [detail] catches
warm light. Hand fills lower half. Soft blurred background.

No face. No person above the wrist. No text, captions, subtitles, overlays, logos, or
written words of any kind anywhere in the frame.

## Text hook (write this for the user):
Write a text hook using the "broke-flex" formula:
- Gen-z texting voice: ur, bc, &, lowercase drift, no period
- Deadpan, self-deprecating money humor. Relatable, not salesy
- Exactly one 😭 (or 😩/💀) at the end. No emoji spam
- No "link in bio", no CTA. ~14-22 words
- Also write 1-2 alternate hooks

## Your workflow:
1. ANALYZE the product from the name and image URL
2. WRITE the text hook + 2 alternates
3. WRITE the Seedance prompt
4. UPLOAD the image to Magnific using creations_upload_image
5. GENERATE the video using video_generate with model slug bytedance-seedance-fast-2.0,
   aspect ratio 9:16, resolution 720p, duration 8
6. Return JSON

IMPORTANT: Return ONLY valid JSON (no markdown, no backticks):
{{"product_name": "...", "prompt_used": "the full seedance prompt", "text_hook": "the main hook", "alt_hooks": ["alt1", "alt2"], "caption": "tiktok caption", "hashtags": "#tag1 #tag2...", "creation_id": "magnific creation id", "status": "queued", "error": null}}
"""

VOICEOVER_SILENT = "## Audio:\nNO voiceover, NO spoken dialogue. Ambient sound only."
VOICEOVER_WITH_SCRIPT = '## Voiceover:\nInclude this voiceover (warm excited woman, casual and friendly):\n"{script}"'


# ═══════════════════════════════════════════════════════════════════
#  SCRAPER
# ═══════════════════════════════════════════════════════════════════

def _name_from_url(url: str) -> str:
    """Extract a readable product name from a URL slug."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    parts = path.split("/")
    best = ""
    for part in parts:
        if len(part) < 5 or part.isdigit() or part.lower() in ("us", "pdp", "dp", "ip", "product"):
            continue
        if len(part) > len(best):
            best = part
    if best:
        name = best.replace("-", " ").replace("_", " ")
        words = name.split()
        if len(words) > 10:
            words = words[:10]
        return " ".join(words).title()
    return "Unknown Product"


def _find_images_in_dict(obj, depth=0, max_depth=8) -> list[str]:
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
    """Scrape a product page for images and name."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        html = resp.text

        # Extract og:image
        img_match = re.search(
            r'<meta\s+(?:property|name)=["\']og:image["\']\s+content=["\']([^"\']+)["\']',
            html, re.IGNORECASE
        )
        if not img_match:
            img_match = re.search(
                r'content=["\']([^"\']+)["\']\s+(?:property|name)=["\']og:image["\']',
                html, re.IGNORECASE
            )

        # Extract og:title
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

        # CDN image URLs in raw HTML
        cdn_imgs = re.findall(
            r'(https?://[^"\'\s]+(?:\.jpg|\.jpeg|\.png|\.webp)(?:\?[^"\'\s]*)?)',
            html
        )
        for ci in cdn_imgs:
            if any(kw in ci.lower() for kw in ['product', 'pdp', 'origin', 'large', '800', '1000', '1200']):
                images.append(ci)

        if not images:
            # Try Playwright fallback
            return _scrape_with_playwright(url)

        # Deduplicate
        seen = set()
        unique_images = []
        for img in images:
            cleaned = html_unescape(img)
            if cleaned not in seen:
                seen.add(cleaned)
                unique_images.append(cleaned)

        name = title_match.group(1).strip() if title_match else ""
        name = re.sub(r'\s*[|\-–—]\s*(TikTok|Shop|Amazon|Walmart).*$', '', name, flags=re.IGNORECASE)
        if not name or name == "Unknown Product":
            name = _name_from_url(url)

        return {
            "name": name[:100],
            "images": unique_images[:5],
            "source_url": url,
        }

    except Exception as e:
        # Try Playwright as fallback
        return _scrape_with_playwright(url)


def _scrape_with_playwright(url: str) -> dict | None:
    """Fallback scraper using headless browser."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=HEADERS["User-Agent"])
            page = context.new_page()

            def route_handler(route):
                if route.request.resource_type in ["font", "stylesheet", "media"]:
                    route.abort()
                else:
                    route.fallback()
            page.route("**/*", route_handler)

            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)

            images = []
            name = ""

            og_img = page.query_selector('meta[property="og:image"]')
            if og_img:
                img_url = og_img.get_attribute("content")
                if img_url:
                    images.append(img_url)

            og_title = page.query_selector('meta[property="og:title"]')
            if og_title:
                name = og_title.get_attribute("content") or ""
            if not name:
                name = page.title() or ""

            # Large visible images
            all_imgs = page.query_selector_all("img")
            for img in all_imgs:
                src = img.get_attribute("src")
                if not src or not src.startswith("http"):
                    continue
                try:
                    box = img.bounding_box()
                    if box and box["width"] > 200 and box["height"] > 200:
                        images.append(src)
                except Exception:
                    pass

            browser.close()

            if not images:
                return None

            seen = set()
            unique = []
            for img in images:
                cleaned = html_unescape(img)
                if cleaned not in seen:
                    seen.add(cleaned)
                    unique.append(cleaned)

            name = re.sub(r'\s*[|\-–—]\s*(TikTok|Shop|Amazon).*$', '', name, flags=re.IGNORECASE).strip()
            if not name:
                name = _name_from_url(url)

            return {"name": name[:100], "images": unique[:5], "source_url": url}

    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════
#  VIDEO GENERATOR
# ═══════════════════════════════════════════════════════════════════

def generate_video(
    api_key: str,
    magnific_token: str,
    product: dict,
    style: str,
    duration: int,
    voice_script: str | None = None,
) -> dict:
    """Call Anthropic API + Magnific MCP to generate a Seedance video."""

    # Pick system prompt based on style
    if style == "shoe_video":
        vo_block = VOICEOVER_WITH_SCRIPT.format(script=voice_script) if voice_script else VOICEOVER_SILENT
        system = SHOE_VIDEO_PROMPT.format(voiceover_instruction=vo_block)
        vid_duration = duration
    else:  # texthook_broll
        system = TEXTHOOK_BROLL_PROMPT
        vid_duration = 8  # Always 8 for this style

    content = [{
        "type": "text",
        "text": (
            f"Generate a {vid_duration}-second Seedance 2.0 Fast video.\n"
            f"Product name: {product['name']}\n"
            f"Product image URL: {product['url']}\n\n"
            f"Steps:\n"
            f"1. Upload the image to Magnific using creations_upload_image with the URL\n"
            f"2. Write the prompt\n"
            f"3. Call video_generate with the creation identifier, your prompt, "
            f"model slug bytedance-seedance-fast-2.0, aspect ratio 9:16, "
            f"resolution 720p, duration {vid_duration}\n"
            f"4. Return JSON"
        ),
    }]

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
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": content}],
            mcp_servers=mcp_servers,
            tools=[{"type": "mcp_toolset", "mcp_server_name": MAGNIFIC_MCP_NAME}],
            betas=[MCP_BETA],
        )
        return _parse_response(response, product, style)

    except Exception as e:
        return {
            "product_name": product["name"],
            "source_url": product.get("source_url", ""),
            "status": "error",
            "error": str(e),
            "creation_id": None,
            "style": style,
        }


def _parse_response(response, product: dict, style: str) -> dict:
    """Extract results from the API response."""
    result = {
        "product_name": product["name"],
        "source_url": product.get("source_url", ""),
        "image_url": product.get("url", ""),
        "status": "unknown",
        "error": None,
        "creation_id": None,
        "prompt_used": None,
        "text_hook": None,
        "alt_hooks": None,
        "caption": None,
        "hashtags": None,
        "style": style,
    }

    text_parts = []
    tool_results = []

    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "mcp_tool_result":
            if hasattr(block, "content") and block.content:
                for sub in block.content:
                    if hasattr(sub, "text"):
                        tool_results.append(sub.text)

    full_text = "\n".join(text_parts)
    try:
        cleaned = re.sub(r'```json\s*', '', full_text)
        cleaned = re.sub(r'```\s*', '', cleaned)
        json_start = cleaned.find("{")
        json_end = cleaned.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            parsed = json.loads(cleaned[json_start:json_end])
            result.update({k: v for k, v in parsed.items() if v is not None})
    except json.JSONDecodeError:
        pass

    for tr in tool_results:
        try:
            tr_data = json.loads(tr)
            if isinstance(tr_data, dict):
                if "creations" in tr_data:
                    for c in tr_data["creations"]:
                        if "identifier" in c:
                            result["creation_id"] = c["identifier"]
                            result["status"] = c.get("status", "queued")
                elif "identifier" in tr_data:
                    result["creation_id"] = tr_data["identifier"]
                    result["status"] = tr_data.get("status", "queued")
        except (json.JSONDecodeError, TypeError):
            pass

    return result


# ═══════════════════════════════════════════════════════════════════
#  STREAMLIT UI
# ═══════════════════════════════════════════════════════════════════

def main():
    # ── Header ──
    st.title("🎬 Seedance Video Generator")
    st.caption("Paste product links → pick a style → hit Generate")

    # ── Helper: get secret from st.secrets, env var, or empty ──
    def get_secret(key: str) -> str:
        """Check st.secrets first (Streamlit Cloud), then env vars."""
        try:
            return st.secrets[key]
        except (KeyError, FileNotFoundError):
            return os.environ.get(key, "")

    # ── Sidebar: API keys ──
    with st.sidebar:
        st.header("⚙️ Settings")

        # If keys are set in secrets/env, auto-use them and hide the inputs
        default_api_key = get_secret("ANTHROPIC_API_KEY")
        default_magnific = get_secret("MAGNIFIC_AUTH_TOKEN")

        if default_api_key and default_magnific:
            st.success("🔑 API keys loaded from secrets")
            api_key = default_api_key
            magnific_token = default_magnific
        else:
            api_key = st.text_input(
                "Anthropic API Key",
                type="password",
                value=default_api_key,
                help="Get yours at console.anthropic.com/settings/keys",
            )

            magnific_token = st.text_input(
                "Magnific Auth Token",
                type="password",
                value=default_magnific,
                help="Get via MCP Inspector → Quick OAuth Flow",
            )

        st.divider()
        st.subheader("🎨 Video Style")
        style = st.radio(
            "Choose style:",
            options=["shoe_video", "texthook_broll"],
            format_func=lambda x: {
                "shoe_video": "👟 Shoe Video (feet-only, 15s)",
                "texthook_broll": "📱 Text-Hook B-Roll (reveal, 8s)",
            }[x],
            help="Shoe Video = feet-and-shoes only. Text-Hook = vibey b-roll → product reveal.",
        )

        if style == "shoe_video":
            duration = st.select_slider("Duration (seconds)", options=[5, 10, 15], value=15)
            voice_script = st.text_area(
                "Voiceover script (optional)",
                placeholder="Leave empty for silent video",
                height=80,
            )
        else:
            duration = 8
            voice_script = None
            st.info("Text-hook style is always 8s and silent. You'll get the text hook to burn in later.")

        st.divider()
        st.caption("💡 Tip: Start with 'Scrape Only' to preview what images it finds before generating.")

    # ── Main area: product links ──
    st.subheader("📦 Product Links")
    links_input = st.text_area(
        "Paste TikTok Shop URLs (one per line)",
        placeholder=(
            "https://shop.tiktok.com/us/pdp/womens-leopard-bow-slipper.../123456\n"
            "https://shop.tiktok.com/us/pdp/suede-clogs-cork-footbed.../789012\n"
            "https://shop.tiktok.com/us/pdp/platform-comfort-slides.../345678"
        ),
        height=150,
    )

    col1, col2 = st.columns(2)
    scrape_btn = col1.button("🔍 Scrape Only", use_container_width=True)
    generate_btn = col2.button("🎬 Scrape + Generate", type="primary", use_container_width=True)

    # ── Parse links ──
    links = [
        line.strip() for line in links_input.strip().split("\n")
        if line.strip() and not line.strip().startswith("#")
    ] if links_input.strip() else []

    if not links and (scrape_btn or generate_btn):
        st.warning("Paste at least one product link above.")
        return

    # ── Scrape ──
    if scrape_btn or generate_btn:
        if generate_btn and (not api_key or not magnific_token):
            st.error("Set your Anthropic API Key and Magnific Auth Token in the sidebar.")
            return

        st.divider()
        st.subheader("📸 Scraping Products")
        products = []
        progress = st.progress(0, text="Starting...")

        for i, url in enumerate(links):
            progress.progress((i) / len(links), text=f"Scraping {i+1}/{len(links)}...")
            with st.spinner(f"Scraping: {url[:60]}..."):
                scraped = scrape_product(url)

            if scraped and scraped["images"]:
                product = {
                    "url": scraped["images"][0],
                    "name": scraped["name"],
                    "source_url": url,
                }
                products.append(product)
                st.success(f"✅ **{scraped['name']}** — found {len(scraped['images'])} image(s)")

                # Show the first image as a preview
                try:
                    st.image(scraped["images"][0], width=200, caption=scraped["name"])
                except Exception:
                    st.caption(f"Image URL: {scraped['images'][0][:80]}...")
            else:
                st.error(f"❌ Couldn't scrape: {url[:60]}...")

        progress.progress(1.0, text="Scraping complete!")

        if not products:
            st.error("No products could be scraped. Check your links.")
            return

        st.info(f"Found **{len(products)}** product(s) ready to go.")

        # ── Scrape-only: stop here ──
        if scrape_btn:
            st.download_button(
                "📥 Download scraped data (JSON)",
                data=json.dumps({"products": products}, indent=2),
                file_name="scraped_products.json",
                mime="application/json",
            )
            return

        # ── Generate videos ──
        st.divider()
        st.subheader("🎬 Generating Videos")

        results = []
        gen_progress = st.progress(0, text="Starting generation...")

        for i, product in enumerate(products):
            gen_progress.progress(
                i / len(products),
                text=f"Generating {i+1}/{len(products)}: {product['name'][:40]}..."
            )

            with st.spinner(f"Generating video for **{product['name']}**... (this may take a minute)"):
                result = generate_video(
                    api_key=api_key,
                    magnific_token=magnific_token,
                    product=product,
                    style=style,
                    duration=duration,
                    voice_script=voice_script if voice_script else None,
                )

            results.append(result)

            if result["status"] == "queued" and result.get("creation_id"):
                st.success(f"✅ **{result['product_name']}** — Creation ID: `{result['creation_id']}`")
            elif result["status"] == "error":
                st.error(f"❌ **{result['product_name']}** — {result.get('error', 'Unknown error')}")
            else:
                st.warning(f"⚠️ **{result['product_name']}** — Status: {result['status']}")

            # Show text-hook details if available
            if result.get("text_hook"):
                with st.expander(f"📝 Hook & Caption — {result['product_name']}"):
                    st.markdown(f"**Main hook:**\n> {result['text_hook']}")
                    if result.get("alt_hooks"):
                        st.markdown("**Alternates:**")
                        for alt in result["alt_hooks"]:
                            st.markdown(f"> {alt}")
                    if result.get("caption"):
                        st.markdown(f"**Caption:** {result['caption']}")
                    if result.get("hashtags"):
                        st.markdown(f"**Hashtags:** {result['hashtags']}")
                    st.caption("🔊 Sound tip: Add a trending upbeat TikTok sound — the render is silent.")

            # Show prompt if available
            if result.get("prompt_used"):
                with st.expander(f"📄 Prompt — {result['product_name']}"):
                    st.code(result["prompt_used"], language=None)

            # Rate limit delay
            if i < len(products) - 1:
                time.sleep(5)

        gen_progress.progress(1.0, text="All done!")

        # ── Summary ──
        st.divider()
        queued = sum(1 for r in results if r["status"] == "queued")
        errors = sum(1 for r in results if r["status"] == "error")

        col1, col2, col3 = st.columns(3)
        col1.metric("Total", len(results))
        col2.metric("Queued", queued)
        col3.metric("Errors", errors)

        # Download results
        st.download_button(
            "📥 Download results (JSON)",
            data=json.dumps({
                "generated_at": datetime.now().isoformat(),
                "style": style,
                "total": len(results),
                "queued": queued,
                "errors": errors,
                "results": results,
            }, indent=2),
            file_name=f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
        )


if __name__ == "__main__":
    main()
