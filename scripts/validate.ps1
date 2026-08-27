param(
    [string]$Blender = "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$blenderRoot = Split-Path -Parent $Blender
$python = Get-ChildItem -LiteralPath $blenderRoot -Recurse -Filter "python.exe" |
    Where-Object { $_.FullName -match '[\\/]python[\\/]bin[\\/]python\.exe$' } |
    Select-Object -First 1
if ($null -eq $python) {
    throw "Could not locate Blender's bundled Python interpreter under $blenderRoot"
}
Push-Location $root
try {
    & $python.FullName -m compileall -q dimensions tests
    if ($LASTEXITCODE -ne 0) { throw "Python compilation failed" }

    & $python.FullName tests\stroke_font_smoke.py
    if ($LASTEXITCODE -ne 0) { throw "Stroke font smoke tests failed" }

    & $Blender --background --factory-startup --python tests\blender_smoke.py
    if ($LASTEXITCODE -ne 0) { throw "Blender smoke tests failed" }

    & $Blender --background --factory-startup --python tests\blender_modal.py
    if ($LASTEXITCODE -ne 0) { throw "Blender modal interaction tests failed" }

    & $Blender --background --factory-startup --python tests\blender_lifecycle.py
    if ($LASTEXITCODE -ne 0) { throw "Blender lifecycle tests failed" }

    & $Blender --background --factory-startup --python tests\output_geometry_smoke.py
    if ($LASTEXITCODE -ne 0) { throw "Output geometry smoke tests failed" }

    & $Blender --background --factory-startup --python tests\output_smoke.py
    if ($LASTEXITCODE -ne 0) { throw "Grease Pencil output smoke tests failed" }

    & $Blender --background --factory-startup --python tests\output_operator_smoke.py
    if ($LASTEXITCODE -ne 0) { throw "Output operator smoke tests failed" }

    & $Blender --background --factory-startup --command extension validate dimensions
    if ($LASTEXITCODE -ne 0) { throw "Extension manifest validation failed" }

    & (Join-Path $PSScriptRoot "build_extension.ps1") -Blender $Blender
    $archive = Get-ChildItem (Join-Path $root "build\dimensions-*.zip") |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($null -eq $archive) { throw "Extension archive was not created" }
    $entries = tar -tf $archive.FullName
    if ($entries -notcontains "LICENSE") { throw "Extension archive does not contain LICENSE" }
    & $Blender --background --factory-startup --command extension validate $archive.FullName
    if ($LASTEXITCODE -ne 0) { throw "Built extension archive validation failed" }
} finally {
    Pop-Location
}
