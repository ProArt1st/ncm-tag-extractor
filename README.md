# NCM 音频解密与元数据提取器

基于 Python 与 Qt (PySide6) 构建的高性能网易云 `.ncm` 音频解密与元数据补全工具。

无需安装 Python 或任何环境，开箱即用，支持 Windows 单文件绿色版与 Linux 单文件 AppImage。

---

## 核心特性

- **NCM 解密与元数据补充**：
  - 支持解密网易云音乐 `.ncm` 格式，转换为通用的 `.flac` 或 `.mp3` 格式；
  - 自动通过网易云官方接口补全高保真标签（多歌手、专辑名、高清原画封面、双语对齐歌词、碟片编号等）；
  - 支持纯离线模式快速解密。
- **极简极客界面**：
  - 沉稳深色主题，支持拖拽文件或文件夹快速导入；
  - 原生系统文件选择，兼容 Windows 与 Linux。
- **自动保存配置 (`config.json`)**：
  - 修改设置即时自动保存，无需手动按保存。
- **时间节点过滤**：
  - 支持记录并保存处理时间点，方便增量转换新下载文件。
- **预检清单与失败记录 (`fail.json`)**：
  - **预检文件清单**：支持文件名搜索与格式分类 Pills（NCM/FLAC/MP3），且展示序号与主界面排序选择器 100% 动态联动；
  - **失败清单预览**：转换失败的音频文件自动写入 `fail.json`，提供天蓝色 `[预览失败清单]` 弹窗，清晰罗列失败文件名、绝对路径、发生时间与错误原因；
  - **自动清理**：当失败列表文件 100% 重试成功后，系统自动清理删除 `fail.json`。
- **原生桌面性能与免安装体验**：
  - 基于 Qt 极客深色设计，直观支持拖拽文件与文件夹；
  - 提供单文件打包脚本，免安装随拷随用。

---

## 🛠️ 环境要求

- **Python 3.10+**
- 依赖库：`pip install -r requirements.txt` (包含 PySide6, Mutagen, PyCryptodome, HTTPX)

---

## 🚀 快速使用说明 (源码直接运行)

在项目根目录下直接运行主程序：

```bash
# 启动 Qt 桌面原生界面
python main.py

# 也可以直接携带文件夹参数启动
python main.py /path/to/music_folder
```

---

## 📦 免安装打包说明 (Windows 单文件 .exe & Linux .AppImage)

本项目提供一键跨平台免安装打包脚本：

```bash
# 安装打包工具
pip install pyinstaller

# 运行一键打包
python scripts/build.py
```

- **Windows 用户**：打包完成后将在 `dist/` 目录下生成 `NCMTagExtractor.exe`，免安装绿色版，随拷随用；
- **Linux 用户**：脚本将自动生成 `AppDir` 并调用 `appimagetool` 生成标准单文件 `dist/NCMTagExtractor-x86_64.AppImage`，赋予执行权限后双击即可运行。
- **GitHub 自动发布**：仓库已配置 GitHub Actions 自动流水线（`.github/workflows/release.yml`），打 tag 推送代码即可自动编译并发布双平台免安装版本。


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
