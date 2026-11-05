param(
    [ValidateSet('menu','first-run','check-repair','repair','check','start','stop','restart','status','configure','logs','diagnostics','install-mysql')]
    [string]$Action = 'menu',
    [Parameter(ValueFromRemainingArguments=$true)][string[]]$ForwardArgs
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding
$env:PYTHONUTF8 = '1'
$projectRoot = Split-Path -Parent $PSScriptRoot
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifests/dependencies.json') -Raw -Encoding UTF8 | ConvertFrom-Json

function Install-VerifiedRuntime($Name) {
    $entry = $manifest.$Name
    if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
        throw 'Automatic runtime installation supports Windows x64 only.'
    }
    $cache = Join-Path $env:LOCALAPPDATA 'CourseInventory/installers'
    New-Item -ItemType Directory -Path $cache -Force | Out-Null
    $file = Join-Path $cache $entry.filename
    if ((-not (Test-Path -LiteralPath $file)) -or ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $entry.sha256)) {
        Write-Host "Downloading $Name $($entry.version)..."
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $downloaded = $false
        foreach ($url in $entry.urls) {
            try { Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $file; $downloaded = $true; break }
            catch { Write-Host 'Download source unavailable; trying next source.' }
        }
        if (-not $downloaded) { throw 'Download failed. Check network or place the verified installer in the cache folder.' }
    }
    if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $entry.sha256) {
        throw 'SHA256 mismatch. Installer was not executed.'
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $file
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch $entry.publisher) {
        throw 'Invalid publisher signature. Installer was not executed.'
    }
    if ($Name -eq 'python') {
        $process = Start-Process -FilePath $file -ArgumentList '/quiet InstallAllUsers=0 Include_test=0 PrependPath=0 Include_launcher=0' -Wait -PassThru -WindowStyle Hidden
    } elseif ($Name -eq 'mysql') {
        $process = Start-Process -FilePath 'msiexec.exe' -ArgumentList "/i `"$file`" /qn /norestart" -Verb RunAs -Wait -PassThru -WindowStyle Hidden
    } else {
        $process = Start-Process -FilePath $file -ArgumentList '/install /quiet /norestart' -Verb RunAs -Wait -PassThru -WindowStyle Hidden
    }
    if ($process.ExitCode -notin @(0,3010) -and -not ($Name -eq 'vcredist' -and $process.ExitCode -eq 1638)) {
        throw "Installer failed with exit code $($process.ExitCode)."
    }
    if ($process.ExitCode -eq 3010) { Write-Host 'Windows reports that a reboot may be required.' }
}

function Find-Python {
    $candidates = @()
    # Windows PowerShell 5 treats stderr from older py.exe as an ErrorRecord,
    # even when redirected. Discovery failures must not abort the bootstrap.
    $ErrorActionPreference = 'Continue'
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        foreach ($version in @('-3.13','-3.12','-3.14')) {
            $candidate = & $launcher.Source $version -c 'import sys; print(sys.executable)' 2>$null
            if ($LASTEXITCODE -eq 0 -and $candidate) { $candidates += $candidate }
        }
    }
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command -and $command.Source -notmatch 'WindowsApps') { $candidates += $command.Source }
    $candidates += Join-Path $env:LOCALAPPDATA 'Programs/Python/Python313/python.exe'
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            & $candidate -c 'import sys,venv; assert sys.version_info >= (3,12)' 2>$null
            if ($LASTEXITCODE -eq 0) { return $candidate }
        }
    }
    return $null
}

try {
    if ($Action -eq 'install-mysql') {
        Install-VerifiedRuntime 'vcredist'
        Install-VerifiedRuntime 'mysql'
        Write-Host 'MySQL binaries installed. The configuration wizard creates its own isolated instance.'
        exit 0
    }
    $venvPython = Join-Path $projectRoot '.venv/Scripts/python.exe'
    $pythonExe = $null
    if ($Action -notin @('repair','first-run') -and (Test-Path -LiteralPath $venvPython)) {
        & $venvPython -c 'import sys; assert sys.version_info >= (3,12)' 2>$null
        if ($LASTEXITCODE -eq 0) { $pythonExe = $venvPython }
    }
    if (-not $pythonExe) { $pythonExe = Find-Python }
    if (-not $pythonExe) {
        if ($Action -notin @('first-run','repair','menu','check-repair')) { throw 'Python is missing. Run FirstRun.cmd first.' }
        Write-Host 'Python is missing; installing the verified per-user runtime.'
        Install-VerifiedRuntime 'python'
        $pythonExe = Find-Python
        if (-not $pythonExe) { throw 'Python installation could not be verified. Reopen FirstRun.cmd.' }
    }
    $manager = Join-Path $PSScriptRoot 'manager.py'
    if ($Action -in @('first-run','repair')) {
        & $pythonExe $manager repair
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        if ($Action -eq 'repair') { exit 0 }
        $pythonExe = $venvPython
    }
    & $pythonExe $manager $Action @ForwardArgs
    exit $LASTEXITCODE
} catch {
    # Avoid dumping invocation arguments or environments containing credentials.
    Write-Host ('Setup failed: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
