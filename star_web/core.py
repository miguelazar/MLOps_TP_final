"""Contrato D2 y lectura segura de la respuesta CSV de SDSS."""
import csv
import io
import math

BANDS = ['u', 'g', 'r', 'i', 'z']
COLORS = ['u-g', 'g-r', 'r-i', 'i-z']
FEATURES = BANDS + COLORS
SQL = '''SELECT TOP 10000
  p.objid, p.ra, p.dec, p.u, p.g, p.r, p.i, p.z,
  s.class, s.z AS redshift
FROM PhotoObj AS p
JOIN SpecObj AS s ON s.bestobjid = p.objid
WHERE s.scienceprimary = 1
ORDER BY p.objid'''
SDSS_URL = 'https://skyserver.sdss.org/dr17/SkyServerWS/SearchTools/SqlSearch'


def validate_features(features):
    if set(features) != set(FEATURES):
        raise ValueError('Enviar exactamente las cinco bandas y los cuatro colores D2.')
    result = {}
    for name in FEATURES:
        if isinstance(features[name], bool):
            raise ValueError(f'{name} debe ser un número finito.')
        try:
            result[name] = float(features[name])
        except (TypeError, ValueError):
            raise ValueError(f'{name} debe ser un número finito.') from None
        if not math.isfinite(result[name]):
            raise ValueError(f'{name} debe ser un número finito.')
    if any(result[band] <= -9000 for band in BANDS):
        raise ValueError('El objeto tiene bandas sin medición válida.')
    for left, right in zip(BANDS[:-1], BANDS[1:]):
        if not math.isclose(result[f'{left}-{right}'], result[left]-result[right], abs_tol=1e-8):
            raise ValueError(f'El color {left}-{right} no coincide con las bandas enviadas.')
    return result


def parse_objects(text):
    lines = [line for line in text.lstrip('\ufeff').splitlines()
             if line.strip() and not line.startswith('#')]
    reader = csv.DictReader(lines)
    expected = {'objid', 'ra', 'dec', *BANDS, 'class', 'redshift'}
    if set(reader.fieldnames or []) != expected:
        raise ValueError('SDSS no devolvió el CSV esperado.')
    rows = list(reader)
    if not rows or len(rows) > 10000:
        raise ValueError('SDSS debe devolver entre 1 y 10000 objetos.')
    objects, seen = [], set()
    for row in rows:
        objid = (row.get('objid') or '').strip()
        try:
            bands = {key: float(row[key]) for key in BANDS}
        except (TypeError, ValueError, KeyError):
            continue
        if not objid or objid in seen or any(not math.isfinite(v) or v <= -9000 for v in bands.values()):
            continue
        record = {'objid':objid, **bands, 'class':(row.get('class') or '').strip()}
        for key in ['ra', 'dec', 'redshift']:
            try:
                value = float(row[key])
                record[key] = value if math.isfinite(value) else None
            except (KeyError, TypeError, ValueError):
                record[key] = None
        objects.append(record)
        seen.add(objid)
    if not objects:
        raise ValueError('La consulta no devolvió objetos con bandas válidas.')
    return {'objects':objects, 'received':len(rows), 'excluded':len(rows)-len(objects)}
