"""Live stream recorder — detect and record ongoing live streams."""

import subprocess
import time
from pathlib import Path
from typing import Optional

from core.downloader import YTDlpEngine
from yt_dlp import YoutubeDL


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
        if not self.is_live(url):
            raise RuntimeError(f"Stream is not live: {url}")

        opts = self.engine._base_opts(url)
        name = output_name or "%(title)s [%(id)s]"
        opts.update({
            "live_from_start": True,
            "outtmpl": str(self.output_dir / f"{name}.%(ext)s"),
        })
        if fmt and self.engine._platform(url) != "bilibili":
            opts["format"] = fmt
        if duration:
            opts["max_filesize"] = None  # yt-dlp doesn't have duration limit directly
            # Workaround: we can use a subprocess with timeout

        # For duration-limited recording, use subprocess with timeout
        if duration:
            return self._record_with_timeout(url, opts, duration)

        with YoutubeDL(opts) as ydl:
            self.engine._safe_call(ydl.download, [url])

        # Find the newest file in output dir
        files = sorted(self.output_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        return files[0] if files else self.output_dir

    def _record_with_timeout(self, url: str, opts: dict, duration: int) -> Path:
        """Record with a hard timeout using subprocess."""
        import json, tempfile

        # Write opts to a temp file and run yt-dlp via subprocess
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(opts, f)
            opts_file = f.name

        cmd = [
            "python", "-c",
            f"""
import json, sys
from yt_dlp import YoutubeDL
with open({repr(opts_file)}) as f:
    opts = json.load(f)
with YoutubeDL(opts) as ydl:
    ydl.download([{repr(url)}])
"""
        ]
        try:
            subprocess.run(cmd, timeout=duration, check=False)
        except subprocess.TimeoutExpired:
            print(f"[INFO] Recording stopped after {duration}s timeout")
        finally:
            Path(opts_file).unlink(missing_ok=True)

        files = sorted(self.output_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        return files[0] if files else self.output_dir

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
