# Windows 安装包构建：PyInstaller → Inno Setup → dist-installer\*setup.exe
# 依赖： Inno Setup 6（https://jrsoftware.org/isdl.php，或用 choco install innosetup）
# 用法： powershell -ExecutionPolicy Bypass -File packaging\windows\build-installer.ps1
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $PSScriptRoot
Set-Location $here

if (-not (Test-Path 'dist\MK87Config')) {
    Write-Host 'PyInstaller 打包中…'
    if (-not (Test-Path '.venv')) {
        python -m venv .venv
        & .venv\Scripts\python.exe -m pip install --upgrade pip -q
        & .venv\Scripts\python.exe -m pip install -r packaging\requirements.txt -q
    }
    & .venv\Scripts\python.exe -m PyInstaller packaging\mk87.spec --noconfirm --clean
} else {
    Write-Host '使用已有 dist\MK87Config（如需重建请删除该目录）'
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
    Write-Warning '未找到 Inno Setup（ISCC.exe）。'
    Write-Warning '安装方法： winget install JRSoftware.InnoSetup   或  choco install innosetup'
    Write-Warning '或先使用便携版： packaging\windows\build-portable.ps1'
    exit 2
}

New-Item -ItemType Directory -Force -Path (Join-Path $here 'dist-installer') | Out-Null
$iss = Join-Path $here 'packaging\windows\mk87.iss'
Write-Host "编译安装包: $iscc $iss"
& $iscc $iss | Out-Host
if ($LASTEXITCODE -ne 0) {
    Write-Warning '安装包编译失败（常见原因：缺少中文语言文件 ChineseSimplified.isl）。'
    Write-Warning '可编辑 packaging\windows\mk87.iss 删除 chinesesimplified 语言行后重试。'
    exit $LASTEXITCODE
}
Write-Host ''
Get-ChildItem (Join-Path $here 'dist-installer\*setup.exe') | ForEach-Object { Write-Host "已生成: $($_.FullName)" }
