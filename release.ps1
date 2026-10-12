# AutoREST DSH Skill — Release Packager
# Usage: powershell -File release.ps1
# Creates autorest-skill-v2.1.0.zip ready for GitHub Releases

param(
    [string]$Version = "2.1.0"
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$skillDir = Join-Path $root ".dsh\skills\autorest"
$outputZip = Join-Path $root "autorest-skill-v$Version.zip"

if (-not (Test-Path $skillDir)) {
    Write-Error "Skill directory not found: $skillDir"
    exit 1
}

Write-Output "==================================="
Write-Output " AutoREST Release Packager v$Version"
Write-Output "==================================="
Write-Output ""
Write-Output "Source: $skillDir"
Write-Output "Output: $outputZip"
Write-Output ""

# Clean old zip
if (Test-Path $outputZip) {
    Remove-Item $outputZip -Force
}

# Create temp staging directory
$staging = Join-Path $env:TEMP "autorest-release-staging"
if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
New-Item -ItemType Directory -Path "$staging\.dsh\skills\autorest" -Force | Out-Null

# Copy skill files (exclude Python .pyc cache)
Get-ChildItem $skillDir -Recurse -File | Where-Object { $_.Extension -ne '.pyc' } | ForEach-Object {
    $relative = $_.FullName.Replace($skillDir, "").TrimStart("\")
    $dest = Join-Path "$staging\.dsh\skills\autorest" $relative
    $destDir = Split-Path $dest -Parent
    if (-not (Test-Path $destDir)) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    }
    Copy-Item $_.FullName $dest -Force
}

# Create zip
Compress-Archive -Path "$staging\*" -DestinationPath $outputZip -Force

# Cleanup
Remove-Item $staging -Recurse -Force

# Verify
$zipSize = [math]::Round((Get-Item $outputZip).Length / 1MB, 2)
$fileCount = (Get-ChildItem $skillDir -Recurse -File | Where-Object { $_.Extension -ne '.pyc' }).Count

Write-Output "✅ Release package created:"
Write-Output "   File:   $outputZip"
Write-Output "   Size:   $zipSize MB"
Write-Output "   Files:  $fileCount"
Write-Output ""
Write-Output "Users install by extracting this zip into their DSH project root."
Write-Output "After extraction: <project>/.dsh/skills/autorest/SKILL.md"
Write-Output ""