$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

function Require-Command([string]$name) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        throw "Required command '$name' was not found. Install the pinned developer runtime and retry."
    }
}

Require-Command "python"
Require-Command "node"
Require-Command "git"
Require-Command "npm"

python -c "import sys; assert sys.version_info -ge (3,10), 'Python 3.10 or newer is required'"
$nodeVersion = (node --version).TrimStart("v")
if ($nodeVersion -ne "22.14.0") { throw "Node 22.14.0 is required; found $nodeVersion" }

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
}
& ".venv\Scripts\python.exe" -m pip install --requirement requirements.txt

$providerDir = Join-Path $repoRoot "runtime\bgutil-ytdlp-pot-provider"
if (-not (Test-Path (Join-Path $providerDir ".git"))) {
    New-Item -ItemType Directory -Force -Path (Split-Path $providerDir) | Out-Null
    git clone --branch 1.3.1 --depth 1 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git $providerDir
} else {
    git -C $providerDir fetch --tags --depth 1 origin 1.3.1
    git -C $providerDir checkout --detach 1.3.1
}
Push-Location (Join-Path $providerDir "server")
npm ci
npm exec -- tsc
Pop-Location

Push-Location (Join-Path $repoRoot "frontend")
npm ci
npm run build
Pop-Location

Write-Host "Developer setup complete. Launch with: .venv\Scripts\python.exe launcher.py --dev"
