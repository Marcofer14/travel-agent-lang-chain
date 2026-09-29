"""Actividades y lugares reales (OpenStreetMap) y perfiles de viajero."""
import json
from functools import lru_cache

import pandas as pd

from core import lugares
from core.config import PROCESSED

CATEGORIAS = {
    "museo": "🖼️ Museo", "galeria": "🎨 Galería", "teatro": "🎭 Teatro / artes escénicas",
    "monumento": "🏛️ Monumento", "mirador": "🌄 Mirador", "restaurante": "🍽️ Restaurante",
    "mercado": "🧺 Mercado", "playa": "🏖️ Playa", "parque": "🌳 Parque", "vida_nocturna": "🌙 Bar / vida nocturna",
    "familiar": "🎡 Plan familiar", "alquiler_auto": "🚗 Alquiler de autos", "otra": "📍 Actividad libre",
}

# Perfil → pesos por categoría (qué le interesa a cada tipo de viajero)
PERFILES = {
    "playero": {"nombre": "🏖️ Playero", "descripcion": "sol, mar, calas y chiringuitos",
                "categorias": {"playa": 3, "mirador": 1.5, "restaurante": 1, "vida_nocturna": 1}},
    "museos": {"nombre": "🖼️ Fan de los museos", "descripcion": "grandes museos, colecciones y galerías",
               "categorias": {"museo": 3, "galeria": 2, "monumento": 1}},
    "foodie": {"nombre": "🍷 Foodie", "descripcion": "mercados, tapas y cocina local",
               "categorias": {"restaurante": 3, "mercado": 3, "vida_nocturna": 1}},
    "cultural": {"nombre": "🎭 Cultural", "descripcion": "teatro, patrimonio y arte",
                 "categorias": {"teatro": 3, "monumento": 2.5, "museo": 1.5, "galeria": 1}},
    "caminador": {"nombre": "🚶 Caminador", "descripcion": "parques, miradores y recorridos a pie",
                  "categorias": {"parque": 3, "mirador": 2.5, "monumento": 1.5, "playa": 1}},
    "familiar": {"nombre": "👨‍👩‍👧 Familiar", "descripcion": "planes para chicos y grandes",
                 "categorias": {"familiar": 3, "parque": 2, "playa": 1.5, "museo": 1}},
    "nocturno": {"nombre": "🌙 Noctámbulo", "descripcion": "bares, música y vida nocturna",
                 "categorias": {"vida_nocturna": 3, "restaurante": 1.5, "teatro": 1}},
    "generalista": {"nombre": "🌍 Generalista", "descripcion": "un poco de todo, lo imperdible",
                    "categorias": {"monumento": 2, "museo": 1.5, "restaurante": 1, "parque": 1, "playa": 1,
                                   "mirador": 1, "mercado": 1}},
}


@lru_cache(maxsize=1)
def catalogo() -> pd.DataFrame:
    ruta = PROCESSED / "actividades.parquet"
    return pd.read_parquet(ruta) if ruta.exists() else pd.DataFrame(columns=["destino", "categoria", "nombre"])


@lru_cache(maxsize=1)
def recomendaciones_pregeneradas() -> dict:
    ruta = PROCESSED / "recomendaciones.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}


def normalizar_perfil(texto: str | None) -> str | None:
    if not texto:
        return None
    t = lugares._normalizar(texto)
    for clave, p in PERFILES.items():
        if clave in t or lugares._normalizar(p["nombre"]).split(" ", 1)[-1] in t:
            return clave
    sinonimos = {"playa": "playero", "museo": "museos", "comida": "foodie", "gastr": "foodie", "teatro": "cultural",
                 "camin": "caminador", "senderis": "caminador", "chicos": "familiar", "nin": "familiar",
                 "fiesta": "nocturno", "noche": "nocturno", "general": "generalista", "todo": "generalista"}
    return next((p for s, p in sinonimos.items() if s in t), None)


def buscar(destino: str, categoria: str | None = None, perfil: str | None = None, cerca_de: str | None = None,
           texto: str | None = None, n: int = 8) -> pd.DataFrame:
    """Filtra lugares reales por destino, categoría o perfil, texto (nombre/cocina) y cercanía a un punto de interés."""
    df = catalogo()
    df = df[df["destino"] == destino].copy()
    if categoria:
        df = df[df["categoria"] == categoria]
    if texto:
        t = texto.lower()
        mask = df["nombre"].str.lower().str.contains(t, regex=False) | df["cocina"].fillna("").str.lower().str.contains(t, regex=False)
        if mask.any():
            df = df[mask]
    df["score"] = df["relevancia"]
    if perfil in PERFILES and not categoria:
        pesos = PERFILES[perfil]["categorias"]
        df = df[df["categoria"].isin(pesos)]
        df["score"] = df["relevancia"] * df["categoria"].map(pesos)
    lugar = lugares.buscar_lugar(destino, cerca_de) if cerca_de else None
    if lugar:
        lat, lon = lugares.LUGARES[destino][lugar]
        df["dist_km"] = lugares.haversine_km(df["latitude"], df["longitude"], lat, lon)
        df["score"] = df["score"] / (1 + df["dist_km"])
    if perfil in PERFILES and not categoria:  # variedad: no más de 3 por categoría
        df = df.sort_values("score", ascending=False).groupby("categoria").head(3)
    return df.sort_values("score", ascending=False).head(n)


def encontrar(destino: str, nombre: str) -> pd.Series | None:
    """Busca un lugar por nombre (exacto, contenido o por palabras en común)."""
    df = catalogo()
    df = df[df["destino"] == destino]
    if df.empty or not nombre:
        return None
    objetivo = lugares._normalizar(nombre)
    normal = df["nombre"].map(lugares._normalizar)
    exacto = df[normal == objetivo]
    if not exacto.empty:
        return exacto.iloc[0]
    contiene = df[normal.str.contains(objetivo, regex=False) | normal.map(lambda n: n in objetivo)]
    if not contiene.empty:
        return contiene.sort_values("relevancia", ascending=False).iloc[0]
    palabras = lugares._palabras(nombre) - {"mercado", "mercat", "restaurante", "restaurant", "teatro", "bar", "cafe"}
    comunes = normal.map(lambda n: palabras & lugares._palabras(n))
    cantidad = comunes.map(len)
    if cantidad.max() >= 2:
        return df.loc[cantidad.idxmax()]
    # una sola palabra en común alcanza si es distintiva (≥ 6 letras) y apunta a un único lugar: "La Boqueria"
    unicos = cantidad[(cantidad == 1) & comunes.map(lambda c: any(len(w) >= 6 for w in c))]
    return df.loc[unicos.index[0]] if len(unicos) == 1 else None


def ficha(fila) -> dict:
    """Datos de un lugar listos para la interfaz y el PDF."""
    def v(c):
        x = fila.get(c)
        if hasattr(x, "item"):  # numpy → tipo nativo (la memoria del agente serializa con msgpack)
            x = x.item()
        return None if x is None or (isinstance(x, float) and pd.isna(x)) else x
    return {"osm_id": v("osm_id"), "destino": v("destino"), "categoria": v("categoria"),
            "tipo": CATEGORIAS.get(v("categoria"), "📍"), "nombre": v("nombre"), "direccion": v("direccion"),
            "horario": v("horario"), "web": v("web"), "telefono": v("telefono"), "cocina": v("cocina"),
            "latitude": v("latitude"), "longitude": v("longitude"),
            "osm_url": f"https://www.openstreetmap.org/{ {'n': 'node', 'w': 'way', 'r': 'relation'}[fila['osm_id'][0]] }/{fila['osm_id'][1:]}"
            if v("osm_id") else None,
            "dist_km": round(float(fila["dist_km"]), 2) if v("dist_km") is not None else None}
