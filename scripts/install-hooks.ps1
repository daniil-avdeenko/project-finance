# Устанавливает локальные git-хуки из scripts/hooks/ в .git/hooks/.

$ErrorActionPreference = "Stop"

$root = git rev-parse --show-toplevel
Push-Location $root

Copy-Item scripts/hooks/pre-push .git/hooks/pre-push -Force
Write-Host "Pre-push hook installed at .git/hooks/pre-push" -ForegroundColor Green

Pop-Location
