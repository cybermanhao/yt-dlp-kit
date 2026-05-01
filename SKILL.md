---
name: yt-dlp-kit
description: 基于 yt-dlp 和 ffmpeg 的智能视频采集与处理工具集。当用户需要以下场景时触发：(1) 从 YouTube、Bilibili 或 1000+ 站点下载视频/音频，(2) 批量采集频道/播放列表视频，(3) 增量同步只下载新内容，(4) 提取高质量音频，(5) 下载字幕或 Bilibili 弹幕，(6) 抓取视频缩略图，(7) 监控并自动录制直播流，(8) 裁剪/合并/转封装视频，(9) 获取视频元数据。触发词包括"下载视频"、"批量采集"、"提取音频"、"获取字幕"、"录制直播"、"裁剪视频"、"转封装"、"视频信息"，以及任何包含 youtube.com、bilibili.com、youtu.be 或 live.bilibili.com 的 URL。
examples:
  - prompt: 帮我把 YouTube 上 @shamio 频道里所有 Monster Hunter 相关的视频下载下来，并提取成音频保存到 music 文件夹。
  - prompt: B站用户"锦恢"有哪些关于 OpenMCP 的视频？帮我全部下载下来。
  - prompt: 监控这个 B站直播间，开播了自动录下来，每小时切一个文件。
  - prompt: 我每天想自动下载这个 YouTube 频道的新视频，不要重复下载旧的。
  - prompt: 下载这个视频，然后帮我裁剪出 30 秒到 2 分钟之间的片段，再转成 MP4。
rootUrl: https://raw.githubusercontent.com/cybermanhao/yt-dlp-kit/main/SKILL.md
---

# yt-dlp-kit

## 平台判断

| URL 包含 | 平台 | 关键差异 |
|---------|------|---------|
| `youtube.com`, `youtu.be` | YouTube | 可用 `-f` 选择格式。公开视频无需认证。安装 Node.js 可解锁高音质。 |
| `bilibili.com`, `live.bilibili.com` | Bilibili | **必须使用 cookies**。**禁止传 `-f`**（音视频分离流）。用 `get_bili_cookie.py` 获取认证。 |
| 其他 | 通用 | yt-dlp 支持 1000+ 站点。先用 `get_video_info` 测试。 |

详细平台规则见 [references/platform-notes.md](references/platform-notes.md)。

## 核心工作流

### 批量采集

YouTube：
```bash
yt-dlp --flat-playlist --playlist-items 1-50 --print "%(title)s\t%(id)s" \
  "https://www.youtube.com/@channel/videos" | findstr -i "keyword" > urls.txt

yt-dlp -a urls.txt -f "best[height<=720]" -o "downloads/%(title)s [%(id)s].%(ext)s"
```

Bilibili：
```bash
python bilibili_tools.py search_user "用户名"                    # 获取 UID
python bilibili_tools.py search_user_keyword_videos UID "关键词"   # 获取 BV 号列表
yt-dlp --cookies bilibili_cookies.txt -o "downloads/%(title)s.%(ext)s" "https://www.bilibili.com/video/BVxxxx"
```

> Bilibili 下载时不可传 `-f` 参数。

### 增量归档同步

```python
from features.archive_sync import ArchiveSync
sync = ArchiveSync(archive_file="archive.txt", output_dir="downloads")
sync.sync("https://www.youtube.com/@channel/videos", date_after="today-7days")
```

### 直播自动录制

```bash
python live_monitor.py add "https://live.bilibili.com/房间号" --name "主播A" --segment 3600
python live_monitor.py start --interval 60
```

配置持久化到 `live_monitor_config.json` / `live_monitor_state.json`。

### 视频后处理（ffmpeg）

```python
from features.video_processor import VideoProcessor
proc = VideoProcessor()

proc.remux("video.webm", output_format="mp4")         # 无损转封装
proc.cut("video.mp4", start=30.0, end=120.0)           # 快速裁剪
proc.concat(["part1.mp4", "part2.mp4"], "out.mp4")     # 合并视频
proc.extract_frames("video.mp4", interval=5.0)         # 抽帧
```

## Usage Examples

### Example 1

**User:** 帮我把 YouTube 上 @shamio 频道里所有 Monster Hunter 相关的视频下载下来，并提取成音频保存到 music 文件夹。

**AI:** 我来帮你批量采集 shamio 的 Monster Hunter 视频并提取音频。

1. 获取频道视频列表并过滤 Monster Hunter：
   ```python
   from core.downloader import YTDlpEngine
   engine = YTDlpEngine(output_dir="downloads/shamio_mh")
   info = engine.extract_info(
       "https://www.youtube.com/@shamio/videos",
       extra_opts={"extract_flat": True, "playlistend": 100, "ignoreerrors": True}
   )
   matches = [e for e in info.get("entries", []) if e and "monster hunter" in e.get("title","").lower()]
   ```

2. 下载视频（720p）：
   ```python
   for m in matches:
       engine.download(m["url"], fmt="best[height<=720]")
   ```

3. 提取音频到 music 文件夹：
   ```python
   for m in matches:
       engine.extract_audio(m["url"], output_dir="music", audio_format="mp3")
   ```

视频保存到 `downloads/shamio_mh/`，音频保存到 `music/`。

### Example 2

**User:** B站用户"锦恢"有哪些关于 OpenMCP 的视频？帮我全部下载下来。

**AI:** 我来帮你搜索并下载锦恢的 OpenMCP 视频。

1. 搜索用户获取 UID：
   ```bash
   python bilibili_tools.py search_user "锦恢"
   # → UID=434469188
   ```

2. 在用户视频中筛选 OpenMCP：
   ```bash
   python bilibili_tools.py search_user_keyword_videos 434469188 "OpenMCP"
   # → 返回 BV 号列表
   ```

3. 使用 yt-dlp 下载（Bilibili 必须带 cookies，不传 `-f`）：
   ```bash
   yt-dlp --cookies bilibili_cookies.txt \
     -o "downloads/%(title)s [%(id)s].%(ext)s" \
     "https://www.bilibili.com/video/BV1YpGHzcEs4"
   ```

如果没有 cookies，先运行 `python get_bili_cookie.py` 自动获取登录状态。

### Example 3

**User:** 监控这个 B站直播间，开播了自动录下来，每小时切一个文件。

**AI:** 配置后台直播监控。

```bash
python live_monitor.py add "https://live.bilibili.com/6" --name "测试直播间" --segment 3600 --convert mp4
python live_monitor.py start --interval 60
```

监控在后台运行，开播自动录制，下播自动保存。文件保存在 `live_recordings/`。可用 `python live_monitor.py status` 查看状态。

### Example 4

**User:** 我每天想自动下载这个 YouTube 频道的新视频，不要重复下载旧的。

**AI:** 使用增量归档同步。

```python
from features.archive_sync import ArchiveSync
sync = ArchiveSync(archive_file="archive.txt", output_dir="downloads")

preview = sync.preview_sync("https://www.youtube.com/@channel/videos", limit=50, date_after="today-1day")
print(f"新视频: {preview['new_count']}")

sync.sync("https://www.youtube.com/@channel/videos", limit=50, date_after="today-1day")
```

`archive.txt` 自动记录已下载的视频 ID。

### Example 5

**User:** 下载这个视频，然后帮我裁剪出 30 秒到 2 分钟之间的片段，再转成 MP4。

**AI:** 先下载，再用 ffmpeg 处理。

```python
download_video("URL", format_spec="best[height<=720]")
cut_video("downloads/视频.mp4", start=30.0, end=120.0)
remux_video("downloads/视频.mp4", output_format="mp4")
```

最终得到 90 秒 MP4 文件。

## 项目脚本

| 脚本 | 用途 |
|------|------|
| `mcp_server.py` | MCP 服务器，暴露 25 个工具 |
| `bilibili_tools.py` | B站用户搜索、视频筛选、下载 |
| `get_bili_cookie.py` | 自动获取 Bilibili cookies |
| `live_monitor.py` | 直播监控独立 CLI |

## 参考文件

按需加载：
- **[references/mcp-tools.md](references/mcp-tools.md)** — 25 个 MCP 工具的完整参数说明
- **[references/platform-notes.md](references/platform-notes.md)** — YouTube/Bilibili 详细规则、认证、URL 格式
- **[references/workflows.md](references/workflows.md)** — 扩展工作流（字幕、缩略图、章节、弹幕、ffmpeg 命令）
