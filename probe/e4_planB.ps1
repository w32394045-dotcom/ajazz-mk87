# E4/E5 实验：验证「方案 B（软件隔离）」是否成立
# 逻辑：两个 VID_0C45 复合设备同时插入、其中一个 Code 10 时，
#       1) 禁用"没在报错"的那个（释放资源）
#       2) 对报错的那个做 disable+enable 重试启动，不行再 CM_Reenumerate
#       3) 检查目标设备子接口是否恢复
# 用法（必须管理员）：
#   powershell -ExecutionPolicy Bypass -File e4_planB.ps1 -Mode auto
#   powershell -ExecutionPolicy Bypass -File e4_planB.ps1 -Mode restore
param(
    [string]$Mode = 'auto',
    [string]$OutFile = 'C:\Users\ptfm\Documents\ajazz-re\docs\e4_planB.json'
)

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'

$state = [ordered]@{
    startTime  = (Get-Date).ToString('s')
    mode       = $Mode
    elevated   = $true
    steps      = @()
    disabled   = @()
    targetOK   = $null
    restored   = $null
}

function Step($name, $data) {
    $script:state.steps += [ordered]@{
        time = (Get-Date).ToString('HH:mm:ss.fff')
        name = $name
        data = $data
    }
}

function Snapshot($tag) {
    $devs = @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
        Where-Object { $_.InstanceId -match 'VID_0C45' } |
        Select-Object @{n = 'instanceId'; e = { $_.InstanceId } },
                      @{n = 'status'; e = { "$($_.Status)" } },
                      @{n = 'class'; e = { "$($_.Class)" } },
                      @{n = 'problem'; e = { "$($_.Problem)" } },
                      @{n = 'friendly'; e = { "$($_.FriendlyName)" } })
    Step "snapshot:$tag" $devs
    return $devs
}

# C# P/Invoke：CM_Locate_DevNodeW + CM_Reenumerate_DevNode（1809 上可用）
if (-not ('PlanB.CM' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace PlanB {
  public static class CM {
    [DllImport("cfgmgr32.dll", CharSet = CharSet.Unicode)]
    public static extern int CM_Locate_DevNodeW(out uint pdnDevInst, string pDeviceID, uint ulFlags);
    [DllImport("cfgmgr32.dll")]
    public static extern int CM_Reenumerate_DevNode(uint dnDevInst, uint ulFlags);
  }
}
'@
}

function Reenumerate([string]$instanceId, [uint32]$flags) {
    $devInst = [uint32]0
    $r = [PlanB.CM]::CM_Locate_DevNodeW([ref]$devInst, $instanceId, 0)
    Step 'locate' @{ instanceId = $instanceId; result = $r; devInst = $devInst }
    if ($r -ne 0) { return $r }
    $r2 = [PlanB.CM]::CM_Reenumerate_DevNode($devInst, $flags)
    Step 'reenumerate' @{ instanceId = $instanceId; flags = $flags; result = $r2 }
    return $r2
}

Write-Output "== 方案 B 实验开始 ($Mode) =="

$devs = Snapshot 'initial'
$parents = @($devs | Where-Object {
        $_.instanceId -match '^USB\\VID_0C45&PID_(8047|FEFE)\\'
    })
foreach ($p in $parents) { Write-Output ("parent: {0} status={1} problem={2}" -f $p.instanceId, $p.status, $p.problem) }

if ($Mode -eq 'restore') {
    # 读上次记录的被禁用设备，逐个启用
    $prev = $null
    if (Test-Path $OutFile) { $prev = Get-Content $OutFile -Raw | ConvertFrom-Json }
    if ($prev -and $prev.disabled) {
        foreach ($id in $prev.disabled) {
            Write-Output "enable: $id"
            try { Enable-PnpDevice -InstanceId $id -Confirm:$false -ErrorAction Stop; Step 'enable-ok' $id }
            catch { Step 'enable-fail' @{ instanceId = $id; error = "$_" } }
            Start-Sleep -Milliseconds 800
        }
    }
    else {
        # 没有记录就尝试启用所有 Error 状态的 0C45 设备
        $errs = @($devs | Where-Object { $_.status -eq 'Error' })
        foreach ($e in $errs) {
            try { Enable-PnpDevice -InstanceId $e.instanceId -Confirm:$false -ErrorAction Stop; Step 'enable-ok' $e.instanceId }
            catch { Step 'enable-fail' @{ instanceId = $e.instanceId; error = "$_" } }
        }
    }
    Start-Sleep -Seconds 1
    $state.restored = Snapshot 'after-restore'
    $state | ConvertTo-Json -Depth 6 | Out-File -FilePath $OutFile -Encoding UTF8
    Write-Output "restore 完成 -> $OutFile"
    exit 0
}

# ---- auto：找冲突组合 ----
$kbd = $parents | Where-Object { $_.instanceId -match 'PID_8047' } | Select-Object -First 1
$dng = $parents | Where-Object { $_.instanceId -match 'PID_FEFE' } | Select-Object -First 1

if (-not $kbd -or -not $dng) {
    Step 'no-both' @{ keyboardPresent = [bool]$kbd; donglePresent = [bool]$dng }
    Write-Output '两个设备没有同时存在，无法做冲突实验（请同时插键盘数据线 + dongle）'
    $state | ConvertTo-Json -Depth 6 | Out-File -FilePath $OutFile -Encoding UTF8
    exit 2
}

$target = $null; $other = $null
if ($kbd.status -eq 'Error' -and $dng.status -ne 'Error') { $target = $kbd; $other = $dng }
elseif ($dng.status -eq 'Error' -and $kbd.status -ne 'Error') { $target = $dng; $other = $kbd }
elseif ($kbd.status -eq 'Error' -and $dng.status -eq 'Error') {
    # 两个都坏：先保留键盘，禁 dongle
    $target = $kbd; $other = $dng
}
else {
    Step 'no-conflict' @{ keyboard = $kbd.status; dongle = $dng.status }
    Write-Output "没有冲突（keyboard=$($kbd.status), dongle=$($dng.status)），跳过"
    $state | ConvertTo-Json -Depth 6 | Out-File -FilePath $OutFile -Encoding UTF8
    exit 3
}
Step 'plan' @{ target = $target.instanceId; targetStatus = $target.status; other = $other.instanceId; otherStatus = $other.status }
Write-Output ("target={0} ({1})  other={2} ({3})" -f $target.instanceId, $target.status, $other.instanceId, $other.status)

# 1) 禁用"另一个"（释放资源）
try {
    Disable-PnpDevice -InstanceId $other.instanceId -Confirm:$false -ErrorAction Stop
    $state.disabled += $other.instanceId
    Step 'disable-other-ok' $other.instanceId
    Write-Output "已禁用: $($other.instanceId)"
}
catch { Step 'disable-other-fail' @{ instanceId = $other.instanceId; error = "$_" }; Write-Output "禁用失败: $_" }
Start-Sleep -Milliseconds 1500
Snapshot 'after-disable-other' | Out-Null

# 2) 目标设备重试启动：disable + enable
try {
    Disable-PnpDevice -InstanceId $target.instanceId -Confirm:$false -ErrorAction Stop
    Step 'disable-target-ok' $target.instanceId
}
catch { Step 'disable-target-fail' @{ error = "$_" } }
Start-Sleep -Milliseconds 600
try {
    Enable-PnpDevice -InstanceId $target.instanceId -Confirm:$false -ErrorAction Stop
    Step 'enable-target-ok' $target.instanceId
}
catch { Step 'enable-target-fail' @{ error = "$_" } }
Start-Sleep -Seconds 2
$snap2 = Snapshot 'after-target-cycle'

# 3) 还不行就 CM_Reenumerate（先 0，再 2=RETRY_INSTALLATION）
$t2 = $snap2 | Where-Object { $_.instanceId -eq $target.instanceId } | Select-Object -First 1
if ($t2 -and $t2.status -eq 'Error') {
    Reenumerate $target.instanceId 0 | Out-Null
    Start-Sleep -Seconds 2
    $snap3 = Snapshot 'after-reenum0'
    $t3 = $snap3 | Where-Object { $_.instanceId -eq $target.instanceId } | Select-Object -First 1
    if ($t3 -and $t3.status -eq 'Error') {
        Reenumerate $target.instanceId 2 | Out-Null
        Start-Sleep -Seconds 2
        Snapshot 'after-reenum2' | Out-Null
    }
}

# 4) 判定：目标设备的子接口（MI_xx）是否出现
$final = Snapshot 'final'
$pidTag = if ($target.instanceId -match 'PID_8047') { 'PID_8047' } else { 'PID_FEFE' }
$children = @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
        Where-Object { $_.InstanceId -match "VID_0C45&$pidTag&MI_" })
$targetFinal = $final | Where-Object { $_.instanceId -eq $target.instanceId } | Select-Object -First 1
$state.targetOK = ($children.Count -gt 0)
$state.targetFinalStatus = if ($targetFinal) { $targetFinal.status } else { 'missing' }
$state.childrenCount = $children.Count
Step 'result' @{ targetOK = $state.targetOK; targetStatus = $state.targetFinalStatus; children = $children.Count }

$state | ConvertTo-Json -Depth 6 | Out-File -FilePath $OutFile -Encoding UTF8
Write-Output ("结果: targetOK={0} targetStatus={1} children={2}" -f $state.targetOK, $state.targetFinalStatus, $children.Count)
Write-Output "日志 -> $OutFile"
if ($state.targetOK) { exit 0 } else { exit 1 }
