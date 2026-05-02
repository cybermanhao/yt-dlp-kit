"""Live stream recorder — detect and record ongoing live streams."""

import subprocess
import time
from pathlib import Path
from typing import Optional

from core.downloader import YTDlpEngine
from yt_dlp import YoutubeDL
from yt_dlp.utils._utils import _UnsafeExtensionError

# Allow fmp4 (Fragmented MP4) used by Bilibili live streams.
# yt-dlp's safelist doesn't include fmp4, causing _UnsafeExtensionError.
_UnsafeExtensionError.ALLOWED_EXTENSIONS = _UnsafeExtensionError.ALLOWED_EXTENSIONS | {"fmp4"}


class LiveRecorder:
    """Detect live streams and record them to disk."""

    def __init__(
        self,
        output_dir: str = "live_recordings",
        engine: Optional[YTDlpEngine] = None,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.engine = engine or YTDlpEngine()

    def is_live(self, url: str) -> bool:
        """Check if the URL is currently streaming live."""
        try:
            info = self.engine.extract_info(url)
            return bool(info.get("is_live"))
        except Exception:
            return False

    def get_stream_info(self, url: str) -> dict:
        """Get live stream metadata.

        Returns:
            {
                "is_live": bool,
                "title": str,
                "uploader": str,
                "viewer_count": int | None,
                "start_time": str | None,
                "formats": [{"format_id": str, "ext": str, "url": str}, ...],
            }
        """
        info = self.engine.extract_info(url)
        formats = info.get("formats", [])
        return {
            "is_live": bool(info.get("is_live")),
            "title": info.get("title", "Unknown"),
            "uploader": info.get("uploader", "Unknown"),
            "viewer_count": info.get("concurrent_viewers") or info.get("view_count"),
            "start_time": info.get("release_timestamp") or info.get("timestamp"),
            "formats": [
                {
                    "format_id": f.get("format_id"),
                    "ext": f.get("ext"),
                    "quality": f.get("quality_label") or f.get("format_note"),
                }
                for f in formats
            ],
        }

    def record(
        self,
        url: str,
        output_name: Optional[str] = None,
        duration: Optional[int] = None,
        fmt: Optional[str] = None,
    ) -> Path:
        """Record a live stream.

        Args:
            url: Live stream URL
            output_name: Output filename (without extension)
            duration: Max recording duration in seconds (None = until stream ends)
            fmt: Format preference (e.g. "best", "worst")

        Returns:
            Path to the recorded file (after recording completes)
        """
        # Extract everything in one yt-dlp call to avoid URL expiry.
        info = self._extract_live_info(url, fmt)
        if not info or not info.get("is_live"):
            raise RuntimeError(f"Stream is not live: {url}")

        if not output_name:
            title = info.get("title", "live")[:50]
            # Sanitize filename for Windows
            for ch in '<>:"/\\|?*':
                title = title.replace(ch, '_')
            name = f"{title}_{int(time.time())}"
        else:
            name = output_name
        output_path = self.output_dir / f"{name}.mp4"

        stream_url = info.get("stream_url")
        if not stream_url:
            raise RuntimeError("Could not extract stream URL")

        cmd = [
            "ffmpeg", "-y",
            "-i", stream_url,
            "-c", "copy",
            "-bsf:a", "aac_adtstoasc",
            "-movflags", "frag_keyframe+empty_moov",
            str(output_path),
        ]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        try:
            proc.wait(timeout=duration)
        except subprocess.TimeoutExpired:
            print(f"[INFO] Recording stopped after {duration}s timeout")
            # Gracefully ask ffmpeg to quit (flushes buffers and closes file)
            try:
                proc.stdin.write(b"q")
                proc.stdin.close()
                proc.wait(timeout=10)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

        return output_path if output_path.exists() else self.output_dir

    def _extract_live_info(self, url: str, fmt: Optional[str] = None) -> Optional[dict]:
        """Extract live info, title, and best stream URL in one call."""
        opts = self.engine._base_opts(url)
        opts["quiet"] = True
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info:
            return None

        formats = info.get("formats", [])
        if not formats:
            return None

        def sort_key(f):
            if f.get("ext") == "fmp4":
                return (2, f.get("tbr", 0) or 0, f.get("height", 0) or 0)
            if f.get("ext") == "flv":
                return (1, f.get("tbr", 0) or 0, f.get("height", 0) or 0)
            return (0, f.get("tbr", 0) or 0, f.get("height", 0) or 0)

        best = max(formats, key=sort_key)
        return {
            "is_live": bool(info.get("is_live")),
            "title": info.get("title", "live"),
            "stream_url": best.get("url"),
        }

    def wait_and_record(
        self,
        url: str,
        check_interval: int = 60,
        max_wait: Optional[int] = None,
        **record_kwargs,
    ) -> Optional[Path]:
        """Wait for stream to go live, then record.

        Args:
            url: Stream URL to monitor
            check_interval: Seconds between checks
            max_wait: Max total wait time in seconds (None = forever)
            **record_kwargs: Passed to record()

        Returns:
            Path to recording, or None if max_wait exceeded.
        """
        waited = 0
        while True:
            if self.is_live(url):
                print(f"[INFO] Stream is live! Starting recording...")
                return self.record(url, **record_kwargs)

            if max_wait and waited >= max_wait:
                print(f"[INFO] Max wait ({max_wait}s) exceeded, giving up.")
                return None

            print(f"[INFO] Stream not live yet, checking again in {check_interval}s...")
            time.sleep(check_interval)
            waited += check_interval
