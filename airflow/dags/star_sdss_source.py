"""Consulta DR17 y valida el CSV antes de escribir en S3."""
import csv
import io

SDSS_ENDPOINT = 'https://skyserver.sdss.org/dr17/SkyServerWS/SearchTools/SqlSearch'
SQL = '''SELECT TOP 1000
  p.objid, p.ra, p.dec, p.u, p.g, p.r, p.i, p.z,
  s.class, s.z AS redshift
FROM PhotoObj AS p
JOIN SpecObj AS s ON s.bestobjid = p.objid
WHERE s.scienceprimary = 1
ORDER BY NEWID()'''
COLUMNS = ['objid', 'ra', 'dec', 'u', 'g', 'r', 'i', 'z', 'class', 'redshift']


def parse_sdss_csv(text):
    # SDSS agrega una línea #Table1 antes de la cabecera.
    lines = [line for line in text.lstrip('\ufeff').splitlines()
             if line.strip() and not line.startswith('#')]
    reader = csv.DictReader(lines)
    if reader.fieldnames != COLUMNS:
        raise ValueError(f'Respuesta SDSS inválida. Cabecera: {reader.fieldnames}')
    rows = list(reader)
    if not 1 <= len(rows) <= 1000:
        raise ValueError(f'Se esperaban entre 1 y 1000 filas, llegaron {len(rows)}')
    if any(set(row) != set(COLUMNS) or any(v is None for v in row.values()) for row in rows):
        raise ValueError('CSV SDSS incompleto o mal formado')
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode('utf-8'), len(rows)


def fetch_csv():
    import os
    from pathlib import Path
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    retry = Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
    # Algunos antivirus inspeccionan HTTPS con una CA confiada en Windows,
    # pero ausente en Linux. Usar solo una CA validada/exportada localmente.
    ca_path = os.getenv('STAR_SDSS_CA_BUNDLE', '/opt/airflow/config/sdss-ca-bundle.pem')
    verify = ca_path if Path(ca_path).is_file() else True
    with requests.Session() as session:
        session.mount('https://', HTTPAdapter(max_retries=retry))
        response = session.get(SDSS_ENDPOINT, params={'cmd': SQL, 'format': 'csv'},
                               timeout=(20, 180), verify=verify)
        response.raise_for_status()
        return parse_sdss_csv(response.text)
