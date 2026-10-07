# NCM Tag Extractor

一款简洁好用的网易云 `.ncm` 音频解密与标签补全工具。

无需安装 Python 或额外环境，下载解压即可运行。支持 Windows 绿色版与 Linux AppImage。

---

## 主要功能

- **格式转换与标签补全**：将 `.ncm` 文件解密为通用的 `.flac` 或 `.mp3`，自动联网补齐封面海报、双语歌词、多位艺术家、专辑等完整元数据（也支持纯离线解密）。
- **时间过滤与增量转换**：可以指定时间节点，只转换该时间之后新下载的文件；支持在“本地时间”与“UTC时间”之间自由切换，避免跨系统或跨分区导致的时区偏差；转换后可自动更新时间戳。
- **预检清单与失败重试**：
  - 点击“预检清单”可在转换前搜索、按格式筛选并查看待处理文件；
  - 遇到异常文件会自动记录到同目录的 `fail.json`，支持一键重试失败项，全部转换成功后自动清理。
- **便携与自动保存**：设置项实时保存至程序同目录下的 `config.json`，支持直接拖拽文件或文件夹导入。

---

## 下载使用

前往 [Releases](https://github.com/ProArt1st/ncm-tag-extractor/releases) 页面下载对应系统的压缩包：

- **Windows 用户**：下载 `NCMTagExtractor-Windows-x86_64.zip`，解压后双击运行即可。
- **Linux 用户**：下载 `NCMTagExtractor-Linux-x86_64.zip`，解压后赋予 AppImage 执行权限（`chmod +x *.AppImage`），双击即可运行。

---

## 源码运行

如果你熟悉 Python 开发环境，也可以直接通过源码运行：

```bash
# 1. 安装依赖 (Python 3.10+)
pip install -r requirements.txt

# 2. 启动程序
python main.py

# 也可以直接携带文件夹路径启动
python main.py /path/to/music
```

---

## 本地打包

项目中提供了自动化打包脚本：

```bash
pip install pyinstaller
python scripts/build.py
```

- 在 Windows 下运行会生成 `.exe` 绿色单文件；
- 在 Linux 下运行会生成标准 `.AppImage` 单文件；
- 打包产物均位于 `dist/` 目录。

---

## 配置说明 (config.json)

程序启动后会在同目录下自动创建并维护 `config.json`：

```json
{
  "input_dirs": ["D:/Music/CloudMusic"],
  "output_dir": "",
  "recursive": true,
  "enrich_netease": true,
  "sort_by": "name",
  "enable_mtime_filter": false,
  "process_after_mtime": "2026-06-02 11:31:48",
  "mtime_tz": "local",
  "auto_update_mtime": true,
  "only_process_failed": false
}
```

- `input_dirs`：待扫描的文件夹路径列表；
- `output_dir`：转换后的输出目录（留空表示直接输出到原音频所在目录）；
- `recursive`：是否递归扫描子文件夹；
- `enrich_netease`：是否联网补全网易云元数据，设为 false 则为离线解密；
- `sort_by`：排序方式（`name` 文件名升序、`mtime` 时间旧到新、`mtime_desc` 时间新到旧）；
- `enable_mtime_filter`：是否启用时间节点过滤；
- `process_after_mtime`：记录的时间节点；
- `mtime_tz`：时间基准（`local` 本地时间、`utc` UTC时间）；
- `auto_update_mtime`：转换完成后是否自动将时间节点更新为最新文件的修改时间；
- `only_process_failed`：是否仅重试处理失败列表。

---

## 开源协议

[MIT License](LICENSE)
