# E4b：验证「方案 B（软件隔离）」的第二轮实验
#   Tier1: 用 CM_Disable_DevNode 原始 API 禁用 dongle 复合设备（cmdlet 报"不支持"）
#   Tier2: 若 Tier1 失败 → 逐个禁用 dongle 的 MI 子设备
#   Tier3: 若仍不行 → DIF_REMOVE 卸载"失败的那个"复合设备实例 + 重扫其父 hub
#   Tier4: 若仍不行 → 重枚举父 hub（最后手段）
# 用法（必须管理员）：
#   powershell -ExecutionPolicy Bypass -File e4b_planB2.ps1 -Mode auto
#   powershell -ExecutionPolicy Bypass -File e4b_planB2.ps1 -Mode restore
param(
    [string]$Mode = 'auto',
    [string]$OutFile = 'C:\Users\ptfm\Documents\ajazz-re\docs\e4b_planB2.json'
)

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'

$state = [ordered]@{ startTime = (Get-Date).ToString('s'); mode = $Mode; steps = @(); notes = @() }

function Step($name, $data) {
    $script:state.steps += [ordered]@{ time = (Get-Date).ToString('HH:mm:ss.fff'); name = $name; data = $data }
}

if (-not ('PlanB2.Api' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
namespace PlanB2 {
  [StructLayout(LayoutKind.Sequential)]
  public struct SP_DEVINFO_DATA { public uint cbSize; public Guid ClassGuid; public uint DevInst; public IntPtr Reserved; }
  [StructLayout(LayoutKind.Sequential)]
  public struct SP_CLASSINSTALL_HEADER { public uint cbSize; public uint InstallFunction; }
  [StructLayout(LayoutKind.Sequential)]
  public struct SP_REMOVEDEVICE_PARAMS { public SP_CLASSINSTALL_HEADER ClassInstallHeader; public uint Scope; public uint HwProfile; }
  public static class Api {
    [DllImport("setupapi.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    public static extern IntPtr SetupDiCreateDeviceInfoList(IntPtr ClassGuid, IntPtr hwndParent);
    [DllImport("setupapi.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    public static extern bool SetupDiOpenDeviceInfoW(IntPtr DeviceInfoSet, string DeviceInstanceId, IntPtr hwndParent, uint OpenFlags, ref SP_DEVINFO_DATA DeviceInfoData);
    [DllImport("setupapi.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    public static extern bool SetupDiSetClassInstallParamsW(IntPtr DeviceInfoSet, ref SP_DEVINFO_DATA DeviceInfoData, ref SP_REMOVEDEVICE_PARAMS ClassInstallParams, uint ClassInstallParamsSize);
    [DllImport("setupapi.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    public static extern bool SetupDiCallClassInstaller(uint InstallFunction, IntPtr DeviceInfoSet, ref SP_DEVINFO_DATA DeviceInfoData);
    [DllImport("setupapi.dll", SetLastError=true)]
    public static extern bool SetupDiDestroyDeviceInfoList(IntPtr DeviceInfoSet);
    [DllImport("cfgmgr32.dll", CharSet=CharSet.Unicode)]
    public static extern int CM_Locate_DevNodeW(out uint pdnDevInst, string pDeviceID, uint ulFlags);
    [DllImport("cfgmgr32.dll")]
    public static extern int CM_Get_Parent(out uint pdnDevInst, uint dnDevInst, uint ulFlags);
    [DllImport("cfgmgr32.dll")]
    public static extern int CM_Disable_DevNode(uint dnDevInst, uint ulFlags);
    [DllImport("cfgmgr32.dll")]
    public static extern int CM_Enable_DevNode(uint dnDevInst, uint ulFlags);
    [DllImport("cfgmgr32.dll")]
    public static extern int CM_Reenumerate_DevNode(uint dnDevInst, uint ulFlags);
    [DllImport("cfgmgr32.dll", CharSet=CharSet.Unicode)]
    public static extern int CM_Get_Device_IDW(uint dnDevInst, StringBuilder Buffer, uint BufferLen, uint ulFlags);
  }
}
'@
}

function Locate([string]$id) {
    $di = [uint32]0
    $r = [PlanB2.Api]::CM_Locate_DevNodeW([ref]$di, $id, 0)
    return @{ result = $r; devInst = $di }
}
function DevId([uint32]$di) {
    $sb = New-Object System.Text.StringBuilder 512
    $r = [PlanB2.Api]::CM_Get_Device_IDW($di, $sb, 512, 0)
    if ($r -eq 0) { return $sb.ToString() } else { return "err=$r" }
}
function DisableRaw([string]$id) {
    $l = Locate $id
    Step 'locate' @{ instanceId = $id; result = $l.result }
    if ($l.result -ne 0) { return $l.result }
    $r = [PlanB2.Api]::CM_Disable_DevNode($l.devInst, 0)
    Step 'cm-disable' @{ instanceId = $id; result = $r }
    return $r
}
function EnableRaw([string]$id) {
    $l = Locate $id
    if ($l.result -ne 0) { return $l.result }
    $r = [PlanB2.Api]::CM_Enable_DevNode($l.devInst, 0)
    Step 'cm-enable' @{ instanceId = $id; result = $r }
    return $r
}
function Reenum([string]$id, [uint32]$flags) {
    $l = Locate $id
    if ($l.result -ne 0) { return $l.result }
    $r = [PlanB2.Api]::CM_Reenumerate_DevNode($l.devInst, $flags)
    Step 'cm-reenumerate' @{ instanceId = $id; flags = $flags; result = $r }
    return $r
}
function RemoveDev([string]$id) {
    $set = [PlanB2.Api]::SetupDiCreateDeviceInfoList([IntPtr]::Zero, [IntPtr]::Zero)
    if ($set -eq [IntPtr]::Zero) { $e = [Runtime.InteropServices.Marshal]::GetLastWin32Error(); Step 'remove-open-set-fail' @{ err = $e }; return $e }
    $d = New-Object PlanB2.SP_DEVINFO_DATA
    $d.cbSize = [uint32][Runtime.InteropServices.Marshal]::SizeOf([type][PlanB2.SP_DEVINFO_DATA])
    $ok = [PlanB2.Api]::SetupDiOpenDeviceInfoW($set, $id, [IntPtr]::Zero, 0, [ref]$d)
    if (-not $ok) { $e = [Runtime.InteropServices.Marshal]::GetLastWin32Error(); [PlanB2.Api]::SetupDiDestroyDeviceInfoList($set) | Out-Null; Step 'remove-open-fail' @{ instanceId = $id; err = $e }; return $e }
    $p = New-Object PlanB2.SP_REMOVEDEVICE_PARAMS
    $p.ClassInstallHeader.cbSize = [uint32][Runtime.InteropServices.Marshal]::SizeOf([type][PlanB2.SP_CLASSINSTALL_HEADER])
    $p.ClassInstallHeader.InstallFunction = 5   # DIF_REMOVE
    $p.Scope = 2                                # SP_REMOVEDEVICE_GLOBAL
    $p.HwProfile = 0
    $ok2 = [PlanB2.Api]::SetupDiSetClassInstallParamsW($set, [ref]$d, [ref]$p, [uint32][Runtime.InteropServices.Marshal]::SizeOf([type][PlanB2.SP_REMOVEDEVICE_PARAMS]))
    if (-not $ok2) { $e = [Runtime.InteropServices.Marshal]::GetLastWin32Error(); Step 'remove-setparams-fail' @{ instanceId = $id; err = $e } }
    $ok3 = [PlanB2.Api]::SetupDiCallClassInstaller(5, $set, [ref]$d)
    $e3 = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
    [PlanB2.Api]::SetupDiDestroyDeviceInfoList($set) | Out-Null
    Step 'dif-remove' @{ instanceId = $id; ok = $ok3; err = $e3 }
    return $(if ($ok3) { 0 } else { $e3 })
}

function StatusOf([string]$id) {
    $d = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -eq $id } | Select-Object -First 1
    if ($d) { return @{ status = "$($d.Status)"; problem = "$($d.Problem)" } } else { return @{ status = 'missing'; problem = '' } }
}
function WaitKey([string]$kbdId) {
    $st = StatusOf $kbdId
    Step 'check-target' @{ instanceId = $kbdId; status = $st.status; problem = $st.problem }
    return $st.status -ne 'Error'
}

Write-Output "== 方案 B 第二轮实验 ($Mode) =="
$all = @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -match 'VID_0C45' })
$parents = @($all | Where-Object { $_.InstanceId -match '^USB\\VID_0C45&PID_(8047|FEFE)\\' })
foreach ($p in $parents) { Write-Output ("parent: {0} status={1}" -f $p.InstanceId, $p.Status) }

$kbd = $parents | Where-Object { $_.InstanceId -match 'PID_8047' } | Select-Object -First 1
$dng = $parents | Where-Object { $_.InstanceId -match 'PID_FEFE' } | Select-Object -First 1

if ($Mode -eq 'restore') {
    if ($dng) { Reenum $dng.InstanceId 0 | Out-Null }
    if ($kbd) { Reenum $kbd.InstanceId 0 | Out-Null }
    Start-Sleep -Seconds 2
    $snap = @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -match '^USB\\VID_0C45' } | ForEach-Object { @{ id = $_.InstanceId; status = "$($_.Status)" } })
    Step 'restore-final' $snap
    $state | ConvertTo-Json -Depth 6 | Out-File -FilePath $OutFile -Encoding UTF8
    Write-Output 'restore done'
    exit 0
}

$targetId = $null; $otherId = $null
if ($kbd -and $dng) {
    if ($kbd.Status -eq 'Error' -and $dng.Status -ne 'Error') { $targetId = $kbd.InstanceId; $otherId = $dng.InstanceId }
    elseif ($dng.Status -eq 'Error' -and $kbd.Status -ne 'Error') { $targetId = $dng.InstanceId; $otherId = $kbd.InstanceId }
    else { Write-Output "两边都正常或都坏，跳过 ($($kbd.Status)/$($dng.Status))"; Step 'skip' @{}; $state | ConvertTo-Json -Depth 6 | Out-File -FilePath $OutFile -Encoding UTF8; exit 3 }
}
else { Write-Output '两个设备没有同时存在'; exit 2 }
Step 'targets' @{ target = $targetId; other = $otherId }
Write-Output "target=$targetId`nother=$otherId"

# ---- Tier1: CM_Disable_DevNode(other) ----
Write-Output 'Tier1: CM_Disable_DevNode(other)'
$r = DisableRaw $otherId
Start-Sleep -Seconds 2
if ($r -eq 0) {
    # 目标设备重试
    [PlanB2.Api]::CM_Disable_DevNode((Locate $targetId).devInst, 0) | Out-Null
    Start-Sleep -Milliseconds 500
    [PlanB2.Api]::CM_Enable_DevNode((Locate $targetId).devInst, 0) | Out-Null
    Start-Sleep -Seconds 2
    Reenum $targetId 0 | Out-Null
    Start-Sleep -Seconds 1
}
$tier1 = WaitKey $targetId
$state.notes += "tier1=$tier1"

if (-not $tier1) {
    # ---- Tier2: 禁用 other 的 MI 子设备 ----
    Write-Output 'Tier2: disable MI children of other'
    $mi = @($all | Where-Object { $_.InstanceId -match '^USB\\VID_0C45' -and $_.InstanceId -match '&MI_' -and $_.InstanceId -match ($(if ($otherId -match 'PID_8047') { 'PID_8047' } else { 'PID_FEFE' })) })
    foreach ($m in $mi) { $rr = DisableRaw $m.InstanceId; Write-Output ("  disable {0} -> {1}" -f $m.InstanceId, $rr) }
    Start-Sleep -Seconds 2
    Reenum $targetId 0 | Out-Null
    Start-Sleep -Seconds 2
    $tier2 = WaitKey $targetId
    $state.notes += "tier2=$tier2"
}
else { $tier2 = $true }

$ok = $tier1 -or $tier2
if (-not $ok) {
    # ---- Tier3: DIF_REMOVE 目标实例 + 重扫父 hub ----
    Write-Output 'Tier3: DIF_REMOVE(target composite) + rescan parent'
    $l = Locate $targetId
    $parentDev = [uint32]0
    $pr = [PlanB2.Api]::CM_Get_Parent([ref]$parentDev, $l.devInst, 0)
    $parentId = DevId $parentDev
    Step 'target-parent' @{ result = $pr; parentId = $parentId }
    $rm = RemoveDev $targetId
    Start-Sleep -Seconds 1
    Reenum $parentId 0 | Out-Null
    Start-Sleep -Seconds 2
    # 重新等设备出现
    for ($i = 0; $i -lt 8; $i++) {
        Start-Sleep -Milliseconds 800
        $st = StatusOf $targetId
        Step 'tier3-wait' @{ i = $i; status = $st.status }
        if ($st.status -ne 'missing') { break }
    }
    $tier3 = WaitKey $targetId
    $state.notes += "tier3=$tier3 parent=$parentId"
}

$final = @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -match '^USB\\VID_0C45' } | ForEach-Object { @{ id = $_.InstanceId; status = "$($_.Status)" } })
Step 'final' $final
$state | ConvertTo-Json -Depth 6 | Out-File -FilePath $OutFile -Encoding UTF8
Write-Output ('最终: ' + (($final | Where-Object { $_.status -eq 'Error' } | ForEach-Object { $_.id }) -join ', '))
Write-Output "日志 -> $OutFile"
exit 0
