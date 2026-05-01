"""Demo: Download shamio Monster Hunter covers from YouTube."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from core.downloader import YTDlpEngine

print("=" * 60)
print("Demo: shamio Monster Hunter Music Download")
print("=" * 60)

engine = YTDlpEngine(output_dir="downloads/shamio_mh")

# 1. Get video list from @shamio channel
print("\n[1/4] Fetching @shamio video list...")
info = engine.extract_info(
    "https://www.youtube.com/@shamio/videos",
    extra_opts={"extract_flat": True, "playlistend": 100, "ignoreerrors": True}
)
entries = info.get("entries", [])
print(f"    Total videos checked: {len(entries)}")

# 2. Filter Monster Hunter titles
print("\n[2/4] Filtering Monster Hunter videos...")
matches = []
for e in entries:
    if not e:
        continue
    title = e.get("title", "")
    if "monster hunter" in title.lower():
        matches.append({
            "title": title,
            "id": e.get("id"),
            "url": f"https://www.youtube.com/watch?v={e.get('id')}"
        })

print(f"    Found {len(matches)} Monster Hunter videos:")
for m in matches:
    print(f"      - {m['title']}")

# 3. Download videos (720p)
print("\n[3/4] Downloading videos (720p)...")
for m in matches[:3]:  # Limit to 3 for demo
    print(f"    Downloading: {m['title'][:50]}...")
    try:
        engine.download(m["url"], fmt="best[height<=720]")
    except Exception as e:
        print(f"    Skip: {e}")

# 4. Extract audio
print("\n[4/4] Extracting audio (best quality)...")
for m in matches[:3]:
    print(f"    Audio: {m['title'][:50]}...")
    try:
        engine.extract_audio(m["url"], output_dir="downloads/shamio_mh/music")
    except Exception as e:
        print(f"    Skip: {e}")

print("\n" + "=" * 60)
print("Demo complete!")
print("=" * 60)
