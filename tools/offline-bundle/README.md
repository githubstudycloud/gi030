# offline-bundle

把 pip 包 + 任意 URL 一次性打包成带 SHA-256 manifest 的 bundle 目录，便于 USB / sneakernet / 内部镜像分发。仅依赖 Python 3.10+ 标准库。背景与设计说明见 [`docs/offline-toolchain.md`](../../docs/offline-toolchain.md)。

## 安装

```powershell
# 无需安装，直接调
python bundle.py --help

# 强烈推荐先装 uv，能让 pack 步骤快 5–10 倍
pip install --user uv
```

如果检测到 `uv`，脚本会自动走 `uv pip download/install`；否则回退到 `python -m pip`。

## 用法

### Pack（在线机器）

```powershell
# 仅 pip
python bundle.py pack --pip-requirements requirements.txt --out bundle

# pip + 额外 URL
python bundle.py pack `
    --pip-requirements requirements.txt `
    --url https://get.scoop.sh `
    --url https://nodejs.org/dist/v20.17.0/node-v20.17.0-x64.msi `
    --out bundle

# 跨平台：在 Windows 上为 Linux 离线机器准备 wheel
python bundle.py pack `
    --pip-requirements requirements.txt `
    --platform manylinux2014_x86_64 --python-version 3.12 `
    --out bundle-linux

# URL 写在文件里（每行一个，# 开头是注释）
python bundle.py pack --urls-file extra.txt --out bundle
```

产出目录结构：

```
bundle/
├── manifest.json     # 含每个文件的 SHA-256
├── wheels/           # pip 下载的 .whl
└── files/            # 任意 URL 下载的原始文件
```

### Verify（离线机器，使用前必跑）

```powershell
python bundle.py verify --bundle bundle
```

退出码：
- `0` — 全部匹配
- `1` — 有 hash 不匹配或文件缺失
- `2` — 没有 manifest

### Install（离线机器，可选语法糖）

```powershell
# 先 verify 再安装；用 lockfile + hashes
python bundle.py install --bundle bundle `
    --pip-requirements requirements.lock --require-hashes --verify-first

# 装到指定目录
python bundle.py install --bundle bundle --pip-requirements req.txt --target .venv\Lib\site-packages

# 直接装包名（无 requirements 文件）
python bundle.py install --bundle bundle uv pip-audit visidata
```

> 这一步只是 `uv pip install --no-index --find-links bundle/wheels [...]` 的封装；你也可以手动跑同样的命令。

## 推荐工作流（最小完整闭环）

```powershell
# === 在线 ===
python bundle.py pack `
    --pip-requirements requirements.lock `
    --url https://get.scoop.sh `
    --out bundle
sha256sum bundle\manifest.json > bundle\manifest.json.sha256
7z a bundle.7z bundle

# 介质传输 …

# === 离线 ===
7z x bundle.7z
sha256sum -c bundle\manifest.json.sha256        # 介质完整性
python bundle.py verify --bundle bundle          # 内容完整性
python bundle.py install --bundle bundle `
    --pip-requirements requirements.lock `
    --require-hashes --verify-first
```

## 已知边界

- **不打包 npm / cargo / go**：这三者各有自己的官方离线机制（`pnpm fetch` / `cargo vendor` / `go mod vendor`），更适合直接用，硬塞进通用 bundle 反而失去元数据。
- **不签名**：仅做 SHA-256；如需防介质投毒，外面再套一层 `minisign` / GPG（在 README 工作流的 `7z a` 之后）。
- **不去重**：同一 wheel 反复 pack 会写多个 bundle，不共享 store。这是 *分发* 工具，不是 *缓存* 工具。
