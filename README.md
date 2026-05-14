# gi030 — Windows × Claude Code 工具栈与 dir2html

本仓库包含以下产物：

1. **[`docs/windows-claude-code-toolchain.md`](docs/windows-claude-code-toolchain.md)** — 一份论文式的分类研究报告，回答“在 Windows 上配合 Claude Code 进行全栈开发与数据采集时，应如何系统化地构建本机工具栈、并规避 npm / pip 供应链投毒风险”。
2. **[`docs/offline-toolchain.md`](docs/offline-toolchain.md)** — 上一份的姊妹篇，覆盖 4 级离线/受限网络场景（L0 完全断网 / L1 sneakernet / L2 单向代理 / L3 内部镜像）下的安装、镜像与启动盘策略。
3. **[`tools/dir2html/`](tools/dir2html/)** — 把任意目录递归转换为可浏览的静态 HTML 站点（Markdown 渲染、代码块、图片/音视频内嵌、Obsidian Wiki 链接解析）。仅依赖 Python 标准库。
4. **[`tools/offline-bundle/`](tools/offline-bundle/)** — 把 pip 包 + 任意 URL 一次性打成带 SHA-256 manifest 的 bundle 目录，供 USB / sneakernet / 内部镜像分发；含 `pack` / `verify` / `install` 三个子命令。仅依赖标准库（自动检测并优先使用 `uv`）。

## 快速开始

```powershell
# 1. 阅读工具栈报告（在线 + 离线双篇）
code docs/windows-claude-code-toolchain.md
code docs/offline-toolchain.md

# 2. 把任意目录变成可浏览网站
python tools/dir2html/dir2html.py "D:\Notes" --out "D:\Notes\_site" --open

# 3. 在线机器上打离线 bundle
python tools/offline-bundle/bundle.py pack `
    --pip-requirements requirements.txt `
    --url https://get.scoop.sh `
    --out bundle
```

## 目录

```
.
├── README.md
├── docs/
│   ├── windows-claude-code-toolchain.md     # 在线工具栈论文
│   └── offline-toolchain.md                 # 离线/受限网络姊妹篇
└── tools/
    ├── dir2html/
    │   ├── dir2html.py                      # 目录 → HTML 站点
    │   └── README.md
    └── offline-bundle/
        ├── bundle.py                        # 离线 bundle pack/verify/install
        └── README.md
```

## 远程

`origin` → <https://github.com/githubstudycloud/gi030.git>
