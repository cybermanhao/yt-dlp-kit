"""Chapter-based video splitting — split long videos by their chapter markers."""

from pathlib import Path
from typing import Optional

from core.downloader import YTDlpEngine
from yt_dlp import YoutubeDL


class ChapterSplitter:
    """Split videos into chapters using yt-dlp's built-in chapter support."""

    def __init__(
        self,
        output_dir: str = "chapters",
        engine: Optional[YTDlpEngine] = None,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.engine = engine or YTDlpEngine()

    def list_chapters(self, url: str) -> list[dict]:
        """Return chapter info without downloading.

        Returns:
            [{"title": str, "start_time": float, "end_time": float, "duration": float}, ...]
        """
        info = self.engine.extract_info(url)
        raw_chapters = info.get("chapters") or []

        chapters: list[dict] = []
        duration = info.get("duration", 0)
        for i, ch in enumerate(raw_chapters):
            start = ch.get("start_time", 0)
            end = ch.get("end_time")
            if end is None:
                # Last chapter ends at video end
                end = duration if i == len(raw_chapters) - 1 else raw_chapters[i + 1].get("start_time", duration)
            chapters.append({
                "title": ch.get("title", f"Chapter {i + 1}"),
                "start_time": start,
                "end_time": end,
                "duration": end - start,
            })
        return chapters

    def split(
        self,
        url: str,
        output_name: Optional[str] = None,
        fmt: Optional[str] = None,
    ) -> list[Path]:
        """Download and split video by chapters.

        Args:
            url: Video URL (must have chapter markers)
            output_name: Output template name component
            fmt: Video format preference

        Returns:
            List of generated chapter files.
        """
        opts = self.engine._base_opts(url)
        name = output_name or "%(section_number)s - %(section_title)s"
        opts.update({
            "split_chapters": True,
            "outtmpl": {
                "default": str(self.output_dir / f"%(title)s [%(id)s].%(ext)s"),
                "chapter": str(self.output_dir / f"{name}.%(ext)s"),
            },
        })
        if fmt and self.engine._platform(url) != "bilibili":
            opts["format"] = fmt

        with YoutubeDL(opts) as ydl:
            self.engine._safe_call(ydl.download, [url])

        # Collect chapter files
        files = sorted(self.output_dir.iterdir(), key=lambda p: p.stat().st_mtime)
        return [f for f in files if f.is_file()]

    def has_chapters(self, url: str) -> bool:
        """Quick check if a video has chapter markers."""
        return len(self.list_chapters(url)) > 0
