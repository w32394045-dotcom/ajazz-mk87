# ============================================================================
# run_test.ps1 —— 端到端测试：用 run.js 抓 test/fakehid.html（不用真实键盘）
#
# 做的事：
#   1. 起 run.js（可见 Chrome 窗口，非 headless），导航到本地 file:/// 测试页
#   2. 测试页自己伪造 navigator.hid，触发 open/sendReport/sendFeatureReport/
#      receiveFeatureReport/inputreport/connect/disconnect/close
#   3. --eval 打印页面内的断言结果（window.__TEST_RESULT）
#   4. 退出后校验 JSONL：test/verify.js
#   5. 清理可能残留的、由本测试拉起（profile 名带 ajazz-cdp-profile）的 Chrome
#
# 运行：  powershell -ExecutionPolicy Bypass -File .\run_test.ps1
#         pwsh -File .\run_test.ps1        （PowerShell 7 也一样）
# 退出码：0 = 全部通过
#
# 注意：本文件保存为「UTF-8 带 BOM」，否则 Windows PowerShell 5.1 会按 GBK
#       解码，中文注释会把语法搞坏（这是踩过的坑）。
# ============================================================================

[CmdletBinding()]
param(
    [string]$Node = '',
    [int]$Port = 9411,
    [int]$AutoExit = 14
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not $Node) {
    $Node = 'C:\Users\ptfm\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe'
    if ($env:DSH_NODE) { $Node = $env:DSH_NODE }
}
if (-not (Test-Path $Node)) { throw "找不到 node.exe: $Node（可用 -Node 指定）" }

$Page    = Join-Path $Root 'test\fakehid.html'
$Log     = Join-Path $Root 'test\ajazz_test_log.jsonl'
$Stdout  = Join-Path $Root 'test\run_test_stdout.txt'
$RunJs   = Join-Path $Root 'run.js'
$Verify  = Join-Path $Root 'test\verify.js'

if (-not (Test-Path $Page)) { throw "找不到测试页: $Page" }
$Url = ([System.Uri]$Page).AbsoluteUri
Write-Host "测试页: $Url" -ForegroundColor Cyan

# 清掉上次的产物，保证结果只反映本次运行
Remove-Item $Log    -ErrorAction SilentlyContinue
Remove-Item $Stdout -ErrorAction SilentlyContinue

# 页面内的断言结果（测试页把它挂在 window.__TEST_RESULT 上）
# 注意：这里刻意写成一个**不含空格**的表达式。Windows PowerShell 5.1 把变量
# 作为参数传给 native exe 时不会自动加引号，带空格的表达式会被拆成多个 argv。
$EvalExpr = 'JSON.stringify(window.__TEST_RESULT)'

Write-Host ''
Write-Host '==== 1/2  运行 run.js（会弹出可见的 Chrome 窗口，测试期间请勿关闭） ====' -ForegroundColor Yellow
Write-Host ''

$out = (& $Node $RunJs --url $Url --out $Log --port $Port --auto-exit $AutoExit --eval-delay 3500 --eval $EvalExpr 2>&1 | Out-String -Width 400)
Write-Host $out
[System.IO.File]::WriteAllText($Stdout, $out, (New-Object System.Text.UTF8Encoding($false)))
$runExit = $LASTEXITCODE

# 兜底：正常 shutdown 会自己关 Chrome；万一没有，只清理由本测试 profile 拉起的进程，
# 绝不碰用户正在用的 Chrome（按命令行里是否含 ajazz-cdp-profile 过滤）
try {
    Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -like '*ajazz-cdp-profile*' } |
        ForEach-Object {
            Write-Host "[cleanup] 结束残留 Chrome PID=$($_.ProcessId)" -ForegroundColor DarkGray
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
} catch { }

Write-Host ''
Write-Host '==== 2/2  校验 JSONL ====' -ForegroundColor Yellow
Write-Host ''

if (-not (Test-Path $Log)) {
    Write-Host "FAIL: 日志文件没有生成: $Log" -ForegroundColor Red
    exit 1
}

& $Node $Verify $Log
$verifyExit = $LASTEXITCODE

Write-Host ''
Write-Host "run.js 退出码 = $runExit ；verify 退出码 = $verifyExit" -ForegroundColor Cyan
if ($runExit -ne 0) { Write-Host '警告: run.js 非 0 退出，详见 test/run_test_stdout.txt' -ForegroundColor Red }

if ($verifyExit -eq 0) { Write-Host '测试通过 ✔' -ForegroundColor Green }
else { Write-Host '测试失败 ✘' -ForegroundColor Red }

exit $verifyExit
