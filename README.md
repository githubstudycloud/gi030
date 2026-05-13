# gi030 — Windows × Claude Code 工具栈与 dir2html

本仓库包含两部分产物：

1. **[`docs/windows-claude-code-toolchain.md`](docs/windows-claude-code-toolchain.md)** — 一份论文式的分类研究报告，回答“在 Windows 上配合 Claude Code 进行全栈开发与数据采集时，应如何系统化地构建本机工具栈、并规避 npm / pip 供应链投毒风险”。
2. **[`tools/dir2html/`](tools/dir2html/)** — 一个零依赖（可选增强）的 Python 脚本，把任意目录递归转换为可在浏览器中浏览的静态 HTML 站点（含 Markdown 渲染、代码高亮占位、图片/音频/视频内嵌、Obsidian Wiki 链接解析）。

## 快速开始

```powershell
# 1. 阅读工具栈报告
code docs/windows-claude-code-toolchain.md

# 2. 把任意目录变成可浏览网站
python tools/dir2html/dir2html.py "D:\Notes" --out "D:\Notes\_site" --open
```

## 目录

```
.
├── README.md                                # 本文件
├── docs/
│   └── windows-claude-code-toolchain.md     # 论文式工具栈报告
└── tools/
    └── dir2html/
        ├── dir2html.py                      # 主脚本（仅依赖标准库）
        └── README.md                        # 用法、参数、扩展点
```

## 远程

`origin` → <https://github.com/githubstudycloud/gi030.git>
