# Platform-Specific Notes

## Bilibili

### Critical Rules

| Rule | Detail |
|------|--------|
| **NO `-f` flag** | Bilibili serves separate audio/video streams. Passing `-f` (even `-f best`) causes "Requested format is not available". Omit `-f` entirely. |
| **Cookie required** | Most operations return HTTP 412 without valid cookies. |
| **Get cookie** | Run `python get_bili_cookie.py` — auto-detects Chrome/Edge login or opens browser for QR scan. |

### Supported URLs

- Video: `bilibili.com/video/BVxxxxx`
- User space: `space.bilibili.com/<UID>`
- Collection: `space.bilibili.com/<UID>/channel/collectiondetail?sid=<SID>`
- Series: `space.bilibili.com/<UID>/channel/seriesdetail?sid=<SID>`
- Favorites: `space.bilibili.com/<UID>/favlist?fid=<FID>`
- Live: `live.bilibili.com/<ROOM_ID>`

### Search Workarounds

Global Bilibili keyword search (`bilisearchN:keyword`) is unstable (412). Use `bilibili_tools.py` instead:

```bash
# Find user by name
python bilibili_tools.py search_user "锦恢"

# Filter user's videos by keyword (client-side)
python bilibili_tools.py search_user_kw "OpenMCP" --uid 434469188 --limit 10
```

## YouTube

### Format Selection

`-f` works normally. Common patterns:

```bash
-f best[height<=720]          # Best 720p
-f bestvideo+bestaudio        # Separate streams, merged by ffmpeg
-f bestaudio                  # Audio only
```

### JS Runtime for High Quality

Without Node.js/Deno → only 360p MP4 + ~128k AAC.
With Node.js → unlocks `bestaudio` opus (160k+) and up to 4K.

```bash
# Check if Node.js is available
node --version

# Use with yt-dlp
yt-dlp --js-runtimes node -f bestaudio "URL"
```

Install Deno if Node.js unavailable:
```powershell
irm https://deno.land/install.ps1 | iex
```

### Public Videos

No auth needed for public videos. Members-only requires `--cookies-from-browser` or exported cookies.
