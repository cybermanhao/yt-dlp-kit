import urllib.request
import urllib.parse
import json
import sys
import os
from pathlib import Path

# Force UTF-8 output on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
os.environ['PYTHONIOENCODING'] = 'utf-8'

COOKIES_FILE = Path(__file__).parent / 'bilibili_cookies.txt'

def load_cookies():
    """Load cookies from Netscape format file."""
    if not COOKIES_FILE.exists():
        return {}
    cookies = {}
    for line in COOKIES_FILE.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split('\t')
        if len(parts) >= 7:
            cookies[parts[5]] = parts[6]
    return cookies


def cookie_header():
    cookies = load_cookies()
    if cookies:
        return '; '.join(f"{k}={v}" for k, v in cookies.items())
    return ''


def search_user(name):
    keyword = urllib.parse.quote(name)
    url = f'https://api.bilibili.com/x/web-interface/search/type?keyword={keyword}&search_type=bili_user'
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    req.add_header('Referer', 'https://search.bilibili.com')
    ck = cookie_header()
    if ck:
        req.add_header('Cookie', ck)
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
                'sign': user.get('usign', '')[:60],
            })
    return results

def search_user_videos(uid, keyword, limit=5):
    """Search videos within a specific user's space."""
    kw = urllib.parse.quote(keyword)
    # Bilibili search API with mid filter
    url = f'https://api.bilibili.com/x/space/wbi/arc/search?mid={uid}&keyword={kw}&ps={limit}&pn=1'
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    req.add_header('Referer', f'https://space.bilibili.com/{uid}')
    ck = cookie_header()
    if ck:
        req.add_header('Cookie', ck)
    resp = urllib.request.urlopen(req)
    data = json.loads(resp.read())
    results = []
    if data.get('data', {}).get('list', {}).get('vlist'):
        for v in data['data']['list']['vlist'][:limit]:
            results.append({
                'bvid': v.get('bvid'),
                'title': v.get('title'),
                'duration': v.get('length'),
                'description': v.get('description', '')[:80],
            })
    return results

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python search_bili_user.py <username> [uid] [video_keyword]")
        sys.exit(1)
    
    username = sys.argv[1]
    users = search_user(username)
    print(f"Found {len(users)} users matching '{username}':")
    for u in users:
        print(f"  UID={u['uid']} | Videos={u['videos']} | Fans={u['fans']} | {u['uname']}")
        print(f"    Sign: {u['sign']}")
    
    if len(sys.argv) >= 4 and users:
        uid = sys.argv[2]
        video_kw = sys.argv[3]
        print(f"\nSearching videos by UID={uid} with keyword='{video_kw}':")
        videos = search_user_videos(uid, video_kw)
        for v in videos:
            print(f"  [{v['bvid']}] {v['title']} ({v['duration']})")
