# Build Windows installer: PyInstaller -> Inno Setup -> dist-installer\*setup.exe
# Requires Inno Setup 6 (https://jrsoftware.org/isdl.php or: choco install innosetup)
# Usage: powershell -ExecutionPolicy Bypass -File packaging\windows\build-installer.ps1
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $here

$venvPy = Join-Path $here '.venv\Scripts\python.exe'
if (Test-Path $venvPy) { $py = $venvPy } else { $py = 'python' }

if (-not (Test-Path 'dist\MK87Config')) {
    Write-Host 'Running PyInstaller...'
    & $py -m PyInstaller packaging\mk87.spec --noconfirm --clean
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
} else {
    Write-Host 'Using existing dist\MK87Config (delete it to rebuild)'
}

$candidates = @(
    (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
    (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe'),
    'iscc.exe'
)
$iscc = $null
foreach ($c in $candidates) {
    if ($c -and (Test-Path $c)) { $iscc = $c; break }
    if ($c -eq 'iscc.exe') {
        $cmd = Get-Command iscc.exe -ErrorAction SilentlyContinue
        if ($cmd) { $iscc = $cmd.Source }
    }
}
if (-not $iscc) {
    Write-Warning 'Inno Setup (ISCC.exe) not found.'
    Write-Warning 'Install: winget install JRSoftware.InnoSetup  or  choco install innosetup'
    Write-Warning 'Or use the portable package: packaging\windows\build-portable.ps1'
    exit 2
}

New-Item -ItemType Directory -Force -Path (Join-Path $here 'dist-installer') | Out-Null
$iss = Join-Path $here 'packaging\windows\mk87.iss'

# Inno Setup ships a limited language set; drop the Chinese language line when
# ChineseSimplified.isl is missing so CI can still produce the English installer.
$isl = Join-Path (Split-Path $iscc) 'Languages\ChineseSimplified.isl'
$useIss = $iss
if (-not (Test-Path $isl)) {
    $tmpIss = Join-Path (Split-Path $iss) '_build_tmp.iss'
    $content = Get-Content $iss -Raw
    $content = $content -replace '(?m)^\s*Name:\s*"chinesesimplified".*\r?\n', ''
    Set-Content -Path $tmpIss -Value $content -Encoding UTF8
    $useIss = $tmpIss
    Write-Host 'ChineseSimplified.isl not found - building English-only installer'
}

Write-Host "Compiling installer: $iscc $useIss"
& $iscc $useIss | Out-Host
$code = $LASTEXITCODE
if ($useIss -ne $iss) { Remove-Item $useIss -Force -ErrorAction SilentlyContinue }
if ($code -ne 0) {
    Write-Warning 'Installer compilation failed.'
    exit $code
}
Write-Host ''
Get-ChildItem (Join-Path $here 'dist-installer\*setup.exe') | ForEach-Object { Write-Host "Built: $($_.FullName)" }
