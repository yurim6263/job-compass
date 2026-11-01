<#
.SYNOPSIS
  Windows 알림(토스트) 한 개를 띄운다. PowerShell 5.1 + 시스템 API, 새 설치 없음.
.DESCRIPTION
  앱 식별자는 PowerShell 것을 쓴다. 알림을 눌렀을 때 파일을 여는 동작은 없다(미시험).
  -DryRun 이면 화면에 알림을 띄우지 않고 보낼 글만 출력한다.
  개인정보(연락처·학번 등)는 제목·내용에 넣지 않는다.
#>
param(
  [Parameter(Mandatory = $true)][string]$Title,
  [Parameter(Mandatory = $true)][string]$Message,
  [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
if ($DryRun) { Write-Output "[알림 미리보기] $Title — $Message"; exit 0 }
try {
  [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
  [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
  $tpl = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
  $nodes = $tpl.GetElementsByTagName('text')
  $nodes.Item(0).AppendChild($tpl.CreateTextNode($Title)) | Out-Null
  $nodes.Item(1).AppendChild($tpl.CreateTextNode($Message)) | Out-Null
  $appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
  $toast = [Windows.UI.Notifications.ToastNotification]::new($tpl)
  [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
  Write-Output "알림을 보냈습니다: $Title"
} catch {
  Write-Output "알림을 띄우지 못했습니다(파일 알림만 남습니다): $($_.Exception.Message)"
  exit 0
}
