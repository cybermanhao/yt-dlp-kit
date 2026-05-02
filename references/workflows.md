# Extended Workflows

For basic workflows (batch collection, audio extraction, metadata), see SKILL.md.

## Archive Sync

Incrementally download only new videos.

```python
from features.archive_sync import ArchiveSync

sync = ArchiveSync(archive_file="archive.txt", output_dir="downloads")

# Preview what would be downloaded
result = sync.preview_sync(
    "https://www.youtube.com/@shamio/videos",
    limit=20,
    date_after="today-7days"
)
print(f"New videos: {result['new_count']}")

# Actually sync
sync.sync(
    "https://www.youtube.com/@shamio/videos",
    limit=20,
    date_after="today-7days"
)
```

CLI equivalent:
```bash
yt-dlp --download-archive archive.txt --dateafter today-7days \
  -o "downloads/%(title)s [%(id)s].%(ext)s" "URL"
```

## Subtitle & Danmaku

```python
from features.subtitle_grabber import SubtitleGrabber

grabber = SubtitleGrabber(output_dir="subtitles")

# Download subtitles
files = grabber.download_subtitles(
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    languages=["en", "zh-CN"],
    auto_generated=True
)

# Download Bilibili danmaku
xml_path = grabber.download_danmaku("BV1YpGHzcEs4")
srt_path = grabber.danmaku_to_srt(xml_path)
```

## Thumbnail Batch

```python
from features.thumbnail_batch import ThumbnailBatch

batch = ThumbnailBatch(output_dir="thumbnails")

# Get thumbnail URL without downloading
info = batch.get_thumbnail_info("URL")
print(info["thumbnail_url"])

# Download thumbnail
batch.download_thumbnail("URL", convert_to="jpg")

# Batch download from playlist
batch.download_playlist_thumbnails("PLAYLIST_URL", limit=50)
```

## Live Stream Auto-Recording

```bash
# Add rooms
python live_monitor.py add "https://live.bilibili.com/ROOM_ID" --name "主播A" --segment 3600
python live_monitor.py add "https://www.youtube.com/@LinusTechTips/live" --name "LTT" --convert mp4

# Start monitoring
python live_monitor.py start --interval 60

# Check status
python live_monitor.py status
```

Programmatic:
```python
from features.live_monitor import LiveMonitor

monitor = LiveMonitor()
monitor.add_room("https://live.bilibili.com/6", name="Test", segment_duration=3600)
monitor.on_live_start = lambda url, room: print(f"LIVE: {room['name']}")
monitor.on_record_done = lambda url, path: print(f"Saved: {path}")
monitor.start(check_interval=60)
```

## Video Post-Processing

```python
from features.video_processor import VideoProcessor

proc = VideoProcessor()

# Remux webm → mp4 (lossless)
proc.remux("video.webm", output_format="mp4")

# Cut segment (stream copy, fast)
proc.cut("video.mp4", start=30.0, end=120.0)

# Cut with re-encode (frame-accurate)
proc.cut("video.mp4", start=30.0, end=120.0, reencode=True)

# Concatenate files
proc.concat(["part1.mp4", "part2.mp4"], "merged.mp4")

# Extract frames every 5 seconds
proc.extract_frames("video.mp4", interval=5.0, max_frames=20)

# Get media info
info = proc.get_media_info("video.mp4")
```

## Chapter Splitting

```python
from features.chapter_split import ChapterSplitter

splitter = ChapterSplitter(output_dir="chapters")
chapters = splitter.list_chapters("URL")
for ch in chapters:
    print(f"{ch['start_time']:.0f}s - {ch['title']}")

files = splitter.split("URL")
```

CLI:
```bash
yt-dlp --split-chapters \
  -o "chapter:%(section_number)s - %(section_title)s.%(ext)s" \
  "URL"
```
