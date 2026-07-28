# 一键启动后端（Windows PowerShell）
# 首次运行会自动安装依赖，之后直接启动。
$ErrorActionPreference = "Stop"
Set-Location -Path (Join-Path $PSScriptRoot "backend")

Write-Host "==> 安装/检查后端依赖..." -ForegroundColor Cyan
python -m pip install -r requirements.txt

Write-Host "==> 启动后端 http://127.0.0.1:8000 (Ctrl+C 停止)" -ForegroundColor Green
python -m uvicorn app.main:app --reload --port 8000
