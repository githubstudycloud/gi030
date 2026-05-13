# dir2html

把任意目录递归转成可在浏览器中浏览的静态 HTML 站点。仅依赖 Python 3.10+ 标准库；可选安装 `markdown` 库以获得更完整的 Markdown 渲染（含表格、TOC）。

## 安装

```powershell
# 无需安装，直接调脚本
python dir2html.py --help

# 可选增强
pip install --user markdown
```

## 使用

```powershell
python dir2html.py <SRC_DIR> --out <OUT_DIR> [选项]
```

| 选项 | 说明 |
| --- | --- |
| `--out PATH` | 输出目录，默认 `./site` |
| `--title NAME` | 站点标题，默认源目录名 |
| `--wiki` | 解析 Obsidian 风格 `[[wiki]]` / `[[Page#Heading]]` / `[[Page\|alias]]` |
| `--md` | 首页只列 Markdown 文件（侧边栏仍是完整树） |
| `--ignore NAME` | 额外忽略的文件/目录名，可重复 |
| `--open` | 生成后在浏览器中打开 `index.html` |

### 示例

```powershell
# 把当前仓库的 docs 目录变成网站
python dir2html.py ../../docs --out ../../site --md --open

# 把 Obsidian vault 转成可分享的网站，解析双链
python dir2html.py "D:\ObsidianVault" --out "D:\ObsidianVault\_site" --wiki
```

## 支持的文件类型

| 类型 | 渲染方式 |
| --- | --- |
| `.md` / `.markdown` | HTML 渲染（含侧边栏导航） |
| 图片 (`.png .jpg .gif .webp .svg ...`) | `<img>` 内嵌 |
| 音频 (`.mp3 .wav .ogg .flac ...`) | `<audio controls>` |
| 视频 (`.mp4 .webm .mov .mkv ...`) | `<video controls>` |
| `.pdf` | `<embed>` 预览 + 下载链接 |
| `.html` | `<iframe>` 嵌入 |
| 源代码 / 文本 (`.py .js .ts .go .rs .java .json .yaml .toml ...`) | `<pre><code>` |
| 其他二进制 | 文件大小 + 下载链接 |

## 默认忽略

`.git`、`.hg`、`.svn`、`__pycache__`、`node_modules`、`.venv`、`venv`、`dist`、`build`、`site`、`_site`、`.DS_Store`、`Thumbs.db`，以及任何以 `.` 开头的目录/文件（少数白名单除外）。

## 设计说明

详细背景、与 Claude Code 的协同方式见仓库根目录的 [`docs/windows-claude-code-toolchain.md`](../../docs/windows-claude-code-toolchain.md) §9。
