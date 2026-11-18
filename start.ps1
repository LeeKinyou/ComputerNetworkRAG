<#
    一键启动 ComputerNetworkRAG（单进程、单端口）。

    用法：
        .\start.ps1               # 同步依赖、构建前端、启动服务并打开浏览器
        .\start.ps1 -SkipBuild    # 前端已构建时跳过 npm build
        .\start.ps1 -NoBrowser    # 不自动打开浏览器

    服务地址 http://127.0.0.1:8000
#>

param(
    [switch]$SkipBuild,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$BaseUrl = 'http://127.0.0.1:8000'
$HealthUrl = "$BaseUrl/api/v2/health"

function Write-Step([string]$Text) {
    Write-Host "`n==> $Text" -ForegroundColor Cyan
}

function Test-Service {
    try {
        $response = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 3
        return $response.status -eq 'ok'
    } catch {
        return $false
    }
}

if (Test-Service) {
    Write-Host '服务已经在运行，直接打开浏览器。' -ForegroundColor Green
    if (-not $NoBrowser) { Start-Process $BaseUrl }
    exit 0
}

Write-Step '检查运行环境'
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host '未找到 uv。请先安装后再运行：' -ForegroundColor Yellow
    Write-Host '  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
    exit 1
}
Write-Host ("uv: " + (uv --version))

$envFile = Join-Path $Root '.env'
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $Root '.env.example') $envFile
    Write-Host '已从 .env.example 生成 .env，请按需填写 LLM_API_KEY 与 EMBEDDING_API_KEY。' -ForegroundColor Yellow
}

$keyLine = Get-Content $envFile | Where-Object { $_ -match '^LLM_API_KEY=' } | Select-Object -First 1
$keyValue = if ($keyLine) { ($keyLine -split '=', 2)[1].Trim() } else { '' }
if ([string]::IsNullOrWhiteSpace($keyValue)) {
    Write-Host '提示：LLM_API_KEY 为空，问答会使用模板答案；填入后重启即可启用模型润色。' -ForegroundColor Yellow
}

Write-Step '同步后端依赖'
Push-Location $Backend
try {
    uv sync --quiet
    if ($LASTEXITCODE -ne 0) { throw 'uv sync 失败' }
} finally {
    Pop-Location
}
Write-Host '依赖已就绪。'

$staticIndex = Join-Path $Backend 'app\static\index.html'
if (-not $SkipBuild) {
    Write-Step '构建前端'
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        if (Test-Path $staticIndex) {
            Write-Host '未找到 npm，沿用已有的前端构建产物。' -ForegroundColor Yellow
        } else {
            Write-Host '未找到 npm，且没有构建产物。请安装 Node.js 后重试。' -ForegroundColor Red
            exit 1
        }
    } else {
        Push-Location $Frontend
        try {
            if (-not (Test-Path (Join-Path $Frontend 'node_modules'))) {
                npm install
                if ($LASTEXITCODE -ne 0) { throw 'npm install 失败' }
            }
            npm run build
            if ($LASTEXITCODE -ne 0) { throw '前端构建失败' }
        } finally {
            Pop-Location
        }
    }
} elseif (Test-Path $staticIndex) {
    Write-Step '跳过前端构建'
    Write-Host '使用已有构建产物。'
}

Write-Step '启动服务'
$process = Start-Process -FilePath 'uv' `
    -ArgumentList 'run', 'python', '-m', 'app.main' `
    -WorkingDirectory $Backend `
    -PassThru

$deadline = (Get-Date).AddSeconds(40)
while ((Get-Date) -lt $deadline) {
    if (Test-Service) { break }
    Start-Sleep -Milliseconds 800
}

if (-not (Test-Service)) {
    Write-Host '服务未在 40 秒内就绪。请在启动窗口查看日志，或运行：' -ForegroundColor Red
    Write-Host "  cd `"$Backend`"; uv run python -m app.main"
    exit 1
}

Write-Host ("服务已启动：$BaseUrl（进程 PID " + $process.Id + '）') -ForegroundColor Green
if (-not $NoBrowser) { Start-Process $BaseUrl }
Write-Host '关闭弹出的服务窗口即停止服务。'
