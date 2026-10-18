<#
  Builds Sony RAW to JPG Converter on Windows 10/11 x64.

  Usage (from the repository root, in PowerShell):
      powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
  Options:
      -SkipTests       skip pytest
      -SkipInstaller   only build dist\SonyRawConverter\SonyRawConverter.exe
  Requires: Python 3.12 x64 on PATH (py launcher), Inno Setup 6 for the installer.
#>
param([switch]$SkipTests, [switch]$SkipInstaller)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Version = (Select-String -Path "src\version.py" -Pattern 'APP_VERSION = "(.+)"').Matches[0].Groups[1].Value
Write-Host "== Building version $Version" -ForegroundColor Cyan

if (-not (Test-Path ".venv")) {
    Write-Host "== Creating virtual environment"
    py -3.12 -m venv .venv
}
$Py = Join-Path $Root ".venv\Scripts\python.exe"
& $Py -m pip install --upgrade pip
& $Py -m pip install -r requirements-dev.txt
if ($LASTEXITCODE) { throw "pip install failed" }

if (-not $SkipTests) {
    Write-Host "== Running tests"
    & $Py -m pytest -q
    if ($LASTEXITCODE) { throw "Tests failed" }
}

Write-Host "== PyInstaller (one-folder)"
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
& $Py -m PyInstaller packaging\sony_raw_converter.spec --noconfirm --clean
if ($LASTEXITCODE) { throw "PyInstaller failed" }

Write-Host "== Self-test of packaged executable"
$StDir = Join-Path $env:TEMP "SonyRawConverterSelfTest"
Remove-Item -Recurse -Force $StDir -ErrorAction SilentlyContinue
$p = Start-Process -FilePath "dist\SonyRawConverter\SonyRawConverter.exe" -ArgumentList "--self-test", "`"$StDir`"" -Wait -PassThru
Get-Content (Join-Path $StDir "self_test.json")
if ($p.ExitCode -ne 0) { throw "Packaged self-test failed (exit $($p.ExitCode))" }

if (-not $SkipInstaller) {
    $Iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
              "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $Iscc) { throw "Inno Setup 6 not found. Install it from https://jrsoftware.org/isdl.php or run: winget install JRSoftware.InnoSetup" }
    Write-Host "== Inno Setup"
    & $Iscc "/DAppVersion=$Version" packaging\installer.iss
    if ($LASTEXITCODE) { throw "Inno Setup failed" }
    Write-Host "Installer: installer_output\SonyRawConverter-Setup-$Version.exe" -ForegroundColor Green
}
Write-Host "Portable app: dist\SonyRawConverter\SonyRawConverter.exe" -ForegroundColor Green
