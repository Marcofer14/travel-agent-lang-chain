"""Clima esperado para las fechas del viaje con Open-Meteo (gratuito, sin API key).

- Si el viaje empieza dentro de los próximos 14 días: pronóstico real.
- Si es más adelante: referencia histórica de las mismas fechas del año anterior.
"""
from datetime import date, timedelta

import requests

from core.config import DESTINOS

FORECAST = "https://api.open-meteo.com/v1/forecast"
ARCHIVO = "https://archive-api.open-meteo.com/v1/archive"
VARIABLES = "temperature_2m_max,temperature_2m_min,precipitation_sum"


def _menos_un_anio(d: date) -> date:
    try:
        return d.replace(year=d.year - 1)
    except ValueError:  # 29 de febrero
        return d - timedelta(days=365)


def clima(destino: str, check_in: str, check_out: str) -> dict:
    lat, lon = DESTINOS[destino]["centro"]
    ini, fin = date.fromisoformat(check_in), date.fromisoformat(check_out)
    hoy = date.today()
    if ini <= hoy + timedelta(days=14) and fin <= hoy + timedelta(days=15):
        url, fuente = FORECAST, "pronóstico"
        params = {"start_date": ini.isoformat(), "end_date": fin.isoformat()}
    else:
        url, fuente = ARCHIVO, f"histórico (mismas fechas de {ini.year - 1})"
        params = {"start_date": _menos_un_anio(ini).isoformat(), "end_date": _menos_un_anio(fin).isoformat()}
    params |= {"latitude": lat, "longitude": lon, "daily": VARIABLES, "timezone": "Europe/Madrid"}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    d = r.json()["daily"]
    maximas = [x for x in d["temperature_2m_max"] if x is not None]
    minimas = [x for x in d["temperature_2m_min"] if x is not None]
    lluvia = [x or 0 for x in d["precipitation_sum"]]
    return {
        "destino": destino, "fuente": fuente, "check_in": check_in, "check_out": check_out,
        "max_promedio": round(sum(maximas) / len(maximas), 1), "min_promedio": round(sum(minimas) / len(minimas), 1),
        "lluvia_total_mm": round(sum(lluvia), 1), "dias_con_lluvia": sum(1 for x in lluvia if x >= 1),
        "dias": [{"fecha": f, "max": mx, "min": mn, "lluvia": ll}
                 for f, mx, mn, ll in zip(d["time"], d["temperature_2m_max"], d["temperature_2m_min"], lluvia)],
    }
