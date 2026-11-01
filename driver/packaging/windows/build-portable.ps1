# Windows 便携版打包：PyInstaller → dist\MK87Config\ → dist-packages\*.zip
# 用法： powershell -ExecutionPolicy Bypass -File packaging\windows\build-portable.ps1
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $PSScriptRoot
Set-Location $here

if (-not (Test-Path '.venv')) {
    Write-Host '创建虚拟环境…'
    python -m venv .venv
    & .venv\Scripts\python.exe -m pip install --upgrade pip -q
    & .venv\Scripts\python.exe -m pip install -r packaging\requirements.txt -q
}
$py = Join-Path $here '.venv\Scripts\python.exe'

if (-not (Test-Path 'dist\MK87Config')) {
    Write-Host 'PyInstaller 打包中…'
    & $py -m PyInstaller packaging\mk87.spec --noconfirm --clean
}

$version = (Get-Content "$here\mk87lib\__init__.py" | Select-String '__version__ = "(.*)"').Matches.Groups[1].Value
$outDir = Join-Path $here 'dist-packages'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$zip = Join-Path $outDir "MK87Studio-$version-win64-portable.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path "dist\MK87Config" -DestinationPath $zip -CompressionLevel Optimal
Write-Host "已生成: $zip"
