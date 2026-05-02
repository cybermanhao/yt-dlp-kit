"""Demo: Download 锦恢's OpenMCP videos from Bilibili."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from bilibili_tools import search_user, search_user_keyword_videos
from core.downloader import YTDlpEngine

print("=" * 60)
print('Demo: Bilibili User "锦恢" OpenMCP Videos')
print("=" * 60)

# 1. Search user
print("\n[1/3] Searching user '锦恢'...")
users = search_user("锦恢")
if not users:
    print("    User not found!")
    sys.exit(1)

user = users[0]
uid = user["uid"]
print(f"    Found: {user['uname']} (UID={uid}, Videos={user.get('videos', '?')})")

# 2. Filter by keyword "OpenMCP"
print('\n[2/3] Filtering videos by keyword "OpenMCP"...')
videos = search_user_keyword_videos(uid, "OpenMCP", limit=10)
print(f"    Matched {len(videos)} videos:")
for v in videos:
    print(f"      - {v['bvid']}: {v['title'][:50]}...")

# 3. Download
print("\n[3/3] Downloading with cookies (no -f flag)...")
engine = YTDlpEngine(output_dir="downloads/jinhui_openmcp")
for v in videos[:2]:  # Limit to 2 for demo
    bvid = v['bvid']
    url = f"https://www.bilibili.com/video/{bvid}"
    print(f"    Downloading: {bvid}")
    try:
        engine.download(url)
        print(f"    OK: {bvid}")
    except Exception as e:
        print(f"    Error: {e}")

print("\n" + "=" * 60)
print("Demo complete!")
print("=" * 60)
