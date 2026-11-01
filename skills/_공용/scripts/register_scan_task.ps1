<#
.SYNOPSIS
  `/job-scan` 무인 실행을 Windows 작업 스케줄러에 등록/해제한다. 기본은 미리보기(아무것도 등록하지 않음).
.DESCRIPTION
  - 하루 1회(기본 08:30). "예약된 시작을 놓친 경우 가능한 한 빨리 실행"을 켠다 → 덮개를 열고 PC가 깨어나면 곧바로 한 번 실행.
  - 전원 설정·덮개 동작 등 PC 설정은 바꾸지 않는다(절전 해제 후 실행 옵션은 쓰지 않는다). 정각 실행은 보장하지 않는다.
  - 등록은 사용자 계정으로만(관리자 권한 불필요), 같은 이름 작업이 이미 있으면 -Apply 전에 알린다.
  - 미시험: Modern Standby에서 "놓친 실행 보충"이 실제로 동작하는지, 무인 실행의 로그인 계정.
.PARAMETER Vault   실행할 볼트 폴더
.PARAMETER Time    매일 실행 시각(HH:mm)
.PARAMETER Apply   실제로 등록한다
.PARAMETER Unregister  등록된 작업을 지운다(-Apply 와 함께)
#>
param(
  [Parameter(Mandatory = $true)][string]$Vault,
  [string]$Time = '08:30',
  [switch]$Apply,
  [switch]$Unregister,
  [string]$TaskName = 'job-compass-scan'
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$runner = Join-Path $here 'run_scan.ps1'
if (-not (Test-Path -LiteralPath $runner)) { throw "run_scan.ps1 을 찾을 수 없습니다: $runner" }
$Vault = (Resolve-Path -LiteralPath $Vault).Path
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

if ($Unregister) {
  if (-not $existing) { Write-Output "등록된 작업이 없습니다: $TaskName"; exit 0 }
  if ($Apply) { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false; Write-Output "작업을 지웠습니다: $TaskName" }
  else { Write-Output "[미리보기] 작업 '$TaskName' 을 지웁니다. 실제로 지우려면 -Apply" }
  exit 0
}

$arg = "-NoProfile -ExecutionPolicy Bypass -File `"$runner`" -Vault `"$Vault`""
Write-Output "작업 이름: $TaskName"
Write-Output "실행: powershell.exe $arg"
Write-Output "시각: 매일 $Time (놓친 실행은 가능한 한 빨리 보충 · 전원 설정은 바꾸지 않음 · 중복 실행 안 함 · 제한 30분)"
if ($existing) { Write-Output "※ 같은 이름의 작업이 이미 있습니다(-Apply 하면 덮어씁니다)." }
if (-not $Apply) { Write-Output "[미리보기] 등록하지 않았습니다. 등록하려면 -Apply"; exit 0 }

$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arg
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description 'job-compass: /job-scan 무인 실행(개인용)' -Force | Out-Null
Write-Output "등록했습니다: $TaskName (매일 $Time)"
