# Builds dist\ClaudePetSetup.exe: the pet (PyInstaller) -> dist\ClaudePet, then the installer (Inno Setup).
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1
# One-time: py -m venv packaging\.venv-build; packaging\.venv-build\Scripts\pip install pyinstaller
#           winget install JRSoftware.InnoSetup
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$root = Split-Path $here
$dist = Join-Path $root "dist"
$py = Join-Path $here ".venv-build\Scripts\python.exe"
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not (Test-Path $py)) { throw "Missing build environment: see the one-time steps at the top of this file." }
if (-not $iscc) { throw "Inno Setup isn't installed: winget install JRSoftware.InnoSetup" }

& $py (Join-Path $here "make_art.py")
& $py -m PyInstaller --noconfirm --clean --log-level WARN --distpath $dist --workpath (Join-Path $root "build") (Join-Path $here "claude-pet.spec")
if ($LASTEXITCODE) { throw "PyInstaller failed" }
& $iscc /Q (Join-Path $here "setup.iss")
if ($LASTEXITCODE) { throw "Inno Setup failed" }
Get-Item (Join-Path $dist "ClaudePetSetup.exe") | Select-Object Name, @{n = "MB"; e = { [math]::Round($_.Length / 1MB, 1) } }
