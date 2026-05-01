"""Subtitle and danmaku (bullet comment) downloader."""

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import urllib.request
import urllib.error
import gzip

from core.downloader import YTDlpEngine
from yt_dlp import YoutubeDL


class SubtitleGrabber:
    """Download video subtitles and Bilibili danmaku."""

    BILI_DANMAKU_API = "https://api.bilibili.com/x/v1/dm/list.so"
    BILI_VIDEO_API = "https://api.bilibili.com/x/web-interface/view"

    def __init__(self, output_dir: str = "subtitles", engine: Optional[YTDlpEngine] = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.engine = engine or YTDlpEngine()

    # ── yt-dlp subtitles ────────────────────────────────────────────────

    def download_subtitles(
        self,
        url: str,
        languages: list[str] | str = "all",
        auto_generated: bool = True,
        convert_to: str = "srt",
    ) -> list[Path]:
        """Download subtitles for a video URL.

        Args:
            url: Video URL (YouTube, Bilibili, etc.)
            languages: Language codes or "all"
            auto_generated: Include auto-generated subtitles
            convert_to: Convert to format (srt, vtt, ass)
        """
        opts = self.engine._base_opts(url)
        opts.update({
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": auto_generated,
            "subtitleslangs": languages if isinstance(languages, list) else [languages],
            "convert_subs": convert_to,
            "outtmpl": str(self.output_dir / "%(title)s [%(id)s].%(ext)s"),
        })

        with YoutubeDL(opts) as ydl:
            info = self.engine._safe_call(ydl.extract_info, url, download=False) or {}
            # Actually write the subtitle files
            self.engine._safe_call(ydl.download, [url])

        # Collect subtitle files
        title = info.get("title", "unknown")
        vid = info.get("id", "unknown")
        files: list[Path] = []
        for f in self.output_dir.iterdir():
            if f.is_file() and vid in f.name and f.suffix in (".srt", ".vtt", ".ass"):
                files.append(f)
        return sorted(files)

    def list_available_subtitles(self, url: str) -> dict:
        """Return available subtitle languages without downloading."""
        info = self.engine.extract_info(url)
        subtitles = info.get("subtitles", {})
        auto_subs = info.get("automatic_captions", {})
        return {
            "manual": {lang: len(subs) for lang, subs in subtitles.items()},
            "auto_generated": {lang: len(subs) for lang, subs in auto_subs.items()},
        }

    # ── Bilibili danmaku ────────────────────────────────────────────────

    def _get_bili_cid(self, bvid: str) -> Optional[str]:
        """Get video CID (required for danmaku API) via Bilibili API with cookies."""
        cookie_str = ""
        if self.engine.cookies_path and Path(self.engine.cookies_path).exists():
            # Read Netscape cookie file to extract SESSDATA
            with open(self.engine.cookies_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip() and not line.startswith("#"):
                        parts = line.strip().split("\t")
                        if len(parts) >= 7:
                            name, value = parts[5], parts[6]
                            if name == "SESSDATA":
                                cookie_str = f"SESSDATA={value}"
                                break

        url = f"{self.BILI_VIDEO_API}?bvid={bvid}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": f"https://www.bilibili.com/video/{bvid}",
        }
        if cookie_str:
            headers["Cookie"] = cookie_str

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("data"):
                return str(data["data"]["cid"])
        except Exception as e:
            print(f"[WARN] API call failed: {e}")
        return None

    def download_danmaku(
        self,
        bvid: str,
        output_name: Optional[str] = None,
    ) -> Optional[Path]:
        """Download Bilibili danmaku (bullet comments) as XML.

        Args:
            bvid: Bilibili video ID (e.g. "BV1YpGHzcEs4")
            output_name: Output filename (without extension)

        Returns:
            Path to saved XML file, or None on failure.
        """
        cid = self._get_bili_cid(bvid)
        if not cid:
            print(f"[WARN] Could not get CID for {bvid}")
            return None

        try:
            url = f"{self.BILI_DANMAKU_API}?oid={cid}"
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "Referer": f"https://www.bilibili.com/video/{bvid}",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read()
        except Exception as e:
            print(f"[WARN] Failed to download danmaku: {e}")
            return None

        # Bilibili returns XML with gzip or raw deflate compression
        if content[:2] == b"\x1f\x8b":
            content = gzip.decompress(content)
        else:
            # Try raw deflate (no zlib header)
            try:
                decompressor = __import__("zlib").decompressobj(-__import__("zlib").MAX_WBITS)
                content = decompressor.decompress(content) + decompressor.flush()
            except Exception:
                pass  # Maybe it's already uncompressed

        name = output_name or f"{bvid}_danmaku"
        xml_path = self.output_dir / f"{name}.xml"
        xml_path.write_bytes(content)
        return xml_path

    def danmaku_to_text(self, xml_path: Path) -> list[dict]:
        """Parse danmaku XML to a list of comment dicts.

        Returns:
            [{"time": float, "text": str, "mode": int, "size": int, "color": str}, ...]
        """
        root = ET.parse(xml_path).getroot()
        comments: list[dict] = []
        for d in root.findall("d"):
            attr = d.get("p", "").split(",")
            if len(attr) >= 4:
                comments.append({
                    "time": float(attr[0]),
                    "mode": int(attr[1]),
                    "size": int(attr[2]),
                    "color": attr[3],
                    "text": d.text or "",
                })
        return sorted(comments, key=lambda x: x["time"])

    def danmaku_to_srt(self, xml_path: Path, output_path: Optional[Path] = None) -> Path:
        """Convert danmaku XML to SRT subtitle format.

        Args:
            xml_path: Path to danmaku XML
            output_path: Optional output SRT path

        Returns:
            Path to generated SRT file
        """
        comments = self.danmaku_to_text(xml_path)
        if not output_path:
            output_path = xml_path.with_suffix(".srt")

        # Group comments by 3-second windows to avoid spam
        window_size = 3.0
        windows: dict[int, list[str]] = {}
        for c in comments:
            w = int(c["time"] // window_size)
            windows.setdefault(w, []).append(c["text"])

        lines: list[str] = []
        idx = 1
        for w in sorted(windows.keys()):
            start = w * window_size
            end = start + window_size
            texts = windows[w][:10]  # limit 10 per window
            if not texts:
                continue
            body = " | ".join(texts)
            lines.append(f"{idx}")
            lines.append(f"{_sec_to_srt(start)} --> {_sec_to_srt(end)}")
            lines.append(body)
            lines.append("")
            idx += 1

        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path


def _sec_to_srt(seconds: float) -> str:
    """Convert seconds to SRT timestamp format."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")
