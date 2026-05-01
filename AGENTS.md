# yt-dlp-kit

Video download and preview MCP server powered by yt-dlp.

## Project Structure

```
yt-dlp-kit/
├── SKILL.md              # yt-dlp skill reference
├── mcp_server.py         # MCP server (FastMCP + Flask preview)
├── PLAN-MCP.md           # MCP architecture design
├── pyproject.toml        # Python project config
├── downloads/            # Default download directory
└── reference/            # yt-dlp source code (git submodule)
```

## MCP Server Registration

Add to `~/.kimi/mcp.json`:

```json
{
  "mcpServers": {
    "yt-dlp-kit": {
      "command": "python",
      "args": ["C:/code/yt-dlp-kit/mcp_server.py"],
      "env": {
        "PROJECT_ROOT": "C:/code/yt-dlp-kit"
      }
    }
  }
}
```

Or run directly:
```bash
cd C:/code/yt-dlp-kit
python mcp_server.py
```

## Tools

| Tool | Description |
|------|-------------|
| `download_video` | Download video from URL |
| `extract_audio` | Extract audio track to MP3/M4A/OPUS/WAV |
| `get_video_info` | Get metadata (title, duration, uploader, thumbnail) |
| `list_formats` | List all available formats |
| `preview_video` | Start local preview server, return browser URL |
| `list_downloads` | List files in downloads directory |

## Bilibili-Specific Tools (`bilibili_tools.py`)

| Command | Description |
|---------|-------------|
| `search_user <name>` | Search Bilibili users by name |
| `list_videos <uid> --limit N` | List videos from a user's space |
| `search <keyword> --limit N` | Search videos by keyword (global) |
| `search_user_kw <keyword> --uid <uid>` | Search videos within a specific user |
| `info <bvid>` | Get metadata for a single video |

### Bilibili Workflow Example

```bash
# 1. Search user by name
python bilibili_tools.py search_user "锦恢"
# → UID=434469188

# 2. List their videos
python bilibili_tools.py list_videos 434469188 --limit 10

# 3. Search for specific topic within their videos
python bilibili_tools.py search_user_kw "OpenMCP" --uid 434469188 --limit 5

# 4. Download matched videos
python -c "from bilibili_tools import download_videos; download_videos(['BV1YpGHzcEs4'])"
```

## Preview Server

`preview_video(file_path)` starts a Flask server on a random localhost port and returns a URL like:
```
http://127.0.0.1:11248/preview/Me%20at%20the%20zoo%20%5BjNQXAC9IVRw%5D.mp4
```

The preview page includes:
- Dark-themed video player with controls
- File metadata (MIME type, size, path)
- Auto-play on open

## Dependencies

- Python 3.10+
- `pip install mcp flask yt-dlp`
- (Optional) FFmpeg for audio extraction and format merging

## Skill Usage

For command-line yt-dlp usage without MCP, refer to `SKILL.md`.
