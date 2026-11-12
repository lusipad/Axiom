"""Build the zero-dependency one-click Windows release bundle and release notes."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import zipfile
from pathlib import Path

OFFLINE_SERVER_PS1 = r"""$ErrorActionPreference = "Stop"
$webRoot = Join-Path $PSScriptRoot "web"
if (-not (Test-Path (Join-Path $webRoot "index.html"))) {
    Write-Host "[错误] 未找到 web/index.html，请先完整解压压缩包后再运行。" -ForegroundColor Red
    Read-Host "按回车键退出"
    exit 1
}

# Find an available local port starting at 8765
$port = 8765
for ($p = 8765; $p -lt 8865; $p++) {
    $testListener = $null
    try {
        $testListener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $p)
        $testListener.Start()
        $testListener.Stop()
        $port = $p
        break
    } catch {
        if ($null -ne $testListener) { try { $testListener.Stop() } catch {} }
    }
}

$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
$listener.Start()

$url = "http://127.0.0.1:$port/"
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  Axiom CNC 现场调参与算法评估工作台 (免安装一键离线版)" -ForegroundColor Green
Write-Host "  本地服务地址: $url" -ForegroundColor Yellow
Write-Host "  正在自动打开默认浏览器... (关闭本窗口即可停止服务)" -ForegroundColor Gray
Write-Host "================================================================" -ForegroundColor Cyan

Start-Process $url

$mimeTypes = @{
    ".html" = "text/html; charset=utf-8"
    ".js"   = "application/javascript; charset=utf-8"
    ".mjs"  = "application/javascript; charset=utf-8"
    ".css"  = "text/css; charset=utf-8"
    ".json" = "application/json; charset=utf-8"
    ".svg"  = "image/svg+xml"
    ".png"  = "image/png"
    ".jpg"  = "image/jpeg"
    ".ico"  = "image/x-icon"
}

try {
    while ($true) {
        $client = $listener.AcceptTcpClient()
        try {
            $stream = $client.GetStream()
            $reader = [System.IO.StreamReader]::new($stream, [System.Text.Encoding]::ASCII, $false, 1024, $true)
            $requestLine = $reader.ReadLine()
            while ($true) {
                $headerLine = $reader.ReadLine()
                if ([string]::IsNullOrEmpty($headerLine)) { break }
            }
            if (-not [string]::IsNullOrEmpty($requestLine)) {
                $parts = $requestLine.Split(" ")
                $rawPath = if ($parts.Length -ge 2) { $parts[1].Split("?")[0] } else { "/" }
                $relPath = [System.Uri]::UnescapeDataString($rawPath).TrimStart("/")
                if ([string]::IsNullOrWhiteSpace($relPath)) { $relPath = "index.html" }
                $filePath = Join-Path $webRoot ($relPath -replace "/", "\")
                if (-not (Test-Path $filePath -PathType Leaf)) {
                    $filePath = Join-Path $webRoot "index.html"
                }
                $bytes = [System.IO.File]::ReadAllBytes($filePath)
                $ext = [System.IO.Path]::GetExtension($filePath).ToLowerInvariant()
                $contentType = if ($mimeTypes.ContainsKey($ext)) { $mimeTypes[$ext] } else { "application/octet-stream" }
                $header = "HTTP/1.1 200 OK`r`nContent-Type: $contentType`r`nContent-Length: $($bytes.Length)`r`nCache-Control: no-cache`r`nConnection: close`r`n`r`n"
                $headerBytes = [System.Text.Encoding]::ASCII.GetBytes($header)
                $stream.Write($headerBytes, 0, $headerBytes.Length)
                $stream.Write($bytes, 0, $bytes.Length)
                $stream.Flush()
            }
        } catch {
            # Ignore client socket resets
        } finally {
            $client.Close()
        }
    }
} finally {
    $listener.Stop()
}
"""

ONECLICK_BAT = """@echo off
chcp 65001 >nul
title Axiom CNC 现场调参与算法评估工作台
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-offline.ps1"
"""

PYTHON_BACKEND_BAT = """@echo off
chcp 65001 >nul
title Axiom CNC 完整 Python 后端服务
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [提示] 未检测到系统 Python 3.12+ 环境。
    echo 请直接双击运行【双击一键启动工作台 ^(免安装^).bat】使用免安装版本！
    pause
    exit /b 1
)
if not exist ".venv\\Scripts\\python.exe" (
    echo 正在创建本地虚拟环境 .venv ...
    python -m venv .venv
)
echo 正在安装/更新本地 Axiom 组件包 ...
for %%f in ("wheels\\*.whl") do (
    ".venv\\Scripts\\python.exe" -m pip install --upgrade "%%f"
)
echo 正在启动 Axiom 本地服务并打开浏览器 ...
".venv\\Scripts\\axiom.exe" serve --host 127.0.0.1 --port 8765 --open
pause
"""

README_TXT = """========================================================================
Axiom CNC 现场调参与算法评估工作台 ({tag}) — 一键使用指南
========================================================================

1. 【免安装离线一键启动（推荐）】
   - 完整解压本压缩包到任意文件夹；
   - 直接双击运行：
       双击一键启动工作台 (免安装).bat
   - 无需安装 Python、Node.js 或任何依赖，无需管理员权限，浏览器将自动打开工作台。
   - 支持西门子 840D sl / 倍福 TwinCAT 3 / 通用 32 维参数快诊、自定义单刀轨迹 JSON 上传诊断与 CNC 算法 A/B 轨迹对比。

2. 【在线即开即用（无需下载）】
   - 浏览器直接访问：https://lusipad.github.io/Axiom/

3. 【完整 Python 后端与 CLI 模式（可选，需 Python 3.12+）】
   - 双击运行 `启动完整Python后端版 (可选).bat`；
   - 或在命令行安装 `wheels/` 目录下的 `.whl` 包后执行：
       axiom serve --open
========================================================================
"""


def build_release_notes(tag: str) -> str:
    return f"""## 🚀 一键使用方式（Quick Start）

### 方式 1：在线即开即用（零安装）
- 🌐 **GitHub Pages 在线工作台**：[**https://lusipad.github.io/Axiom/**](https://lusipad.github.io/Axiom/)

### 方式 2：Windows 免环境一键离线包（推荐下载）
1. 下载下方 Assets 中的 **`axiom-workbench-{tag}-oneclick-win-x64.zip`** 并解压；
2. 双击 **`双击一键启动工作台 (免安装).bat`**，无需安装 Python 或 Node.js，自动拉起浏览器进入完整工作台（内置纯前端 CNC 轨迹 A/B 评估与单刀机理快诊引擎）。

### 方式 3：Python 完整后端与 CLI 工具
```bash
pip install axiom_evaluator-{tag.removeprefix("v")}-py3-none-any.whl
axiom serve --open
```

---

## 📦 发行包说明（Release Assets）
| 文件名 | 用途说明 |
| :--- | :--- |
| **`axiom-workbench-{tag}-oneclick-win-x64.zip`** | **Windows 免安装双击一键启动版**（含离线前端引擎、一键启动脚本与离线 Python wheel） |
| `axiom_evaluator-{tag.removeprefix("v")}-py3-none-any.whl` | Python 标准安装包（支持 `axiom serve --open` 与全套 CLI 命令） |
| `axiom-opcua-shadow-{tag}-win-x64.zip` | Windows R7-C/D/E 只读 OPC UA 见证适配器与 TwinCAT 权限校验工具 |
| `axiom_evaluator-{tag.removeprefix("v")}.tar.gz` | 源码归档包 |
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True, help="Release tag, e.g. v0.23.0")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    dist_dir = repo_root / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)

    stage_dir = dist_dir / "oneclick-stage"
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    web_out = stage_dir / "web"
    wheels_out = stage_dir / "wheels"
    web_out.mkdir(parents=True, exist_ok=True)
    wheels_out.mkdir(parents=True, exist_ok=True)

    # Build standalone demo frontend into stage_dir/web without touching src/axiom/web_dist
    npx_cmd = "npx.cmd" if shutil.which("npx.cmd") else "npx"
    subprocess.run(
        [
            npx_cmd,
            "vite",
            "build",
            "--mode",
            "demo",
            "--outDir",
            str(web_out),
            "--emptyOutDir",
        ],
        cwd=repo_root / "web",
        check=True,
    )

    for whl in dist_dir.glob("*.whl"):
        shutil.copy2(whl, wheels_out / whl.name)

    (stage_dir / "start-offline.ps1").write_text(
        OFFLINE_SERVER_PS1, encoding="utf-8-sig"
    )
    (stage_dir / "双击一键启动工作台 (免安装).bat").write_text(
        ONECLICK_BAT, encoding="utf-8"
    )
    (stage_dir / "启动完整Python后端版 (可选).bat").write_text(
        PYTHON_BACKEND_BAT, encoding="utf-8"
    )
    (stage_dir / "使用说明-README.txt").write_text(
        README_TXT.format(tag=args.tag), encoding="utf-8-sig"
    )

    zip_path = dist_dir / f"axiom-workbench-{args.tag}-oneclick-win-x64.zip"
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(stage_dir.rglob("*")):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(stage_dir))

    shutil.rmtree(stage_dir)

    notes_path = dist_dir / "release-notes.md"
    notes_path.write_text(build_release_notes(args.tag), encoding="utf-8")
    print(f"Built one-click bundle: {zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
