# 🎵 NCM 音频解密 & 网易云高保真元数据提取器

一个基于 Python (FastAPI/Mutagen) 与 React (Vite/TypeScript) 构建的高颜值、高性能网易云 `.ncm` 音频解密与官方高保真元数据自动补全工具。

无需繁琐编译与发行版安装，启动本地 Python 服务后即可直接在浏览器中使用！

---

## ✨ 核心特性

- 🔒 **NCM 本地解密与元数据增强**：
  - 支持解密网易云音乐专属 `.ncm` 格式，转换为通用的 `.flac` 或 `.mp3` 格式；
  - 自动通过网易云官方 API 检索并写入高保真 ID3 标签（多歌手、专辑名称、高清原画封面、歌词、碟片编号等）；
  - 支持纯离线模式快速解密 NCM。
- 📂 **跨平台原生文件夹选择**：
  - 彻底抛弃手动打字填路径，点击按钮即可直接调起 Windows / macOS 原生系统目录选择框；
  - 100% 同构卡片化呈现，支持选择多个输入文件夹及自定义输出保存目录。
- ⚡ **配置即改即存 (`config.json`)**：
  - 前端任意参数修改（文件夹增删、排序方式、复选框开关、时间节点等）自动采用防抖静默落盘写入 `config.json`，无需手动按保存。
- ⏱️ **时间节点记录与自由解耦过滤**：
  - 转换成功后可自动记录并保存最新的处理时间点；
  - 时间节点记录与“时间拦截过滤”彻底解耦，提供独立的 `☑️ 启用时间节点过滤` 复选框，默认全量转换，绝不强行拦截。
- 👁️ **预检文件清单 & 失败明细 (`fail.json`)**：
  - **预检文件清单**：支持文件名搜索与格式分类 Pills（NCM/FLAC/MP3），且展示序号与主界面排序选择器 100% 动态联动；
  - **失败清单预览**：转换失败的音频文件自动写入 `fail.json`，提供天蓝色 `[预览失败清单]` 弹窗，清晰罗列失败文件名、绝对路径、发生时间与错误原因；
  - **自动清理**：当失败列表文件 100% 重试成功后，系统自动清理删除 `fail.json`。
- 🔒 **结算状态锁存与极致性能**：
  - 主界面彻底纯化，取消海量卡片堆叠，面对万首音频也保持 60 FPS 极速响应，绝不发烫卡顿；
  - 转换完成后，进度条与统计数据（准备处理 X、已处理 X、成功 Y、失败 Z）锁定保持在 100% 结算状态。
- 🔌 **智能端口防冲突与自动顺延**：
  - 默认使用 `8000` 端口。若 8000 端口被其他软件占用，启动脚本会自动寻找 `8001`, `8002`... 等可用空闲端口，并自动打开浏览器。

---

## 🛠️ 环境要求

- **Python 3.10+**
- *(可选)* **Node.js 18+** （仅在修改前端源码并重新 build 时需要）

---

## 🚀 快速使用说明 (源码直接运行)

由于本项目暂未提供独立 `.exe` 发行版软件，您只需通过命令行源码启动服务即可使用：

### 1. 克隆/下载本仓库并安装依赖

```bash
# 克隆仓库
git clone https://github.com/jitwxs/163MusicLyrics.git
cd ncm-tag-extractor

# 安装 Python 依赖库
pip install -r requirements.txt
```

### 2. 一键启动 Web 服务器

在项目根目录下直接运行启动脚本：

```bash
python run_server.py
```

终端将显示启动信息，并**自动为您打开浏览器访问页面**：

```text
==================================================
 🎵 NCM Tag Extractor Web Server Started
 🌐 Access UI in Browser: http://127.0.0.1:8000
==================================================
```

#### 💡 自定义启动参数

如果默认的 8000 端口已被其他程序占用，程序会自动无感顺延至可用端口（如 8001）。您也可以手动指定端口或禁止自动打开浏览器：

```bash
# 手动指定端口为 8080
python run_server.py -p 8080

# 仅启动服务，不自动调起浏览器
python run_server.py --no-browser
```

---

## 🛠️ 前端二次开发与构建 (前端修改)

如果您对 `web/` 目录下的 React 前端代码进行了二次开发，需要重新编译打包前端静态文件：

```bash
# 进入 web 目录
cd web

# 安装 Node 依赖
npm install

# 编译打包 (输出至 web/dist)
npm run build
```

打包完成后，重新运行 `python run_server.py` 即可生效最新的 UI 界面。

---

## ⚙️ 配置文件说明 (`config.json`)

系统在首次运行或修改设置时会自动在根目录生成并维护 `config.json`：

```json
{
  "input_dirs": ["D:/Music/NCM"],
  "output_dir": "D:/Music/Output",
  "recursive": true,
  "enrich_netease": true,
  "sort_by": "name",
  "enable_mtime_filter": false,
  "process_after_mtime": "2026-07-23 22:00:00",
  "auto_update_mtime": true,
  "only_process_failed": false
}
```

- `input_dirs`: 待扫描的输入文件夹列表；
- `output_dir`: 输出转换后音频的文件夹（留空则默认输出至原音频所在目录）；
- `recursive`: 是否递归扫描子文件夹；
- `enrich_netease`: `true` 表示获取网易云官方高保真元数据，`false` 表示纯离线解密 NCM；
- `sort_by`: 转换排序规则（`name` 文件名升序 / `mtime` 修改时间升序 / `mtime_desc` 修改时间降序）；
- `enable_mtime_filter`: 是否开启时间节点过滤开关；
- `process_after_mtime`: 记录保存的最新转换时间戳节点（格式 `YYYY-MM-DD HH:mm:ss`）；
- `auto_update_mtime`: 转换成功后是否自动更新保存 `process_after_mtime`；
- `only_process_failed`: 是否仅处理上次失败列表（`fail.json`）。

---

## 📄 开源许可

[MIT License](LICENSE)
