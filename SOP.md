# SOP — Headless Media Scraper 使用手册

## 1. 前置条件

- Python 3.10+
- 安装依赖：
  ```powershell
  pip install -r requirements-headless.txt
  ```
  依赖仅两个：`beautifulsoup4`（HTML 解析）、`httpx[socks]`（HTTP 客户端）

---

## 2. 配置 — 编辑 `config.py`

所有运行时常量集中在 `config.py` 顶部，按需修改即可。

### 2.1 必改项

| 变量 | 说明 | 示例 |
|---|---|---|
| `SOURCE_DIR` | 媒体文件所在目录（递归扫描） | `Path(r"W:\new")` |
| `OUTPUT_DIR` | 刮削成功后的输出目录 | `Path(r"F:\P\link")` |

### 2.2 刮削行为

| 变量 | 说明 | 默认值 |
|---|---|---|
| `MEDIA_ACTION` | `"copy"` 或 `"move"`，媒体文件是复制到输出还是移动 | `"copy"` |
| `ENABLED_SOURCES` | 启用的刮削源，目前仅支持 `"javdb"` | `("javdb",)` |
| `MEDIA_EXTENSIONS` | 识别的媒体文件扩展名 | `.mp4 .mkv .avi .mov` 等 |
| `MAX_ITEMS` | 限制本次运行处理的文件数，`None` 为全部 | `None` |

### 2.3 网络

| 变量 | 说明 | 默认值 |
|---|---|---|
| `HTTP_TIMEOUT` | 单次请求超时（秒） | `20.0` |
| `HTTP_RETRIES` | 请求失败重试次数 | `2` |
| `REQUEST_INTERVAL_SECONDS` | 两次请求之间的间隔（秒），防止被限速 | `0.0` |
| `USER_AGENT` | 请求 UA | Chrome 136 |

### 2.4 输出控制

| 变量 | 说明 | 默认值 |
|---|---|---|
| `WRITE_NFO` | 是否生成 `.nfo`（Kodi/Jellyfin 兼容） | `True` |
| `WRITE_METADATA_JSON` | 是否生成 `metadata.json` | `True` |
| `DOWNLOAD_IMAGES` | 是否下载封面/海报/fanart | `True` |
| `DOWNLOAD_TRAILER` | 是否下载预告片 | `False` |

### 2.5 增量与容错

| 变量 | 说明 | 默认值 |
|---|---|---|
| `SKIP_RECORDED_SUCCESS` | 跳过已成功处理的文件 | `True` |
| `STOP_ON_ERROR` | 遇到错误立即中止（调试用） | `False` |
| `COPY_FAILED_MEDIA` | 是否把失败的文件也复制到 failed 目录 | `False` |

---

## 3. 运行

```powershell
cd d:\tools\scrape
python main.py
```

### 运行流程

```
1. 读取 config.py 配置
2. 递归扫描 SOURCE_DIR，过滤媒体扩展名
3. 从文件名提取番号（如 AKA-029、FC2-123456）
4. 跳过已成功记录的文件
5. 依次调用启用的刮削源查询元数据
6. 成功 → 在 OUTPUT_DIR 创建文件夹，放入媒体+NFO+图片
7. 失败 → 在 runtime/failed/ 记录 failure.json
8. 写出本次运行摘要
```

---

## 4. 输出结构

### 4.1 成功输出（OUTPUT_DIR 下）

```
F:\P\link\
  AKA-029 标题文字\
    AKA-029.mp4          ← 媒体文件（复制或移动）
    movie.nfo            ← Kodi 兼容的元数据 XML
    metadata.json        ← 完整的元数据 JSON
    thumb.jpg            ← 缩略图
    poster.jpg           ← 海报
    fanart.jpg           ← 背景图
    extrafanart\         ← 额外剧照（如有）
      01.jpg
      02.jpg
```

### 4.2 失败输出

```
d:\tools\scrape\runtime\failed\
  AKA-067_ba5d519e\
    failure.json         ← 记录源路径、番号、失败原因
```

### 4.3 运行日志

| 文件 | 内容 |
|---|---|
| `runtime/logs/scrape.log` | 完整运行日志 |
| `runtime/logs/last_run_summary.json` | 上次运行的结构化摘要（成功/失败/跳过明细） |
| `runtime/logs/success_paths.txt` | 已成功处理的源文件路径列表（增量依据） |

---

## 5. 增量运行

- 默认 `SKIP_RECORDED_SUCCESS = True`
- 每次成功处理后，源文件绝对路径追加到 `success_paths.txt`
- 再次运行时自动跳过这些文件
- 如需重新刮削某个文件：打开 `success_paths.txt`，删除对应行即可

---

## 6. 文件名解析规则

解析器（`parsers/media_code.py`）从文件名提取番号，优先级：

| 优先级 | 格式 | 示例文件名 → 提取结果 |
|---|---|---|
| 1 | 西方日期格式 | `BigTits - 2013.11.28 Sierra.mp4` → `Bigtits.13.11.28` |
| 2 | FC2 | `FC2-PPV-1234567.mp4` → `FC2-1234567` |
| 3 | HEYZO | `HEYZO-1234.mp4` → `HEYZO-1234` |
| 4 | 日期编码 | `CARIB-012345-123.mp4` → `CARIB-012345-123` |
| 5 | 数字-数字 | `012345_123.mp4` → `012345-123` |
| 6 | 通用番号 | `AKA-029.mp4` → `AKA-29` |
| 7 | 紧凑格式 | `AKA029.mp4` → `AKA-29` |

文件名中的 `[44x.me]`、`(PRESTIGE)`、`{TAG}` 等括号内容会被忽略。  
`FHD`、`4K`、`HEVC` 等画质/编码标签也会被过滤。

---

## 7. 当前限制 / 待办

| 项目 | 现状 |
|---|---|
| Cookie 支持 | **未实现**。JavDB 等站点如果被 Cloudflare 拦截，目前没有配置 cookie 的入口 |
| 刮削源数量 | 仅 JavDB 一个源 |
| 代理支持 | httpx 底层支持 `HTTP_PROXY` / `HTTPS_PROXY` 环境变量，但 config.py 中未显式配置 |
| 多源合并 | pipeline 目前取第一个返回结果的源，不做多源字段合并 |
