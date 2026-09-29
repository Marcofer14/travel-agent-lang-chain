"""Puntos de interés por destino y distancias desde cada alojamiento (fórmula de haversine)."""
import unicodedata

import numpy as np
import pandas as pd

LUGARES = {
    "barcelona": {
        "Sagrada Família": (41.4036, 2.1744),
        "Park Güell": (41.4145, 2.1527),
        "Passeig de Gràcia / Casa Batlló": (41.3917, 2.1650),
        "Barrio Gótico / Catedral": (41.3840, 2.1762),
        "Plaça de Catalunya": (41.3870, 2.1701),
        "Playa de la Barceloneta": (41.3784, 2.1925),
        "Camp Nou": (41.3809, 2.1228),
        "Aeropuerto El Prat": (41.2974, 2.0833),
    },
    "madrid": {
        "Puerta del Sol": (40.4169, -3.7035),
        "Plaza Mayor": (40.4155, -3.7074),
        "Museo del Prado": (40.4138, -3.6921),
        "Palacio Real": (40.4180, -3.7143),
        "Parque del Retiro": (40.4153, -3.6845),
        "Gran Vía": (40.4200, -3.7058),
        "Estadio Santiago Bernabéu": (40.4531, -3.6883),
        "Aeropuerto Barajas": (40.4983, -3.5676),
    },
    "mallorca": {
        "Catedral de Palma (casco antiguo)": (39.5676, 2.6484),
        "Sóller": (39.7667, 2.7150),
        "Valldemossa": (39.7106, 2.6225),
        "Pollença": (39.8770, 3.0160),
        "Playa de Alcúdia": (39.8390, 3.1270),
        "Cala Millor": (39.5960, 3.3830),
        "Playa Es Trenc": (39.3450, 2.9860),
        "Cuevas del Drach": (39.5360, 3.3300),
        "Aeropuerto de Palma": (39.5517, 2.7388),
    },
}
AEROPUERTOS = {"barcelona": "Aeropuerto El Prat", "madrid": "Aeropuerto Barajas", "mallorca": "Aeropuerto de Palma"}
RADIO_CERCA_KM = {"barcelona": 1.5, "madrid": 1.5, "mallorca": 12.0}


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


VACIAS = {"de", "del", "la", "el", "los", "las", "y", "cerca", "casco", "museo", "playa", "plaza", "placa", "parque"}


def _palabras(texto: str) -> set[str]:
    return {p for p in "".join(c if c.isalnum() else " " for c in _normalizar(texto)).split()
            if len(p) >= 3 and p not in VACIAS}


def buscar_lugar(destino: str, texto: str) -> str | None:
    """Encuentra el punto de interés que mejor coincide con lo que escribió el usuario (por palabras en común,
    sin tildes ni mayúsculas: 'el aeropuerto', 'sagrada familia', 'museo del prado'...)."""
    consulta = _palabras(texto)
    puntajes = {nombre: len(consulta & _palabras(nombre)) for nombre in LUGARES.get(destino, {})}
    mejor = max(puntajes, key=puntajes.get, default=None)
    return mejor if mejor and puntajes[mejor] > 0 else None


def texto_distancia(km: float, destino: str) -> str:
    if destino != "mallorca" and km <= 2.5:
        return f"{max(1, round(km * 12))} min a pie"  # ~5 km/h
    if destino == "mallorca":
        return f"{km:.0f} km (~{max(5, round(km / 50 * 60))} min en auto)"
    return f"{km:.1f} km"


def distancias(df: pd.DataFrame, destino: str) -> pd.DataFrame:
    """Una columna dist_<lugar> en km por cada punto de interés del destino."""
    df = df.copy()
    for nombre, (lat, lon) in LUGARES[destino].items():
        df[f"dist::{nombre}"] = haversine_km(df["latitude"], df["longitude"], lat, lon)
    return df


def cercanias(fila, destino: str, n: int = 2) -> list[dict]:
    """Los n puntos de interés más cercanos (sin contar el aeropuerto) + la distancia al aeropuerto."""
    lat, lon = float(fila["latitude"]), float(fila["longitude"])
    aeropuerto = AEROPUERTOS[destino]
    dist = {nombre: float(haversine_km(lat, lon, *coords)) for nombre, coords in LUGARES[destino].items()}
    cercanos = sorted((k for k in dist if k != aeropuerto), key=dist.get)[:n] + [aeropuerto]
    return [{"lugar": k, "km": round(dist[k], 2), "texto": texto_distancia(dist[k], destino)} for k in cercanos]
