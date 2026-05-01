# yt-dlp-kit MCP Server 设计

## 定位
专业的视频处理 MCP Server，聚焦 yt-dlp 下载 + 轻量视频处理 + 可视化预览。
与 cli-helper 互补：cli-helper 是通用 GUI 基础设施，yt-dlp-kit 是视频专用处理层。

## 技术栈
- Python + FastMCP (mcp SDK)
- yt-dlp (直接 import)
- Flask (可视化 web server)

## 提供的 Tools

### 1. 下载类
- `download_video` - 下载视频到指定目录
- `extract_audio` - 提取音频
- `batch_download` - 批量下载

### 2. 信息类
- `get_video_info` - 获取视频元数据（JSON）
- `list_formats` - 列出可用格式
- `download_subtitles` - 下载字幕

### 3. 可视化类
- `preview_video` - 启动本地 web 预览指定视频
- `show_downloads` - 列出已下载文件，返回可预览的链接

## 运行方式
- MCP mode: stdio (供 Kimi CLI 调用)
- Web mode: Flask server 在 localhost 提供视频预览
