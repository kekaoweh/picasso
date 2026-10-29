"""Licensed footage on the open web: search, preview and download for the editing agent.

Only libraries whose licenses allow reuse in new videos are used, so finished work is safe
to publish. Pexels and Pixabay need a free API key (PEXELS_API_KEY / PIXABAY_API_KEY);
Wikimedia Commons, NASA and the Internet Archive's Prelinger collection work without one.
"""

import asyncio
import html
import io
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import quote, urlparse

import httpx
from PIL import Image, ImageDraw, ImageFont

from .config import font_path

Kind = Literal["video", "image", "audio"]
USER_AGENT = "Picasso/0.1 (https://github.com/kekaoweh/picasso; video editor)"
MAX_DOWNLOAD_BYTES = 700 * 1024 * 1024
TIMEOUT = httpx.Timeout(20.0, read=60.0)


@dataclass
class Candidate:
    provider: str
    kind: Kind
    title: str
    page_url: str
    preview_url: str
    author: str = ""
    license: str = ""
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    download_url: Optional[str] = None  # resolved lazily for NASA / Internet Archive
    extra: dict = field(default_factory=dict)
    id: str = ""

    def describe(self) -> str:
        size = f"{self.width}x{self.height}" if self.width else "size unknown"
        dur = f"{self.duration:.1f}s" if self.duration else ("still" if self.kind == "image" else "length unknown")
        by = f" by {self.author}" if self.author else ""
        return f"[{self.id}] {self.provider} · {self.kind} · {dur} · {size} · {self.license}{by} · “{self.title[:90]}”"


# Effect plates and keying footage look empty or broken when cut in on their own.
UTILITY_TAGS = ("overlay", "green screen", "greenscreen", "chroma", "alpha channel", "transparent", "particles",
                "light leak", "bokeh overlay", "lower third", "countdown", "glitch effect")


def is_utility_clip(tags: str) -> bool:
    t = (tags or "").lower()
    return any(u in t for u in UTILITY_TAGS)


STOPWORDS = {"a", "an", "the", "of", "in", "on", "at", "with", "and", "or", "to", "from", "by", "for", "into", "over",
             "under", "shot", "shots", "footage", "video", "clip", "slow", "motion", "close", "up", "wide"}


def broader_queries(query: str) -> list[str]:
    """Progressively shorter keyword versions of a descriptive query, for libraries that match every word."""
    words = [w for w in re.findall(r"[\w'-]+", query.lower()) if w not in STOPWORDS]
    out = []
    for n in (4, 3, 2):
        q = " ".join(words[:n])
        if q and q != query.lower() and q not in out:
            out.append(q)
    return out


def _strip_html(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


class Provider:
    name = ""
    kinds: tuple[Kind, ...] = ()
    needs_key: Optional[str] = None

    @property
    def enabled(self) -> bool:
        return not self.needs_key or bool(os.environ.get(self.needs_key))

    async def search(self, client: httpx.AsyncClient, query: str, kind: Kind, orientation: str, n: int) -> list[Candidate]:
        raise NotImplementedError

    async def resolve(self, client: httpx.AsyncClient, c: Candidate) -> str:
        assert c.download_url
        return c.download_url


class Pexels(Provider):
    name, kinds, needs_key = "Pexels", ("video", "image"), "PEXELS_API_KEY"

    async def search(self, client, query, kind, orientation, n):
        headers = {"Authorization": os.environ["PEXELS_API_KEY"]}
        params = {"query": query, "per_page": n}
        if orientation in ("landscape", "portrait", "square"):
            params["orientation"] = orientation
        if kind == "video":
            r = await client.get("https://api.pexels.com/videos/search", params=params, headers=headers)
            r.raise_for_status()
            out = []
            for v in r.json().get("videos", []):
                files = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("width")]
                # Sharpest file that is not absurdly large: prefer <= 2560 wide.
                files.sort(key=lambda f: (f["width"] <= 2560, f["width"]), reverse=True)
                if not files:
                    continue
                out.append(Candidate(
                    provider=self.name, kind="video", title=v.get("url", "").rstrip("/").split("/")[-1].replace("-", " ") or "Pexels video",
                    page_url=v.get("url", ""), preview_url=v.get("image", ""), author=(v.get("user") or {}).get("name", ""),
                    license="Pexels License (free to use)", duration=v.get("duration"),
                    width=files[0]["width"], height=files[0]["height"], download_url=files[0]["link"]))
            return out
        r = await client.get("https://api.pexels.com/v1/search", params=params, headers=headers)
        r.raise_for_status()
        return [Candidate(
            provider=self.name, kind="image", title=p.get("alt") or "Pexels photo", page_url=p.get("url", ""),
            preview_url=p["src"]["medium"], author=p.get("photographer", ""), license="Pexels License (free to use)",
            width=p.get("width"), height=p.get("height"), download_url=p["src"].get("large2x") or p["src"]["original"])
            for p in r.json().get("photos", [])]


class Pixabay(Provider):
    name, kinds, needs_key = "Pixabay", ("video", "image"), "PIXABAY_API_KEY"

    async def search(self, client, query, kind, orientation, n):
        # Pixabay requires every word to match, so descriptive queries can come back thin;
        # top up with shorter keyword versions until there are enough results.
        out: list[Candidate] = []
        seen: set[str] = set()
        for q in [query, *broader_queries(query)]:
            for c in await self._search_once(client, q, kind, orientation, n):
                if c.page_url not in seen:
                    seen.add(c.page_url)
                    out.append(c)
            if len(out) >= n:
                break
        return out[:n]

    async def _search_once(self, client, query, kind, orientation, n):
        params = {"key": os.environ["PIXABAY_API_KEY"], "q": query[:100], "per_page": max(3, n), "safesearch": "true"}
        if kind == "video":
            r = await client.get("https://pixabay.com/api/videos/", params=params)
            r.raise_for_status()
            out = []
            for h in r.json().get("hits", []):
                if is_utility_clip(h.get("tags", "")):
                    continue
                vids = h.get("videos", {})
                renditions = [v for v in (vids.get("large"), vids.get("medium"), vids.get("small")) if v and v.get("url")]
                if not renditions:
                    continue
                # Picasso renders at 1080p: take the smallest rendition that is still at least
                # 1080p on its short side, so 4K sources download ~4x faster with no visible loss.
                sharp = [v for v in renditions if min(v.get("width") or 0, v.get("height") or 0) >= 1080]
                best = min(sharp, key=lambda v: v.get("width") or 0) if sharp else renditions[0]
                out.append(Candidate(
                    provider=self.name, kind="video", title=h.get("tags", "Pixabay video"), page_url=h.get("pageURL", ""),
                    preview_url=best.get("thumbnail") or vids.get("medium", {}).get("thumbnail", ""), author=h.get("user", ""),
                    license="Pixabay Content License (free to use)", duration=h.get("duration"),
                    width=best.get("width"), height=best.get("height"), download_url=best["url"]))
            return out
        if orientation in ("landscape", "portrait"):
            params["orientation"] = "horizontal" if orientation == "landscape" else "vertical"
        r = await client.get("https://pixabay.com/api/", params={**params, "image_type": "photo"})
        r.raise_for_status()
        return [Candidate(
            provider=self.name, kind="image", title=h.get("tags", "Pixabay photo"), page_url=h.get("pageURL", ""),
            preview_url=h.get("webformatURL", ""), author=h.get("user", ""), license="Pixabay Content License (free to use)",
            width=h.get("imageWidth"), height=h.get("imageHeight"), download_url=h.get("largeImageURL"))
            for h in r.json().get("hits", [])]


class WikimediaCommons(Provider):
    name, kinds = "Wikimedia Commons", ("video", "image", "audio")
    ALLOWED = re.compile(r"^(cc0|public domain|pd|cc by(-sa)?( \d\.\d)?)", re.I)

    async def search(self, client, query, kind, orientation, n):
        filetype = {"video": "video", "image": "bitmap", "audio": "audio"}[kind]
        params = {
            "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
            "gsrsearch": f"filetype:{filetype} {query}", "gsrlimit": min(n * 2, 40),
            "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 480,
            "iiextmetadatafilter": "LicenseShortName|Artist|ObjectName",
        }
        r = await client.get("https://commons.wikimedia.org/w/api.php", params=params)
        r.raise_for_status()
        pages = sorted(r.json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
        out = []
        for p in pages:
            info = (p.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata", {})
            lic = _strip_html(meta.get("LicenseShortName", {}).get("value", ""))
            if not self.ALLOWED.match(lic):
                continue
            if kind != "audio" and (info.get("width") or 0) < 960:
                continue  # keep the edit sharp
            title = _strip_html(meta.get("ObjectName", {}).get("value", "")) or p["title"].removeprefix("File:")
            out.append(Candidate(
                provider=self.name, kind=kind, title=title, page_url=info.get("descriptionurl", ""),
                preview_url=info.get("thumburl", "") if kind != "audio" else "",
                author=_strip_html(meta.get("Artist", {}).get("value", ""))[:80], license=lic,
                duration=info.get("duration"), width=info.get("width") or None, height=info.get("height") or None,
                extra={"url": info.get("url", "").split("?")[0], "size": info.get("size") or 0}))
            if len(out) >= n:
                break
        return out

    async def resolve(self, client, c):
        url, size = c.extra["url"], c.extra["size"]
        if c.kind == "video" and size > 150 * 1024 * 1024:
            # Commons keeps web transcodes of every video; use one instead of a huge original.
            path = urlparse(url).path.removeprefix("/wikipedia/commons/")
            name = path.split("/")[-1]
            base = f"https://upload.wikimedia.org/wikipedia/commons/transcoded/{path}/{name}"
            for variant in (".1080p.vp9.webm", ".720p.vp9.webm", ".1080p.webm", ".720p.webm"):
                head = await client.head(base + variant)
                if head.status_code == 200:
                    return base + variant
        return url


class NASA(Provider):
    name, kinds = "NASA", ("video", "image", "audio")

    async def search(self, client, query, kind, orientation, n):
        r = await client.get("https://images-api.nasa.gov/search", params={"q": query, "media_type": kind, "page_size": n})
        r.raise_for_status()
        out = []
        for item in r.json().get("collection", {}).get("items", [])[:n]:
            data = (item.get("data") or [{}])[0]
            preview = next((l["href"] for l in item.get("links", []) if l.get("render") == "image" or l.get("rel") == "preview"), "")
            out.append(Candidate(
                provider=self.name, kind=kind, title=data.get("title", "NASA media"),
                page_url=f"https://images.nasa.gov/details/{quote(data.get('nasa_id', ''))}", preview_url=preview,
                author=data.get("center", "NASA"), license="Public domain (NASA)", extra={"collection": item.get("href", "")}))
        return out

    async def resolve(self, client, c):
        r = await client.get(c.extra["collection"])
        r.raise_for_status()
        urls = [u.replace("http://", "https://") for u in r.json()]
        order = {"video": ["~large.mp4", "~medium.mp4", "~orig.mp4", "~mobile.mp4"],
                 "image": ["~large.jpg", "~orig.jpg", "~medium.jpg"],
                 "audio": ["~128k.mp3", "~orig.mp3", "~orig.wav"]}[c.kind]
        for suffix in order:
            for u in urls:
                if u.lower().endswith(suffix):
                    return u
        raise RuntimeError("No downloadable file in this NASA item")


class PrelingerArchive(Provider):
    name, kinds = "Internet Archive (Prelinger)", ("video",)

    async def search(self, client, query, kind, orientation, n):
        q = f"({query}) AND mediatype:movies AND collection:prelinger"
        r = await client.get("https://archive.org/advancedsearch.php",
                             params={"q": q, "fl[]": ["identifier", "title", "creator"], "rows": n, "output": "json"})
        r.raise_for_status()
        return [Candidate(
            provider=self.name, kind="video", title=d.get("title", d["identifier"]),
            page_url=f"https://archive.org/details/{d['identifier']}",
            preview_url=f"https://archive.org/services/img/{d['identifier']}",
            author=(d.get("creator") if isinstance(d.get("creator"), str) else "Prelinger Archives") or "Prelinger Archives",
            license="Public domain (Prelinger Archives)", extra={"identifier": d["identifier"]})
            for d in r.json().get("response", {}).get("docs", [])]

    async def resolve(self, client, c):
        ident = c.extra["identifier"]
        r = await client.get(f"https://archive.org/metadata/{ident}")
        r.raise_for_status()
        files = [f for f in r.json().get("files", []) if f.get("name", "").lower().endswith(".mp4")]
        if not files:
            raise RuntimeError("No MP4 in this Archive item")
        files.sort(key=lambda f: int(f.get("size") or 0))
        pick = files[-1] if int(files[-1].get("size") or 0) <= MAX_DOWNLOAD_BYTES else files[0]
        return f"https://archive.org/download/{quote(ident)}/{quote(pick['name'])}"


PROVIDERS: list[Provider] = [Pexels(), Pixabay(), WikimediaCommons(), NASA(), PrelingerArchive()]


def provider_status() -> list[dict]:
    return [{"name": p.name, "kinds": list(p.kinds), "enabled": p.enabled, "needs_key": p.needs_key} for p in PROVIDERS]


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT})


async def search_all(query: str, kind: Kind, orientation: str, per_provider: int = 6,
                     only: Optional[list[str]] = None) -> tuple[list[Candidate], list[str]]:
    """Search every enabled library in parallel and interleave the results."""
    chosen = [p for p in PROVIDERS if p.enabled and kind in p.kinds
              and (not only or any(o.lower() in p.name.lower() for o in only))]
    notes: list[str] = []
    async with client() as http:
        async def one(p: Provider):
            try:
                return await p.search(http, query, kind, orientation, per_provider)
            except Exception as exc:  # noqa: BLE001 - one library failing shouldn't stop the search
                notes.append(f"{p.name} unavailable ({type(exc).__name__})")
                return []
        results = await asyncio.gather(*(one(p) for p in chosen))
    merged: list[Candidate] = []
    for i in range(max((len(r) for r in results), default=0)):
        merged += [r[i] for r in results if i < len(r)]
    return merged, notes


async def preview_sheet(cands: list[Candidate]) -> Optional[bytes]:
    """A numbered grid of result previews so the agent can judge look and quality."""
    tiles = [c for c in cands if c.preview_url]
    if not tiles:
        return None
    tw, th, cols = 320, 180, 4
    async with client() as http:
        async def fetch(c: Candidate):
            try:
                r = await http.get(c.preview_url)
                r.raise_for_status()
                return c, Image.open(io.BytesIO(r.content)).convert("RGB")
            except Exception:  # noqa: BLE001
                return c, None
        loaded = await asyncio.gather(*(fetch(c) for c in tiles))
    rows = (len(loaded) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * th), (24, 23, 21))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(font_path(), 17)
    except Exception:  # noqa: BLE001
        font = ImageFont.load_default()
    for i, (c, img) in enumerate(loaded):
        x, y = (i % cols) * tw, (i // cols) * th
        if img:
            scale = max(tw / img.width, th / img.height)
            img = img.resize((int(img.width * scale) + 1, int(img.height * scale) + 1))
            left, top = (img.width - tw) // 2, (img.height - th) // 2
            sheet.paste(img.crop((left, top, left + tw, top + th)), (x, y))
        label = c.id + (f" {c.duration:.0f}s" if c.duration else "")
        draw.rectangle([x + 6, y + 6, x + 14 + 10 * len(label), y + 30], fill=(0, 0, 0))
        draw.text((x + 10, y + 8), label, fill=(255, 255, 255), font=font)
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=72)
    return buf.getvalue()


_EXT = {"video/mp4": ".mp4", "video/webm": ".webm", "video/ogg": ".ogv", "image/jpeg": ".jpg", "image/png": ".png",
        "image/webp": ".webp", "audio/mpeg": ".mp3", "audio/ogg": ".ogg", "audio/wav": ".wav", "audio/x-wav": ".wav"}


async def download(c: Candidate, dest_stem: Path) -> Path:
    async with client() as http:
        url = c.download_url or await c_resolve(http, c)
        async with http.stream("GET", url) as r:
            r.raise_for_status()
            ctype = r.headers.get("content-type", "").split(";")[0].strip()
            ext = Path(urlparse(url).path).suffix.lower() or _EXT.get(ctype, "")
            if ext not in {".mp4", ".mov", ".webm", ".ogv", ".ogg", ".jpg", ".jpeg", ".png", ".webp", ".mp3", ".wav", ".m4v", ".tif", ".tiff"}:
                ext = _EXT.get(ctype, ".bin")
            dest = dest_stem.with_suffix(ext)
            size = 0
            with dest.open("wb") as fh:
                async for chunk in r.aiter_bytes(1024 * 256):
                    size += len(chunk)
                    if size > MAX_DOWNLOAD_BYTES:
                        fh.close()
                        dest.unlink(missing_ok=True)
                        raise RuntimeError("file is larger than 700 MB")
                    fh.write(chunk)
    return dest


async def c_resolve(http: httpx.AsyncClient, c: Candidate) -> str:
    provider = next(p for p in PROVIDERS if p.name == c.provider)
    c.download_url = await provider.resolve(http, c)
    return c.download_url
