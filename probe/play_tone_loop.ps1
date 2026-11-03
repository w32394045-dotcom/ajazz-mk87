param([string]$wav)
$p = New-Object System.Media.SoundPlayer $wav
$p.PlayLooping()
$stop = Join-Path $env:TEMP 'mk87_tone_stop.flag'
while (-not (Test-Path $stop)) { Start-Sleep -Milliseconds 200 }
$p.Stop()
