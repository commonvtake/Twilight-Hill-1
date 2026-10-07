param(
    [string]$GamePath,
    [switch]$Baseline,
    [switch]$LegacyGraphics,
    [switch]$Outdoor,
    [switch]$Connected,
    [switch]$Fog,
    [switch]$Town,
    [switch]$District,
    [switch]$OldTown,
    [switch]$PCProfile
)
$ErrorActionPreference = 'Stop'
$projectDir = $PSScriptRoot
$engineVersion = '2.0.3'
$engineUrl = 'https://github.com/TwilitRealm/dusklight/releases/download/v2.0.3/Dusklight-v2.0.3-win32-x86_64.zip'
$engineHash = 'ac63514eeb13cd4e9bd22be02dabee4952d1331a78f0496326bba2b577b12caf'

try {
    if (-not [Environment]::Is64BitOperatingSystem) {
        throw 'This test launcher requires 64-bit Windows.'
    }
    Write-Host 'Silent Hill / Twilight Princess - experimental area test'
    Write-Host 'First run downloads Dusklight 2.0.3 (about 56 MB) from its official GitHub release.'
    Write-Host 'Your selected disc image is read locally. Test data stays beside this launcher.'
    Write-Host ''
    $runtimeDir = Join-Path $projectDir 'Runtime'
    $engineDir = Join-Path $runtimeDir ('Dusklight-' + $engineVersion)
    $engineExe = Get-ChildItem -LiteralPath $engineDir -Filter 'dusklight.exe' -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $engineExe) {
        New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
        $archive = Join-Path $runtimeDir ('Dusklight-' + $engineVersion + '.zip')
        if (-not (Test-Path -LiteralPath $archive)) {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            $client = New-Object Net.WebClient
            try {
                Write-Host 'Downloading the official runtime...'
                $client.DownloadFile($engineUrl, $archive + '.part')
                Move-Item -LiteralPath ($archive + '.part') -Destination $archive -Force
            } finally {
                $client.Dispose()
            }
        }
        if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $engineHash) {
            throw "Runtime download failed its SHA-256 check. Delete only '$archive' and run again."
        }
        Write-Host 'Verified download. Extracting runtime...'
        Expand-Archive -LiteralPath $archive -DestinationPath $engineDir -Force
        $engineExe = Get-ChildItem -LiteralPath $engineDir -Filter 'dusklight.exe' -Recurse | Select-Object -First 1
        if (-not $engineExe) { throw 'The runtime archive did not contain dusklight.exe.' }
    }

    $pathRecord = Join-Path $projectDir 'Selected-Game.txt'
    if (-not $GamePath -and (Test-Path -LiteralPath $pathRecord)) {
        $savedPath = (Get-Content -LiteralPath $pathRecord -Raw).Trim()
        if (Test-Path -LiteralPath $savedPath -PathType Leaf) { $GamePath = $savedPath }
    }
    if (-not $GamePath) {
        Add-Type -AssemblyName System.Windows.Forms
        $picker = New-Object System.Windows.Forms.OpenFileDialog
        $picker.Title = 'Select your extracted Twilight Princess USA GameCube disc image'
        $picker.Filter = 'Game disc images (*.ciso;*.iso;*.gcm;*.rvz)|*.ciso;*.iso;*.gcm;*.rvz'
        $picker.CheckFileExists = $true
        try {
            if ($picker.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
                Write-Host 'No disc image selected. Nothing was launched.'
                exit 0
            }
            $GamePath = $picker.FileName
        } finally { $picker.Dispose() }
    }
    if (-not (Test-Path -LiteralPath $GamePath -PathType Leaf)) { throw 'The selected disc image was not found.' }
    $GamePath = (Resolve-Path -LiteralPath $GamePath).Path
    if ([IO.Path]::GetExtension($GamePath).ToLowerInvariant() -notin @('.iso','.ciso','.gcm','.rvz')) {
        throw 'Select the extracted disc image, not a .7z archive or split archive volume.'
    }
    Set-Content -LiteralPath $pathRecord -Value $GamePath -Encoding UTF8

    $dataDir = Join-Path $projectDir 'TestData'
    $logsDir = Join-Path $projectDir 'Logs\Cafe'
    $modsDir = Join-Path $projectDir 'mods'
    $modFile = 'SilentHillCafe.dusk'
    $stageTarget = 'R_SP108,0,0,0'
    if ($Outdoor -and -not $Baseline) {
        $dataDir = Join-Path $projectDir 'OutdoorTestData'
        $logsDir = Join-Path $projectDir 'Logs\Outdoor'
        $modsDir = Join-Path $projectDir 'OutdoorMods'
        $modFile = 'SilentHillOutdoor.dusk'
        Write-Host 'Outdoor test: one bounded street block. Gameplay validation is pending.'
    }
    if ($Connected -and -not $Baseline) {
        $dataDir = Join-Path $projectDir 'ConnectedTestData'
        $logsDir = Join-Path $projectDir 'Logs\Connected'
        $modsDir = Join-Path $projectDir 'ConnectedMods'
        $modFile = 'SilentHillConnected.dusk'
        Write-Host 'Connected test 0.3.1: supported doors; face the wooden door and press Open.'
        Write-Host 'The cafe and street are linked in both directions. Playtest pending.'
    }
    if ($Fog -and -not $Baseline) {
        $dataDir = Join-Path $projectDir 'FogTestData'
        $logsDir = Join-Path $projectDir 'Logs\Fog'
        $modsDir = Join-Path $projectDir 'FogMods'
        $modFile = 'SilentHillFogTest.dusk'
        $stageTarget = 'R_SP109,0,0,0'
        Write-Host 'Silent Hill prototype 0.4.0: foggy street and cafe. Campaign not implemented.'
        Write-Host 'Native fog and door patch require in-game testing.'
    }
    if ($Town -and -not $Baseline) {
        $dataDir = Join-Path $projectDir 'TownTestData'
        $logsDir = Join-Path $projectDir 'Logs\Town'
        $modsDir = Join-Path $projectDir 'TownMods'
        $modFile = 'SilentHillTown.dusk'
        $stageTarget = 'R_SP109,0,0,0'
        Write-Host 'Silent Hill prototype 0.5.0: three street tiles, fog and cafe. Campaign not implemented.'
        Write-Host 'Expanded map and door patch require in-game testing.'
    }
    if ($District -and -not $Baseline) {
        $dataDir = Join-Path $projectDir 'DistrictTestData'
        $logsDir = Join-Path $projectDir 'Logs\District'
        $modsDir = Join-Path $projectDir 'DistrictMods'
        $modFile = 'SilentHillDistrict.dusk'
        $stageTarget = 'R_SP109,0,0,0'
        Write-Host 'Silent Hill prototype 0.6.0: central district (3 x 3 town blocks), fog, cafe.'
        Write-Host 'Silent Hill Core: Start > Options = settings, LB or Space = jump, sword and shield.'
        Write-Host 'Campaign not implemented. Expanded map and new controls require in-game testing.'
        if (-not (Test-Path -LiteralPath (Join-Path $modsDir 'silent_hill_core.dusk'))) {
            Write-Host 'Note: silent_hill_core.dusk is missing from DistrictMods; jump/settings features are off.' -ForegroundColor Yellow
        }
    }
    if ($OldTown -and -not $Baseline) {
        # Same data profile as the 0.6 district test so your settings and mod options carry over.
        $dataDir = Join-Path $projectDir 'DistrictTestData'
        $logsDir = Join-Path $projectDir 'Logs\OldTown'
        $modsDir = Join-Path $projectDir 'OldTownMods'
        $modFile = 'SilentHillOldTown.dusk'
        $stageTarget = 'D_SB01,0,0,0'
        Write-Host 'Silent Hill prototype 0.7.0: Old Silent Hill town - walk across street edges to'
        Write-Host 'move between areas. Cafe, fog, Stalhounds and Guays. Story not implemented yet.'
        Write-Host 'LB/Space jump, RB dodge roll, X sword, B lantern, Y bow, Start > Options = settings.'
        if (-not (Test-Path -LiteralPath (Join-Path $modsDir 'silent_hill_core.dusk'))) {
            Write-Host 'Note: silent_hill_core.dusk is missing from OldTownMods; controls and starter kit are off.' -ForegroundColor Yellow
        }
    }
    if ($Baseline) {
        $logsDir = Join-Path $projectDir 'Logs\NormalZelda'
        $dataDir = Join-Path $projectDir 'NormalGameTestData'
        $modsDir = Join-Path $projectDir 'EmptyMods'
        New-Item -ItemType Directory -Path $modsDir -Force | Out-Null
    } elseif (-not (Test-Path -LiteralPath (Join-Path $modsDir $modFile))) {
        throw "Missing $modFile. Extract the entire test ZIP before launching."
    }
    New-Item -ItemType Directory -Path $dataDir,$logsDir -Force | Out-Null
    if ($PCProfile -and -not $Baseline) {
        & (Join-Path $projectDir 'tools\Apply-PCProfile.ps1') -DataDirectory $dataDir
    }
    $launchArgs = @('--user-dir', $dataDir, '--log-dir', $logsDir, '--mods', $modsDir)
    if (-not $Baseline) { $launchArgs += @('--stage',$stageTarget) }
    if ($LegacyGraphics) { $launchArgs += @('--backend','d3d11') }
    $launchArgs += $GamePath
    Write-Host 'Starting game. First launch may take longer while data and shaders are prepared.'
    Write-Host ('Logs: ' + $logsDir)
    # Quote each argument for Windows Start-Process; paths may contain spaces.
    $quotedArgs = ($launchArgs | ForEach-Object { '"' + $_ + '"' }) -join ' '
    $gameProcess = Start-Process -FilePath $engineExe.FullName -ArgumentList $quotedArgs -Wait -PassThru
    $gameExit = $gameProcess.ExitCode
    if ($gameExit -ne 0) {
        throw "The game exited with code $gameExit. Send the newest file from Logs and describe what appeared."
    }
} catch {
    Write-Host ''
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host 'If the test fails, try Test-Normal-Zelda.cmd and send the newest log from the relevant Logs subfolder.'
    exit 1
}
