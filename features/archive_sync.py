"""Incremental archive sync — download only new videos."""

import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from core.downloader import YTDlpEngine
from yt_dlp import YoutubeDL


class ArchiveSync:
    """Maintain a download archive to skip already-downloaded videos."""

    def __init__(
        self,
        archive_file: Optional[str] = None,
        output_dir: str = "downloads",
        engine: Optional[YTDlpEngine] = None,
    ):
        self.archive_file = archive_file or "archive.txt"
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.engine = engine or YTDlpEngine(output_dir=output_dir)
        self._ensure_archive()

    def _ensure_archive(self) -> None:
        """Create archive file if it doesn't exist."""
        Path(self.archive_file).touch(exist_ok=True)

    def _read_archive(self) -> set[str]:
        """Read archived video IDs."""
        if not Path(self.archive_file).exists():
            return set()
        with open(self.archive_file, "r", encoding="utf-8") as f:
            # archive.txt format: "youtube <id>" or "bilibili <id>"
            return {
                line.strip().split()[-1]
                for line in f
                if line.strip()
            }

    def _write_archive(self, ids: set[str]) -> None:
        """Append new IDs to archive."""
        with open(self.archive_file, "a", encoding="utf-8") as f:
            for vid in sorted(ids):
                f.write(f"{vid}\n")

    def list_new_videos(
        self,
        url: str,
        limit: Optional[int] = None,
        date_after: Optional[str] = None,
    ) -> list[dict]:
        """Return videos that are NOT in the archive, newest first.

        Args:
            url: Playlist / channel / user URL
            limit: Max videos to check (None = all)
            date_after: ISO date string or yt-dlp date expression
                (e.g. "20240101", "today-7days")
        """
        archived = self._read_archive()

        opts = self.engine._base_opts(url)
        opts.update({
            "extract_flat": True,
            "playlistend": limit,
            "skip_download": True,
        })
        if date_after:
            opts["dateafter"] = date_after

        new_videos: list[dict] = []
        with YoutubeDL(opts) as ydl:
            info = self.engine._safe_call(ydl.extract_info, url, download=False) or {}
            entries = info.get("entries", [])
            for entry in entries:
                if not entry:
                    continue
                vid = entry.get("id")
                if vid and vid not in archived:
                    new_videos.append({
                        "id": vid,
                        "title": entry.get("title", "Unknown"),
                        "url": entry.get("url", f"{url.split('/')[0]}//{url.split('/')[2]}/watch?v={vid}"),
                        "duration": entry.get("duration"),
                        "upload_date": entry.get("upload_date"),
                    })
        return new_videos

    def sync(
        self,
        url: str,
        fmt: Optional[str] = None,
        limit: Optional[int] = None,
        date_after: Optional[str] = None,
        audio_only: bool = False,
    ) -> list[str]:
        """Download only new videos and update archive.

        Returns list of downloaded file path templates.
        """
        archived = self._read_archive()

        opts = self.engine._base_opts(url)
        opts.update({
            "download_archive": self.archive_file,
            "outtmpl": str(self.output_dir / "%(title)s [%(id)s].%(ext)s"),
            "playlistend": limit,
        })
        if date_after:
            opts["dateafter"] = date_after
        if fmt and self.engine._platform(url) != "bilibili":
            opts["format"] = fmt
        if audio_only:
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "best",
                    "preferredquality": "0",
                }
            ]

        with YoutubeDL(opts) as ydl:
            self.engine._safe_call(ydl.download, [url])

        # Return what was actually downloaded (approximate)
        return [str(f) for f in self.output_dir.glob("*")]

    def preview_sync(
        self,
        url: str,
        limit: int = 20,
        date_after: Optional[str] = None,
    ) -> dict:
        """Show what would be downloaded without actually downloading.

        Returns:
            {"new": [...], "already_archived": count, "total_checked": count}
        """
        new = self.list_new_videos(url, limit=limit, date_after=date_after)
        archived_count = len(self._read_archive())
        return {
            "new_videos": new,
            "new_count": len(new),
            "already_archived": archived_count,
            "total_checked": limit,
        }

    def reset_archive(self) -> None:
        """Clear the archive (use with caution!)."""
        Path(self.archive_file).write_text("", encoding="utf-8")
