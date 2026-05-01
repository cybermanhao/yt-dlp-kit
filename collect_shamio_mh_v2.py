#!/usr/bin/env python3
"""
Collect shamio Monster Hunter videos with best quality.
Video -> C:/ytbdl/video
Audio -> C:/ytbdl/music
Uses Node.js as JS runtime for full format access.
"""
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
os.environ['PYTHONIOENCODING'] = 'utf-8'

from yt_dlp import YoutubeDL

VIDEO_DIR = Path("C:/ytbdl/video")
MUSIC_DIR = Path("C:/ytbdl/music")
VIDEO_DIR.mkdir(parents=True, exist_ok=True)
MUSIC_DIR.mkdir(parents=True, exist_ok=True)

MH_KEYWORDS = ['monster hunter', 'monsterhunter']
EXCLUDE = ['beastars']


def is_mh(title):
    t = title.lower()
    return any(k in t for k in MH_KEYWORDS) and not any(k in t for k in EXCLUDE)


def get_videos():
    opts = {
        'quiet': True, 'no_warnings': True,
        'extract_flat': True, 'playlistend': 500,
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info('https://www.youtube.com/@shamio/videos', download=False)
    return [v for v in info.get('entries', []) if is_mh(v.get('title', ''))]


def download_video_and_audio(videos):
    """Download video to video dir, extract best audio to music dir."""
    urls = [f"https://www.youtube.com/watch?v={v['id']}" for v in videos]

    # Step 1: Download videos (best 720p) to video dir
    print("=== Downloading videos to C:/ytbdl/video ===")
    video_opts = {
        'quiet': False,
        'no_warnings': True,
        'js_runtimes': {'node': {}},
        'format': 'best[height<=720]',
        'outtmpl': str(VIDEO_DIR / '%(title)s [%(id)s].%(ext)s'),
    }
    with YoutubeDL(video_opts) as ydl:
        for url in urls:
            print(f"\n[VIDEO] {url}")
            try:
                ydl.download([url])
            except Exception as e:
                print(f"Skip: {e}")

    # Step 2: Extract best audio to music dir
    print("\n=== Extracting best audio to C:/ytbdl/music ===")
    audio_opts = {
        'quiet': False,
        'no_warnings': True,
        'js_runtimes': {'node': {}},
        'format': 'bestaudio/best',
        'outtmpl': str(MUSIC_DIR / '%(title)s [%(id)s].%(ext)s'),
        'extract_audio': True,
        'audio_quality': '0',
        'audio_format': 'best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'best',
            'preferredquality': '0',
        }],
    }
    with YoutubeDL(audio_opts) as ydl:
        for url in urls:
            print(f"\n[AUDIO] {url}")
            try:
                ydl.download([url])
            except Exception as e:
                print(f"Skip: {e}")


def main():
    print("Fetching @shamio video list...")
    videos = get_videos()
    print(f"Found {len(videos)} Monster Hunter videos")
    for i, v in enumerate(videos, 1):
        print(f"  {i}. {v['title']}")

    if not videos:
        return

    download_video_and_audio(videos)
    print("\n=== Done ===")
    print(f"Videos: {VIDEO_DIR}")
    print(f"Music:  {MUSIC_DIR}")


if __name__ == '__main__':
    main()
