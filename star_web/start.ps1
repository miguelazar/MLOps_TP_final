param([switch]$PrepareOnly)

$ErrorActionPreference = 'Stop'
$starRepo = Split-Path -Parent $PSScriptRoot
$starEnv = Join-Path $starRepo '.venv-star-web'
$starPython = Join-Path $starEnv 'Scripts/python.exe'

if (-not (Test-Path -LiteralPath $starPython)) {
    # Preferir versiones soportadas, sin depender de Anaconda ni de una ruta fija.
    $starCandidates = @(
        @{ Command = 'py'; Arguments = @('-3.12') },
        @{ Command = 'py'; Arguments = @('-3.13') },
        @{ Command = 'py'; Arguments = @('-3.11') },
        @{ Command = 'python'; Arguments = @() }
    )
    $starCreated = $false
    foreach ($starCandidate in $starCandidates) {
        $starCommand = Get-Command $starCandidate.Command -ErrorAction SilentlyContinue
        if (-not $starCommand) { continue }
        $starArguments = $starCandidate.Arguments
        try {
            & $starCommand.Source @starArguments -c 'import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] < (3,14) else 1)' 2>$null
            if ($LASTEXITCODE -ne 0) { continue }
            Write-Host 'Creando un entorno Python aislado para la web...'
            & $starCommand.Source @starArguments -m venv $starEnv
            if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno Python.' }
            $starCreated = $true
            break
        } catch {
            if (Test-Path -LiteralPath $starPython) { throw }
        }
    }
    if (-not $starCreated) {
        throw 'Instalar Python 3.11, 3.12 o 3.13 (recomendado: 3.12), con venv y pip, y volver a ejecutar el script.'
    }
}

& $starPython -c 'import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] < (3,14) else 1)'
if ($LASTEXITCODE -ne 0) { throw 'El entorno existente requiere Python 3.11 a 3.13.' }

# Desactivar herencia si el entorno se creó con la versión anterior del script.
$starVenvConfig = Join-Path $starEnv 'pyvenv.cfg'
$starConfig = Get-Content -LiteralPath $starVenvConfig -Raw -Encoding UTF8
if ($starConfig -match 'include-system-site-packages\s*=\s*true') {
    $starConfig = $starConfig -replace 'include-system-site-packages\s*=\s*true', 'include-system-site-packages = false'
    [System.IO.File]::WriteAllText($starVenvConfig, $starConfig, [System.Text.UTF8Encoding]::new($false))
}

$starRequirements = Join-Path $PSScriptRoot 'requirements.txt'
$starStamp = Join-Path $starEnv 'star-requirements.sha256'
$starHash = (Get-FileHash -LiteralPath $starRequirements -Algorithm SHA256).Hash + '|isolated-v2'
if (-not (Test-Path -LiteralPath $starStamp) -or (Get-Content -LiteralPath $starStamp -Raw).Trim() -ne $starHash) {
    Write-Host 'Instalando las dependencias de la web...'
    & $starPython -m pip install --disable-pip-version-check -r $starRequirements
    if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias. Revisar el acceso a PyPI.' }
    Set-Content -LiteralPath $starStamp -Value $starHash
}

$starEnvFile = Join-Path $starRepo '.env'
$starEnvExample = Join-Path $starRepo '.env.example'
if (-not (Test-Path -LiteralPath $starEnvFile) -and (Test-Path -LiteralPath $starEnvExample)) {
    Copy-Item -LiteralPath $starEnvExample -Destination $starEnvFile
    Write-Host 'Se creó .env con los valores locales de ejemplo. Revisar la configuración si corresponde.'
}
if ($PrepareOnly) { Write-Host 'Entorno de la web listo.'; return }

Write-Host 'Iniciando la web (por defecto http://localhost:8801). Ctrl+C para detener.'
& $starPython (Join-Path $PSScriptRoot 'app.py')
if ($LASTEXITCODE -ne 0) { throw 'La aplicación no pudo iniciarse o terminó con error.' }
