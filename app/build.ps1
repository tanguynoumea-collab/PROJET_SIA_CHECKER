# Construit SIA Check Viewer prêt à copier : app WPF autonome + moteur sia-check embarqué.
#
#   powershell -ExecutionPolicy Bypass -File app\build.ps1
#
# Résultat : app\dist\SiaCheckViewer\
#   SiaCheck.Viewer.exe          visionneuse (.NET 10 autonome, pas de runtime à installer)
#   engine\sia-check.exe         moteur Python (PyInstaller), lancé par la visionneuse
#   engine\config.yaml           nomenclature et tolérances, modifiables sans recompiler
# et, si Inno Setup 6 est installé : app\dist\SiaCheckViewer-<version>-setup.exe (installeur par utilisateur,
# raccourcis menu Démarrer / bureau). Version : <Version> de SiaCheck.Viewer.csproj.

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$dist = Join-Path $PSScriptRoot 'dist\SiaCheckViewer'
$py = Join-Path $root '.venv\Scripts\python.exe'
$work = Join-Path $env:TEMP 'siacheck-build'

if (Test-Path $dist) { Remove-Item -Recurse -Force $dist }

# 1. Moteur : onedir (démarrage rapide, pas de décompression à chaque analyse).
#    ifcopenshell est embarqué (V4) : la génération depuis l'IFC (sia-check --generer) lit et triangule la maquette ;
#    --collect-all prend son module binaire et ses schémas. Les modules de génération sont importés à la demande.
#    shapely est embarqué pour les preuves de la revue IA et la géométrie de la génération.
& $py -m pip install -q pyinstaller shapely ifcopenshell
& $py -m PyInstaller --noconfirm --clean --name sia-check --console `
    --distpath (Join-Path $work 'dist') --workpath (Join-Path $work 'build') --specpath $work `
    --exclude-module numpy.tests --exclude-module pytest `
    --hidden-import sia_check.preuves --collect-submodules shapely `
    --collect-all ifcopenshell --collect-submodules sia_check.generation `
    --add-data "$(Join-Path $root 'src\sia_check\templates');sia_check\templates" `
    --paths (Join-Path $root 'src') (Join-Path $root 'src\sia_check\__main__.py')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller a échoué' }

# 2. Visionneuse : publication autonome win-x64.
dotnet publish (Join-Path $PSScriptRoot 'SiaCheck.Viewer\SiaCheck.Viewer.csproj') -c Release -r win-x64 `
    --self-contained true -p:PublishSingleFile=false -o $dist
if ($LASTEXITCODE -ne 0) { throw 'dotnet publish a échoué' }

Copy-Item -Recurse (Join-Path $work 'dist\sia-check') (Join-Path $dist 'engine')
Copy-Item (Join-Path $root 'config.yaml') (Join-Path $dist 'engine\config.yaml')
Write-Host "Prêt : $dist"

# 3. Installeur (Inno Setup 6, installation utilisateur ou machine).
$version = ([xml](Get-Content (Join-Path $PSScriptRoot 'SiaCheck.Viewer\SiaCheck.Viewer.csproj'))).Project.PropertyGroup.Version | Where-Object { $_ } | Select-Object -First 1
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    & $iscc /Q "/DAppVersion=$version" (Join-Path $PSScriptRoot 'installer\SiaCheckViewer.iss')
    if ($LASTEXITCODE -ne 0) { throw 'Inno Setup a échoué' }
    Write-Host "Installeur : $(Join-Path $PSScriptRoot "dist\SiaCheckViewer-$version-setup.exe")"
} else {
    Write-Host 'Inno Setup 6 absent : installeur non construit (dossier prêt à copier seulement).'
}
