param([switch]$PrepareOnly)

$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'star_web/start.ps1') -PrepareOnly:$PrepareOnly
