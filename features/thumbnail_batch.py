"""Thumbnail batch downloader — covers, avatars, and storyboards."""

from pathlib import Path
from typing import Optional

from core.downloader import YTDlpEngine
from yt_dlp import YoutubeDL


class ThumbnailBatch:
    """Download video thumbnails in bulk."""

    def __init__(self, output_dir: str = "thumbnails", engine: Optional[YTDlpEngine] = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.engine = engine or YTDlpEngine()

    def get_thumbnail_info(self, url: str) -> dict:
        """Return thumbnail metadata without downloading.

        Returns:
            {
                "title": str,
                "id": str,
                "thumbnail_url": str,      # best available
                "thumbnails": [{"url": str, "height": int, "width": int}, ...],
                "uploader_avatar": str | None,
            }
        """
        info = self.engine.extract_info(url)
        thumbnails = info.get("thumbnails", [])
        # Sort by resolution, best first
        sorted_thumbs = sorted(
            thumbnails,
            key=lambda t: (t.get("height", 0) or 0) * (t.get("width", 0) or 0),
            reverse=True,
        )
        return {
            "title": info.get("title", "Unknown"),
            "id": info.get("id", "unknown"),
            "thumbnail_url": info.get("thumbnail", ""),
            "thumbnails": [
                {"url": t.get("url", ""), "height": t.get("height"), "width": t.get("width")}
                for t in sorted_thumbs
            ],
            "uploader_avatar": info.get("uploader_thumbnail") or info.get("channel_thumbnail"),
        }

    def download_thumbnail(
        self,
        url: str,
        output_name: Optional[str] = None,
        convert_to: str = "jpg",
    ) -> Path:
        """Download the best thumbnail for a single video.

        Args:
            url: Video URL
            output_name: Custom filename (without extension)
            convert_to: Convert to format (jpg, png, webp)
        """
        opts = self.engine._base_opts(url)
        name = output_name or "%(title)s [%(id)s]"
        opts.update({
            "skip_download": True,
            "writethumbnail": True,
            "convert_thumbnails": convert_to,
            "outtmpl": str(self.output_dir / f"{name}.%(ext)s"),
        })

        with YoutubeDL(opts) as ydl:
            info = self.engine._safe_call(ydl.extract_info, url, download=False) or {}
            self.engine._safe_call(ydl.download, [url])

        vid = info.get("id", "unknown")
        # Find the downloaded file
        for f in self.output_dir.iterdir():
            if vid in f.name and f.suffix in (f".{convert_to}", ".webp", ".jpg", ".png"):
                return f
        # Fallback: return first matching file
        for f in sorted(self.output_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if f.suffix in (f".{convert_to}", ".webp", ".jpg", ".png"):
                return f
        return self.output_dir / f"{name}.{convert_to}"

    def batch_download(
        self,
        urls: list[str],
        output_dir: Optional[str] = None,
        convert_to: str = "jpg",
    ) -> list[Path]:
        """Download thumbnails for multiple URLs.

        Returns list of downloaded file paths.
        """
        out = Path(output_dir) if output_dir else self.output_dir
        out.mkdir(parents=True, exist_ok=True)
        results: list[Path] = []
        for url in urls:
            try:
                p = self.download_thumbnail(url, convert_to=convert_to)
                if p.exists():
                    results.append(p)
            except Exception as e:
                print(f"[WARN] Failed thumbnail for {url}: {e}")
        return results

    def download_playlist_thumbnails(
        self,
        playlist_url: str,
        limit: Optional[int] = None,
        convert_to: str = "jpg",
    ) -> list[Path]:
        """Download thumbnails for all videos in a playlist.

        Args:
            playlist_url: Playlist/channel URL
            limit: Max videos to process
            convert_to: Output format
        """
        info = self.engine.extract_info(playlist_url)
        entries = info.get("entries", [])
        if limit:
            entries = entries[:limit]

        urls = []
        for entry in entries:
            if entry:
                urls.append(entry.get("url", entry.get("webpage_url", "")))

        return self.batch_download(urls, convert_to=convert_to)
