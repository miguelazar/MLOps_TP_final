# Exporta SOLO certificados públicos de cadenas aceptadas por Windows.
# No cambia el almacén de confianza ni desactiva la verificación TLS.
$ErrorActionPreference = 'Stop'
$starBundlePath = Join-Path $PSScriptRoot 'airflow/config/pip-ca-bundle.pem'
$starOverridePath = Join-Path $PSScriptRoot 'docker-compose.override.yaml'
$starOverrideMarker = '# Generado por preparar-ca.ps1; configuracion CA local.'
if ((Test-Path $starOverridePath) -and -not ([System.IO.File]::ReadAllText($starOverridePath).StartsWith($starOverrideMarker))) {
    throw 'Ya existe docker-compose.override.yaml propio. Conservarlo y usar docker-compose.ca.yaml con -f; no se sobrescribe.'
}
$starCertificates = @{}
foreach ($starHostName in @('pypi.org', 'files.pythonhosted.org', 'skyserver.sdss.org')) {
    $starTcp = [System.Net.Sockets.TcpClient]::new()
    $starTls = $null
    try {
        $starConnect = $starTcp.ConnectAsync($starHostName, 443)
        if (-not $starConnect.Wait(20000)) { throw "Timeout al conectar con $starHostName" }
        $starTls = [System.Net.Security.SslStream]::new($starTcp.GetStream(), $false)
        $starTls.ReadTimeout = 20000
        $starTls.WriteTimeout = 20000
        # La validación por defecto exige certificado válido para ese hostname.
        $starTls.AuthenticateAsClient($starHostName)
        $starLeaf = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($starTls.RemoteCertificate)
        $starChain = [System.Security.Cryptography.X509Certificates.X509Chain]::new()
        try {
            if (-not $starChain.Build($starLeaf)) {
                throw "Windows no pudo validar la cadena de $starHostName. Consultar la CA con el administrador de red."
            }
            foreach ($starElement in $starChain.ChainElements) {
                $starCertificate = $starElement.Certificate
                if ($starCertificate.Thumbprint -ne $starLeaf.Thumbprint) {
                    $starCertificates[$starCertificate.Thumbprint] = [Convert]::ToBase64String(
                        $starCertificate.RawData, [Base64FormattingOptions]::InsertLineBreaks)
                }
            }
        } finally {
            $starChain.Dispose()
            $starLeaf.Dispose()
        }
        Write-Host "Cadena HTTPS validada por Windows: $starHostName"
    } finally {
        if ($null -ne $starTls) { $starTls.Dispose() }
        $starTcp.Dispose()
    }
}
if ($starCertificates.Count -eq 0) { throw 'No se encontraron certificados CA válidos para exportar.' }
$starPem = ''
foreach ($starThumbprint in ($starCertificates.Keys | Sort-Object)) {
    $starPem += "-----BEGIN CERTIFICATE-----`n" + $starCertificates[$starThumbprint] + "`n-----END CERTIFICATE-----`n"
}
[System.IO.Directory]::CreateDirectory((Split-Path -Parent $starBundlePath)) | Out-Null
[System.IO.File]::WriteAllText($starBundlePath, $starPem, [System.Text.Encoding]::ASCII)
Write-Host "Bundle público guardado: $starBundlePath"
Write-Host 'No subir este archivo local al repositorio. No contiene claves privadas.'

$starOverride = $starOverrideMarker + "`n" + [System.IO.File]::ReadAllText((Join-Path $PSScriptRoot 'docker-compose.ca.yaml'))
[System.IO.File]::WriteAllText($starOverridePath, $starOverride, [System.Text.UTF8Encoding]::new($false))
Write-Host 'Configuracion CA local activada automaticamente para Docker Compose.'
Write-Host 'Proximo arranque: docker compose --profile airflow --profile mlflow up -d --build'