param([Parameter(Mandatory=$true)][string]$ParametersFile)
$ErrorActionPreference = 'Stop'
$update = Get-Content -LiteralPath $ParametersFile -Raw -Encoding UTF8 | ConvertFrom-Json
try {
    Set-Content -LiteralPath $update.ready -Value 'ready' -Encoding ASCII
    $previous = Get-Process -Id $update.process -ErrorAction SilentlyContinue
    if ($previous -and !$previous.WaitForExit(120000)) {
        throw 'O aplicativo não encerrou a tempo. Nenhum processo foi forçado a fechar.'
    }
    if ((Get-FileHash -LiteralPath $update.installer -Algorithm SHA256).Hash.ToLower() -ne $update.sha256) {
        throw 'O instalador mudou antes da instalação. Atualização cancelada.'
    }
    $installArguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
        '/NOCLOSEAPPLICATIONS', '/NORESTARTAPPLICATIONS',
        ('/DIR="' + $update.directory + '"'), ('/LOG="' + $update.log + '"'))
    $installation = Start-Process -FilePath $update.installer -ArgumentList $installArguments `
        -WindowStyle Hidden -Wait -PassThru
    if ($installation.ExitCode -ne 0) {
        throw ('O instalador retornou o código ' + $installation.ExitCode + '. Consulte install.log.')
    }
    @{success=$true; message='Atualização instalada.'} | ConvertTo-Json | Set-Content `
        -LiteralPath $update.status -Encoding UTF8
    Start-Process -FilePath $update.executable -ArgumentList '--gui' -WindowStyle Hidden
} catch {
    @{success=$false; message=$_.Exception.Message} | ConvertTo-Json | Set-Content `
        -LiteralPath $update.status -Encoding UTF8
    # If installation failed, leave the installed application available to report the failure.
    if (Test-Path -LiteralPath $update.executable) {
        Start-Process -FilePath $update.executable -ArgumentList '--gui' -WindowStyle Hidden
    }
} finally {
    Remove-Item -LiteralPath $ParametersFile -ErrorAction SilentlyContinue
}
