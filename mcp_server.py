"""yt-dlp-kit MCP Server — video download, metadata, and advanced features."""

import os
import sys
import json
import threading
import shutil
import contextlib
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from flask import Flask, send_file, render_template_string
from mcp.server.fastmcp import FastMCP
from yt_dlp import YoutubeDL

# ── Add project root to path for core/features imports ────────────────
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.downloader import YTDlpEngine
from features.archive_sync import ArchiveSync
from features.subtitle_grabber import SubtitleGrabber
from features.thumbnail_batch import ThumbnailBatch
from features.live_recorder import LiveRecorder
from features.live_monitor import LiveMonitor
from features.chapter_split import ChapterSplitter
from features.video_processor import VideoProcessor

# Suppress Flask startup messages on stdout (breaks MCP stdio)
os.environ.setdefault("FLASK_ENV", "production")
_flask_log = open(os.devnull, "w")

mcp = FastMCP("yt-dlp-kit")

DOWNLOADS_DIR = PROJECT_ROOT / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)
COOKIES_FILE = PROJECT_ROOT / "bilibili_cookies.txt"

# Shared engine instance
_engine = YTDlpEngine(output_dir=str(DOWNLOADS_DIR), cookies_path=str(COOKIES_FILE) if COOKIES_FILE.exists() else None)


# ── Helpers ───────────────────────────────────────────────────────────

def _human_readable_size(size_bytes):
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _suppress_stdout(func, *args, **kwargs):
    with open(os.devnull, "w") as devnull:
        with contextlib.redirect_stdout(devnull):
            return func(*args, **kwargs)


def _build_ydl_opts(base: dict) -> dict:
    """Inject cookies if available."""
    if COOKIES_FILE.exists():
        base["cookiefile"] = str(COOKIES_FILE)
    return base


# ── Flask Preview Server ──────────────────────────────────────────────

_preview_app = Flask("yt-dlp-kit-preview")
_preview_server_thread = None
_preview_port = None


@_preview_app.route("/video/<path:filename>")
def serve_video(filename):
    file_path = DOWNLOADS_DIR / filename
    if not file_path.exists():
        return "File not found", 404
    return send_file(file_path, as_attachment=False)


@_preview_app.route("/preview/<path:filename>")
def preview_page(filename):
    file_path = DOWNLOADS_DIR / filename
    if not file_path.exists():
        return "File not found", 404
    ext = file_path.suffix.lower()
    mime_map = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".qt": "video/quicktime",
        ".mkv": "video/x-matroska",
        ".avi": "video/x-msvideo",
        ".ogv": "video/ogg",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".wav": "audio/wav",
        ".opus": "audio/opus",
    }
    mime = mime_map.get(ext, "video/mp4")
    video_url = f"/video/{quote(filename)}"
    return render_template_string(
        """
<!DOCTYPE html>
<html>
<head>
    <title>Video Preview - {{ filename }}</title>
    <style>
        body { margin: 0; background: #0d0d0d; color: #e0e0e0;
               font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
               display: flex; flex-direction: column; align-items: center; min-height: 100vh; }
        .container { max-width: 1000px; width: 95%; margin: 30px auto; }
        h1 { margin: 0 0 20px; font-size: 20px; color: #fff; font-weight: 500; }
        video { width: 100%; border-radius: 10px; background: #000; box-shadow: 0 8px 32px rgba(0,0,0,0.6); }
        .info { margin-top: 20px; font-size: 13px; color: #888;
                background: #1a1a1a; padding: 12px 16px; border-radius: 8px; }
        .badge { display: inline-block; background: #2a2a2a; color: #aaa;
                 padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-right: 8px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>{{ filename }}</h1>
        <video controls autoplay>
            <source src="{{ video_url }}" type="{{ mime }}">
            Your browser does not support the video tag.
        </video>
        <div class="info">
            <span class="badge">{{ mime }}</span>
            <span class="badge">{{ size }}</span>
            Path: {{ path }}
        </div>
    </div>
</body>
</html>
    """,
        filename=filename,
        video_url=video_url,
        mime=mime,
        path=str(file_path),
        size=_human_readable_size(file_path.stat().st_size),
    )


def _start_preview_server(port=0):
    global _preview_server_thread, _preview_port
    import socket

    if _preview_port is not None:
        return _preview_port

    if port == 0:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

    _preview_port = port
    _preview_server_thread = threading.Thread(
        target=_preview_app.run,
        kwargs={
            "host": "127.0.0.1",
            "port": port,
            "debug": False,
            "use_reloader": False,
        },
        daemon=True,
    )
    _preview_server_thread.start()
    return port


# ── Existing MCP Tools ────────────────────────────────────────────────

@mcp.tool()
def download_video(url: str, output_dir: str = None, format_spec: str = "best") -> str:
    """Download a video from a URL to local storage.

    Args:
        url: The video URL to download.
        output_dir: Directory to save the file (default: downloads/).
        format_spec: Format selection string, e.g. "best", "bestvideo+bestaudio", "best[height<=720]".
                     NOTE: Do NOT use format_spec for Bilibili URLs.
    """
    out_dir = Path(output_dir) if output_dir else DOWNLOADS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # Use engine for platform-aware defaults
    template = _engine.download(url, output_dir=str(out_dir), fmt=format_spec)
    return json.dumps({"status": "downloaded", "output_template": template}, ensure_ascii=False)


@mcp.tool()
def extract_audio(
    url: str,
    output_dir: str = None,
    audio_format: str = "mp3",
    audio_quality: str = "5",
) -> str:
    """Extract audio track from a video URL.

    Args:
        url: The video URL.
        output_dir: Directory to save the file (default: downloads/).
        audio_format: Target audio format (mp3, m4a, wav, opus, flac).
        audio_quality: Quality 0 (best) to 10 (worst), or bitrate like "128K".
    """
    out_dir = Path(output_dir) if output_dir else DOWNLOADS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    template = _engine.extract_audio(
        url, output_dir=str(out_dir), audio_format=audio_format, audio_quality=audio_quality
    )
    return json.dumps({"status": "extracted", "output_template": template}, ensure_ascii=False)


@mcp.tool()
def get_video_info(url: str) -> str:
    """Retrieve video metadata without downloading the file.

    Args:
        url: The video URL to inspect.
    Returns:
        JSON string with title, duration, uploader, thumbnail, etc.
    """
    info = _engine.extract_info(url)
    return json.dumps(
        {
            "title": info.get("title"),
            "duration": info.get("duration"),
            "uploader": info.get("uploader"),
            "upload_date": info.get("upload_date"),
            "view_count": info.get("view_count"),
            "like_count": info.get("like_count"),
            "thumbnail": info.get("thumbnail"),
            "description": (info.get("description") or "")[:500],
            "id": info.get("id"),
            "webpage_url": info.get("webpage_url"),
            "is_live": info.get("is_live"),
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def list_formats(url: str) -> str:
    """List all available download formats for a video URL.

    Args:
        url: The video URL.
    Returns:
        JSON array of format objects.
    """
    formats = _engine.list_formats(url)
    result = []
    for f in formats:
        result.append(
            {
                "format_id": f.get("format_id"),
                "ext": f.get("ext"),
                "resolution": f.get("resolution"),
                "fps": f.get("fps"),
                "filesize": f.get("filesize") or f.get("filesize_approx"),
                "vcodec": f.get("vcodec"),
                "acodec": f.get("acodec"),
                "abr": f.get("abr"),
                "vbr": f.get("vbr"),
            }
        )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def preview_video(file_path: str) -> str:
    """Start a local preview server for a video/audio file and return the viewing URL.

    Args:
        file_path: Absolute or relative path to the media file.
    Returns:
        The preview URL to open in a browser.
    """
    path = Path(file_path).resolve()
    if not path.exists():
        return json.dumps({"error": f"File not found: {file_path}"}, ensure_ascii=False)

    if path.parent != DOWNLOADS_DIR.resolve():
        dest = DOWNLOADS_DIR / path.name
        if not dest.exists() or dest.stat().st_size != path.stat().st_size:
            shutil.copy2(path, dest)
        filename = path.name
    else:
        filename = path.name

    port = _start_preview_server()
    url = f"http://127.0.0.1:{port}/preview/{quote(filename)}"
    return json.dumps(
        {"status": "preview_ready", "url": url, "file": str(path)}, ensure_ascii=False
    )


@mcp.tool()
def list_downloads() -> str:
    """List all files in the downloads directory.

    Returns:
        JSON array of file objects with name, size, and modification time.
    """
    files = []
    for f in sorted(DOWNLOADS_DIR.iterdir()):
        if f.is_file():
            stat = f.stat()
            files.append(
                {
                    "name": f.name,
                    "size": _human_readable_size(stat.st_size),
                    "size_bytes": stat.st_size,
                    "modified": stat.st_mtime,
                    "path": str(f),
                }
            )
    return json.dumps(files, ensure_ascii=False, indent=2)


# ── NEW: Archive Sync Tools ───────────────────────────────────────────

@mcp.tool()
def preview_sync(url: str, limit: int = 20, date_after: str = None) -> str:
    """Preview which videos from a playlist/channel would be downloaded in an incremental sync.

    Args:
        url: Playlist, channel, or user URL.
        limit: Max videos to check.
        date_after: Only check videos uploaded after this date (e.g. "20240101", "today-7days").
    Returns:
        JSON with new videos and counts.
    """
    sync = ArchiveSync(archive_file=str(PROJECT_ROOT / "archive.txt"), output_dir=str(DOWNLOADS_DIR), engine=_engine)
    result = sync.preview_sync(url, limit=limit, date_after=date_after)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def sync_archive(
    url: str,
    limit: int = None,
    date_after: str = None,
    audio_only: bool = False,
) -> str:
    """Incrementally download only new videos from a playlist/channel.

    Args:
        url: Playlist, channel, or user URL.
        limit: Max videos to download.
        date_after: Only download videos after this date.
        audio_only: If true, extract audio instead of video.
    Returns:
        JSON status.
    """
    sync = ArchiveSync(archive_file=str(PROJECT_ROOT / "archive.txt"), output_dir=str(DOWNLOADS_DIR), engine=_engine)
    sync.sync(url, limit=limit, date_after=date_after, audio_only=audio_only)
    return json.dumps({"status": "sync_complete", "archive": str(sync.archive_file)}, ensure_ascii=False)


# ── NEW: Subtitle & Danmaku Tools ─────────────────────────────────────

@mcp.tool()
def download_subtitles(
    url: str,
    languages: str = "all",
    auto_generated: bool = True,
) -> str:
    """Download subtitles for a video URL.

    Args:
        url: Video URL.
        languages: Comma-separated language codes or "all".
        auto_generated: Include auto-generated subtitles.
    Returns:
        JSON with list of downloaded subtitle file paths.
    """
    grabber = SubtitleGrabber(output_dir=str(DOWNLOADS_DIR / "subtitles"), engine=_engine)
    lang_list = [l.strip() for l in languages.split(",")] if languages != "all" else "all"
    files = grabber.download_subtitles(url, languages=lang_list, auto_generated=auto_generated)
    return json.dumps(
        {"status": "done", "files": [str(f) for f in files]}, ensure_ascii=False, indent=2
    )


@mcp.tool()
def download_danmaku(bvid: str) -> str:
    """Download Bilibili bullet comments (danmaku) as XML.

    Args:
        bvid: Bilibili video ID (e.g. "BV1YpGHzcEs4").
    Returns:
        JSON with path to downloaded XML file.
    """
    grabber = SubtitleGrabber(output_dir=str(DOWNLOADS_DIR / "danmaku"), engine=_engine)
    xml_path = grabber.download_danmaku(bvid)
    if xml_path:
        return json.dumps({"status": "done", "xml": str(xml_path)}, ensure_ascii=False)
    return json.dumps({"status": "failed", "reason": "Could not download danmaku"}, ensure_ascii=False)


# ── NEW: Thumbnail Tools ──────────────────────────────────────────────

@mcp.tool()
def download_thumbnail(url: str, convert_to: str = "jpg") -> str:
    """Download the best-quality thumbnail for a video.

    Args:
        url: Video URL.
        convert_to: Output format (jpg, png, webp).
    Returns:
        JSON with path to downloaded thumbnail.
    """
    batch = ThumbnailBatch(output_dir=str(DOWNLOADS_DIR / "thumbnails"), engine=_engine)
    path = batch.download_thumbnail(url, convert_to=convert_to)
    return json.dumps(
        {"status": "done", "file": str(path), "size_bytes": path.stat().st_size if path.exists() else 0},
        ensure_ascii=False,
    )


# ── NEW: Live Stream Tools ────────────────────────────────────────────

@mcp.tool()
def check_live(url: str) -> str:
    """Check if a URL is currently streaming live.

    Args:
        url: Live stream URL (YouTube live, Bilibili live, etc.).
    Returns:
        JSON with is_live status and stream metadata.
    """
    recorder = LiveRecorder(output_dir=str(DOWNLOADS_DIR / "live"), engine=_engine)
    info = recorder.get_stream_info(url)
    return json.dumps(info, ensure_ascii=False, indent=2)


# ── NEW: Chapter Tools ────────────────────────────────────────────────

@mcp.tool()
def list_chapters(url: str) -> str:
    """List chapter markers for a video.

    Args:
        url: Video URL.
    Returns:
        JSON array of chapter objects with title, start_time, end_time.
    """
    splitter = ChapterSplitter(output_dir=str(DOWNLOADS_DIR / "chapters"), engine=_engine)
    chapters = splitter.list_chapters(url)
    return json.dumps(chapters, ensure_ascii=False, indent=2)


# ── NEW: Live Monitor Tools ───────────────────────────────────────────

_live_monitor_instance: Optional[LiveMonitor] = None


def _get_live_monitor() -> LiveMonitor:
    global _live_monitor_instance
    if _live_monitor_instance is None:
        _live_monitor_instance = LiveMonitor(
            config_file=str(PROJECT_ROOT / "live_monitor_config.json"),
            state_file=str(PROJECT_ROOT / "live_monitor_state.json"),
            default_output_dir=str(DOWNLOADS_DIR / "live_recordings"),
            engine=_engine,
        )
    return _live_monitor_instance


@mcp.tool()
def add_live_monitor(
    url: str,
    name: str = None,
    segment_duration: int = None,
    post_convert: str = None,
) -> str:
    """Add a live stream room to the background monitor.

    The monitor will check periodically and auto-record when the stream goes live.

    Args:
        url: Live stream URL (YouTube live, Bilibili live, etc.)
        name: Human-readable name for this room.
        segment_duration: Auto-split recording every N seconds (e.g. 3600 for 1 hour).
        post_convert: Remux to this format after recording (e.g. "mp4").
    Returns:
        JSON with added room config.
    """
    monitor = _get_live_monitor()
    room = monitor.add_room(
        url=url,
        name=name,
        segment_duration=segment_duration,
        post_convert=post_convert,
    )
    return json.dumps({"status": "added", "room": room}, ensure_ascii=False, indent=2)


@mcp.tool()
def list_monitored_rooms() -> str:
    """List all live stream rooms being monitored.

    Returns:
        JSON array of room configs and their current recording status.
    """
    monitor = _get_live_monitor()
    rooms = monitor.list_rooms()
    active = monitor.list_active_recordings()
    active_urls = {r["url"] for r in active}

    for r in rooms:
        r["currently_recording"] = r["url"] in active_urls

    return json.dumps({"rooms": rooms, "monitor_running": monitor.is_running()}, ensure_ascii=False, indent=2)


@mcp.tool()
def remove_live_monitor(url: str) -> str:
    """Remove a live stream room from monitoring.

    Args:
        url: The room URL to remove.
    Returns:
        JSON status.
    """
    monitor = _get_live_monitor()
    found = monitor.remove_room(url)
    return json.dumps({"status": "removed" if found else "not_found", "url": url}, ensure_ascii=False)


@mcp.tool()
def start_live_monitor(check_interval: int = 60) -> str:
    """Start the background live stream monitor.

    The monitor runs in a background thread, polling all configured rooms
    and auto-recording when they go live.

    Args:
        check_interval: Seconds between live checks (default: 60).
    Returns:
        JSON status.
    """
    monitor = _get_live_monitor()
    if monitor.is_running():
        return json.dumps({"status": "already_running"}, ensure_ascii=False)

    monitor.start(check_interval=check_interval)
    return json.dumps(
        {"status": "started", "check_interval": check_interval, "rooms_count": len(monitor.list_rooms())},
        ensure_ascii=False,
    )


@mcp.tool()
def stop_live_monitor() -> str:
    """Stop the background live stream monitor.

    Returns:
        JSON status.
    """
    monitor = _get_live_monitor()
    monitor.stop()
    return json.dumps({"status": "stopped"}, ensure_ascii=False)


@mcp.tool()
def get_monitor_status() -> str:
    """Get current live monitor status including active recordings.

    Returns:
        JSON with monitor_running, active_recordings, rooms_count.
    """
    monitor = _get_live_monitor()
    active = monitor.list_active_recordings()
    return json.dumps(
        {
            "monitor_running": monitor.is_running(),
            "rooms_count": len(monitor.list_rooms()),
            "active_recordings": active,
            "active_count": len(active),
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def force_stop_recording(url: str) -> str:
    """Force-stop an active recording for a specific room.

    Args:
        url: The room URL whose recording should be stopped.
    Returns:
        JSON status.
    """
    monitor = _get_live_monitor()
    stopped = monitor.force_stop_recording(url)
    return json.dumps({"status": "stopped" if stopped else "not_recording", "url": url}, ensure_ascii=False)


# ── NEW: Video Processor Tools ────────────────────────────────────────

_video_processor: Optional[VideoProcessor] = None


def _get_video_processor() -> VideoProcessor:
    global _video_processor
    if _video_processor is None:
        _video_processor = VideoProcessor()
    return _video_processor


@mcp.tool()
def remux_video(file_path: str, output_format: str = "mp4") -> str:
    """Remux a video file to a different container format (lossless, no re-encode).

    Useful for converting .webm/.mkv downloads to .mp4 for better compatibility.

    Args:
        file_path: Path to the input video file.
        output_format: Target container format (mp4, mkv, mov, etc.).
    Returns:
        JSON with output file path.
    """
    proc = _get_video_processor()
    out = proc.remux(file_path, output_format=output_format)
    return json.dumps(
        {"status": "remuxed", "input": file_path, "output": str(out), "size_bytes": out.stat().st_size},
        ensure_ascii=False,
    )


@mcp.tool()
def cut_video(file_path: str, start: float, end: float, reencode: bool = False) -> str:
    """Extract a segment from a video.

    Args:
        file_path: Path to the input video file.
        start: Start time in seconds.
        end: End time in seconds.
        reencode: If true, re-encodes for frame-accurate cuts (slower). If false, stream copy (fast).
    Returns:
        JSON with output file path.
    """
    proc = _get_video_processor()
    out = proc.cut(file_path, start=start, end=end, reencode=reencode)
    return json.dumps(
        {"status": "cut", "input": file_path, "output": str(out), "size_bytes": out.stat().st_size},
        ensure_ascii=False,
    )


@mcp.tool()
def concat_videos(file_paths: list[str], output_name: str = None) -> str:
    """Concatenate multiple video files into one.

    Tries lossless concat first, falls back to re-encode if formats differ.

    Args:
        file_paths: List of video file paths to concatenate.
        output_name: Output filename (default: concatenated.mp4 in downloads/).
    Returns:
        JSON with output file path.
    """
    proc = _get_video_processor()
    out_path = DOWNLOADS_DIR / (output_name or "concatenated.mp4")
    out = proc.concat(file_paths, output_path=out_path)
    return json.dumps(
        {"status": "concatenated", "output": str(out), "size_bytes": out.stat().st_size},
        ensure_ascii=False,
    )


@mcp.tool()
def extract_frames(file_path: str, interval: float = 1.0, max_frames: int = 10) -> str:
    """Extract frames from a video at regular intervals.

    Args:
        file_path: Path to the input video file.
        interval: Seconds between extracted frames.
        max_frames: Maximum number of frames to extract.
    Returns:
        JSON with list of extracted frame file paths.
    """
    proc = _get_video_processor()
    out_dir = DOWNLOADS_DIR / "frames"
    frames = proc.extract_frames(
        file_path, interval=interval, output_dir=out_dir, max_frames=max_frames
    )
    return json.dumps(
        {
            "status": "done",
            "count": len(frames),
            "files": [str(f) for f in frames],
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def get_media_info(file_path: str) -> str:
    """Get detailed media info for a video/audio file using ffprobe.

    Args:
        file_path: Path to the media file.
    Returns:
        JSON with duration, resolution, codecs, bitrate, etc.
    """
    proc = _get_video_processor()
    info = proc.get_media_info(file_path)
    return json.dumps(info, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
