# Build Windows portable package: PyInstaller -> dist\MK87Config\ -> dist-packages\*.zip
# Usage: powershell -ExecutionPolicy Bypass -File packaging\windows\build-portable.ps1
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $PSScriptRoot
Set-Location $here

# Pick interpreter: local venv if present, else the CI/system python
$venvPy = Join-Path $here '.venv\Scripts\python.exe'
if (Test-Path $venvPy) {
    $py = $venvPy
} else {
    $py = 'python'
}

if (-not (Test-Path 'dist\MK87Config')) {
    Write-Host 'Running PyInstaller...'
    & $py -m PyInstaller packaging\mk87.spec --noconfirm --clean
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
} else {
    Write-Host 'Using existing dist\MK87Config (delete it to rebuild)'
}

$version = (Get-Content "$here\mk87lib\__init__.py" | Select-String '__version__ = "(.*)"').Matches.Groups[1].Value
$outDir = Join-Path $here 'dist-packages'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$zip = Join-Path $outDir "MK87Studio-$version-win64-portable.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path "dist\MK87Config" -DestinationPath $zip -CompressionLevel Optimal
Write-Host "Built: $zip"
