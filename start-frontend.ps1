# 一键启动前端（Windows PowerShell）
# 首次运行会自动安装依赖，之后直接启动开发服务器。
$ErrorActionPreference = "Stop"
Set-Location -Path (Join-Path $PSScriptRoot "frontend")

if (-not (Test-Path "node_modules")) {
    Write-Host "==> 首次运行，安装前端依赖..." -ForegroundColor Cyan
    npm install
}

Write-Host "==> 启动前端 http://localhost:3000 (Ctrl+C 停止)" -ForegroundColor Green
npm run dev
