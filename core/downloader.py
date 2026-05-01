"""Unified yt-dlp wrapper with platform-aware defaults."""

import os
import re
import contextlib
from io import StringIO
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

from yt_dlp import YoutubeDL


class YTDlpEngine:
    """Wrap yt-dlp with sensible defaults per platform and stdio-safe output."""

    DEFAULT_OUTPUT_DIR = "downloads"
    COOKIE_FILE = "bilibili_cookies.txt"

    def __init__(
        self,
        output_dir: Optional[str] = None,
        cookies_path: Optional[str] = None,
        proxy: Optional[str] = None,
        quiet: bool = True,
        js_runtime: Optional[str] = None,
    ):
        self.output_dir = Path(output_dir or self.DEFAULT_OUTPUT_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cookies_path = cookies_path or self._find_cookie_file()
        self.proxy = proxy
        self.quiet = quiet
        self.js_runtime = js_runtime or self._detect_js_runtime()

    # ── helpers ──────────────────────────────────────────────────────────

    @classmethod
    def _find_cookie_file(cls) -> Optional[str]:
        """Auto-discover bilibili_cookies.txt in project root."""
        candidates = [
            Path(__file__).parent.parent / cls.COOKIE_FILE,
            Path.cwd() / cls.COOKIE_FILE,
        ]
        for p in candidates:
            if p.exists():
                return str(p)
        return None

    @classmethod
    def _detect_js_runtime(cls) -> Optional[str]:
        """Check if Node.js is available for YouTube format unlocking."""
        import shutil
        if shutil.which("node"):
            return "node"
        return None

    @staticmethod
    def _platform(url: str) -> str:
        """Detect platform from URL."""
        lowered = url.lower()
        if "bilibili.com" in lowered:
            return "bilibili"
        if "youtube.com" in lowered or "youtu.be" in lowered:
            return "youtube"
        return "generic"

    def _base_opts(self, url: str) -> dict[str, Any]:
        """Build base yt-dlp options, platform-aware."""
        opts: dict[str, Any] = {
            "quiet": self.quiet,
            "no_warnings": True,
            "outtmpl": str(self.output_dir / "%(title)s [%(id)s].%(ext)s"),
        }

        # JS runtime (YouTube format unlocking)
        if self.js_runtime:
            opts["js_runtimes"] = {self.js_runtime: {}}

        # Proxy
        if self.proxy:
            opts["proxy"] = self.proxy

        # Platform-specific defaults
        platform = self._platform(url)
        if platform == "bilibili":
            if self.cookies_path:
                opts["cookiefile"] = self.cookies_path
            # Bilibili: never pass 'format' — let yt-dlp auto-merge A/V streams
            # Callers should omit 'format' from opts when platform is bilibili
        elif platform == "youtube":
            # YouTube works fine without cookies for public videos
            pass

        return opts

    @staticmethod
    def _safe_call(func: Callable, *args, **kwargs):
        """Suppress stdout to protect MCP stdio transport."""
        with contextlib.redirect_stdout(StringIO()):
            return func(*args, **kwargs)

    # ── public API ───────────────────────────────────────────────────────

    def extract_info(self, url: str, **extra_opts) -> dict[str, Any]:
        """Extract metadata without downloading."""
        opts = self._base_opts(url)
        opts.update(extra_opts)
        opts.setdefault("skip_download", True)

        with YoutubeDL(opts) as ydl:
            return self._safe_call(ydl.extract_info, url, download=False) or {}

    def list_formats(self, url: str) -> list[dict[str, Any]]:
        """Return available formats as a list."""
        info = self.extract_info(url)
        return info.get("formats", [])

    def download(
        self,
        url: str,
        output_dir: Optional[str] = None,
        fmt: Optional[str] = None,
        playlist_items: Optional[str] = None,
        extra_opts: Optional[dict] = None,
    ) -> str:
        """Download a video/playlist. Returns output file path."""
        opts = self._base_opts(url)
        if output_dir:
            opts["outtmpl"] = str(Path(output_dir) / "%(title)s [%(id)s].%(ext)s")
        if fmt and self._platform(url) != "bilibili":
            opts["format"] = fmt
        if playlist_items:
            opts["playlist_items"] = playlist_items
        if extra_opts:
            opts.update(extra_opts)

        with YoutubeDL(opts) as ydl:
            self._safe_call(ydl.download, [url])

        # yt-dlp doesn't return the exact path; caller can scan output_dir
        return opts["outtmpl"]

    def extract_audio(
        self,
        url: str,
        output_dir: Optional[str] = None,
        audio_format: str = "best",
        audio_quality: str = "0",
    ) -> str:
        """Extract best-quality audio from URL."""
        opts = self._base_opts(url)
        if output_dir:
            opts["outtmpl"] = str(Path(output_dir) / "%(title)s [%(id)s].%(ext)s")
        opts.update({
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": audio_format,
                    "preferredquality": audio_quality,
                }
            ],
        })

        with YoutubeDL(opts) as ydl:
            self._safe_call(ydl.download, [url])
        return opts["outtmpl"]

    def download_subtitles(
        self,
        url: str,
        languages: list[str] | str = "all",
        auto_subs: bool = False,
        output_dir: Optional[str] = None,
    ) -> list[str]:
        """Download subtitles without video. Returns list of subtitle file paths."""
        opts = self._base_opts(url)
        if output_dir:
            opts["outtmpl"] = str(Path(output_dir) / "%(title)s [%(id)s].%(ext)s")
        opts.update({
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": auto_subs,
            "subtitleslangs": languages if isinstance(languages, list) else [languages],
            "convert_subs": "srt",
        })

        with YoutubeDL(opts) as ydl:
            info = self._safe_call(ydl.extract_info, url, download=False) or {}
            self._safe_call(ydl.download, [url])

        # Collect written subtitle files
        files: list[str] = []
        base = opts["outtmpl"].replace(".%(ext)s", "")
        entries = info.get("entries", [info])
        for entry in entries:
            title = entry.get("title", "unknown")
            vid = entry.get("id", "unknown")
            # subtitle extensions are unpredictable; scan output dir
            scan_dir = Path(output_dir or self.output_dir)
            pattern = re.escape(f"{title} [{vid}]") + r"\.[\w-]+\.srt$"
            files.extend(str(f) for f in scan_dir.glob("*") if re.search(pattern, f.name))
        return files

    def download_thumbnails(
        self,
        url: str,
        output_dir: Optional[str] = None,
    ) -> list[str]:
        """Download thumbnails only. Returns list of file paths."""
        opts = self._base_opts(url)
        if output_dir:
            opts["outtmpl"] = str(Path(output_dir) / "%(title)s [%(id)s].%(ext)s")
        opts.update({
            "skip_download": True,
            "writethumbnail": True,
        })

        with YoutubeDL(opts) as ydl:
            self._safe_call(ydl.download, [url])

        scan_dir = Path(output_dir or self.output_dir)
        return [str(f) for f in scan_dir.glob("*.jpg") + list(scan_dir.glob("*.webp"))]

    def is_live(self, url: str) -> bool:
        """Check if a URL is currently streaming live."""
        info = self.extract_info(url)
        return bool(info.get("is_live"))
