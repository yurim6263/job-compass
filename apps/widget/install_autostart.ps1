<#
.SYNOPSIS
  job-compass 알림 아이콘을 윈도우 시작 시 자동으로 켜고, 시작 메뉴에서도 눌러 켤 수 있게 바로가기를 만든다(내 계정만, 관리자 권한 불필요).
.DESCRIPTION
  기본은 미리보기. -Apply 를 붙여야 만든다. -Remove -Apply 로 지운다.
  만드는 것(둘 다 바로가기 파일 하나씩):
    - 시작 프로그램: %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\job-compass 알림.lnk
    - 시작 메뉴:     %APPDATA%\Microsoft\Windows\Start Menu\Programs\job-compass 알림.lnk
  바로가기는 pythonw.exe(창 없음)로 run_widget.pyw 를 켠다. 이미 켜져 있으면 두 번째 실행은 조용히 끝난다.
.PARAMETER Python  pythonw.exe 경로. 비우면 PATH 의 python 옆에서 찾는다
#>
param([switch]$Apply, [switch]$Remove, [string]$Python = '')
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$entry = Join-Path $here 'run_widget.pyw'
if (-not (Test-Path -LiteralPath $entry)) { throw "run_widget.pyw 를 찾을 수 없습니다: $entry" }
if (-not $Python) {
  $py = (Get-Command python -ErrorAction SilentlyContinue).Source
  if (-not $py) { throw 'python 을 찾을 수 없습니다. -Python 으로 pythonw.exe 경로를 주세요' }
  $Python = Join-Path (Split-Path -Parent $py) 'pythonw.exe'
}
if (-not (Test-Path -LiteralPath $Python)) { throw "pythonw.exe 가 없습니다: $Python" }
$progs = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
$targets = @((Join-Path $progs 'Startup\job-compass 알림.lnk'), (Join-Path $progs 'job-compass 알림.lnk'))

if ($Remove) {
  foreach ($t in $targets) {
    if (Test-Path -LiteralPath $t) { if ($Apply) { Remove-Item -LiteralPath $t; Write-Output "지움: $t" } else { Write-Output "[미리보기] 지울 것: $t" } }
  }
  exit 0
}
Write-Output "실행: `"$Python`" `"$entry`""
foreach ($t in $targets) { Write-Output ("바로가기: $t" + $(if (Test-Path -LiteralPath $t) { ' (있음 — 덮어씀)' } else { '' })) }
if (-not $Apply) { Write-Output '[미리보기] 만들지 않았습니다. 만들려면 -Apply'; exit 0 }
$sh = New-Object -ComObject WScript.Shell
foreach ($t in $targets) {
  $lnk = $sh.CreateShortcut($t)
  $lnk.TargetPath = $Python
  $lnk.Arguments = "`"$entry`""
  $lnk.WorkingDirectory = $here
  $lnk.Description = 'job-compass 알림 아이콘(취업 현황)'
  $lnk.Save()
  Write-Output "만듦: $t"
}
