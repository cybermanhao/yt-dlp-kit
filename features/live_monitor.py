"""Live stream monitor — background multi-room watcher with auto-record."""

import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from core.downloader import YTDlpEngine


class LiveMonitor:
    """Monitor multiple live streams in background, auto-record when they go live.

    State is persisted to disk so monitoring survives restarts.
    """

    def __init__(
        self,
        config_file: str = "live_monitor_config.json",
        state_file: str = "live_monitor_state.json",
        default_output_dir: str = "live_recordings",
        engine: Optional[YTDlpEngine] = None,
    ):
        self.config_file = Path(config_file)
        self.state_file = Path(state_file)
        self.default_output_dir = Path(default_output_dir)
        self.default_output_dir.mkdir(parents=True, exist_ok=True)
        self.engine = engine or YTDlpEngine()

        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # Callbacks
        self.on_live_start: Optional[Callable[[str, dict], None]] = None
        self.on_record_done: Optional[Callable[[str, Path], None]] = None
        self.on_record_error: Optional[Callable[[str, str], None]] = None

        self._ensure_files()

    # ── Persistence ────────────────────────────────────────────────────

    def _ensure_files(self) -> None:
        if not self.config_file.exists():
            self._save_config({"rooms": []})
        if not self.state_file.exists():
            self._save_state({"recordings": {}, "last_check": None})

    def _load_config(self) -> dict:
        return json.loads(self.config_file.read_text(encoding="utf-8"))

    def _save_config(self, data: dict) -> None:
        self.config_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _load_state(self) -> dict:
        return json.loads(self.state_file.read_text(encoding="utf-8"))

    def _save_state(self, data: dict) -> None:
        self.state_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── Room Management ────────────────────────────────────────────────

    def add_room(
        self,
        url: str,
        name: Optional[str] = None,
        output_dir: Optional[str] = None,
        auto_record: bool = True,
        segment_duration: Optional[int] = None,  # seconds, None = no split
        fmt: Optional[str] = None,
        post_convert: Optional[str] = None,  # e.g. "mp4" to remux after recording
    ) -> dict:
        """Add a live room to the monitor list.

        Args:
            url: Live stream URL (YouTube live, Bilibili live, etc.)
            name: Human-readable name for the room
            output_dir: Directory to save recordings (default: live_recordings/<name>)
            auto_record: Start recording automatically when live
            segment_duration: Auto-split recording every N seconds
            fmt: Video format preference (e.g. "best", "worst")
            post_convert: Remux to this format after recording (e.g. "mp4")
        """
        config = self._load_config()
        rooms = config.get("rooms", [])

        # Remove existing entry for same URL
        rooms = [r for r in rooms if r["url"] != url]

        room = {
            "url": url,
            "name": name or f"room_{len(rooms) + 1}",
            "output_dir": output_dir or str(self.default_output_dir / (name or f"room_{len(rooms) + 1}")),
            "auto_record": auto_record,
            "segment_duration": segment_duration,
            "fmt": fmt,
            "post_convert": post_convert,
            "added_at": datetime.now().isoformat(),
        }
        rooms.append(room)
        config["rooms"] = rooms
        self._save_config(config)
        return room

    def remove_room(self, url: str) -> bool:
        """Remove a room from monitoring. Returns True if found."""
        config = self._load_config()
        original_len = len(config.get("rooms", []))
        config["rooms"] = [r for r in config["rooms"] if r["url"] != url]
        self._save_config(config)
        return len(config["rooms"]) < original_len

    def list_rooms(self) -> list[dict]:
        """Return all monitored rooms."""
        return self._load_config().get("rooms", [])

    def get_room(self, url: str) -> Optional[dict]:
        """Get config for a specific room."""
        for r in self.list_rooms():
            if r["url"] == url:
                return r
        return None

    # ── Recording Control ──────────────────────────────────────────────

    def _is_live_now(self, url: str) -> bool:
        """Quick live check with error handling."""
        try:
            info = self.engine.extract_info(url)
            return bool(info.get("is_live"))
        except Exception:
            return False

    def _start_recording(self, room: dict) -> subprocess.Popen:
        """Start a yt-dlp subprocess to record the stream."""
        url = room["url"]
        out_dir = Path(room["output_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)

        # Build timestamped filename
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"{room['name']}_{ts}"

        opts = self.engine._base_opts(url)
        opts.update({
            "live_from_start": True,
            "outtmpl": str(out_dir / f"{name}.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
        })

        fmt = room.get("fmt")
        if fmt and self.engine._platform(url) != "bilibili":
            opts["format"] = fmt

        # Segment duration via max_filesize approximation or subprocess timeout
        segment = room.get("segment_duration")

        # Write opts to temp file for subprocess
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(opts, f)
            opts_file = f.name

        cmd = [
            sys.executable, "-c",
            f"""
import json, sys
from yt_dlp import YoutubeDL
with open({repr(opts_file)}) as f:
    opts = json.load(f)
with YoutubeDL(opts) as ydl:
    ydl.download([{repr(url)}])
"""
        ]

        # Start recording process
        if segment:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Schedule kill after segment_duration
            def _kill_after():
                time.sleep(segment)
                if proc.poll() is None:
                    proc.terminate()
                    time.sleep(2)
                    if proc.poll() is None:
                        proc.kill()
            threading.Thread(target=_kill_after, daemon=True).start()
        else:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        return proc

    def _stop_recording(self, url: str) -> bool:
        """Stop the recording process for a URL."""
        state = self._load_state()
        recordings = state.get("recordings", {})
        rec = recordings.get(url)
        if not rec:
            return False

        pid = rec.get("pid")
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(1)
                try:
                    os.kill(pid, 0)  # Check if still alive
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            except ProcessLookupError:
                pass

        rec["status"] = "stopped"
        rec["stopped_at"] = datetime.now().isoformat()
        self._save_state(state)
        return True

    def _run_post_convert(self, room: dict, recorded_file: Path) -> Path:
        """Remux recorded file to target format if specified."""
        target_fmt = room.get("post_convert")
        if not target_fmt:
            return recorded_file

        import shutil
        if not shutil.which("ffmpeg"):
            print(f"[WARN] ffmpeg not found, skipping post-convert for {recorded_file}")
            return recorded_file

        out_path = recorded_file.with_suffix(f".{target_fmt}")
        cmd = [
            "ffmpeg", "-y", "-i", str(recorded_file),
            "-c", "copy",
            str(out_path)
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            recorded_file.unlink()  # Remove original
            return out_path
        except subprocess.CalledProcessError as e:
            print(f"[WARN] Post-convert failed: {e}")
            return recorded_file

    # ── Main Monitor Loop ──────────────────────────────────────────────

    def _monitor_loop(self, check_interval: int = 60) -> None:
        """Background thread: poll rooms and auto-record."""
        print(f"[Monitor] Started with check_interval={check_interval}s")

        while not self._stop_event.is_set():
            config = self._load_config()
            state = self._load_state()
            recordings = state.setdefault("recordings", {})

            for room in config.get("rooms", []):
                url = room["url"]
                if not room.get("auto_record", True):
                    continue

                rec = recordings.get(url)
                is_currently_recording = rec and rec.get("status") == "recording"

                if self._is_live_now(url):
                    if not is_currently_recording:
                        print(f"[Monitor] {room['name']} is LIVE! Starting recording...")
                        try:
                            proc = self._start_recording(room)
                            recordings[url] = {
                                "status": "recording",
                                "pid": proc.pid,
                                "started_at": datetime.now().isoformat(),
                                "output_dir": room["output_dir"],
                                "room_name": room["name"],
                            }
                            self._save_state(state)

                            if self.on_live_start:
                                self.on_live_start(url, room)
                        except Exception as e:
                            print(f"[Monitor] Failed to start recording for {room['name']}: {e}")
                            if self.on_record_error:
                                self.on_record_error(url, str(e))
                else:
                    if is_currently_recording:
                        # Stream went offline — stop recording and post-process
                        print(f"[Monitor] {room['name']} went offline. Stopping recording...")
                        self._stop_recording(url)

                        # Find the recorded file
                        out_dir = Path(room["output_dir"])
                        recent_files = sorted(
                            [f for f in out_dir.iterdir() if f.is_file()],
                            key=lambda p: p.stat().st_mtime,
                            reverse=True,
                        )
                        if recent_files:
                            recorded = recent_files[0]
                            converted = self._run_post_convert(room, recorded)
                            print(f"[Monitor] Saved: {converted}")
                            if self.on_record_done:
                                self.on_record_done(url, converted)

            state["last_check"] = datetime.now().isoformat()
            self._save_state(state)

            # Wait for next check or stop signal
            self._stop_event.wait(check_interval)

        print("[Monitor] Stopped.")

    # ── Public Control ─────────────────────────────────────────────────

    def start(self, check_interval: int = 60) -> None:
        """Start the background monitor thread."""
        if self._monitor_thread and self._monitor_thread.is_alive():
            print("[Monitor] Already running.")
            return

        self._stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(check_interval,),
            daemon=True,
        )
        self._monitor_thread.start()

    def stop(self) -> None:
        """Signal the monitor thread to stop."""
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)

    def is_running(self) -> bool:
        """Check if monitor thread is active."""
        return self._monitor_thread is not None and self._monitor_thread.is_alive()

    def list_active_recordings(self) -> list[dict]:
        """Return currently running recordings."""
        state = self._load_state()
        recordings = state.get("recordings", {})
        active = []
        for url, rec in recordings.items():
            if rec.get("status") == "recording":
                # Verify process is still alive
                pid = rec.get("pid")
                if pid:
                    try:
                        os.kill(pid, 0)
                        active.append({"url": url, **rec})
                    except ProcessLookupError:
                        rec["status"] = "crashed"
                        self._save_state(state)
        return active

    def force_stop_recording(self, url: str) -> bool:
        """Force-stop a recording and run post-convert."""
        room = self.get_room(url)
        if not room:
            return False

        stopped = self._stop_recording(url)
        if stopped:
            out_dir = Path(room["output_dir"])
            recent_files = sorted(
                [f for f in out_dir.iterdir() if f.is_file()],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if recent_files:
                self._run_post_convert(room, recent_files[0])
        return stopped
