# 恢复实验中被禁用/报错的 VID_0C45 设备（管理员）
param([string]$OutFile = 'C:\Users\ptfm\Documents\ajazz-re\docs\e4_restore.json')
$ErrorActionPreference = 'Continue'
$log = [ordered]@{ time = (Get-Date).ToString('s'); actions = @() }

function Rec($name, $data) {
    $script:log.actions += [ordered]@{ t = (Get-Date).ToString('HH:mm:ss.fff'); name = $name; data = $data }
}

$devs = @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -match 'VID_0C45' })
foreach ($d in $devs) { Rec 'before' @{ id = $d.InstanceId; status = "$($d.Status)" } }

# 1) 启用所有处于 Error 的子设备（实验里被 disable 的）
$errs = @($devs | Where-Object { $_.Status -eq 'Error' -and $_.InstanceId -match '&MI_' })
foreach ($e in $errs) {
    try { Enable-PnpDevice -InstanceId $e.InstanceId -Confirm:$false -ErrorAction Stop; Rec 'enable-ok' $e.InstanceId }
    catch { Rec 'enable-fail' @{ id = $e.InstanceId; err = "$_" } }
    Start-Sleep -Milliseconds 600
}

# 2) 重枚举两个复合设备
foreach ($d in @($devs | Where-Object { $_.InstanceId -match '^USB\\VID_0C45&PID_(8047|FEFE)\\' })) {
    try { Disable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false -ErrorAction Stop; Rec 'composite-disable-ok' $d.InstanceId }
    catch { Rec 'composite-disable-skip' @{ id = $d.InstanceId; err = "$_" } }
    Start-Sleep -Milliseconds 500
    try { Enable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false -ErrorAction Stop; Rec 'composite-enable-ok' $d.InstanceId }
    catch { Rec 'composite-enable-fail' @{ id = $d.InstanceId; err = "$_" } }
    Start-Sleep -Milliseconds 1200
}

Start-Sleep -Seconds 1
$devs2 = @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -match 'VID_0C45' })
foreach ($d in $devs2) { Rec 'after' @{ id = $d.InstanceId; status = "$($d.Status)" } }
$log | ConvertTo-Json -Depth 6 | Out-File -FilePath $OutFile -Encoding UTF8
Write-Output 'restore done'
Write-Output ('仍 Error: ' + ((@($devs2 | Where-Object { $_.Status -eq 'Error' }) | ForEach-Object { $_.InstanceId }) -join '; '))
