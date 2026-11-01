# Windows 打包脚本：在 driver/ 目录下运行
#   powershell -ExecutionPolicy Bypass -File packaging\build-win.ps1
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $PSScriptRoot
Set-Location $here

if (-not (Test-Path '.venv')) {
    Write-Host '创建虚拟环境…'
    python -m venv .venv
}
$py = Join-Path $here '.venv\Scripts\python.exe'
& $py -m pip install --upgrade pip -q
& $py -m pip install -r packaging\requirements.txt -q
& $py -m pip install pyinstaller -q
& $py -m PyInstaller packaging\mk87.spec --noconfirm --clean
Write-Host ''
Write-Host "打包完成: $here\dist\MK87Config\MK87Config.exe"
