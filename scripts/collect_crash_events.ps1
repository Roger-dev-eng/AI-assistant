# Read Application events only; never change Windows crash-reporting policies.
$ErrorActionPreference = 'Stop'
try {
    $directory = $env:ASSISTANT_LOG_DIR
    if (!$directory) { throw 'ASSISTANT_LOG_DIR is required.' }
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $events = @(Get-WinEvent -FilterHashtable @{
        LogName = 'Application'
        Id = @(1000, 1001)
        StartTime = (Get-Date).AddMinutes(-45)
    } -ErrorAction SilentlyContinue | Where-Object {
        $_.Message -match '(?i)python|AssistantDesktop|Qt6'
    } | Select-Object TimeCreated, Id, ProviderName, Message)
    ConvertTo-Json -InputObject $events -Depth 4 |
        Set-Content -LiteralPath (Join-Path $directory 'windows-crash-events.json') -Encoding utf8
} catch {
    # Diagnostics are best effort and must not mask the original job failure.
    Write-Warning "Windows crash events unavailable: $($_.Exception.Message)"
}
