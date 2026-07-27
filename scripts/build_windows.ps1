$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
$version = (Get-Content "VERSION.txt" -Raw).Trim()
$stage = Join-Path $repoRoot "release\StudySuite-$version-windows-x64"
if (Test-Path $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $stage | Out-Null

& ".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --name StudySuite launcher.py
Copy-Item -LiteralPath "dist\StudySuite\*" -Destination $stage -Recurse -Force
Copy-Item -LiteralPath "runtime" -Destination $stage -Recurse -Force
Copy-Item -LiteralPath "frontend\dist" -Destination (Join-Path $stage "frontend") -Recurse -Force
Copy-Item -LiteralPath "client_secret.json" -Destination $stage -Force
Copy-Item -LiteralPath "VERSION.txt" -Destination $stage -Force

$nodeExe = Join-Path $stage "runtime\node\node.exe"
if (-not (Test-Path $nodeExe)) { $nodeExe = "node" }

$manifest = [ordered]@{
    study_suite_version = $version
    python_version = (& ".venv\Scripts\python.exe" --version)
    node_version = (& $nodeExe --version)
    yt_dlp_version = "2026.06.09"
    bgutil_provider_version = "1.3.1"
    po_token_source_commit = (& git -C "runtime\bgutil-ytdlp-pot-provider" rev-parse HEAD).Trim()
}
$manifest | ConvertTo-Json | Set-Content (Join-Path $stage "release-manifest.json")

$zip = Join-Path $repoRoot "release\StudySuite-$version-windows-x64.zip"
if (Test-Path $zip) { Remove-Item -LiteralPath $zip -Force }
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip
(Get-FileHash -Algorithm SHA256 $zip).Hash + "  " + (Split-Path $zip -Leaf) | Set-Content ($zip + ".sha256")
Write-Host "Created $zip"
