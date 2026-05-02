# MCP Tools Reference

The MCP server (`mcp_server.py`) exposes 25 tools. Register it in `~/.kimi/mcp.json`:

```json
{
  "mcpServers": {
    "yt-dlp-kit": {
      "command": "python",
      "args": ["C:/code/yt-dlp-kit/mcp_server.py"]
    }
  }
}
```

## Basic Download (6 tools)

| Tool | Purpose | Key Params |
|------|---------|-----------|
| `download_video` | Download video | `url`, `format_spec` (e.g. `best[height<=720]`) |
| `extract_audio` | Extract audio track | `audio_format` (mp3/m4a/opus/flac), `audio_quality` |
| `get_video_info` | Metadata without download | returns title, duration, views, thumbnail |
| `list_formats` | List all quality formats | returns resolution, codec, bitrate |
| `preview_video` | Local preview server | `file_path` → returns browser URL |
| `list_downloads` | List files in downloads/ | returns name, size, path |

## Archive Sync (2 tools)

| Tool | Purpose |
|------|---------|
| `preview_sync` | Preview which videos are new (not in archive) |
| `sync_archive` | Incrementally download only new videos |

Both use `archive.txt` to track already-downloaded IDs. Use `date_after` to filter by upload date.

## Subtitles & Thumbnails (3 tools)

| Tool | Purpose |
|------|---------|
| `download_subtitles` | Download subtitles (manual + auto-generated) |
| `download_danmaku` | Download Bilibili bullet comments as XML |
| `download_thumbnail` | Download best-quality thumbnail |

## Live Stream Monitor (8 tools)

| Tool | Purpose |
|------|---------|
| `check_live` | Check if URL is streaming live |
| `add_live_monitor` | Add room to background monitor |
| `list_monitored_rooms` | List all monitored rooms |
| `remove_live_monitor` | Remove room from monitoring |
| `start_live_monitor` | Start background auto-record thread |
| `stop_live_monitor` | Stop monitor thread |
| `get_monitor_status` | Get active recordings + status |
| `force_stop_recording` | Force-stop a recording by URL |

Monitor config/state is persisted to `live_monitor_config.json` and `live_monitor_state.json`.

## Video Processing (5 tools)

| Tool | Purpose | ffmpeg Operation |
|------|---------|-----------------|
| `remux_video` | Container conversion (webm→mp4) | `-c copy` |
| `cut_video` | Cut segment | `-ss -t` |
| `concat_videos` | Merge multiple files | `concat demuxer` → fallback `filter_complex` |
| `extract_frames` | Extract frames at intervals | `-vf fps=1/N` |
| `get_media_info` | Media metadata | `ffprobe` |

Requires ffmpeg and ffprobe in PATH.

## Chapter (1 tool)

| Tool | Purpose |
|------|---------|
| `list_chapters` | List video chapter markers |
