<#
.SYNOPSIS
  `/job-scan`을 무인으로 한 번 실행한다(작업 스케줄러가 부르는 래퍼). 결과는 파일에 남기고, 마감 임박·새 후보가 있으면 Windows 알림.
.DESCRIPTION
  - 볼트 폴더에서 `claude -p`를 돌린다. 무인 실행이라 허용 규칙을 **대화형보다 훨씬 좁게** 명시한다(아래 $allow/$deny).
    쓰기 허용: Areas/취업/ 의 공고 후보함·_scan-cache·_scan-log·마감 캘린더·내보내기·오늘 현황·_widget·_백업 뿐.
    금지: raw/ · wiki/ · output/ · Notes/ · .claude/ 수정, 삭제 명령, 메일·제출(그런 도구 자체를 허용하지 않음).
  - 개인정보는 프롬프트·로그에 쓰지 않는다. 프롬프트에는 개인 내용이 없다.
  - 신뢰하지 않은 작업 폴더에서는 .claude/settings.json 의 허용 규칙이 무시된다. 이 래퍼는 플래그로 규칙을 직접 준다.
    그래도 처음 한 번은 볼트 폴더에서 Claude Code를 대화형으로 열어 폴더 신뢰를 수락해 두는 것이 안전하다(미시험).
  - 실행이 밀려도(놓친 실행 보충) 결과가 틀리지 않게 `/job-scan`이 실행 시각 기준으로 D-n을 계산하고 로그에 실행 시각을 적는다.
  - 미시험: 이 PC에서 무인(로그인하지 않은 상태 포함) 실행이 어느 계정으로 도는지, 사용량(%).
.PARAMETER Vault
  볼트 폴더(예: 가짜 볼트 fixtures\test-vault, 실제 볼트는 사용자가 정한 뒤).
.PARAMETER DryRun
  claude 를 부르지 않고 만들 명령과 허용 규칙만 출력한다.
.PARAMETER ConfigDir
  Claude Code 설정 폴더(CLAUDE_CONFIG_DIR). 계정마다 설정 폴더를 따로 쓰는 경우 이 폴더의 로그인 계정으로 실행된다.
  비우면 실행 환경의 CLAUDE_CONFIG_DIR(없으면 기본 폴더 ~\.claude)의 계정을 쓴다. 작업 스케줄러는 터미널의 환경 변수를 물려받지 않으므로
  기본 폴더가 아닌 계정으로 돌리려면 반드시 이 값을 준다.
#>
param(
  [Parameter(Mandatory = $true)][string]$Vault,
  [switch]$DryRun,
  [int]$TimeoutMinutes = 30,
  [string]$ConfigDir = ''
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Vault -PathType Container)) { throw "볼트 폴더가 없습니다: $Vault" }
$Vault = (Resolve-Path -LiteralPath $Vault).Path
if ($ConfigDir) {
  if (-not (Test-Path -LiteralPath $ConfigDir -PathType Container)) { throw "설정 폴더가 없습니다: $ConfigDir" }
  $ConfigDir = (Resolve-Path -LiteralPath $ConfigDir).Path
}
$configNote = if ($ConfigDir) { $ConfigDir } elseif ($env:CLAUDE_CONFIG_DIR) { "$($env:CLAUDE_CONFIG_DIR) (환경 변수)" } else { '기본 폴더(~\.claude)' }
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

$prompt = 'job-scan 스킬을 사용해 검색 조건 파일대로 공고 후보를 수집하고, 스킬 5단계대로 상위 K건의 미리보기 점수까지 내 주세요. 무인 실행입니다: 질문하지 말고, 명령은 스킬에 적힌 한 줄 명령을 그대로 쓰세요(셸 변수·cd·&&·파이프·리디렉션 없이). 허용되지 않아 못 한 단계와 실패한 소스는 요약에 적으세요. 현황표·raw·wiki는 수정하지 마세요.'
$allow = @(
  'Skill', 'Read', 'Glob', 'Grep', 'WebFetch',
  'Edit(Areas/취업/공고 후보함.md)', 'Edit(Areas/취업/_scan-log.md)', 'Edit(Areas/취업/_scan-cache/**)',
  'Edit(Areas/취업/마감 캘린더.md)', 'Edit(Areas/취업/내보내기/**)', 'Edit(Areas/취업/오늘 현황.md)',
  'Edit(Areas/취업/_widget/**)', 'Edit(Areas/취업/_백업/**)',
  'Bash(python -I -X utf8 .claude/skills/_공용/scripts/*)', 'Bash(curl *)', 'Bash(perl *)', 'Bash(mkdir -p *)', 'Bash(date *)', 'Bash(sleep *)'
)
$deny = @(
  'Edit(Projects/**)', 'Edit(Notes/**)', 'Edit(.claude/**)', 'Edit(Areas/취업/지원 현황.md)',
  'Bash(rm *)', 'Bash(rmdir *)', 'Bash(del *)', 'PowerShell(Remove-Item *)'
)
$claudeArgs = @('-p', $prompt, '--permission-mode', 'acceptEdits', '--allowedTools') + $allow + @('--disallowedTools') + $deny

$log = Join-Path $Vault 'Areas\취업\_scan-log.md'
$start = Get-Date
if ($DryRun) {
  Write-Output "[미리보기] 볼트: $Vault"
  Write-Output "[미리보기] 설정 폴더(계정): $configNote"
  Write-Output "[미리보기] claude $($claudeArgs -join ' ')"
  exit 0
}
$claude = (Get-Command claude -ErrorAction Stop).Source
Push-Location $Vault
try {
  # 백그라운드 작업은 새 프로세스라 콘솔 출력 인코딩이 기본(한글 코드페이지)이다 — claude 의 UTF-8 출력이 깨지지 않게 UTF-8 로 맞춘다
  $job = Start-Job -ScriptBlock { param($c, $a, $v, $cfg) [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8; if ($cfg) { $env:CLAUDE_CONFIG_DIR = $cfg }; Set-Location $v; & $c @a 2>&1 | Out-String } -ArgumentList $claude, $claudeArgs, $Vault, $ConfigDir
  if (-not (Wait-Job $job -Timeout ($TimeoutMinutes * 60))) { Stop-Job $job; $result = "시간 초과($TimeoutMinutes 분)로 중단"; $code = 1 }
  else { $result = (Receive-Job $job); $code = 0 }
  Remove-Job $job -Force
} finally { Pop-Location }
$line = "- $($start.ToString('yyyy-MM-dd HH:mm')) · 무인 실행 종료(소요 $([int]((Get-Date) - $start).TotalSeconds)초, 코드 $code)"
if (Test-Path -LiteralPath $log) { Add-Content -LiteralPath $log -Value $line -Encoding UTF8 }

# 알림: 마감 임박·새 후보 (오늘 현황.json 기준)
$json = Join-Path $Vault 'Areas\취업\_widget\오늘 현황.json'
if (Test-Path -LiteralPath $json) {
  $d = Get-Content -LiteralPath $json -Raw -Encoding UTF8 | ConvertFrom-Json
  $urgent = [int]$d.counts.urgent; $cands = [int]$d.counts.new_candidates; $over = [int]$d.counts.overdue
  if ($urgent -gt 0 -or $cands -gt 0 -or $over -gt 0) {
    $msg = "마감 임박 $urgent건 · 마감 지난 지원 전 $over건 · 새 후보 $cands건 — 채용공고를 확인하세요"
    & (Join-Path $here 'notify.ps1') -Title '채용 현황' -Message $msg | Out-Null
  }
}
Write-Output $result
