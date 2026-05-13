# 在 Windows 上构建可被 Claude Code 调用的全栈开发与数据采集工具栈

> 一份面向单人开发者的本机环境工程化报告
> 作者：githubstudycloud   日期：2026-05-14   版本：v1.0
> 目标读者：使用 Windows 10/11 + Claude Code，希望以最小手动开销让 AI 能直接驱动本地工具完成全栈开发、运维、数据采集与个人知识管理的开发者。

---

## 摘要 (Abstract)

Claude Code 的能力上限受制于其所处的 **本机工具集**：当 CLI 缺失时，模型只能要求用户手工执行或临时编写脚本，效率低、可重现性差。本文将用户的原始诉求拆为五类问题（**§2 问题分类**），并按“**通用包管理 → 安全源 → 分类工具清单 → 供应链加固 → Claude Code 集成**”的顺序给出工程化方案。核心结论：

1. **用 winget + Scoop 双轨制管理 CLI**，避免 GUI 安装器与到处散落的 PATH。
2. **所有数据库 / 中间件优先使用其官方原生 CLI**（`mysql`、`redis-cli`、`mongosh`、`kcat`、`rabbitmqadmin`），而不是再让 AI 现造脚本。
3. **npm / pip 供应链问题不是“能否避免”而是“如何控住爆炸半径”**：私有镜像 + lockfile 校验 + 安装期沙箱 + 已知恶意包阻断 (`pip-audit` / `npm audit signatures` / `socket`) 四件套是当前的工程下限。
4. **Claude Code 与 Obsidian 通过文件系统 + CLI 协同**，无需自定义 MCP 即可达到“AI 写笔记、笔记回喂上下文”的闭环。

---

## 1. 引言 (Introduction)

用户原始提问可压缩为一句话：

> *“当我在 Windows 上使用 Claude Code 做全栈开发、远程运维与数据采集时，缺哪些 CLI？该怎么装？怎么不被供应链攻击？以及——能不能顺手做一个目录转 HTML 的小工具？”*

本报告聚焦 **本机基础设施**，不讨论模型选择或提示工程。所有推荐都遵循三条硬约束：

| 约束 | 含义 |
| --- | --- |
| **可被 CLI 调用** | Claude Code 只能驱动 CLI / API；纯 GUI 工具一律降级为辅助。 |
| **可在 PowerShell 中工作** | 不强制 WSL，但对 Linux-only 工具给出 WSL2 路径。 |
| **包来源可审计** | 优先官方源、有签名校验、可锁版本。 |

---

## 2. 问题分类 (Taxonomy of the Question)

将原始提问解析为以下 **五个正交类别**，下文章节与之对应：

| 编号 | 类别 | 用户原话锚点 | 对应章节 |
| --- | --- | --- | --- |
| **C1** | 本机包管理与安装策略 | “我应该怎么构建我的机器的软件工具安装” | §3 |
| **C2** | 缺失的 CLI 工具栈（开发、运维、中间件、浏览器） | “缺乏 CLI 工具，比如笔记、远程 docker、ssh、mysql、redis、kafka、mongodb、rabbitmq、浏览器、自动化浏览器” | §4 |
| **C3** | 个人使用的可视化层 | “以及个人使用可视化” | §5 |
| **C4** | 供应链安全（npm / pip 投毒） | “npm 和 pip 经常出现供应链被投放病毒脚本，怎么处理这个问题，连接安全源” | §6 |
| **C5** | 全栈语言工具 + 网络数据采集 / 媒体下载 | “全栈开发各语言经常需要的工具，包括网络数据搜集、文章、图片、音频、视频下载等等” | §7 |

附属诉求（非分类，但属于交付物）：

- **D1** Obsidian 已开启 CLI，要求与本工具栈互通 → §8。
- **D2** 实现“任意目录 → HTML 网站”脚本 → §9 与 [`tools/dir2html/`](../tools/dir2html/)。

---

## 3. C1 · 包管理与安装策略

### 3.1 三个候选与建议组合

| 包管理器 | 来源 | 适合什么 | 是否推荐 |
| --- | --- | --- | --- |
| **winget** | 微软官方 | 桌面应用、官方签名包、IDE | ✅ 主用 |
| **Scoop** | 社区 bucket | 命令行工具、便携版、不污染注册表 | ✅ 主用 |
| **Chocolatey** | 社区 | 老牌、覆盖广，但需管理员、易残留 | ⚠️ 仅在前两者无包时备用 |

**建议组合**：**winget 装 GUI / 系统级**（Docker Desktop、浏览器、Obsidian），**Scoop 装 CLI**（`gh`、`fd`、`rg`、`jq`、`kcat`、`mongosh`、`mysql`、`redis`…）。原因：

- Scoop 默认安装在 `%USERPROFILE%\scoop`，无需管理员；
- Scoop 自动加 PATH、自动写 shims，AI 调用时不必猜路径；
- winget 的源签名可校验（`winget settings` 中可启用 `requireExplicitSource`）。

### 3.2 一次性引导脚本

以下脚本在普通 PowerShell 中运行（不开管理员），用于完成 Scoop 自举与必备 bucket：

```powershell
# 1) 允许当前用户执行脚本
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 2) 安装 Scoop（官方一次性 bootstrap）
Invoke-RestMethod -Uri https://get.scoop.sh | Invoke-Expression

# 3) 加入常用 bucket
scoop bucket add main
scoop bucket add extras
scoop bucket add versions
scoop bucket add nerd-fonts

# 4) 关键 CLI 一次装齐
scoop install git gh fd ripgrep bat fzf jq yq curl wget 7zip aria2 `
              python nodejs-lts pnpm uv `
              mysql redis mongosh `
              openssh nmap
```

> **设计要点**：所有命令都是 *声明式* 的——同一脚本反复运行幂等，便于在新机重建。

### 3.3 何时引入 WSL2

下列工具在 Windows 原生体验差，建议在 WSL2 中使用：

- `kafkacat` / `kcat` 的发行版本在 Linux 更新更快；
- `rabbitmqadmin` 是 Python 脚本但依赖较多；
- 任何需要 *eBPF / strace / iptables* 的故障排查；
- `playwright` 录制脚本时遇到 Windows 字体抗锯齿差异。

---

## 4. C2 · 缺失的 CLI 工具栈

按 **职能 → 工具 → 安装方式 → Claude Code 调用要点** 组织。所有命令都假定已完成 §3.2。

### 4.1 笔记 / 知识管理

| 需求 | 工具 | 安装 | 说明 |
| --- | --- | --- | --- |
| Markdown 编辑 + 双链 | **Obsidian**（GUI）+ **obsidian-cli** | `winget install Obsidian.Obsidian`；CLI 见 §8 | 与本仓库 §9 dir2html 联动 |
| 终端 TUI 笔记 | **`glow`**（Markdown 阅读）+ **`zk`**（zettelkasten） | `scoop install glow zk` | AI 可直接 `zk new --title "..."` |
| 剪贴板/速记 | **`espanso`** | `winget install Espanso.Espanso` | 不是 AI 调用项，但能让 AI 输出片段被快速复用 |

### 4.2 远程 Docker

| 需求 | 工具 | 安装 | 调用要点 |
| --- | --- | --- | --- |
| 本机引擎 | **Docker Desktop** | `winget install Docker.DockerDesktop` | 提供 `docker` CLI |
| 远程主机 | **`docker context`** | 内置 | `docker context create remote --docker "host=ssh://user@host"`；之后 `docker --context remote ps` |
| 多主机编排 | **`lazydocker`**（TUI）/ `docker compose` | `scoop install lazydocker` | TUI 适合人工，AI 用 `docker compose ps --format json` |

> **安全**：远程访问一律走 **SSH 隧道** 而非暴露 `2375/tcp`。

### 4.3 SSH / 远程 Shell

| 工具 | 安装 | 用途 |
| --- | --- | --- |
| **OpenSSH 客户端** | `scoop install openssh`（或 Windows 可选功能） | 基础 `ssh` / `scp` / `sftp` |
| **`mosh`** | WSL2 内 `apt install mosh` | 移动网络下断线续连 |
| **`sshpass`** | WSL2 | 自动化场景，仅在受控网络使用 |
| **`tailscale`** | `winget install tailscale.tailscale` | 零配置组网，省去 SSH 端口转发 |

### 4.4 数据库 CLI

| 系统 | 官方 CLI | 安装 | 备注 |
| --- | --- | --- | --- |
| MySQL / MariaDB | `mysql` | `scoop install mysql` | 仅装客户端可用 `scoop install mysql-workbench-no-mysql`；AI 喜欢 `mysql --batch -e "..."` |
| PostgreSQL | `psql` | `scoop install postgresql` | 配合 `pgcli`（`pip install --user pgcli`）有补全 |
| SQLite | `sqlite3` | `scoop install sqlite` | 内置随 Python，但独立 CLI 更顺手 |
| Redis | `redis-cli` | `scoop install redis` | `redis-cli --json` 利于 AI 解析 |
| MongoDB | `mongosh` | `scoop install mongosh` | 取代旧 `mongo`；脚本可 `mongosh --eval "JSON.stringify(...)"` |

### 4.5 消息中间件 CLI

| 系统 | CLI | 安装 | 调用要点 |
| --- | --- | --- | --- |
| Kafka | **`kcat`**（原 kafkacat） | `scoop install kcat`（Linux 更稳，必要时 WSL2） | 生产 `kcat -P -t topic`，消费 `kcat -C -t topic -o end -e -J` |
| RabbitMQ | **`rabbitmqadmin`** | `python -m pip install --user rabbitmqadmin`（或服务端自带） | `rabbitmqadmin list queues --format=raw_json` |
| NATS | `nats` | `scoop install nats` | 可选 |
| MQTT | `mosquitto_pub/sub` | `winget install EclipseFoundation.Mosquitto` | IoT 场景 |

### 4.6 浏览器 / 自动化浏览器

| 角色 | 工具 | 安装 | 说明 |
| --- | --- | --- | --- |
| 主浏览器 | Edge / Chrome / Firefox | winget | 略 |
| **CLI 抓页面** | **`curl`** + **`httpie`** + **`xh`** | `scoop install curl httpie xh` | `xh` 是 Rust 重写的 httpie，更快 |
| **无头浏览器（首选）** | **Playwright** | `pip install --user playwright && playwright install` | 三大引擎一把梭，Claude Code 可生成脚本后直接运行 |
| 兼容场景 | Selenium + WebDriver | `pip install --user selenium` | 老系统兼容 |
| 录制 → 脚本 | `playwright codegen <url>` | 同上 | 录制 GUI 操作即可生成 Python/JS 代码，AI 二次改写 |
| 站点抓取 | `wget --mirror`、`httrack`、`monolith` | `scoop install wget httrack monolith` | `monolith` 把页面打包成单 HTML，便于喂给模型 |

### 4.7 网络 / 故障排查

| 工具 | 安装 | 用途 |
| --- | --- | --- |
| `nmap` | `scoop install nmap` | 端口扫描（仅授权目标） |
| `mtr` / `tracert` | 内置 / WSL2 | 路由追踪 |
| `dig` / `nslookup` | `scoop install dig` | DNS 排查 |
| `gping` | `scoop install gping` | 带图 ping |
| `bandwhich` | `scoop install bandwhich` | 进程级流量 |
| `wireshark` | `winget install WiresharkFoundation.Wireshark` | 深包；AI 调 `tshark` |

---

## 5. C3 · 个人使用的可视化层

“个人使用可视化”指 *单机即可起、不需要部署集群* 的可视化工具。下表按 **数据形态 → 工具** 给出最小可用组合：

| 数据形态 | 工具 | 安装 | AI 调用方式 |
| --- | --- | --- | --- |
| 表格 / CSV | **VisiData**（TUI） | `pip install --user visidata` | `vd file.csv`；脚本中 `vd --batch -o out.json` |
| Notebook 探索 | **JupyterLab** | `pip install --user jupyterlab` | `jupyter nbconvert --execute` |
| 即时图表 | **`plotext`**（终端图）/ **`matplotlib`** | `pip install --user plotext matplotlib` | 终端直出，无需开浏览器 |
| Dashboard | **Streamlit** / **Gradio** | `pip install --user streamlit gradio` | AI 写 `app.py`，`streamlit run app.py` |
| 时序监控 | **Grafana + Prometheus**（Docker Compose） | 见 §4.2 | 单机 `compose up` 即得 |
| Markdown / 笔记预览 | **Obsidian** + 本仓库 §9 dir2html | 见 §8 / §9 | — |
| 数据库可视化 | **DBeaver CE** / **TablePlus** | `winget install dbeaver.dbeaver` | GUI 辅助；AI 仍走 §4.4 CLI |

设计原则：**“能 CLI 决不开 GUI；能 Streamlit 决不写前端”**——这样 Claude Code 每一步都可重放。

---

## 6. C4 · 供应链安全（npm / pip 投毒防护）

### 6.1 威胁模型

| 攻击向量 | 真实案例 | 影响 |
| --- | --- | --- |
| **Typosquatting**（拼写近似包） | `colourama`、`python-sqlite` | 安装即执行 `setup.py` |
| **依赖混淆**（公共仓覆盖私仓同名包） | 2021 Alex Birsan PoC，多家公司中招 | 内网泄露 |
| **维护者账号被劫持** | `event-stream`、`ua-parser-js` | 下游全量受影响 |
| **post-install 脚本** | npm 默认执行 `postinstall` | 安装阶段即获代码执行 |
| **预编译 wheel / native addon** | 二进制不可审 | 持久化 |

### 6.2 工程化下限（强烈建议每条都做）

#### 6.2.1 锁定与审计

```powershell
# Python：用 uv 管理虚拟环境与锁文件，速度与可重现性优于 pip
scoop install uv
uv venv .venv
uv pip install -r requirements.txt
uv pip compile requirements.in -o requirements.txt   # 生成可重现锁

# 漏洞扫描
pip install --user pip-audit
pip-audit -r requirements.txt

# Node：始终使用 lockfile + 审计
pnpm install --frozen-lockfile
pnpm audit --prod
npm audit signatures   # npm v9+：核对发布者签名
```

#### 6.2.2 安装期“静默”脚本拦截

```powershell
# Node：禁止安装期执行 postinstall（仅在你显式信任时再开启）
pnpm config set ignore-scripts true
# 或对 npm
npm config set ignore-scripts true

# Python：避免 setup.py 任意代码——优先 wheel
uv pip install --only-binary=:all: <pkg>
```

> 关掉脚本会破坏部分包（如 `puppeteer`、`esbuild`）。做法是 **白名单**：默认关，对受信包逐个 `--include=<pkg>` 放开。

#### 6.2.3 私有镜像与签名源

| 生态 | 推荐源 | 配置 |
| --- | --- | --- |
| Python | **PyPI 官方 + Sigstore 校验** | `uv pip install --require-hashes -r requirements.txt` |
| 国内加速 | 清华 / 阿里云 / 腾讯 PyPI 镜像 | `uv pip install -i https://pypi.tuna.tsinghua.edu.cn/simple ...` |
| Node | npm 官方 + `provenance` | `npm config set registry https://registry.npmjs.org/`；安装 CI 包用 `npm install --foreground-scripts=false` |
| 自托管代理 | **Verdaccio** / **devpi** / **JFrog Artifactory** | 全部依赖打到自家代理，配合白名单 |

> **重要**：使用国内镜像加速时，**仍需校验 hash 或签名**，否则相当于把信任交给镜像方。`uv pip compile --generate-hashes` 会把 SHA256 写入 lockfile。

#### 6.2.4 沙箱化安装

- **Windows Sandbox**（专业版以上内置）：临时安装、用完即销，免费且原生。
- **Dev Drive (ReFS)**：把 `node_modules` / `.venv` 放在 Dev Drive 上，配合 *Microsoft Defender 性能模式*。
- **WSL2 一次性容器**：`docker run --rm -it -v $PWD:/w -w /w python:3.12 bash`，安装行为不污染主机。

#### 6.2.5 行为级监控

- **Socket.dev** / **Snyk** 的免费层支持 PR 阻断已知恶意包；
- 若不想接入第三方，至少订阅 [GHSA Python](https://github.com/advisories?query=ecosystem%3Apip) / [GHSA npm](https://github.com/advisories?query=ecosystem%3Anpm) RSS。

### 6.3 决策树（“我装一个新包前要做什么”）

```
       ┌─ 包名是否与知名包近似？──是──► 拒绝/手动核对
       │
新包 ──┼─ 是否在 lockfile/hash 内？──否──► 重新 compile 锁
       │
       └─ 是否需要 postinstall？──否──► 装；是──► Sandbox 或受控容器装
```

---

## 7. C5 · 全栈语言工具 + 网络数据采集

### 7.1 多语言运行时统一管理

| 工具 | 作用 | 安装 |
| --- | --- | --- |
| **`mise`**（前 rtx） | 跨语言版本管理（Node/Python/Go/Java/Ruby/Rust…） | `scoop install mise` |
| **`uv`** | Python 包/虚拟环境，10× 快于 pip | `scoop install uv` |
| **`pnpm`** | Node 包管理，硬链接节省磁盘 | `scoop install pnpm` |
| **`bun`** | JS/TS 一体化 runtime | `scoop install bun` |
| **`go`** | Go | `scoop install go` |
| **`rustup`** | Rust 工具链 | `winget install Rustlang.Rustup` |
| **JDK** | Java | `scoop install temurin21-jdk` |

### 7.2 通用全栈 CLI（按使用频度）

```
git gh           # 版本与 PR
make just task   # 任务运行；just/task 是更现代的 make
fd ripgrep       # 查找
bat              # cat with syntax
jq yq            # JSON / YAML
sd               # sed 替代
hyperfine        # 基准测试
tokei            # 代码统计
zoxide           # cd 增强
lsd / eza        # ls 增强
delta            # git diff 增强
```

一次安装：

```powershell
scoop install git gh just fd ripgrep bat jq yq sd hyperfine tokei zoxide eza delta
```

### 7.3 网络数据采集

#### 7.3.1 文章 / HTML 正文

| 需求 | 工具 | 命令示例 |
| --- | --- | --- |
| 下载并去广告，输出可读 HTML/MD | **`monolith`**（单文件 HTML） + **`readability-cli`** | `monolith https://x -o page.html`；`npx @mozilla/readability-cli url > article.html` |
| RSS 订阅抓取 | **`newsboat`**（WSL2）/ Python `feedparser` | — |
| 全站镜像 | `wget --mirror -k -p -E -np` | — |
| 结构化抓取 | Python `httpx + selectolax`、Node `playwright + cheerio` | AI 即写即跑 |

#### 7.3.2 图片

| 工具 | 安装 | 用途 |
| --- | --- | --- |
| **`gallery-dl`** | `pip install --user gallery-dl` | 主流图站、社交平台批量下载 |
| **ImageMagick** | `scoop install imagemagick` | `magick mogrify -resize 1280x ...` |
| `oxipng` / `jpegoptim` | `scoop install oxipng jpegoptim` | 压缩 |

#### 7.3.3 音视频

| 工具 | 安装 | 用途 |
| --- | --- | --- |
| **`yt-dlp`** | `scoop install yt-dlp` | YouTube / B 站 / 上千站点 |
| **`ffmpeg`** | `scoop install ffmpeg` | 转码/剪辑 |
| **`mpv`** | `scoop install mpv` | 验证与播放 |
| `aria2` | `scoop install aria2` | 多线程加速；`yt-dlp --downloader aria2c` |

#### 7.3.4 下载加速与断点

```powershell
# 多线程 + 断点
aria2c -x 16 -s 16 https://example.com/file.zip

# yt-dlp 调用 aria2 加速大视频
yt-dlp -f "bv*+ba/b" --downloader aria2c --downloader-args "aria2c:-x16 -s16" <url>
```

> **法律与伦理**：上述工具需遵守目标站 ToS、版权法与 robots.txt。商业抓取建议先核合规。

---

## 8. D1 · Obsidian CLI 集成

Obsidian 自带的 URI 协议 + 第三方 `obsidian-cli` 已足以让 Claude Code 完成 *“写笔记 → 立即在 Obsidian 中打开”* 闭环。

### 8.1 安装

```powershell
# 主程序
winget install Obsidian.Obsidian

# 第三方 CLI（任选其一）
npm i -g obsidian-cli                    # Node 实现
# 或
cargo install obsidian-cli               # Rust 实现，启动更快
```

### 8.2 推荐工作流（与本仓库 §9 dir2html 联动）

1. **AI 写**：Claude Code 调 `obsidian new "项目/2026-05-14-工具栈调研" --content "$(cat report.md)"`；
2. **人工读**：Obsidian 自动同步显示；
3. **对外发**：定期跑 `python tools/dir2html/dir2html.py "$VAULT" --out site --md --wiki`，把 vault 转成静态网站发布或本机预览（`--wiki` 解析 `[[双链]]`，见 §9.3）。

### 8.3 与 Claude Code 的桥接建议

- 在 `~/.claude/CLAUDE.md` 中声明 vault 根路径，避免每次都问；
- 用 hook（参见 update-config skill）在 `Stop` 事件中追加“今日做了什么”到 `Daily/2026-05-14.md`；
- 笔记里链接到代码：使用本仓库 README 用到的相对路径形式，让 Claude Code 在 IDE 中可点击。

---

## 9. D2 · dir2html：任意目录 → HTML 站点

完整脚本见 [`tools/dir2html/dir2html.py`](../tools/dir2html/dir2html.py)，本节仅说明设计。

### 9.1 设计目标

| 目标 | 实现 |
| --- | --- |
| **零依赖**即可跑 | 仅用 Python 3.10+ 标准库；可选 `markdown`、`pygments` 增强 |
| **任意类型文件** | Markdown 渲染、代码 `<pre>`、图片/音频/视频 `<img/audio/video>`、PDF/未知文件给下载链接 |
| **目录树侧边栏** | 折叠式，原生 `<details>` 实现，无 JS 依赖 |
| **Obsidian 兼容** | `--wiki` 时把 `[[Page]]` / `[[Page#章节]]` 解析为相对链接 |
| **可重复执行** | 输出目录幂等，源文件改动后再次运行覆盖即可 |
| **可被 Claude Code 调用** | 全部参数走命令行；产出固定结构便于继续处理 |

### 9.2 用法

```powershell
python tools/dir2html/dir2html.py <SRC_DIR> --out <OUT_DIR> [--title "Site"] [--md] [--wiki] [--open]

# 示例：把当前 docs 目录预览
python tools/dir2html/dir2html.py docs --out site --md --open
```

### 9.3 Wiki 链接解析约定

`[[Note]]` → `Note.html`；`[[Note#Heading]]` → `Note.html#heading`（GFM 锚点：小写、空格变 `-`、去除标点）。

### 9.4 已知限制

- 不做全文索引（如需，可后续叠加 [Pagefind](https://pagefind.app)）；
- Markdown 渲染若未安装 `markdown` 库则降级为最小子集（标题、段落、代码块、链接、图片、列表）。

---

## 10. 结论 (Conclusion)

本文围绕 *“让 Claude Code 在 Windows 上拥有完整工具上下文”* 这一目标，给出了 5 类工具栈推荐与 1 套供应链加固办法，并交付了 `dir2html` 作为最小可复用产物。**关键在于把 AI 视为 CLI 的高阶调用者**：装好工具，AI 才能真正 *干活* 而不是 *写脚本让你干活*。

后续可扩展方向：

1. **MCP 化**：将 §4 的 CLI 用 MCP 包装为 tool，进一步降低提示成本；
2. **离线镜像**：在企业内网中复用 §6.2.3 的 Verdaccio + devpi 模式；
3. **观测**：把 §5 的 Grafana + Prometheus 接到 §4.2 的 Docker，形成本机 SRE 闭环。

---

## 参考与延伸阅读

- Scoop 官方文档：<https://scoop.sh>
- winget 文档：<https://learn.microsoft.com/windows/package-manager/>
- Sigstore for PyPI：<https://docs.pypi.org/attestations/>
- npm Provenance：<https://docs.npmjs.com/generating-provenance-statements>
- Alex Birsan, *Dependency Confusion*, 2021：<https://medium.com/@alex.birsan/dependency-confusion-4a5d60fec610>
- Playwright：<https://playwright.dev>
- yt-dlp：<https://github.com/yt-dlp/yt-dlp>
- Obsidian URI：<https://help.obsidian.md/Advanced+topics/Using+obsidian+URI>
