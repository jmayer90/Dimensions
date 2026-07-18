param(
    [string]$Blender = "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe",
    [string]$OutputDirectory = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $root "build"
}
$stage = Join-Path $root "build\extension-stage"
if (Test-Path -LiteralPath $stage) {
    Remove-Item -LiteralPath $stage -Recurse -Force
}
New-Item -ItemType Directory -Path $stage -Force | Out-Null
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
Copy-Item -Path (Join-Path $root "dimensions\*") -Destination $stage -Recurse -Force
Copy-Item -LiteralPath (Join-Path $root "LICENSE") -Destination (Join-Path $stage "LICENSE")
Copy-Item -LiteralPath (Join-Path $root "README.md") -Destination (Join-Path $stage "README.md")

& $Blender --background --factory-startup --command extension build --source-dir $stage --output-dir $OutputDirectory
if ($LASTEXITCODE -ne 0) {
    throw "Blender extension build failed with exit code $LASTEXITCODE"
}

$manifestVersion = Select-String -LiteralPath (Join-Path $stage "blender_manifest.toml") -Pattern '^version\s*=\s*"([^"]+)"$'
if ($null -eq $manifestVersion) {
    throw "Could not read the extension version from blender_manifest.toml"
}
$version = $manifestVersion.Matches[0].Groups[1].Value
$archive = Join-Path $OutputDirectory "dimensions-$version.zip"
if (-not (Test-Path -LiteralPath $archive)) {
    throw "Expected extension archive was not created: $archive"
}

& $Blender --background --factory-startup --command extension validate $archive
if ($LASTEXITCODE -ne 0) {
    throw "Built extension archive validation failed with exit code $LASTEXITCODE"
}

$entries = @(tar -tf $archive)
$requiredEntries = @("__init__.py", "blender_manifest.toml", "LICENSE", "README.md")
foreach ($entry in $requiredEntries) {
    if ($entries -notcontains $entry) {
        throw "Extension archive does not contain required release file: $entry"
    }
}
$unwantedEntries = @($entries | Where-Object { $_ -match '(^|/)__pycache__/' -or $_ -match '\.py[co]$' })
if ($unwantedEntries.Count -ne 0) {
    throw "Extension archive contains generated Python cache files: $($unwantedEntries -join ', ')"
}

Write-Host "Submission-ready extension archive: $archive"
