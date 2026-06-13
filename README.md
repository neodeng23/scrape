# JAV 元数据刮削器

为 Emby / Jellyfin / Kodi 生成元数据的命令行工具。

扫描视频文件 → 从文件名提取番号 → 从 JavDB / JavBus 抓取元数据 → 生成 NFO + 图片 + 软链接，组织成 Emby 可识别的目录结构。

---

## 目录

- [快速开始](#快速开始)
- [三个目录的概念](#三个目录的概念)
- [配置文件](#配置文件)
- [命令一览](#命令一览)
- [完整工作流程](#完整工作流程)
- [手动匹配未命中的文件](#手动匹配未命中的文件)
- [输出结构](#输出结构)
- [常见问题](#常见问题)

---

## 快速开始

### 1. 安装依赖

```powershell
pip install -r requirements.txt
```

核心依赖：`httpx`、`beautifulsoup4`、`pyyaml`。可选 `curl-cffi`（绕过 Cloudflare，**强烈推荐安装**）。

```powershell
pip install curl-cffi
```

### 2. 编辑配置

打开 [config.yaml](config.yaml)，至少设置这两项（必填）：

```yaml
source_dir: "W:\P\J"           # 你的视频文件所在目录
output_dir: "F:\P\link"        # 刮削结果输出目录
```

### 3. 预览将要处理什么（不实际刮削）

```powershell
python scrape.py --scan-only
```

### 4. 开始刮削

```powershell
python scrape.py
```

---

## 三个目录的概念

理解这三个目录的关系是使用本工具的关键：

```
source_dir   ──→  output_dir   ──→  final_dir
(原始视频)       (刮削结果)        (Emby 读取)
W:\P\J          F:\P\link         F:\P\emby_softlink
```

| 目录 | 作用 | 是否必填 |
|------|------|----------|
| `source_dir` | 存放原始视频文件，**不会被修改**（除非用 move 模式） | ✅ 必填 |
| `output_dir` | 刮削结果：每个视频一个文件夹，含 NFO、图片、媒体软链接 | ✅ 必填 |
| `final_dir` | Emby 实际扫描的目录。存放指向 output_dir 的二级软链接 | ⚪ 可选 |

- **`source_dir` 安全**：默认 `media_action: symlink`，原始文件只被创建软链接，不会被移动或删除。
- **`final_dir` 的作用**：用于增量检测。程序会扫描 final_dir 中已存在的软链接，避免重复处理。如果不配置，则改用 `success.txt` 做增量。

---

## 配置文件

### [config.yaml](config.yaml) — 用户设置

```yaml
source_dir: "W:\P\J"
output_dir: "F:\P\link"
final_dir: "F:\P\emby_softlink"

provider_order:     # 数据源优先级，前者优先
  - javdb
  - javbus

# 网络
timeout: 20
retries: 2          # 重试次数（不含首次，总尝试 = retries + 1）
delay: 0.5          # 请求间隔（秒，防限流）
proxy_url: null     # 代理，如 "socks5://127.0.0.1:1080"
user_agent: "..."

# 输出
media_action: symlink    # symlink | copy | move
download_images: true
download_trailer: false
write_metadata_json: true

# 增量
skip_processed: true     # 跳过 success.txt 中已记录的文件

# 调试
max_items: null          # 限制处理数量，调试用
stop_on_error: false     # 出错即停
```

### [sites.yaml](sites.yaml) — 站点配置（URL / Cookie）

数据源的网址和认证信息，与用户设置分离。

```yaml
javdb:
  base_url: "https://javdb.com"
  search_url: "/search?q={code}&locale=en"
  locale: "en"

javbus:
  base_url: "https://www.javbus.com"
  search_url: "/search/{code}?type=1"
  direct_url: "/{code}"
  cookies: ""   # 见下方「JavBus 年龄验证」
```

---

## 命令一览

```powershell
python scrape.py                  # 正常刮削
python scrape.py --dry-run        # 预览（不实际处理）
python scrape.py --scan-only      # 扫描并显示状态（不处理）
python scrape.py --scan-output r.json   # 扫描结果导出为 JSON
python scrape.py --init           # 用 final_dir 现有软链接初始化 success.txt
python scrape.py --retry-unmatched  # 用手动指定的 URL 重试未命中文件
python scrape.py --config 其他.yaml    # 使用其他配置文件
```

### 各模式说明

| 命令 | 作用 |
|------|------|
| `--dry-run` | 列出每个文件将被如何处理（process / skip / no-code），不发起网络请求、不写文件 |
| `--scan-only` | 扫描所有文件并分类，显示 ready（待处理）/ no-code（无法提取番号）/ skipped（已处理），并列出待处理文件的完整路径 |
| `--init` | **迁移场景专用**。当你已有指向源视频的软链接库，用此命令把它们登记进 success.txt，避免重新刮削 |
| `--retry-unmatched` | 读取 `.scrape/unmatched.txt`，对其中手动添加了 URL 的文件直接刮削 |

---

## 完整工作流程

### 首次使用

```powershell
# 1. 检查环境（确认能访问 JavDB）
python scrape.py --scan-only

# 2. 试运行，确认番号提取正确
python scrape.py --dry-run

# 3. 正式刮削（建议先用 max_items 测几个）
python scrape.py

# 4. 处理未命中的文件（见下一节）
python scrape.py --retry-unmatched
```

### 日常增量使用

直接运行 `python scrape.py` 即可。程序会：
1. 读取 `success.txt`，跳过已处理文件
2. 检查 `final_dir` 中是否已有软链接
3. 只处理新增文件

### 调试单个文件

在 config.yaml 临时加一行：

```yaml
max_items: 1
stop_on_error: true
```

---

## 手动匹配未命中的文件

有些文件名无法提取番号，或提取的番号搜不到结果。本工具支持手动指定 JavDB 详情页 URL。

### 工作流

```powershell
# 1. 正常刮削 —— 所有失败的文件会自动写入：
#    <output_dir>/.scrape/unmatched.txt
python scrape.py
```

程序结束时如果存在失败文件，会提示：
```
未匹配文件已写入: F:\P\link\.scrape\unmatched.txt
请编辑该文件，在路径后添加 " # <JavDB URL>"，然后运行:
  python scrape.py --retry-unmatched
```

### 2. 编辑 unmatched.txt

文件内容（每次刮削后覆盖写入，仅含本次失败）：

```
# 未匹配文件 — 添加 " # " 和 JavDB URL 后运行 --retry-unmatched
# 示例: W:\P\J\file.mp4 # https://javdb.com/v/abcde?locale=en
W:\P\J\无法识别的文件名.mp4
W:\P\J\番号搜不到的视频.mp4
```

手动在文件路径后加 ` # ` 和 JavDB 详情页 URL（注意 `#` 前后各一个空格）：

```
W:\P\J\无法识别的文件名.mp4 # https://javdb.com/v/abcde?locale=en
W:\P\J\番号搜不到的视频.mp4 # https://javdb.com/v/xyz12?locale=en
```

URL 获取方式：在 JavDB 搜索该视频，打开详情页，复制地址栏的 URL。

### 3. 用 URL 重新刮削

```powershell
python scrape.py --retry-unmatched
```

程序会直接用 URL 抓取元数据（跳过搜索），成功后自动写入 success.txt，下次不再处理。

---

## 输出结构

```
output_dir/
  .scrape/                      # 状态目录（勿删）
    success.txt                 # 已成功处理的文件路径（增量依据）
    failed.jsonl                # 失败记录（append-only，排查用）
    unmatched.txt               # 待手动匹配的文件
    scrape.log                  # 运行日志
  SSIS-001 标题/
    SSIS-001.nfo                # Emby 识别的元数据 XML
    SSIS-001.mp4                # 媒体文件（软链接到源）
    metadata.json               # 完整元数据 JSON（可选）
    poster.jpg                  # 海报
    fanart.jpg                  # 同人图
    thumb.jpg                   # 缩略图
    extrafanart/                # 剧照集
      fanart1.jpg
```

> NFO 文件名与视频文件名一致（如 `SSIS-001.nfo` 配 `SSIS-001.mp4`），Emby 兼容性最佳。

---

## 常见问题

### Q: JavDB 连接超时 / 403？

JavDB 在中国大陆受 Cloudflare + DNS 阻断。两种解决方式：

1. **配置代理**（推荐）—— config.yaml：
   ```yaml
   proxy_url: "socks5://127.0.0.1:1080"
   ```
2. **安装 curl-cffi**（绕过 Cloudflare 指纹检测）：
   ```powershell
   pip install curl-cffi
   ```
3. 两者都用最稳妥。

### Q: JavBus 提示需要年龄/驾驶验证？

JavBus 需要在浏览器通过「驾驶规则测验」（无法程序绕过）。通过后导出 Cookie：

1. 浏览器打开 JavBus，完成测验
2. F12 → Application → Cookies，复制全部 cookie
3. 粘贴到 [sites.yaml](sites.yaml)：
   ```yaml
   javbus:
     cookies: "PHPSESSID=abc123; existmag=mag; age=verified"
   ```

> 注：通常只靠 JavDB 即可。JavBus 作为补充数据源。

### Q: Windows 创建软链接失败 / 提示权限不足？

Windows 创建软链接需要以下之一：

- **以管理员身份运行** PowerShell / 终端
- **开启开发者模式**：设置 → 隐私和安全性 → 开发者选项 → 开发人员模式

若仍失败，程序会自动回退到复制模式（copy）。也可直接改 config：
```yaml
media_action: copy    # 或 move
```

### Q: 番号提取错了怎么办？

- **简单情况**：重命名源文件，让番号更清晰（如 `SSIS-001.mp4`）
- **完全无法识别**：用[手动匹配](#手动匹配未命中的文件)功能指定 URL

### Q: 想重新刮削某个文件？

从 `output_dir/.scrape/success.txt` 中删除该文件对应的行，然后重新运行。或在 output_dir 中删除该视频的输出文件夹。

### Q: `--init` 什么时候用？

当你已经有了一堆指向源视频的软链接（比如手动建好的 Emby 库），想让程序把它们都登记为「已处理」，避免重新刮削。`--init` 会扫描 `final_dir`，把指向 `source_dir` 的有效软链接写入 success.txt。

---

## 数据源说明

| 源 | 状态 | 备注 |
|----|------|------|
| **JavDB** | ✅ 主力 | 优先级最高，数据最全。需代理或 curl-cffi |
| **JavBus** | ⚠️ 备用 | 补充数据。需手动通过验证并导出 Cookie |

多源合并规则：标量字段（标题、日期等）取优先级高的源；列表字段（演员、标签等）去重合并。

---

## 相关文档

- [CLAUDE.md](CLAUDE.md) — 架构设计与开发指南（给开发者/AI）
- [Kodi/Emby NFO 规范](https://kodi.wiki/view/NFO_files/Movies)
