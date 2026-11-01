<#
.SYNOPSIS
  한글(Hancom) 프로그램으로 hwp·hwpx 파일 하나를 PDF로 저장한다. 원본은 읽기만 한다.
.DESCRIPTION
  - 한글이 설치돼 있어 자동 조작(COM, HWPFrame.HwpObject)이 될 때만 동작한다. 없으면 종료 코드 2.
  - 변환은 별도 프로세스에서 하고 제한 시간(기본 60초)을 둔다. 끝나거나 시간이 지나면, 이 실행이 시작한 뒤 새로 뜬
    한글 프로세스 중 10초 안에 스스로 닫히지 않은 것을 정리한다(사용자가 그 사이 한글을 새로 열면 함께 닫힐 수 있음).
  - 암호 문서·깨진 파일은 창을 띄우지 않고 실패로 알린다(열기 옵션 forceopen·suspendpassword).
  - 보안 모듈은 등록하지 않는다. 한글 보안 확인 창이 뜨는 PC에서는 제한 시간이 지나 실패로 끝날 수 있다.
  - 마지막 줄에 결과 JSON 한 줄: {"ok","pdf","note"}
  종료 코드: 0 성공 / 2 한글 자동 조작 불가 / 4 열기·저장 실패(암호·깨짐·형식) / 7 제한 시간 초과
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File hwp_to_pdf.ps1 -Src a.hwp -Out cache\a.hwp.pdf
  powershell -NoProfile -ExecutionPolicy Bypass -File hwp_to_pdf.ps1 -Check
#>
param(
  [string]$Src,
  [string]$Out,
  [int]$TimeoutSeconds = 60,
  [switch]$Check,
  [switch]$Worker,
  [string]$ResultFile
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Emit($ok, $pdf, $note, $code) {
  $o = [ordered]@{ ok = $ok; pdf = $pdf; note = $note }
  Write-Output ($o | ConvertTo-Json -Compress)
  exit $code
}

$available = Test-Path 'Registry::HKEY_CLASSES_ROOT\HWPFrame.HwpObject'
if ($Check) {
  if ($available) { Emit $true $null '한글 자동 조작(COM) 사용 가능' 0 } else { Emit $false $null '한글 자동 조작(COM) 없음 — 한글이 설치되지 않음' 2 }
}

if ($Worker) {
  # 실제 변환(별도 프로세스, STA). 결과는 ResultFile 에 한 줄로 남긴다.
  $res = 'FAIL 알 수 없는 오류'
  try {
    $fmt = if ([IO.Path]::GetExtension($Src).ToLower() -eq '.hwpx') { 'HWPX' } else { 'HWP' }
    $h = New-Object -ComObject HWPFrame.HwpObject
    try {
      if (-not $h.Open($Src, $fmt, 'forceopen:true;suspendpassword:true;versionwarning:false')) { $res = 'FAIL 열지 못함(암호·깨진 파일·지원 안 하는 형식일 수 있음)' }
      elseif (-not $h.SaveAs($Out, 'PDF', '')) { $res = 'FAIL PDF로 저장하지 못함' }
      elseif (-not (Test-Path -LiteralPath $Out)) { $res = 'FAIL PDF 파일이 생기지 않음' }
      else { $res = 'OK' }
      $h.Clear(1) | Out-Null
    } finally { $h.Quit() }
  } catch { $res = 'FAIL ' + $_.Exception.Message }
  [IO.File]::WriteAllText($ResultFile, $res, (New-Object System.Text.UTF8Encoding($false)))
  exit 0
}

if (-not $available) { Emit $false $null '한글 자동 조작(COM) 없음 — 한글이 설치되지 않음' 2 }
if (-not $Src -or -not $Out) { Emit $false $null '-Src 와 -Out 이 필요함' 4 }
if (-not (Test-Path -LiteralPath $Src -PathType Leaf)) { Emit $false $null "파일이 없음: $Src" 4 }
$Src = (Resolve-Path -LiteralPath $Src).Path
$outDir = Split-Path -Parent $Out
if ($outDir) { New-Item -ItemType Directory -Force -Path $outDir | Out-Null }
$Out = [IO.Path]::GetFullPath($Out)
if (Test-Path -LiteralPath $Out) { Emit $false $null "같은 이름 PDF가 이미 있음: $Out" 4 }

$resultFile = [IO.Path]::GetTempFileName()
$before = @(Get-Process Hwp -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
$t0 = Get-Date
$p = Start-Process powershell.exe -WindowStyle Hidden -PassThru -ArgumentList @(
  '-NoProfile', '-STA', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"",
  '-Worker', '-Src', "`"$Src`"", '-Out', "`"$Out`"", '-ResultFile', "`"$resultFile`"")
$done = $p.WaitForExit($TimeoutSeconds * 1000)
if (-not $done) { try { Stop-Process -Id $p.Id -Force -Confirm:$false } catch {} }

# 이 실행이 띄운 한글 프로세스 정리(스스로 닫힐 시간 10초)
$deadline = (Get-Date).AddSeconds(10)
do {
  $left = @(Get-Process Hwp -ErrorAction SilentlyContinue | Where-Object { $before -notcontains $_.Id -and $_.StartTime -ge $t0.AddSeconds(-1) })
  if ($left.Count -eq 0) { break }
  Start-Sleep -Milliseconds 500
} while ((Get-Date) -lt $deadline)
foreach ($x in $left) { try { Stop-Process -Id $x.Id -Force -Confirm:$false } catch {} }

$res = ''
if (Test-Path -LiteralPath $resultFile) { $res = [IO.File]::ReadAllText($resultFile, [System.Text.Encoding]::UTF8); Remove-Item -LiteralPath $resultFile -Force -Confirm:$false }
if (-not $done) { Emit $false $null "제한 시간($TimeoutSeconds 초) 초과 — 한글 확인 창이나 큰 파일 때문일 수 있음" 7 }
if ($res -eq 'OK') { Emit $true $Out '한글(COM)로 PDF 저장' 0 }
Emit $false $null ($res -replace '^FAIL ', '') 4