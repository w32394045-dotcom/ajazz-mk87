# MK87 Studio - Windows Defender false-positive whitelist helper (v0.1.8.7)
#
# Why: Windows Defender flags the CI-built MK87Config.exe as
#      Trojan:Win32/Bearfoos.A!ml (machine-learning false positive for an
#      unsigned PyInstaller binary). This helper adds a Defender exclusion for
#      the app folder + installer and tries to restore the quarantined file.
#
# Usage: double-click the companion .cmd, or right-click -> "Run with PowerShell".
#        The script self-elevates via UAC. Safe to run again.
#
# After Microsoft fixes the definition, remove the exclusion with:
#   Remove-MpPreference -ExclusionPath "C:\Program Files\MK87 Studio"

$ErrorActionPreference = 'Continue'
$threat = 'Trojan:Win32/Bearfoos.A!ml'
$appDirs = @(
    'C:\Program Files\MK87 Studio',
    (Join-Path $env:LOCALAPPDATA 'Programs\MK87 Studio')
)
$homeDir = [Environment]::GetFolderPath('UserProfile')
$installer = Join-Path $homeDir 'Downloads\MK87Studio-0.1.8.7-win64-setup.exe'

function Test-Administrator {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Administrator)) {
    Write-Host 'Requesting administrator rights (UAC prompt)...' -ForegroundColor Cyan
    $args = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    try {
        Start-Process powershell.exe -Verb RunAs -ArgumentList $args
    } catch {
        Write-Host "Could not elevate: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host 'Right-click this file -> "Run with PowerShell" as administrator instead.'
    }
    exit 0
}

Write-Host ''
Write-Host 'MK87 Studio - Windows Defender false-positive whitelist' -ForegroundColor Cyan
Write-Host ("Threat name: {0}" -f $threat)
Write-Host ''

# 1) Try to restore the quarantined / removed exe (best effort).
$mp = Join-Path $env:ProgramFiles 'Windows Defender\MpCmdRun.exe'
if (Test-Path $mp) {
    Write-Host 'Trying to restore the quarantined file...'
    try {
        & $mp -Restore -Name $threat
    } catch {
        Write-Host "  (restore did not succeed - you can simply reinstall; details: $($_.Exception.Message))"
    }
} else {
    Write-Host 'MpCmdRun.exe not found; skipping quarantine restore.'
}

# 2) Add exclusions for the install folder(s) and the installer.
$added = 0
foreach ($d in $appDirs) {
    if (Test-Path $d) {
        try {
            Add-MpPreference -ExclusionPath $d -ErrorAction Stop
            Write-Host ("  [ok] exclusion: {0}" -f $d) -ForegroundColor Green
            $added++
        } catch {
            Write-Host ("  [fail] exclusion {0}: {1}" -f $d, $_.Exception.Message) -ForegroundColor Yellow
        }
    }
}
if (Test-Path $installer) {
    try {
        Add-MpPreference -ExclusionPath $installer -ErrorAction Stop
        Write-Host ("  [ok] exclusion: {0}" -f $installer) -ForegroundColor Green
        $added++
    } catch {
        Write-Host ("  [fail] exclusion {0}: {1}" -f $installer, $_.Exception.Message) -ForegroundColor Yellow
    }
} else {
    Write-Host ("  (installer not found at {0}; add its path manually if it is elsewhere)" -f $installer)
}

Write-Host ''
Write-Host 'Next steps:' -ForegroundColor Cyan
Write-Host '  1. Re-run the official installer: MK87Studio-0.1.8.7-win64-setup.exe'
Write-Host '     (the installer re-creates MK87Config.exe, the shortcut and the uninstall entry).'
Write-Host '  2. Verify: the app starts and Windows Security shows it in "Allowed threats".'
Write-Host '  3. Report the false positive to Microsoft (the real fix, ~2 min):'
Write-Host '     https://www.microsoft.com/en-us/wdsi/filesubmission'
Write-Host '     -> "Software developer" -> "I believe this file is incorrectly detected"'
Write-Host '     -> upload the installer, threat name: Trojan:Win32/Bearfoos.A!ml,'
Write-Host '        detection date: 2026-11-07, SHA256:'
Write-Host '        54fbbaae6eb2c6565dba76a923b58e3e1beab3bd83454b07267589ecde3d6c5f'
Write-Host '  4. When Microsoft fixes the definition, remove the temporary exclusion:'
Write-Host '     Remove-MpPreference -ExclusionPath "C:\Program Files\MK87 Studio"'
Write-Host ''
Write-Host ("Exclusions added: {0}" -f $added) -ForegroundColor Cyan
Write-Host 'Done.'
if (-not $env:MK87_NOPAUSE) {
    Read-Host 'Press Enter to close'
}
