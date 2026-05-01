"""Standalone live monitor CLI.

Usage:
    python live_monitor.py add <url> [--name NAME] [--output-dir DIR] [--segment SECONDS]
    python live_monitor.py list
    python live_monitor.py remove <url>
    python live_monitor.py start [--interval SECONDS]
    python live_monitor.py stop
    python live_monitor.py status
    python live_monitor.py force-stop <url>

Examples:
    python live_monitor.py add "https://live.bilibili.com/6" --name "B站官方测试" --segment 3600
    python live_monitor.py add "https://www.youtube.com/@LinusTechTips/live" --name "LTT"
    python live_monitor.py start --interval 30
    python live_monitor.py status
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from features.live_monitor import LiveMonitor


def cmd_add(args):
    monitor = LiveMonitor()
    room = monitor.add_room(
        url=args.url,
        name=args.name,
        output_dir=args.output_dir,
        auto_record=not args.no_auto,
        segment_duration=args.segment,
        fmt=args.format,
        post_convert=args.convert,
    )
    print(f"[OK] Added room: {room['name']} -> {room['url']}")
    print(f"     Output: {room['output_dir']}")
    if room['segment_duration']:
        print(f"     Segment: {room['segment_duration']}s")


def cmd_list(args):
    monitor = LiveMonitor()
    rooms = monitor.list_rooms()
    if not rooms:
        print("No rooms configured.")
        return

    state = monitor._load_state()
    recordings = state.get("recordings", {})

    print(f"{'Name':<20} {'URL':<45} {'Auto':<6} {'Status':<12} {'Started'}")
    print("-" * 110)
    for r in rooms:
        rec = recordings.get(r["url"], {})
        status = rec.get("status", "idle")
        started = rec.get("started_at", "-")[:19] if rec.get("started_at") else "-"
        print(f"{r['name']:<20} {r['url']:<45} {str(r.get('auto_record', True)):<6} {status:<12} {started}")


def cmd_remove(args):
    monitor = LiveMonitor()
    if monitor.remove_room(args.url):
        print(f"[OK] Removed: {args.url}")
    else:
        print(f"[WARN] Room not found: {args.url}")


def cmd_start(args):
    monitor = LiveMonitor()

    def on_live(url, room):
        print(f"\n[ALERT] {room['name']} is LIVE! Recording started.")

    def on_done(url, path):
        print(f"\n[DONE] Recording saved: {path}")

    monitor.on_live_start = on_live
    monitor.on_record_done = on_done

    rooms = monitor.list_rooms()
    if not rooms:
        print("No rooms configured. Add one first with: python live_monitor.py add <url>")
        sys.exit(1)

    print(f"[Monitor] Starting with {len(rooms)} room(s), check every {args.interval}s")
    print("[Monitor] Press Ctrl+C to stop\n")
    monitor.start(check_interval=args.interval)

    try:
        while monitor.is_running():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Monitor] Stopping...")
        monitor.stop()
        print("[Monitor] Stopped.")


def cmd_stop(args):
    monitor = LiveMonitor()
    monitor.stop()
    print("[OK] Monitor stopped.")


def cmd_status(args):
    monitor = LiveMonitor()
    active = monitor.list_active_recordings()
    rooms = monitor.list_rooms()

    print(f"Monitor running: {monitor.is_running()}")
    print(f"Monitored rooms: {len(rooms)}")
    print(f"Active recordings: {len(active)}")

    if active:
        print("\nActive recordings:")
        for rec in active:
            print(f"  - {rec.get('room_name', 'unknown')} ({rec['url']})")
            print(f"    Started: {rec.get('started_at', '?')}")
            print(f"    PID: {rec.get('pid', '?')}")
            print(f"    Output: {rec.get('output_dir', '?')}")


def cmd_force_stop(args):
    monitor = LiveMonitor()
    if monitor.force_stop_recording(args.url):
        print(f"[OK] Recording stopped for: {args.url}")
    else:
        print(f"[WARN] No active recording for: {args.url}")


def main():
    parser = argparse.ArgumentParser(description="Live stream monitor and auto-recorder")
    sub = parser.add_subparsers(dest="command")

    # add
    p_add = sub.add_parser("add", help="Add a live room to monitor")
    p_add.add_argument("url", help="Live stream URL")
    p_add.add_argument("--name", help="Room name")
    p_add.add_argument("--output-dir", help="Output directory")
    p_add.add_argument("--no-auto", action="store_true", help="Don't auto-record")
    p_add.add_argument("--segment", type=int, help="Auto-split every N seconds")
    p_add.add_argument("--format", help="Format preference (best, worst, etc.)")
    p_add.add_argument("--convert", help="Post-convert to format (mp4, mkv, etc.)")

    # list
    sub.add_parser("list", help="List monitored rooms")

    # remove
    p_remove = sub.add_parser("remove", help="Remove a room")
    p_remove.add_argument("url", help="Room URL to remove")

    # start
    p_start = sub.add_parser("start", help="Start monitoring")
    p_start.add_argument("--interval", type=int, default=60, help="Check interval in seconds")

    # stop
    sub.add_parser("stop", help="Stop monitoring")

    # status
    sub.add_parser("status", help="Show monitor status")

    # force-stop
    p_fs = sub.add_parser("force-stop", help="Force stop a recording")
    p_fs.add_argument("url", help="Room URL")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "add": cmd_add,
        "list": cmd_list,
        "remove": cmd_remove,
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
        "force-stop": cmd_force_stop,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
