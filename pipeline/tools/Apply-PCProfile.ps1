param([Parameter(Mandatory=$true)][string]$DataDirectory, [switch]$Force)
$ErrorActionPreference = 'Stop'
$profileId = 'i5-12400F-RTX3060-v1'
$marker = Join-Path $DataDirectory ($profileId + '.applied')
if ((Test-Path -LiteralPath $marker) -and -not $Force) { return }
$profilePath = Join-Path (Split-Path $PSScriptRoot -Parent) 'profiles\i5-12400F-RTX3060.json'
$profile = Get-Content -LiteralPath $profilePath -Raw | ConvertFrom-Json
New-Item -ItemType Directory -Path $DataDirectory -Force | Out-Null
$configPath = Join-Path $DataDirectory 'config.json'
$config = [pscustomobject]@{}
if (Test-Path -LiteralPath $configPath) {
    $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    if ($null -eq $config -or $config -isnot [pscustomobject]) { throw 'Existing config.json must be a JSON object. It was left unchanged.' }
    $backup = $configPath + '.before-pc-profile-' + (Get-Date -Format 'yyyyMMdd-HHmmss-ffff')
    Copy-Item -LiteralPath $configPath -Destination $backup
}
foreach ($property in $profile.PSObject.Properties) {
    $config | Add-Member -MemberType NoteProperty -Name $property.Name -Value $property.Value -Force
}
# UTF-8 without BOM supports Windows PowerShell 5.1 and the engine JSON reader.
$json = $config | ConvertTo-Json -Depth 100
$temp = $configPath + '.tmp'
[IO.File]::WriteAllText($temp, $json, (New-Object Text.UTF8Encoding($false)))
Move-Item -LiteralPath $temp -Destination $configPath -Force
[IO.File]::WriteAllText($marker, $profileId, (New-Object Text.UTF8Encoding($false)))
Write-Host 'PC profile applied: 1080p window, VSync, 60 FPS interpolation cap, standard shadows.'
