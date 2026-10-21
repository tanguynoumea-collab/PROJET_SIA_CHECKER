# Construit SIA Check Viewer prêt à copier : app WPF autonome + moteur sia-check embarqué.
#
#   powershell -ExecutionPolicy Bypass -File app\build.ps1
#
# Résultat : app\dist\SiaCheckViewer\
#   SiaCheck.Viewer.exe          visionneuse (.NET 10 autonome, pas de runtime à installer)
#   engine\sia-check.exe         moteur Python (PyInstaller), lancé par la visionneuse
#   engine\config.yaml           nomenclature et tolérances, modifiables sans recompiler

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$dist = Join-Path $PSScriptRoot 'dist\SiaCheckViewer'
$py = Join-Path $root '.venv\Scripts\python.exe'
$work = Join-Path $env:TEMP 'siacheck-build'

if (Test-Path $dist) { Remove-Item -Recurse -Force $dist }

# 1. Moteur : onedir (démarrage rapide, pas de décompression à chaque analyse).
#    ifcopenshell est exclu : la visionneuse lit les projets .tgm ; la CLI complète reste disponible via pip.
& $py -m pip install -q pyinstaller
& $py -m PyInstaller --noconfirm --clean --name sia-check --console `
    --distpath (Join-Path $work 'dist') --workpath (Join-Path $work 'build') --specpath $work `
    --exclude-module ifcopenshell --exclude-module numpy.tests --exclude-module pytest `
    --paths (Join-Path $root 'src') (Join-Path $root 'src\sia_check\__main__.py')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller a échoué' }

# 2. Visionneuse : publication autonome win-x64.
dotnet publish (Join-Path $PSScriptRoot 'SiaCheck.Viewer\SiaCheck.Viewer.csproj') -c Release -r win-x64 `
    --self-contained true -p:PublishSingleFile=false -o $dist
if ($LASTEXITCODE -ne 0) { throw 'dotnet publish a échoué' }

Copy-Item -Recurse (Join-Path $work 'dist\sia-check') (Join-Path $dist 'engine')
Copy-Item (Join-Path $root 'config.yaml') (Join-Path $dist 'engine\config.yaml')
Write-Host "Prêt : $dist"
