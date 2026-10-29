import asyncio
import io
import re
import shutil
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Optional

from PIL import Image, ImageDraw, ImageFont

from .config import ffmpeg_path, font_path
from .db import Asset, Style
from .timeline import ASPECTS, FPS, Clip, Timeline

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".heic"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}

RENDER_CONCURRENCY = 3


class MediaError(RuntimeError):
    pass


async def _run_ffmpeg(*args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        ffmpeg_path(), "-hide_banner", "-nostdin", *args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    output = stderr.decode(errors="replace")
    if proc.returncode != 0:
        raise MediaError(output.strip().splitlines()[-1] if output.strip() else "ffmpeg failed")
    return output


def kind_for(filename: str, content_type: str | None) -> Optional[str]:
    ext = Path(filename).suffix.lower()
    if ext in VIDEO_EXTS or (content_type or "").startswith("video/"):
        return "video"
    if ext in IMAGE_EXTS or (content_type or "").startswith("image/"):
        return "image"
    if ext in AUDIO_EXTS or (content_type or "").startswith("audio/"):
        return "audio"
    return None


@dataclass
class Probe:
    duration: Optional[float]
    width: Optional[int]
    height: Optional[int]
    has_audio: bool


async def probe(path: Path) -> Probe:
    # `ffmpeg -i` with no output exits non-zero but still prints stream info.
    proc = await asyncio.create_subprocess_exec(
        ffmpeg_path(), "-hide_banner", "-nostdin", "-i", str(path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    info = stderr.decode(errors="replace")
    duration = None
    if m := re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", info):
        duration = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    width = height = None
    if m := re.search(r"Stream #\S+.*?Video:.*?(\d{2,5})x(\d{2,5})", info):
        width, height = int(m[1]), int(m[2])
    if width is None and duration is None:
        raise MediaError("Unsupported or unreadable media file")
    return Probe(duration, width, height, has_audio=bool(re.search(r"Stream #\S+.*?Audio:", info)))


async def make_thumbnail(src: Path, kind: str, duration: Optional[float], out: Path) -> Optional[Path]:
    if kind == "audio":
        return None
    # Input seeking on a still image (even -ss 0) yields no frames, so only seek videos.
    seek = ["-ss", f"{min(1.0, (duration or 0) / 3):.2f}"] if kind == "video" else []
    await _run_ffmpeg("-y", *seek, "-i", str(src), "-frames:v", "1",
                      "-vf", "scale=640:-2", "-q:v", "4", str(out))
    return out if out.exists() else None


async def contact_sheet(asset: Asset, count: int = 6, start: float = 0.0,
                        end: Optional[float] = None) -> bytes:
    """A labelled grid of frames so the agent can see what's in a clip."""
    src = Path(asset.path)
    with tempfile.TemporaryDirectory() as tmp:
        frames: list[tuple[float, Path]] = []
        if asset.kind == "image":
            out = Path(tmp) / "f0.jpg"
            await _run_ffmpeg("-y", "-i", str(src), "-frames:v", "1", "-vf", "scale=768:-2", str(out))
            frames.append((0.0, out))
        else:
            end = min(end or asset.duration or 0, asset.duration or 0)
            span = max(end - start, 0.1)
            count = max(1, min(count, 12))
            for i in range(count):
                t = start + span * (i + 0.5) / count
                out = Path(tmp) / f"f{i}.jpg"
                await _run_ffmpeg("-y", "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1",
                                  "-vf", "scale=384:-2", str(out))
                frames.append((t, out))

        images = [(t, Image.open(p).convert("RGB")) for t, p in frames]
        if len(images) == 1:
            buf = io.BytesIO()
            images[0][1].save(buf, "JPEG", quality=80)
            return buf.getvalue()

        cols = 3 if len(images) > 4 else 2
        rows = (len(images) + cols - 1) // cols
        w, h = images[0][1].size
        sheet = Image.new("RGB", (cols * w, rows * h), "black")
        draw = ImageDraw.Draw(sheet)
        try:
            font = ImageFont.truetype(font_path(), 18)
        except Exception:
            font = ImageFont.load_default()
        for i, (t, img) in enumerate(images):
            x, y = (i % cols) * w, (i // cols) * h
            sheet.paste(img.resize((w, h)), (x, y))
            label = f"{t:.1f}s"
            draw.rectangle([x + 6, y + 6, x + 16 + 11 * len(label), y + 32], fill="black")
            draw.text((x + 11, y + 8), label, fill="white", font=font)
        buf = io.BytesIO()
        sheet.save(buf, "JPEG", quality=75)
        return buf.getvalue()


# ---------------------------------------------------------------------------
# Rendering


def _escape_path(path: str) -> str:
    return path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _text_filter(clip: Clip, style: Style, width: int, height: int, workdir: Path, index: int) -> str:
    overlay = clip.text
    assert overlay
    size_factor = {"title": 0.075, "subtitle": 0.034, "caption": 0.045}[overlay.style]
    fontsize = int(min(width, height) * size_factor * (1.25 if height > width else 1))
    chars_per_line = max(12, int(width * 0.86 / (fontsize * 0.55)))
    wrapped = "\n".join(textwrap.wrap(overlay.text.strip(), chars_per_line)[:4])
    text_file = workdir / f"text_{index}.txt"
    text_file.write_text(wrapped, encoding="utf-8")

    position = overlay.position or ("center" if overlay.style == "title" else style.caption_position)
    margin = int(height * 0.08)
    y = {
        "top": str(margin),
        "center": "(h-text_h)/2",
        "bottom": f"h-text_h-{margin}",
        "lower_third": f"h*0.70",
    }[position]
    color = style.caption_color.lstrip("#")
    # Captions ease in and out over a quarter second instead of popping on and off.
    fade = min(0.25, clip.duration / 4)
    alpha = f"if(lt(t,{fade:.3f}),t/{fade:.3f},if(gt(t,{clip.duration - fade:.3f}),({clip.duration:.3f}-t)/{fade:.3f},1))"
    parts = [
        f"fontfile='{_escape_path(font_path('bold' if overlay.style == 'title' else 'semibold'))}'",
        f"textfile='{_escape_path(str(text_file))}'",
        f"fontsize={fontsize}",
        f"fontcolor=0x{color}",
        "text_align=C",
        f"line_spacing={int(fontsize * 0.25)}",
        "x=(w-text_w)/2",
        f"y={y}",
        f"alpha='{alpha}'",
    ]
    if style.caption_box and overlay.style != "title":
        parts += ["box=1", "boxcolor=0x14120f@0.48", f"boxborderw={int(fontsize * 0.45)}|{int(fontsize * 0.7)}"]
    else:
        parts += ["shadowcolor=black@0.55", "shadowx=0", f"shadowy={max(1, fontsize // 22)}"]
    return "drawtext=" + ":".join(parts)


def _motion_filter(motion: str, width: int, height: int, frames: int) -> str:
    # Upscale first so the slow zoom doesn't jitter, then animate with zoompan.
    big_w, big_h = width * 2, height * 2
    pre = f"scale={big_w}:{big_h}:force_original_aspect_ratio=increase,crop={big_w}:{big_h},"
    n = max(frames - 1, 1)
    centre = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    zp = {
        "zoom_in": f"z='1+0.18*on/{n}':{centre}",
        "zoom_out": f"z='1.18-0.18*on/{n}':{centre}",
        "pan_left": f"z=1.15:x='(iw-iw/zoom)*(1-on/{n})':y='ih/2-(ih/zoom/2)'",
        "pan_right": f"z=1.15:x='(iw-iw/zoom)*on/{n}':y='ih/2-(ih/zoom/2)'",
    }[motion]
    return pre + f"zoompan={zp}:d={frames}:s={width}x{height}:fps={FPS}"


async def _render_segment(clip: Clip, index: int, asset: Optional[Asset], style: Style,
                          width: int, height: int, fade_in: bool, fade_out: bool,
                          workdir: Path) -> Path:
    out = workdir / f"seg_{index:05d}.mp4"
    dur = clip.duration
    frames = max(int(round(dur * FPS)), 1)
    inputs: list[str] = []
    vf: list[str] = []

    if clip.kind == "title_card":
        inputs += ["-f", "lavfi", "-i", f"color=c=0x{clip.background.lstrip('#')}:s={width}x{height}:r={FPS}:d={dur:.3f}"]
    elif asset and asset.kind == "image":
        if clip.motion != "none":
            inputs += ["-i", asset.path]
            vf.append(_motion_filter(clip.motion, width, height, frames))
        else:
            inputs += ["-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.3f}", "-i", asset.path]
    elif asset:
        inputs += ["-ss", f"{clip.source_start:.3f}", "-t", f"{dur:.3f}", "-i", asset.path]
    else:
        raise MediaError(f"clip {index} has no source")

    use_source_audio = bool(asset and asset.kind == "video" and asset.has_audio and clip.keep_audio)
    inputs += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]

    if not vf:
        vf.append(f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}")
    vf += [f"fps={FPS}", "setsar=1"]
    if (style.brightness, style.contrast, style.saturation) != (0.0, 1.0, 1.0):
        vf.append(f"eq=brightness={style.brightness}:contrast={style.contrast}:saturation={style.saturation}")
    if clip.text and clip.text.text.strip():
        vf.append(_text_filter(clip, style, width, height, workdir, index))
    fade_d = min(0.5, dur / 3)
    if fade_in:
        vf.append(f"fade=t=in:st=0:d={fade_d:.2f}")
    if fade_out:
        vf.append(f"fade=t=out:st={dur - fade_d:.3f}:d={fade_d:.2f}")
    vf += [f"trim=duration={dur:.3f}", "format=yuv420p"]

    if use_source_audio:
        af = [f"[0:a]aresample=48000,aformat=channel_layouts=stereo,apad,atrim=duration={dur:.3f}"]
    else:
        af = ["[1:a]anull"]
    if fade_in:
        af.append(f"afade=t=in:st=0:d={fade_d:.2f}")
    if fade_out:
        af.append(f"afade=t=out:st={dur - fade_d:.3f}:d={fade_d:.2f}")

    graph = f"[0:v]{','.join(vf)}[v];{','.join(af)}[a]"
    await _run_ffmpeg(
        "-y", *inputs, "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
        "-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-video_track_timescale", "15360", str(out),
    )
    return out


ProgressFn = Callable[[int, int], Awaitable[None]]


async def render_timeline(timeline: Timeline, assets: dict[str, Asset], style: Style,
                          aspect: str, out_path: Path, workdir: Path,
                          progress: Optional[ProgressFn] = None) -> float:
    width, height = ASPECTS.get(aspect, ASPECTS["16:9"])
    workdir.mkdir(parents=True, exist_ok=True)
    clips = timeline.clips
    total = len(clips)
    sem = asyncio.Semaphore(RENDER_CONCURRENCY)
    done = 0

    def transition(c: Clip) -> str:
        return c.transition or style.transition

    async def one(i: int, clip: Clip) -> Path:
        nonlocal done
        async with sem:
            fade_in = i == 0 or transition(clip) == "fade"
            fade_out = i == total - 1 or transition(clips[i + 1]) == "fade"
            seg = await _render_segment(clip, i, assets.get(clip.asset_id or ""), style,
                                        width, height, fade_in, fade_out, workdir)
            done += 1
            if progress:
                await progress(done, total)
            return seg

    segments = await asyncio.gather(*(one(i, c) for i, c in enumerate(clips)))

    concat_list = workdir / "concat.txt"
    concat_list.write_text("".join(f"file '{s.name}'\n" for s in segments))
    joined = workdir / "joined.mp4"
    await _run_ffmpeg("-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
                      "-c", "copy", "-movflags", "+faststart", str(joined))

    total_dur = timeline.total_duration
    music = timeline.music
    if music and music.asset_id in assets:
        track = assets[music.asset_id]
        delay_ms = int(music.start_at * 1000)
        fade_start = max(total_dur - 2.5, 0)
        graph = (
            f"[1:a]volume={music.volume},adelay={delay_ms}|{delay_ms},"
            f"afade=t=out:st={fade_start:.2f}:d=2.5[m];"
            f"[0:a][m]amix=inputs=2:duration=first:normalize=0[a]"
        )
        await _run_ffmpeg("-y", "-i", str(joined), "-stream_loop", "-1", "-i", track.path,
                          "-filter_complex", graph, "-map", "0:v", "-map", "[a]",
                          "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                          "-t", f"{total_dur:.3f}", "-movflags", "+faststart", str(out_path))
    else:
        shutil.move(str(joined), out_path)

    shutil.rmtree(workdir, ignore_errors=True)
    return total_dur
