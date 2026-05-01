"""Video post-processor using ffmpeg — remux, cut, concat, extract frames."""

import json
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path
from typing import Optional


class VideoProcessor:
    """Wrap ffmpeg/ffprobe for common video operations."""

    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe"):
        self.ffmpeg = ffmpeg_path
        self.ffprobe = ffprobe_path
        self._check_tools()

    def _check_tools(self) -> None:
        if not shutil.which(self.ffmpeg):
            raise RuntimeError(f"ffmpeg not found: {self.ffmpeg}")
        if not shutil.which(self.ffprobe):
            raise RuntimeError(f"ffprobe not found: {self.ffprobe}")

    @staticmethod
    def _run(cmd: list[str], check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
        """Run a subprocess command."""
        kwargs = {"check": check}
        if capture:
            kwargs.update({"stdout": subprocess.PIPE, "stderr": subprocess.PIPE})
        return subprocess.run(cmd, **kwargs)

    @staticmethod
    def _to_timecode(seconds: float) -> str:
        """Convert seconds to HH:MM:SS.ms format."""
        td = timedelta(seconds=seconds)
        total_seconds = int(td.total_seconds())
        hrs = total_seconds // 3600
        mins = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        ms = int((seconds - int(seconds)) * 1000)
        return f"{hrs:02d}:{mins:02d}:{secs:02d}.{ms:03d}"

    # ── Operations ───────────────────────────────────────────────────────

    def remux(self, input_path: str | Path, output_format: str = "mp4", output_path: Optional[str | Path] = None) -> Path:
        """Remux video to a different container format (lossless, -c copy).

        Args:
            input_path: Input video file.
            output_format: Target container format (mp4, mkv, mov, etc.).
            output_path: Optional explicit output path.

        Returns:
            Path to the remuxed file.
        """
        inp = Path(input_path)
        if not inp.exists():
            raise FileNotFoundError(f"Input not found: {inp}")

        out = Path(output_path) if output_path else inp.with_suffix(f".{output_format}")
        if out == inp:
            out = inp.with_stem(f"{inp.stem}_remuxed").with_suffix(f".{output_format}")

        cmd = [
            self.ffmpeg, "-y",
            "-i", str(inp),
            "-c", "copy",
            "-map", "0",
            "-movflags", "+faststart",
            str(out),
        ]
        self._run(cmd)
        return out

    def cut(
        self,
        input_path: str | Path,
        start: float,
        end: float,
        output_path: Optional[str | Path] = None,
        reencode: bool = False,
    ) -> Path:
        """Extract a segment from a video.

        Args:
            input_path: Input video file.
            start: Start time in seconds.
            end: End time in seconds.
            output_path: Optional explicit output path.
            reencode: If False, uses stream copy (fast, lossless). If True, re-encodes (slower, frame-accurate).

        Returns:
            Path to the cut segment.
        """
        inp = Path(input_path)
        if not inp.exists():
            raise FileNotFoundError(f"Input not found: {inp}")

        duration = end - start
        out = Path(output_path) if output_path else inp.with_stem(f"{inp.stem}_cut_{int(start)}-{int(end)}")

        cmd = [
            self.ffmpeg, "-y",
            "-ss", self._to_timecode(start),
            "-t", self._to_timecode(duration),
            "-i", str(inp),
        ]
        if not reencode:
            cmd.extend(["-c", "copy"])
        cmd.append(str(out))

        self._run(cmd)
        return out

    def concat(self, file_paths: list[str | Path], output_path: str | Path) -> Path:
        """Concatenate multiple video files into one.

        Tries lossless concat demuxer first, falls back to re-encode if formats differ.

        Args:
            file_paths: List of video files to concatenate.
            output_path: Output file path.

        Returns:
            Path to the concatenated file.
        """
        files = [Path(p) for p in file_paths]
        for f in files:
            if not f.exists():
                raise FileNotFoundError(f"Input not found: {f}")

        out = Path(output_path)

        # Build concat list file
        list_file = out.parent / f"_concat_list_{out.stem}.txt"
        with open(list_file, "w", encoding="utf-8") as f:
            for vid in files:
                # Use absolute path and escape backslashes for ffmpeg
                abs_path = str(vid.resolve()).replace("\\", "/")
                f.write(f"file '{abs_path}'\n")

        try:
            # Try lossless concat first
            cmd = [
                self.ffmpeg, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(list_file),
                "-c", "copy",
                str(out),
            ]
            try:
                self._run(cmd)
                return out
            except subprocess.CalledProcessError:
                # Fallback: re-encode using filter_complex
                inputs = []
                filter_parts = []
                for i, _ in enumerate(files):
                    inputs.extend(["-i", str(files[i])])
                    filter_parts.append(f"[{i}:v:0][{i}:a:0]")
                filter_parts.append(f"concat=n={len(files)}:v=1:a=1[outv][outa]")
                cmd2 = [
                    self.ffmpeg, "-y",
                    *inputs,
                    "-filter_complex", "".join(filter_parts),
                    "-map", "[outv]",
                    "-map", "[outa]",
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "23",
                    "-c:a", "aac",
                    str(out),
                ]
                self._run(cmd2)
        finally:
            list_file.unlink(missing_ok=True)

        return out

    def extract_frames(
        self,
        input_path: str | Path,
        interval: float = 1.0,
        output_dir: Optional[str | Path] = None,
        output_pattern: str = "frame_%04d.jpg",
        max_frames: Optional[int] = None,
    ) -> list[Path]:
        """Extract frames from a video at regular intervals.

        Args:
            input_path: Input video file.
            interval: Seconds between frames.
            output_dir: Directory for output frames (default: same as input).
            output_pattern: Filename pattern for frames.
            max_frames: Maximum number of frames to extract.

        Returns:
            List of extracted frame file paths.
        """
        inp = Path(input_path)
        if not inp.exists():
            raise FileNotFoundError(f"Input not found: {inp}")

        out_dir = Path(output_dir) if output_dir else inp.parent
        out_dir.mkdir(parents=True, exist_ok=True)

        output_template = str(out_dir / output_pattern)

        cmd = [
            self.ffmpeg, "-y",
            "-i", str(inp),
            "-vf", f"fps=1/{interval}",
            "-q:v", "2",
            output_template,
        ]
        self._run(cmd)

        # Collect generated frames
        frames = sorted(out_dir.glob(output_pattern.replace("%04d", "*")))
        if max_frames and len(frames) > max_frames:
            for f in frames[max_frames:]:
                f.unlink()
            frames = frames[:max_frames]
        return frames

    def get_media_info(self, input_path: str | Path) -> dict:
        """Get detailed media info using ffprobe.

        Returns:
            Dict with format info, video stream info, audio stream info, duration, etc.
        """
        inp = Path(input_path)
        if not inp.exists():
            raise FileNotFoundError(f"Input not found: {inp}")

        cmd = [
            self.ffprobe,
            "-v", "error",
            "-show_format",
            "-show_streams",
            "-of", "json",
            str(inp),
        ]
        result = self._run(cmd)
        data = json.loads(result.stdout.decode("utf-8"))

        fmt = data.get("format", {})
        streams = data.get("streams", [])

        video = next((s for s in streams if s.get("codec_type") == "video"), {})
        audio = next((s for s in streams if s.get("codec_type") == "audio"), {})

        return {
            "filename": inp.name,
            "format_name": fmt.get("format_name"),
            "duration": float(fmt.get("duration", 0)),
            "size_bytes": int(fmt.get("size", 0)),
            "bitrate": int(fmt.get("bit_rate", 0)),
            "video": {
                "codec": video.get("codec_name"),
                "width": video.get("width"),
                "height": video.get("height"),
                "fps": eval(video.get("r_frame_rate", "0/1")),  # e.g. "30/1" -> 30.0
                "pix_fmt": video.get("pix_fmt"),
            } if video else None,
            "audio": {
                "codec": audio.get("codec_name"),
                "sample_rate": audio.get("sample_rate"),
                "channels": audio.get("channels"),
            } if audio else None,
        }
