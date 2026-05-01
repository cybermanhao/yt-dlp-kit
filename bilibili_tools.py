#!/usr/bin/env python3
"""
Bilibili utility tools powered by yt-dlp.
Handles WBI signing, cookies, and format merging automatically.
"""
import os
import sys
import json
import re
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
os.environ['PYTHONIOENCODING'] = 'utf-8'

from yt_dlp import YoutubeDL

COOKIES_FILE = Path(__file__).parent / 'bilibili_cookies.txt'
DL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'cookiefile': str(COOKIES_FILE) if COOKIES_FILE.exists() else None,
}


def _suppress_stdout(func, *args, **kwargs):
    import contextlib
    with open(os.devnull, 'w') as devnull:
        with contextlib.redirect_stdout(devnull):
            return func(*args, **kwargs)


def search_user(name):
    """Search Bilibili users by name. Returns list of user dicts."""
    import urllib.request, urllib.parse
    keyword = urllib.parse.quote(name)
    url = f'https://api.bilibili.com/x/web-interface/search/type?keyword={keyword}&search_type=bili_user'
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    req.add_header('Referer', 'https://search.bilibili.com')
    if COOKIES_FILE.exists():
        cookies = {}
        for line in COOKIES_FILE.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) >= 7:
                cookies[parts[5]] = parts[6]
        if cookies:
            req.add_header('Cookie', '; '.join(f"{k}={v}" for k, v in cookies.items()))
    resp = urllib.request.urlopen(req)
    data = json.loads(resp.read())
    results = []
    if data.get('data', {}).get('result'):
        for user in data['data']['result'][:5]:
            results.append({
                'uid': user.get('mid'),
                'uname': user.get('uname'),
                'videos': user.get('videos'),
                'fans': user.get('fans'),
                'sign': user.get('usign', '')[:80],
            })
    return results


def list_user_videos(uid, limit=20):
    """List videos from a user's space. Returns list of video dicts."""
    url = f'https://space.bilibili.com/{uid}/video'
    opts = {**DL_OPTS, 'playlistend': limit}
    with YoutubeDL(opts) as ydl:
        info = _suppress_stdout(ydl.extract_info, url, download=False)
    results = []
    for entry in info.get('entries', [])[:limit]:
        results.append({
            'bvid': entry.get('id'),
            'title': entry.get('title'),
            'url': entry.get('url'),
        })
    return results


def search_keyword_videos(keyword, limit=10):
    """Search Bilibili videos by keyword. Returns list of video dicts."""
    import subprocess, sys
    url = f'bilisearch{limit}:{keyword}'
    result = subprocess.run(
        [sys.executable, '-m', 'yt_dlp', '--cookies', str(COOKIES_FILE),
         '--flat-playlist', '--playlist-items', f'1-{limit}',
         '--print', '%(title)s\t%(id)s', url],
        capture_output=True, text=True, cwd=str(Path(__file__).parent / 'reference')
    )
    results = []
    for line in result.stdout.strip().split('\n'):
        if '\t' in line:
            title, bvid = line.split('\t', 1)
            results.append({
                'bvid': bvid,
                'title': title if title != 'NA' else None,
                'url': f'https://www.bilibili.com/video/{bvid}',
            })
    return results


def search_user_keyword_videos(uid, keyword, limit=10):
    """Search videos from a specific user matching a keyword."""
    videos = list_user_videos(uid, limit=50)  # fetch more for filtering
    kw_lower = keyword.lower()
    results = [v for v in videos if kw_lower in v.get('title', '').lower()]
    return results[:limit]


def get_video_info(bvid):
    """Get metadata for a single video."""
    url = f'https://www.bilibili.com/video/{bvid}'
    with YoutubeDL(DL_OPTS) as ydl:
        info = _suppress_stdout(ydl.extract_info, url, download=False)
    return {
        'title': info.get('title'),
        'duration': info.get('duration'),
        'uploader': info.get('uploader'),
        'view_count': info.get('view_count'),
        'bvid': info.get('id'),
        'thumbnail': info.get('thumbnail'),
    }


def download_videos(urls_or_bvids, output_dir='downloads'):
    """Download one or more videos. urls_or_bvids can be a single URL/BVID or a list."""
    if isinstance(urls_or_bvids, str):
        urls_or_bvids = [urls_or_bvids]
    # Normalize to full URLs
    urls = []
    for item in urls_or_bvids:
        if item.startswith('BV') and len(item) == 12:
            urls.append(f'https://www.bilibili.com/video/{item}')
        elif item.startswith('http'):
            urls.append(item)
        else:
            urls.append(f'https://www.bilibili.com/video/{item}')
    outdir = Path(output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    opts = {
        **DL_OPTS,
        'outtmpl': str(outdir / '%(title)s [%(id)s].%(ext)s'),
    }
    downloaded = []
    with YoutubeDL(opts) as ydl:
        for url in urls:
            info = _suppress_stdout(ydl.extract_info, url, download=True)
            fname = ydl.prepare_filename(info)
            downloaded.append(fname)
    return downloaded


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Bilibili tools')
    parser.add_argument('action', choices=['search_user', 'list_videos', 'search', 'search_user_kw', 'info'])
    parser.add_argument('query')
    parser.add_argument('--uid', type=str, default=None)
    parser.add_argument('--limit', type=int, default=10)
    args = parser.parse_args()

    if args.action == 'search_user':
        for u in search_user(args.query):
            print(f"UID={u['uid']} | Videos={u['videos']} | Fans={u['fans']} | {u['uname']}")
            print(f"  Sign: {u['sign']}")

    elif args.action == 'list_videos':
        for v in list_user_videos(args.query, args.limit):
            print(f"[{v['bvid']}] {v['title']}")

    elif args.action == 'search':
        for v in search_keyword_videos(args.query, args.limit):
            print(f"[{v['bvid']}] {v['title']}")

    elif args.action == 'search_user_kw':
        if not args.uid:
            print("--uid is required for search_user_kw")
            return
        for v in search_user_keyword_videos(args.uid, args.query, args.limit):
            print(f"[{v['bvid']}] {v['title']}")

    elif args.action == 'info':
        info = get_video_info(args.query)
        print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
