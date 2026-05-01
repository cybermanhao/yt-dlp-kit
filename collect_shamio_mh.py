#!/usr/bin/env python3
"""
Collect all Monster Hunter videos from YouTube user @shamio
and download them with best-quality audio extraction.
"""
import os
import sys
import re
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
os.environ['PYTHONIOENCODING'] = 'utf-8'

from yt_dlp import YoutubeDL

OUTPUT_DIR = Path(__file__).parent / 'downloads' / 'shamio_monster_hunter'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Keywords to match Monster Hunter videos
MH_KEYWORDS = [
    'monster hunter',
    'monsterhunter',
]

EXCLUDE_KEYWORDS = [
    'beastars',  # false positive
]


def is_monster_hunter(title):
    t = title.lower()
    if any(k in t for k in EXCLUDE_KEYWORDS):
        return False
    return any(k in t for k in MH_KEYWORDS)


def get_channel_videos(channel_url):
    """Get all videos from a YouTube channel."""
    opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'playlistend': 500,  # get up to 500 videos
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)
    videos = []
    for entry in info.get('entries', []):
        title = entry.get('title', '')
        vid = entry.get('id', '')
        if title and vid:
            videos.append({'title': title, 'id': vid, 'url': f'https://www.youtube.com/watch?v={vid}'})
    return videos


def filter_videos(videos):
    """Filter videos by Monster Hunter keywords."""
    matched = []
    for v in videos:
        if is_monster_hunter(v['title']):
            matched.append(v)
    return matched


def download_with_audio(video_urls, output_dir):
    """Download videos and extract best-quality audio."""
    opts = {
        'quiet': False,
        'no_warnings': True,
        'outtmpl': str(output_dir / '%(title)s [%(id)s].%(ext)s'),
        'format': 'best[height<=720]',  # limit video to 720p to save space
        'extract_audio': True,
        'audio_quality': '0',  # best audio quality
        'audio_format': 'best',  # best available format
        'keep_video': True,  # keep both video and audio
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'best',
            'preferredquality': '0',
        }],
    }
    with YoutubeDL(opts) as ydl:
        for url in video_urls:
            print(f"\nDownloading: {url}")
            try:
                ydl.download([url])
            except Exception as e:
                print(f"Error downloading {url}: {e}")


def main():
    print("=== Step 1: Fetching @shamio video list ===")
    videos = get_channel_videos('https://www.youtube.com/@shamio/videos')
    print(f"Total videos in channel: {len(videos)}")

    print("\n=== Step 2: Filtering Monster Hunter videos ===")
    matched = filter_videos(videos)
    print(f"Matched {len(matched)} Monster Hunter videos:")
    for i, v in enumerate(matched, 1):
        print(f"  {i}. {v['title']}")

    if not matched:
        print("No videos matched. Exiting.")
        return

    # Save URL list for batch download
    url_file = OUTPUT_DIR / 'urls.txt'
    url_file.write_text('\n'.join(v['url'] for v in matched), encoding='utf-8')
    print(f"\nURL list saved to: {url_file}")

    print(f"\n=== Step 3: Downloading {len(matched)} videos + best audio ===")
    print(f"Output directory: {OUTPUT_DIR}")
    urls = [v['url'] for v in matched]
    download_with_audio(urls, OUTPUT_DIR)

    print("\n=== Done ===")
    print(f"Files saved in: {OUTPUT_DIR}")


if __name__ == '__main__':
    main()
