"""
InstaGet Backend — FastAPI + yt-dlp
Deploy FREE on Render.com
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import re

app = FastAPI(title="InstaGet API", version="1.0.0")

# ─── CORS ─── Allow your frontend domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Replace * with your domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Request model ───
class DownloadRequest(BaseModel):
    url: str

# ─── Validate Instagram URL ───
def is_valid_instagram_url(url: str) -> bool:
    pattern = r"https?://(www\.)?instagram\.com/(p|reel|tv|stories|s)/[\w\-]+"
    return bool(re.match(pattern, url))

# ─── Health check ───
@app.get("/")
def root():
    return {"status": "ok", "service": "InstaGet API"}

@app.get("/health")
def health():
    return {"status": "healthy"}

# ─── Main download endpoint ───
@app.post("/api/download")
def download(req: DownloadRequest):
    url = req.url.strip()

    if not is_valid_instagram_url(url):
        raise HTTPException(status_code=400, detail="Invalid Instagram URL")

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,          # We only fetch info, not download on server
        "extract_flat": False,
        "cookiefile": None,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Could not fetch Instagram content. Make sure the post is public. ({str(e)[:120]})"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)[:120]}")

    # ─── Extract all available formats ───
    formats = []
    seen_heights = set()

    raw_formats = info.get("formats") or []

    for f in raw_formats:
        vcodec = f.get("vcodec", "none")
        acodec = f.get("acodec", "none")
        height = f.get("height")
        ext    = f.get("ext", "mp4")
        url_f  = f.get("url", "")

        if not url_f:
            continue

        # Video formats
        if vcodec and vcodec != "none" and height and height not in seen_heights:
            seen_heights.add(height)
            label = (
                "1080p Full HD" if height >= 1080 else
                "720p HD"       if height >= 720  else
                "480p SD"       if height >= 480  else
                f"{height}p"
            )
            tag = (
                "BEST"  if height >= 1080 else
                "HD"    if height >= 720  else
                "FAST"
            )
            formats.append({
                "label": label,
                "tag":   tag,
                "type":  "video",
                "ext":   ext,
                "url":   url_f,
                "height": height,
            })

        # Best audio-only format for MP3
        elif vcodec in (None, "none") and acodec and acodec != "none":
            if not any(x["type"] == "audio" for x in formats):
                formats.append({
                    "label": "MP3 Audio",
                    "tag":   "AUDIO",
                    "type":  "audio",
                    "ext":   "mp3",
                    "url":   url_f,
                    "height": 0,
                })

    # Sort video by quality descending, audio last
    formats.sort(key=lambda x: x["height"], reverse=True)

    # Fallback: if no formats parsed, return the direct URL
    if not formats:
        direct = info.get("url") or info.get("webpage_url", "")
        if direct:
            formats.append({
                "label": "Download Video",
                "tag":   "BEST",
                "type":  "video",
                "ext":   "mp4",
                "url":   direct,
                "height": 0,
            })

    if not formats:
        raise HTTPException(
            status_code=404,
            detail="No downloadable formats found. The post may be private."
        )

    return {
        "title":     info.get("title") or info.get("description", "Instagram Video")[:80],
        "thumbnail": info.get("thumbnail", ""),
        "duration":  info.get("duration"),
        "uploader":  info.get("uploader") or info.get("channel", ""),
        "formats":   formats,
    }
