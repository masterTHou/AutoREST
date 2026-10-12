# AutoREST DSH Skill — Windows Installer
# Usage: powershell -ExecutionPolicy Bypass -File install.ps1
# Or just copy .dsh/skills/autorest/ to your project/.dsh/skills/autorest/

param(
    [string]$TargetDir = ""
)

$skillSource = Join-Path $PSScriptRoot ".dsh\skills\autorest"

if (-not (Test-Path $skillSource)) {
    Write-Error "Skill source not found: $skillSource"
    Write-Error "Make sure you run this script from the AutoREST project root."
    exit 1
}

if ($TargetDir -eq "") {
    # Install to current directory (project-level)
    $TargetDir = Join-Path (Get-Location) ".dsh\skills\autorest"
}

Write-Output "==================================="
Write-Output " AutoREST DSH Skill Installer"
Write-Output "==================================="
Write-Output ""
Write-Output "Source: $skillSource"
Write-Output "Target: $TargetDir"
Write-Output ""

New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
Copy-Item "$skillSource\*" $TargetDir -Recurse -Force

Write-Output "✅ AutoREST Skill installed to: $TargetDir"
Write-Output ""
Write-Output "Next steps:"
Write-Output "  1. Restart DSH (close completely and reopen)"
Write-Output "  2. Say: '帮我算一个水分子的单点能'"
Write-Output "  3. DSH will discover AutoREST and show selection panels"
Write-Output ""