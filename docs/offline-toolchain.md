# 在离线 / 受限网络环境下构建 Claude Code 工具栈

> 与 [`windows-claude-code-toolchain.md`](windows-claude-code-toolchain.md) 配套的姊妹篇
> 作者：githubstudycloud   日期：2026-05-14   版本：v1.0
> 适用对象：网络受限到完全断网的 Windows 工作机；同时面向多机统一发包的小团队。

---

## 摘要 (Abstract)

“离线”不是 0/1 状态，而是 **四级网络可达性**（§1）。本文给出一条贯穿四级的工程方法：**把在线机器视为采购代理（procurement proxy）**，由它一次性下载 → 摘要校验 → 介质或镜像分发 → 离线机器侧加载安装。我们按以下顺序展开：

1. **场景分级与威胁模型**（§1）；
2. **通用三原则**：采购代理化、Hash/签名优先、bootstrap 优先（§2）；
3. **系统级包管理器的离线工作流**：winget / Scoop / Chocolatey（§3）；
4. **各语言生态的 download-then-sideload 套路**：Python / Node / Go / Rust / Java（§4）；
5. **容器与中间件**：`docker save/load`、portable zip（§5–6）；
6. **内部镜像方案**（L3）：devpi / Verdaccio / Athens / Nexus（§7）；
7. **启动盘 (Bootstrap kit) 配方**（§8）；
8. **离线 AI 与文档**（§9）；
9. **同步与轮替策略**（§10）；
10. **与 dir2html / 本仓库工具的协同**（§11）。

> 配套脚本：[`tools/offline-bundle/bundle.py`](../tools/offline-bundle/bundle.py) — 可在在线机器上把 pip 包 + 任意 URL 一次性打包成带 SHA-256 manifest 的 bundle 目录。

---

## 1. 场景分级 (Taxonomy of "Offline")

| 级别 | 名称 | 可达性 | 典型场景 |
| --- | --- | --- | --- |
| **L0** | 完全隔离 | 没有任何网络出口；不允许 USB | 涉密、SCIF |
| **L1** | 物理断网 + 介质传递（Sneakernet） | 允许 USB / 光盘进出 | 工控网、工程师轮换 |
| **L2** | 单向代理 / 白名单 | HTTP(S) 代理，限定域名 | 银行办公网、企业 DMZ |
| **L3** | 内网镜像 | 内网可达 Verdaccio/Nexus 等 | 大企业研发网 |

> **威胁模型差异**：L0/L1 的核心是 *介质投毒*（U 盘里被替换成恶意 wheel），L2/L3 的核心是 *镜像被攻陷* 或 *代理被滥用*。两者的应对都收敛到一个动作 —— **本地校验 SHA-256 / Sigstore 签名**。

---

## 2. 通用三原则

### 2.1 在线机器 = 采购代理

不要让生产机器自己去“试连一下能不能装”。专门保留一台联网的“采购代理”（可以是同一物理机的 WSL2、也可以是另一台笔记本），所有 *download* 类命令都在它上面跑，产出 *bundle 目录*。生产机只接受打好包的 bundle，从不主动联网。

### 2.2 Hash / 签名优先

任何 bundle 的根目录必须有 `manifest.json`：

```json
{
  "version": "1",
  "created": "2026-05-14T08:00:00Z",
  "items": [
    { "path": "wheels/uv-0.5.14-py3-none-win_amd64.whl", "sha256": "..." },
    { "path": "files/scoop-install.ps1",                  "sha256": "..." }
  ]
}
```

校验方有义务在 *使用前* 跑一遍校验脚本（[`bundle.py verify`](../tools/offline-bundle/bundle.py)）。**没有 manifest 的 bundle 一律拒绝。**

### 2.3 Bootstrap 优先

“离线装 Python” 比 “离线装 numpy” 难得多。**先解决底层运行时，再谈生态包**。这意味着第一批 bundle 必须包含：

- Git (官方 PortableGit `.7z.exe`)
- Python 安装器 (`python-3.x.y-amd64.exe`)
- Node LTS 安装器 (`node-vXX.Y.Z-x64.msi`)
- 7-Zip (`7z2408-x64.exe`) — 解压介质用
- Scoop bootstrap 脚本 + 至少一个 bucket 的离线快照

这套被称为 **“启动盘”（Bootstrap kit）**，详见 §8。

---

## 3. 系统级包管理器

### 3.1 winget

| 操作 | 在线侧 | 离线侧 |
| --- | --- | --- |
| 列出现有 | `winget export -o packages.json` | — |
| 同步安装 | — | `winget import -i packages.json --accept-package-agreements` |
| 拉单个包 | `winget download --id Git.Git -d C:\bundle\winget` | — |
| 离线安装单包 | — | 直接双击 `.exe`/`.msi`/`.msix`，或 `Add-AppxPackage`（msix） |

> **限制**：`winget` 至今没有“完全离线”的安装路径——`download` 拿到的就是原始安装器，离线侧需要 *手动调起安装器*。它最大的价值是 `export/import` 用于在两台连网机器之间同步软件清单。

### 3.2 Scoop（最适合离线）

Scoop 由三部分组成：**bucket repo（manifest）+ cache（下载产物）+ shims（软连接）**。把前两者打包，离线机几乎可以原样使用：

```powershell
# === 在线机器：制作 Scoop 离线快照 ===
$out = "D:\bundle\scoop"
mkdir $out\cache, $out\buckets, $out\bin -Force

# 1. 拷贝当前已下载的 cache（默认在 ~\scoop\cache）
Copy-Item "$env:USERPROFILE\scoop\cache\*" "$out\cache\" -Recurse

# 2. 拷贝 bucket 仓库（git clone 的）
Copy-Item "$env:USERPROFILE\scoop\buckets" "$out\buckets" -Recurse

# 3. 一并带上 Scoop 自身（PortableGit + Scoop install.ps1）
Invoke-WebRequest https://get.scoop.sh -OutFile "$out\install.ps1"
```

```powershell
# === 离线机器：还原 ===
$src = "E:\bundle\scoop"
$env:SCOOP = "$env:USERPROFILE\scoop"
mkdir $env:SCOOP -Force
Copy-Item "$src\buckets" "$env:SCOOP\buckets" -Recurse
Copy-Item "$src\cache"   "$env:SCOOP\cache"   -Recurse

# 仅当还没装 Scoop 才执行（需要预先装好 PortableGit）
& powershell -ExecutionPolicy Bypass -File "$src\install.ps1"

# 之后 install 命令就能命中本地 cache，无需联网
scoop install fd ripgrep bat jq yq mongosh redis mysql
```

> **校验**：`scoop` 自身的 manifest 内置 `hash` 字段，命中本地 cache 时也会强制 SHA 校验，比手动包好。

### 3.3 Chocolatey

```powershell
# 在线侧：把公网包“内化”成内网可分发的 NuGet 包
choco download <pkgid> --internalize --output-directory C:\bundle\choco

# 离线侧：把这些 .nupkg 推到内部 NuGet feed，或者直接安装
choco install <pkgid> --source="C:\bundle\choco"
```

适合 L3（已经有内部 NuGet/Nexus 的环境）。

---

## 4. 语言生态的 download-then-sideload

> **铁律**：任何 `--no-index` / `--offline` / `vendor` 模式的命令，都必须在“在线机器先把缓存填满”之后才能在离线机器上工作。下面每节给出 **在线 / 离线** 两段命令的对照。

### 4.1 Python（pip / uv）

```powershell
# === 在线机器：下载到 wheelhouse ===
mkdir wheelhouse
# 推荐用 uv（快得多），pip 也可以
uv pip download -r requirements.txt -d wheelhouse `
    --only-binary=:all: `
    --python-version 3.12 --platform win_amd64

# 如果目标平台不同（比如要给 Linux 机器用）
uv pip download -r requirements.txt -d wheelhouse-linux `
    --only-binary=:all: `
    --python-version 3.12 --platform manylinux2014_x86_64

# 生成带 hash 的锁
uv pip compile requirements.in -o requirements.lock --generate-hashes
```

```powershell
# === 离线机器：从 wheelhouse 安装 ===
uv pip install -r requirements.lock --no-index --find-links wheelhouse `
              --require-hashes
```

要点：
- `--only-binary=:all:` 强制 wheel，避开离线无法执行的 `setup.py`；
- `--require-hashes` 配合 `requirements.lock`，相当于把供应链信任链固化在 lock 文件里，离线侧无须任何外部信任源；
- **uv 比 pip 快 10×**，且 lock 与 download 一致性更好，离线场景强烈推荐。

### 4.2 Node（npm / pnpm）

**方案 A：tarball 文件夹（小项目最简单）**

```powershell
# 在线侧：把 lockfile 涉及的所有 tarball 拉下来
mkdir tarballs
npm pack $(npm ls --all --parseable --json | python ...) -pack-destination tarballs
# 实际更常用：直接把 node_modules 打 tar，离线 untar 即可（前提：架构相同）
tar czf node_modules.tgz node_modules
```

**方案 B：pnpm fetch（推荐，可重复）**

```powershell
# 在线侧
pnpm fetch                         # 把 lock 中所有包灌进 ~/.pnpm-store
# 把 ~/.pnpm-store 整个打包带走
```

```powershell
# 离线侧：还原 store 后
pnpm install --offline             # 全部命中本地 store
```

**方案 C：私有 registry（L2/L3）**

在采购代理上跑 [Verdaccio](https://verdaccio.org/)：

```powershell
npm i -g verdaccio
verdaccio   # 默认 4873 端口，自带磁盘缓存
# 客户端 .npmrc：
# registry=http://verdaccio.internal:4873
```

> **关键安全点**：离线/内部 registry 不豁免你做 `pnpm audit signatures`。任何镜像都可能被投毒。

### 4.3 Go

```powershell
# === 在线侧 ===
# 方式 1：vendor 目录，提交进仓库
go mod vendor

# 方式 2：导出 module cache
$env:GOMODCACHE = "D:\bundle\gomodcache"
go mod download -x
```

```powershell
# === 离线侧 ===
# 方式 1：构建时
go build -mod=vendor ./...

# 方式 2：还原 GOMODCACHE 后
$env:GOMODCACHE = "C:\Users\me\go\pkg\mod"
$env:GOFLAGS = "-mod=mod"
$env:GOPROXY = "off"        # 严禁意外联网
go build ./...
```

### 4.4 Rust

```powershell
# === 在线侧 ===
cargo vendor                # 生成 vendor/ 目录
# 同时它会打印 .cargo/config.toml 应该追加的内容，照做
```

```powershell
# === 离线侧 ===
cargo build --offline       # 严格离线
```

### 4.5 Java（Maven / Gradle）

```powershell
# === Maven 在线侧 ===
mvn -B dependency:go-offline   # 把所有依赖灌进 ~/.m2/repository
# 把 ~/.m2/repository 整体打包带走

# === Gradle 在线侧 ===
gradle --refresh-dependencies build
# 复制 ~/.gradle/caches
```

```powershell
# === 离线侧 ===
mvn -o package                 # -o = offline
gradle --offline build
```

L3 推荐 Nexus / Artifactory 做镜像，配置 `settings.xml` / `init.gradle` 指向内网。

---

## 5. 容器镜像

### 5.1 单镜像 sneakernet

```powershell
# 在线侧
docker pull mysql:8.4
docker save mysql:8.4 -o D:\bundle\mysql-8.4.tar
sha256sum D:\bundle\mysql-8.4.tar > D:\bundle\mysql-8.4.tar.sha256
```

```powershell
# 离线侧
sha256sum -c mysql-8.4.tar.sha256
docker load -i mysql-8.4.tar
```

### 5.2 多仓库 / 多 tag

[Skopeo](https://github.com/containers/skopeo)（Linux/WSL2）支持仓库间直接 copy，不落本地 docker：

```bash
skopeo copy docker://mysql:8.4 dir:/mnt/usb/mysql-8.4
# 离线机
skopeo copy dir:/mnt/usb/mysql-8.4 docker-daemon:mysql:8.4
```

### 5.3 私有 registry（L3）

部署 Harbor 或 [`registry:2`](https://hub.docker.com/_/registry)。配 `daemon.json` 的 `registry-mirrors` 指向它，离线机所有 `docker pull` 自动走内网。

---

## 6. 数据库 / 中间件二进制

| 软件 | 离线方案 |
| --- | --- |
| **MySQL** | 官方 ZIP 解压版 (`mysql-8.x-winx64.zip`)；客户端 `mysql.exe` 直接拷出来 |
| **PostgreSQL** | EnterpriseDB 提供 Windows ZIP；或 Docker tar |
| **Redis** | Windows 没有官方版，用 [Memurai](https://www.memurai.com)（兼容协议）或 WSL2/Docker |
| **MongoDB** | 官方 `.zip`；`mongosh` 单独提供独立 ZIP |
| **Kafka** | 官方 `kafka_2.13-x.y.z.tgz`，含脚本与 `kcat` 二进制（Windows 推荐 WSL2） |
| **RabbitMQ** | 安装包 + Erlang/OTP runtime（必装顺序：Erlang → RabbitMQ） |

> **关键操作**：所有 ZIP/TGZ 在打包时都生成 `.sha256`，离线侧第一步是校验。

---

## 7. 内部镜像（L3 推荐拓扑）

```
                ┌──────────────────────┐
                │  Internet            │
                └─────────┬────────────┘
                          │ 一台“采购代理”
                ┌─────────▼────────────┐
                │  Mirror Hub          │
                │  ─────────────       │
                │  • Verdaccio (npm)   │
                │  • devpi (PyPI)      │
                │  • Athens (Go)       │
                │  • Nexus (universal) │
                │  • Harbor (docker)   │
                └─────────┬────────────┘
                          │ 内网
       ┌──────────┬───────┴───────┬──────────┐
       ▼          ▼               ▼          ▼
   开发机 1    开发机 2         CI runner   离线 lab
```

| 角色 | 推荐组件 | 备注 |
| --- | --- | --- |
| Python | **devpi-server** | 透明代理 PyPI；可建“私有 index”叠在公共上 |
| Node | **Verdaccio** | 默认磁盘缓存，配置极简 |
| Go | **Athens** (`gomods/athens`) | 兼容 GOPROXY 协议 |
| Maven/Gradle | **Sonatype Nexus** OSS | 同时能托 npm/PyPI/Docker |
| Universal | **JFrog Artifactory** | 商业，但企业级最稳 |
| 容器 | **Harbor** | 自带签名、扫描、RBAC |

**最小化配置示例**（在采购代理上一次跑全）：

```powershell
docker compose up -d verdaccio devpi athens harbor
```

客户端配置（一次写入，所有项目复用）：

```powershell
# Python：~/AppData/Roaming/pip/pip.ini
[global]
index-url = https://devpi.internal/root/pypi/+simple/
trusted-host = devpi.internal

# Node：~/.npmrc
registry=https://verdaccio.internal/
//verdaccio.internal/:_authToken=...

# Go：环境变量
$env:GOPROXY = "https://athens.internal,direct"
$env:GOSUMDB = "off"   # 仅在确实无法访问 sum.golang.org 时
```

---

## 8. 启动盘 (Bootstrap kit) 配方

> 适用于 L0/L1 的“一台新机器，从零到能跑 Claude Code”。

**目录结构**

```
bootstrap-kit/
├── manifest.json                # SHA-256 清单
├── README.md                    # 安装顺序
├── installers/
│   ├── PortableGit-2.45.2-64-bit.7z.exe
│   ├── python-3.12.5-amd64.exe
│   ├── node-v20.17.0-x64.msi
│   ├── 7z2408-x64.exe
│   ├── vscode-system-x64.exe       (可选)
│   └── claude-code-setup.exe       (从 anthropic.com 下载)
├── scoop/
│   ├── install.ps1                  # Scoop bootstrap
│   ├── buckets/                     # main + extras 快照
│   └── cache/                       # 预下载的 .7z / .zip
├── wheelhouse/                      # pip 离线包
│   └── *.whl                        (uv, pip-audit, ipython, ...)
├── npm/                             # pnpm store 或 .tgz
└── docker/                          # docker save 出来的 .tar
    └── mysql-8.4.tar
```

**`README.md` 安装顺序（关键！）**

1. 校验 manifest：在另一台机器上 `bundle.py verify`；
2. 装 7-Zip → 装 PortableGit → 装 Python → 装 Node；
3. 跑 `scoop\install.ps1`，恢复 buckets/cache；
4. `scoop install` 业务工具；
5. `uv pip install --no-index --find-links wheelhouse -r requirements.lock`；
6. `pnpm install --offline`；
7. 必要时 `docker load -i docker\*.tar`。

整个 kit 压成一个 7z + `.sig`（GPG 或 minisign 签名），单文件下发。

---

## 9. 离线 AI 与文档

### 9.1 Claude Code 本身：必须联网

Claude Code 调用的是 Anthropic API，**没有完全离线模式**。L0/L1 场景下你只有两个选择：

- **A. 把可联网机器作为 AI 工作站**：在采购代理上跑 Claude Code，结果以代码 / 报告形式带回；
- **B. 改用本地模型**：在离线机上跑 [Ollama](https://ollama.com) + 本地权重（`gpt-oss`, `qwen2.5-coder`, `deepseek-coder`），再用 [continue.dev](https://continue.dev)、[aider](https://aider.chat) 或 [cline](https://github.com/cline/cline) 等开源前端做 IDE 集成。

> 本地模型与 Claude 的能力差距是真实存在的，不要期待对等替代。把本地 LLM 当成“写小函数 / 解释代码 / 生成 boilerplate”的助手即可。

### 9.2 离线文档

| 工具 | 说明 |
| --- | --- |
| **Zeal** | Dash docset for Windows，支持 200+ 语言 / 框架，单次下载后完全离线 |
| **DevDocs (PWA)** | 浏览器装一次，所有 docset 缓存到本地 |
| **`man` / `help`** | 老生常谈但常被忘 |
| **本仓库 `dir2html`** | 把 vault / 公司内部 wiki 编译成离线静态站点 |

---

## 10. 同步与轮替

离线 mirror **必须有节奏地同步**，否则两个月后所有依赖都会落后到无人敢升级。建议：

| 频率 | 动作 | 责任人 |
| --- | --- | --- |
| 每周 | 在采购代理上跑 `pip-audit` / `npm audit signatures`，更新内部 mirror | DevOps |
| 每月 | 重打 bootstrap-kit，签名后入档 | DevOps |
| 每季度 | 旧 bundle 归档 / 销毁，更新 SHA 列表 | 安全 |
| 即时 | 收到 GHSA 高危公告，立即 `--upgrade` 并替换 mirror 中相应版本 | 安全 |

---

## 11. 与本仓库其它工具的协同

- **dir2html**：把内部 wiki / Obsidian vault 转成离线静态站，放到 bootstrap-kit 里随机器分发；
- **offline-bundle**（[`tools/offline-bundle/bundle.py`](../tools/offline-bundle/bundle.py)）：单脚本完成“pip 包 + 任意 URL → 带 manifest 的 bundle 目录”的打包/校验流程，是 §2.1 “采购代理化” 的最小实现；
- **windows-claude-code-toolchain.md**：在线版工具栈清单，离线时把每条 `winget install` / `scoop install` / `pip install` 替换成对应离线套路即可。

---

## 12. 一页速查 (TL;DR)

| 需要 | 在线侧（采购代理） | 离线侧 |
| --- | --- | --- |
| Python 包 | `uv pip download -d wheelhouse -r req.txt --only-binary=:all:` | `uv pip install --no-index --find-links wheelhouse -r req.lock --require-hashes` |
| Node 包 | `pnpm fetch` 后打包 `~/.pnpm-store` | `pnpm install --offline` |
| Go 包 | `go mod vendor` | `go build -mod=vendor` |
| Rust 包 | `cargo vendor` | `cargo build --offline` |
| Maven | `mvn dependency:go-offline` | `mvn -o package` |
| Scoop 包 | 复制 `~/scoop/cache` + `~/scoop/buckets` | `scoop install <name>`（命中 cache） |
| 容器镜像 | `docker save img -o img.tar` | `docker load -i img.tar` |
| GUI 软件 | `winget download` 或厂商离线安装包 | 双击安装 |
| 文档 | Zeal/DevDocs 拉 docset | 直接看 |
| AI | 在采购代理上跑 Claude Code，或本地 Ollama | 同左 |
| 安全 | 给每个 bundle 算 SHA-256 / 签名 | 使用前 `bundle.py verify` |

---

## 参考

- Scoop 官方文档：<https://scoop.sh>
- pip download：<https://pip.pypa.io/en/stable/cli/pip_download/>
- pnpm offline：<https://pnpm.io/cli/install#--offline>
- Verdaccio：<https://verdaccio.org/>
- devpi：<https://devpi.net/>
- Athens (Go module proxy)：<https://docs.gomods.io/>
- Skopeo：<https://github.com/containers/skopeo>
- Sigstore for PyPI：<https://docs.pypi.org/attestations/>
- Ollama：<https://ollama.com>
- Zeal docs viewer：<https://zealdocs.org>
