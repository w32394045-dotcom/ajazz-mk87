# E4c：验证「软件拔插」方案——用 DIF_REMOVE 卸载设备实例，模拟"拔掉不用的那个"
# 目标：键盘 USB 复合设备 Code 10 时，把 dongle 设备实例卸载掉（释放它占的 hub 资源），
#       再让键盘复合设备重试/重扫，看是否能启动。
# 用法（管理员）：
#   powershell -ExecutionPolicy Bypass -File e4c_remove_test.ps1 -Mode remove-dongle
#   powershell -ExecutionPolicy Bypass -File e4c_remove_test.ps1 -Mode remove-keyboard
#   powershell -ExecutionPolicy Bypass -File e4c_remove_test.ps1 -Mode restore
param(
    [string]$Mode = 'remove-dongle',
    [string]$OutFile = 'C:\Users\ptfm\Documents\ajazz-re\docs\e4c_remove_test.json'
)
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
$log = [ordered]@{ start = (Get-Date).ToString('s'); mode = $Mode; steps = @() }

function Rec($n, $d) { $script:log.steps += [ordered]@{ t = (Get-Date).ToString('HH:mm:ss.fff'); name = $n; data = $d } }

if (-not ('E4C.Api' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
namespace E4C {
  [StructLayout(LayoutKind.Sequential)]
  public struct SP_DEVINFO_DATA { public uint cbSize; public Guid ClassGuid; public uint DevInst; public IntPtr Reserved; }
  [StructLayout(LayoutKind.Sequential)]
  public struct SP_CLASSINSTALL_HEADER { public uint cbSize; public uint InstallFunction; }
  [StructLayout(LayoutKind.Sequential)]
  public struct SP_REMOVEDEVICE_PARAMS { public SP_CLASSINSTALL_HEADER ClassInstallHeader; public uint Scope; public uint HwProfile; }
  public static class Api {
    [DllImport("setupapi.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    public static extern IntPtr SetupDiGetClassDevsW(IntPtr ClassGuid, string Enumerator, IntPtr hwndParent, uint Flags);
    [DllImport("setupapi.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    public static extern bool SetupDiEnumDeviceInfo(IntPtr DeviceInfoSet, uint MemberIndex, ref SP_DEVINFO_DATA DeviceInfoData);
    [DllImport("setupapi.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    public static extern bool SetupDiGetDeviceInstanceIdW(IntPtr DeviceInfoSet, ref SP_DEVINFO_DATA DeviceInfoData, StringBuilder DeviceInstanceId, uint DeviceInstanceIdSize, out uint RequiredSize);
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
    public static extern int CM_Reenumerate_DevNode(uint dnDevInst, uint ulFlags);
    [DllImport("cfgmgr32.dll", CharSet=CharSet.Unicode)]
    public static extern int CM_Get_Device_IDW(uint dnDevInst, StringBuilder Buffer, uint BufferLen, uint ulFlags);
  }
}
'@
}

function GetDevInfoSet { return [E4C.Api]::SetupDiGetClassDevsW([IntPtr]::Zero, $null, [IntPtr]::Zero, 0x6) }  # DIGCF_ALLCLASSES|DIGCF_PRESENT

function RemoveInstance([string]$instanceId) {
    $set = GetDevInfoSet
    if ($set -eq [IntPtr]::Zero) { $e = [Runtime.InteropServices.Marshal]::GetLastWin32Error(); Rec 'getclassdevs-fail' @{ err = $e }; return $e }
    $d = New-Object E4C.SP_DEVINFO_DATA
    $d.cbSize = [uint32][Runtime.InteropServices.Marshal]::SizeOf([type][E4C.SP_DEVINFO_DATA])
    $found = $false
    for ($i = 0; $i -lt 512; $i++) {
        $ok = [E4C.Api]::SetupDiEnumDeviceInfo($set, [uint32]$i, [ref]$d)
        if (-not $ok) { break }
        $sb = New-Object System.Text.StringBuilder 512
        $req = [uint32]0
        if ([E4C.Api]::SetupDiGetDeviceInstanceIdW($set, [ref]$d, $sb, 512, [ref]$req)) {
            if ($sb.ToString() -eq $instanceId) { $found = $true; break }
        }
    }
    if (-not $found) { [E4C.Api]::SetupDiDestroyDeviceInfoList($set) | Out-Null; Rec 'instance-not-found' $instanceId; return 1168 }
    $rp = New-Object E4C.SP_REMOVEDEVICE_PARAMS
    $rp.ClassInstallHeader.cbSize = [uint32][Runtime.InteropServices.Marshal]::SizeOf([type][E4C.SP_CLASSINSTALL_HEADER])
    $rp.ClassInstallHeader.InstallFunction = 5    # DIF_REMOVE
    $rp.Scope = 2                                 # DI_REMOVEDEVICE_GLOBAL
    $rp.HwProfile = 0
    $okp = [E4C.Api]::SetupDiSetClassInstallParamsW($set, [ref]$d, [ref]$rp, [uint32][Runtime.InteropServices.Marshal]::SizeOf([type][E4C.SP_REMOVEDEVICE_PARAMS]))
    $ep = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
    Rec 'setparams' @{ ok = $okp; err = $ep }
    $okr = [E4C.Api]::SetupDiCallClassInstaller(5, $set, [ref]$d)
    $er = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
    [E4C.Api]::SetupDiDestroyDeviceInfoList($set) | Out-Null
    Rec 'dif-remove' @{ instanceId = $instanceId; ok = $okr; err = $er }
    return $(if ($okr) { 0 } else { $er })
}

function ReenumParent([string]$id) {
    $dn = [uint32]0
    $r = [E4C.Api]::CM_Locate_DevNodeW([ref]$dn, $id, 0)
    if ($r -ne 0) { Rec 'locate-fail' @{ id = $id; r = $r }; return }
    $p = [uint32]0
    $rp = [E4C.Api]::CM_Get_Parent([ref]$p, $dn, 0)
    $sb = New-Object System.Text.StringBuilder 512
    [E4C.Api]::CM_Get_Device_IDW($p, $sb, 512, 0) | Out-Null
    $pid = $sb.ToString()
    $rr = [E4C.Api]::CM_Reenumerate_DevNode($p, 0)
    Rec 'reenum-parent' @{ id = $id; parent = $pid; result = $rr }
}

function Snap($tag) {
    $rows = @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -match 'VID_0C45' } |
        Select-Object @{n = 'id'; e = { $_.InstanceId } }, @{n = 'status'; e = { "$($_.Status)" } }, @{n = 'problem'; e = { "$($_.Problem)" } })
    Rec "snapshot:$tag" $rows
    return $rows
}

Write-Output "== E4c 软件拔插实验 ($Mode) =="
Snap 'initial' | Out-Null
$kbd = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -match '^USB\\VID_0C45&PID_8047\\' } | Select-Object -First 1
$dng = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -match '^USB\\VID_0C45&PID_FEFE\\' } | Select-Object -First 1

if ($Mode -eq 'restore') {
    if ($dng) { ReenumParent $dng.InstanceId }
    if ($kbd) { ReenumParent $kbd.InstanceId }
    Start-Sleep -Seconds 2
    Snap 'final' | Out-Null
    $log | ConvertTo-Json -Depth 6 | Out-File -FilePath $OutFile -Encoding UTF8
    Write-Output 'restore done'; exit 0
}

$targetId = $null; $otherId = $null
if ($kbd -and $dng) {
    if ($kbd.Status -eq 'Error' -and $dng.Status -ne 'Error') { $targetId = $kbd.InstanceId; $otherId = $dng.InstanceId }
    elseif ($dng.Status -eq 'Error' -and $kbd.Status -ne 'Error') { $targetId = $dng.InstanceId; $otherId = $kbd.InstanceId }
    else { Write-Output '没有冲突/两个都坏，停止'; exit 3 }
}
else { Write-Output '两个设备未同时存在'; exit 2 }
Rec 'plan' @{ target = $targetId; other = $otherId }
Write-Output "target=$targetId  other=$otherId"

$removeId = $(if ($Mode -eq 'remove-dongle') { $otherId } else { $targetId })
Write-Output "将卸载: $removeId"
$r = RemoveInstance $removeId
Start-Sleep -Seconds 1
Snap 'after-remove' | Out-Null

# 目标设备：重试 + 重扫父设备
Try { Disable-PnpDevice -InstanceId $targetId -Confirm:$false -ErrorAction Stop } catch {}
Start-Sleep -Milliseconds 500
Try { Enable-PnpDevice -InstanceId $targetId -Confirm:$false -ErrorAction Stop } catch {}
Start-Sleep -Milliseconds 1500
ReenumParent $targetId
Start-Sleep -Seconds 2
Snap 'after-target-retry' | Out-Null

# 判定
$t = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -eq $targetId } | Select-Object -First 1
$kids = @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -match 'VID_0C45' -and $_.InstanceId -match '&MI_' })
$ok = ($t -and $t.Status -ne 'Error' -and $kids.Count -gt 0)
Rec 'result' @{ targetStatus = if ($t) { "$($t.Status)" } else { 'missing' }; miChildren = $kids.Count; ok = $ok }
Write-Output ("结果: ok={0} targetStatus={1} MI children={2}" -f $ok, $(if ($t) { $t.Status } else { 'missing' }), $kids.Count)
$log | ConvertTo-Json -Depth 6 | Out-File -FilePath $OutFile -Encoding UTF8
Write-Output "日志 -> $OutFile"
if ($ok) { exit 0 } else { exit 1 }
