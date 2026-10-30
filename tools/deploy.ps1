<#
.SYNOPSIS
  job-compass 의 skills\ 를 볼트의 .claude\skills\ 로 "복사"해서 배포한다.

.DESCRIPTION
  기본은 미리보기(DryRun)다. 아무것도 복사하지 않고 무엇이 바뀌는지 목록만 보여 준다.
  -Apply 를 붙여야 실제로 복사한다. 삭제는 하지 않는다.

  - 새 파일 / 바뀐 파일 / 같은 파일 / 볼트에서 직접 고친 흔적(DRIFT) / 볼트에만 있는 파일을 구분한다.
  - DRIFT(마지막 배포 이후 볼트 쪽이 바뀐 파일)는 -Apply 만으로는 덮어쓰지 않는다. -Force 가 있어야 덮어쓴다.
  - 덮어쓰기 전의 볼트 쪽 파일은 <Target>\.claude\_deploy-backup\<날짜-시각>\ 에 복사해 둔다.
  - 배포 기록은 <Target>\.claude\job-compass-deploy.json 에 남긴다(날짜, git 커밋, 파일 해시).
  - 볼트의 .claude\skills\ 안에 있는, 이 저장소에 없는 스킬(예: 기존 job-posting 이 아직 없을 때)은 건드리지 않는다.

.PARAMETER Target
  배포할 볼트 폴더. 예: C:\Users\...\yurim  (필수)
.PARAMETER Source
  스킬 원본 폴더. 기본은 이 스크립트 옆의 ..\skills
.PARAMETER Apply
  실제로 복사한다.
.PARAMETER Force
  DRIFT 파일도 덮어쓴다(백업은 항상 남긴다).
#>
param(
  [Parameter(Mandatory = $true)][string]$Target,
  [string]$Source = (Join-Path $PSScriptRoot '..\skills'),
  [switch]$Apply,
  [switch]$Force
)

$ErrorActionPreference = 'Stop'

# 복사하지 않는 것
$ExcludeNames = @('.gitkeep', 'desktop.ini', '.DS_Store', 'Thumbs.db')
$ExcludeDirs = @('__pycache__', '.tmp', '.pytest_cache', '.venv')

if (-not (Test-Path -LiteralPath $Source -PathType Container)) { throw "원본 폴더가 없습니다: $Source" }
if (-not (Test-Path -LiteralPath $Target -PathType Container)) { throw "볼트 폴더가 없습니다: $Target" }

$Source = (Resolve-Path -LiteralPath $Source).Path
$Target = (Resolve-Path -LiteralPath $Target).Path
$claudeDir = Join-Path $Target '.claude'
$skillsDir = Join-Path $claudeDir 'skills'
$manifestPath = Join-Path $claudeDir 'job-compass-deploy.json'

function Get-Hash([string]$path) { (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash }

function Get-RelFiles([string]$root) {
  Get-ChildItem -LiteralPath $root -Recurse -File -Force | Where-Object {
    $rel = $_.FullName.Substring($root.Length).TrimStart('\')
    $parts = $rel.Split('\')
    -not ($ExcludeNames -contains $_.Name) -and -not ($parts | Where-Object { $ExcludeDirs -contains $_ })
  } | ForEach-Object { $_.FullName.Substring($root.Length).TrimStart('\') }
}

# 마지막 배포 기록
$last = @{}
if (Test-Path -LiteralPath $manifestPath) {
  try {
    $m = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($p in $m.files.PSObject.Properties) { $last[$p.Name] = $p.Value }
  } catch { Write-Warning "배포 기록을 읽지 못했습니다(무시하고 계속): $($_.Exception.Message)" }
}

$srcFiles = @(Get-RelFiles $Source)
$plan = @()
foreach ($rel in $srcFiles) {
  $src = Join-Path $Source $rel
  $dst = Join-Path $skillsDir $rel
  $srcHash = Get-Hash $src
  if (-not (Test-Path -LiteralPath $dst)) {
    $plan += [pscustomobject]@{ State = 'NEW'; Rel = $rel; SrcHash = $srcHash; DstHash = $null }
    continue
  }
  $dstHash = Get-Hash $dst
  if ($dstHash -eq $srcHash) {
    $plan += [pscustomobject]@{ State = 'SAME'; Rel = $rel; SrcHash = $srcHash; DstHash = $dstHash }
  } elseif ($last.ContainsKey($rel) -and $last[$rel] -eq $dstHash) {
    # 볼트 쪽이 마지막 배포 그대로이고 원본이 바뀐 것 = 정상 업데이트
    $plan += [pscustomobject]@{ State = 'CHANGED'; Rel = $rel; SrcHash = $srcHash; DstHash = $dstHash }
  } else {
    # 볼트 쪽이 마지막 배포와도 다르거나, 배포 기록이 없는데 내용이 다름 = 직접 고친 흔적(또는 기록 없음)
    $plan += [pscustomobject]@{ State = 'DRIFT'; Rel = $rel; SrcHash = $srcHash; DstHash = $dstHash }
  }
}

# 볼트에만 있는 파일: 같은 이름의 스킬 폴더 안에서 원본에 없는 것
$skillNames = @($srcFiles | ForEach-Object { $_.Split('\')[0] } | Sort-Object -Unique)
$extra = @()
foreach ($name in $skillNames) {
  $dir = Join-Path $skillsDir $name
  if (Test-Path -LiteralPath $dir -PathType Container) {
    foreach ($rel in (Get-RelFiles $skillsDir | Where-Object { $_.StartsWith($name + '\') })) {
      if ($srcFiles -notcontains $rel) { $extra += $rel }
    }
  }
}

Write-Host ''
Write-Host "원본: $Source"
Write-Host "볼트: $Target"
Write-Host ('모드: ' + $(if ($Apply) { '실제 복사(-Apply)' } else { '미리보기(복사 안 함)' }) + $(if ($Force) { ' / -Force' } else { '' }))
Write-Host ''

foreach ($state in 'NEW', 'CHANGED', 'DRIFT', 'SAME') {
  $items = @($plan | Where-Object { $_.State -eq $state })
  $label = switch ($state) {
    'NEW' { '새 파일' } 'CHANGED' { '바뀐 파일(정상 업데이트)' }
    'DRIFT' { '볼트에서 직접 고친 흔적 또는 배포 기록 없음 — -Force 없이는 덮어쓰지 않음' } 'SAME' { '같은 파일' }
  }
  Write-Host ("[{0}] {1}: {2}건" -f $state, $label, $items.Count)
  if ($state -ne 'SAME') { foreach ($i in $items) { Write-Host ('   ' + $i.Rel) } }
}
Write-Host ("[EXTRA] 볼트에만 있는 파일(삭제하지 않음): {0}건" -f $extra.Count)
foreach ($e in $extra) { Write-Host ('   ' + $e) }
Write-Host ''

if (-not $Apply) {
  Write-Host '미리보기만 했습니다. 이대로 복사하려면 -Apply 를 붙여 다시 실행하세요.'
  return
}

$toCopy = @($plan | Where-Object { $_.State -in 'NEW', 'CHANGED' -or ($_.State -eq 'DRIFT' -and $Force) })
$skipped = @($plan | Where-Object { $_.State -eq 'DRIFT' -and -not $Force })
if ($skipped.Count -gt 0) {
  Write-Warning ("DRIFT {0}건은 건너뜁니다. 볼트 쪽 변경을 확인한 뒤 필요하면 -Force 로 다시 실행하세요." -f $skipped.Count)
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupRoot = Join-Path $claudeDir "_deploy-backup\$stamp"
$copied = 0
foreach ($i in $toCopy) {
  $src = Join-Path $Source $i.Rel
  $dst = Join-Path $skillsDir $i.Rel
  if (Test-Path -LiteralPath $dst) {
    $bak = Join-Path $backupRoot $i.Rel
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $bak) | Out-Null
    Copy-Item -LiteralPath $dst -Destination $bak -Force
  }
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) | Out-Null
  Copy-Item -LiteralPath $src -Destination $dst -Force
  $copied++
}

# 배포 기록: "마지막으로 배포한 내용"의 해시.
# 건너뛴 DRIFT 파일은 볼트 쪽 현재 해시가 아니라 **이전 배포 기록을 그대로 둔다**
# (그래야 다음 실행에서도 직접 고친 흔적으로 계속 잡힌다). 이전 기록이 없었다면 기록하지 않는다.
$files = [ordered]@{}
foreach ($i in ($plan | Sort-Object Rel)) {
  $dst = Join-Path $skillsDir $i.Rel
  if ($i.State -eq 'DRIFT' -and -not $Force) {
    if ($last.ContainsKey($i.Rel)) { $files[$i.Rel] = $last[$i.Rel] }
  } elseif (Test-Path -LiteralPath $dst) {
    $files[$i.Rel] = Get-Hash $dst
  }
}
# 이번 실행 대상이 아닌(원본에서 사라진) 파일의 이전 기록은 보존한다
foreach ($k in $last.Keys) { if (-not $files.Contains($k) -and ($srcFiles -notcontains $k)) { $files[$k] = $last[$k] } }
$commit = $null
try {
  $repo = Split-Path -Parent $Source
  $commit = (& git -C $repo rev-parse --short HEAD 2>$null)
  if ($LASTEXITCODE -ne 0) { $commit = $null }
} catch { $commit = $null }
New-Item -ItemType Directory -Force -Path $claudeDir | Out-Null
[ordered]@{
  deployed_at = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
  source_commit = $commit
  source_dirty_note = '커밋되지 않은 변경이 있으면 source_commit 과 내용이 다를 수 있음'
  files = $files
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

Write-Host ("복사 완료: {0}건. 건너뜀(DRIFT): {1}건." -f $copied, $skipped.Count)
if (Test-Path -LiteralPath $backupRoot) { Write-Host "덮어쓴 파일의 이전 내용: $backupRoot" }
Write-Host "배포 기록: $manifestPath"
Write-Host '참고: 배포한 뒤 Claude Code 가 새 스킬 내용을 바로 읽는지, 새 세션이 필요한지는 아직 시험하지 않았습니다.'
