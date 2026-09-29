"""Descarga lugares y actividades reales de OpenStreetMap (API Overpass, pública y gratuita) para los tres destinos.

Uso:  python preprocesado/descargar_actividades.py
Salida: app/data/processed/actividades.parquet  (museos, teatros, restaurantes, playas, parques, alquiler de autos...)
Fuente: © colaboradores de OpenStreetMap, licencia ODbL.
"""
import re
import time

import numpy as np
import pandas as pd
import requests

from _rutas import PROCESSED

ESPEJOS = ["https://overpass-api.de/api/interpreter",
           "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
           "https://overpass.private.coffee/api/interpreter"]

# (sur, oeste, norte, este)
BBOX = {
    "barcelona": (41.32, 2.05, 41.47, 2.23),
    "madrid": (40.36, -3.80, 40.50, -3.58),
    "mallorca": (39.25, 2.30, 39.97, 3.48),
}

# categoría → (filtros Overpass, máximo a conservar por destino)
CATEGORIAS = {
    "alquiler_auto": (['["amenity"="car_rental"]["name"]'], 40),
    "teatro": (['["amenity"~"^(theatre|arts_centre)$"]["name"]'], 50),
    "museo": (['["tourism"="museum"]["name"]'], 70),
    "galeria": (['["tourism"="gallery"]["name"]'], 30),
    "mirador": (['["tourism"="viewpoint"]["name"]'], 30),
    "familiar": (['["tourism"~"^(zoo|aquarium|theme_park)$"]["name"]', '["leisure"="water_park"]["name"]'], 25),
    "restaurante": (['["amenity"="restaurant"]["name"]["cuisine"]'], 150),
    "mercado": (['["amenity"="marketplace"]["name"]'], 25),
    "playa": (['["natural"="beach"]["name"]'], 60),
    "vida_nocturna": (['["amenity"~"^(nightclub|pub)$"]["name"]'], 40),
    "parque": (['["leisure"="park"]["name"]["wikidata"]'], 40),
    "monumento": (['["tourism"="attraction"]["wikidata"]', '["historic"~"castle|monument|cathedral|palace"]["wikidata"]'], 70),
}


def clasificar(tags: dict) -> str | None:
    """Asigna la categoría de un elemento OSM (el orden importa: lo más específico primero)."""
    t, a, h = tags.get("tourism"), tags.get("amenity"), tags.get("historic")
    if a == "car_rental":
        return "alquiler_auto"
    if a in ("theatre", "arts_centre"):
        return "teatro"
    if t == "museum":
        return "museo"
    if t == "gallery":
        return "galeria"
    if t == "viewpoint":
        return "mirador"
    if t in ("zoo", "aquarium", "theme_park") or tags.get("leisure") == "water_park":
        return "familiar"
    if a == "restaurant":
        return "restaurante"
    if a == "marketplace":
        return "mercado"
    if tags.get("natural") == "beach":
        return "playa"
    if a in ("nightclub", "pub"):
        return "vida_nocturna"
    if tags.get("leisure") == "park":
        return "parque"
    if t == "attraction" or h:
        return "monumento"
    return None


def consultar(filtros: list[str], bbox: tuple) -> list[dict]:
    caja = ",".join(map(str, bbox))
    cuerpo = "".join(f"nwr{f}({caja});" for f in filtros)
    query = f"[out:json][timeout:180];({cuerpo});out center tags;"
    for intento in range(6):
        url = ESPEJOS[intento % len(ESPEJOS)]
        try:
            r = requests.post(url, data={"data": query}, timeout=240,
                              headers={"User-Agent": "RutaIberica/1.0 (proyecto academico NLP)"})
            if r.status_code == 200:
                return r.json()["elements"]
            print(f"    {url} → HTTP {r.status_code}, reintento")
        except Exception as e:
            print(f"    {url} → {type(e).__name__}, reintento")
        time.sleep(5 * (intento + 1))
    raise RuntimeError("Overpass no respondió después de 6 intentos")


def a_fila(elemento: dict, destino: str, categoria: str) -> dict | None:
    tags = elemento.get("tags", {})
    nombre = tags.get("name:es") or tags.get("name")
    lat = elemento.get("lat") or elemento.get("center", {}).get("lat")
    lon = elemento.get("lon") or elemento.get("center", {}).get("lon")
    if not nombre or lat is None:
        return None
    calle = " ".join(filter(None, [tags.get("addr:street"), tags.get("addr:housenumber")]))
    return {
        "osm_id": f"{elemento['type'][0]}{elemento['id']}", "destino": destino, "categoria": categoria,
        "nombre": nombre, "latitude": lat, "longitude": lon,
        "direccion": ", ".join(filter(None, [calle, tags.get("addr:city")])) or None,
        "horario": tags.get("opening_hours"), "web": tags.get("website") or tags.get("contact:website"),
        "telefono": tags.get("phone") or tags.get("contact:phone"), "cocina": tags.get("cuisine"),
        "wikidata": tags.get("wikidata"), "wikipedia": tags.get("wikipedia"),
        "tipo_osm": tags.get("tourism") or tags.get("amenity") or tags.get("historic") or tags.get("natural")
                    or tags.get("leisure"),
    }


def popularidad_wikidata(ids: list[str]) -> dict[str, int]:
    """Cantidad de Wikipedias que tienen artículo del lugar (proxy de popularidad), vía la API pública de Wikidata."""
    salida = {}
    ids = sorted({i for i in ids if isinstance(i, str) and re.fullmatch(r"Q\d+", i)})
    for n in range(0, len(ids), 50):
        for intento in range(3):
            try:
                r = requests.get("https://www.wikidata.org/w/api.php", timeout=60,
                                 params={"action": "wbgetentities", "ids": "|".join(ids[n:n + 50]),
                                         "props": "sitelinks", "format": "json"},
                                 headers={"User-Agent": "RutaIberica/1.0 (proyecto academico NLP)"})
                for qid, ent in r.json().get("entities", {}).items():
                    salida[qid] = len(ent.get("sitelinks", {}))
                break
            except Exception:
                time.sleep(3 * (intento + 1))
        time.sleep(0.5)
    return salida


def relevancia(df: pd.DataFrame) -> pd.Series:
    """Lugares populares (Wikipedias) y bien documentados en OSM primero."""
    base = (3 * df["wikidata"].notna() + 2 * df["wikipedia"].notna() + df["web"].notna()
            + df["horario"].notna() + 0.5 * df["direccion"].notna() + 0.5 * df["cocina"].notna())
    if "wikipedias" in df:
        base = base + 2.5 * np.log1p(df["wikipedias"].fillna(0))
    return base


def agregar_popularidad(df: pd.DataFrame) -> pd.DataFrame:
    pop = popularidad_wikidata(df["wikidata"].dropna().tolist())
    df = df.assign(wikipedias=df["wikidata"].map(pop).fillna(0).astype(int))
    return df.assign(relevancia=relevancia(df))


def descargar() -> pd.DataFrame:
    """Una sola consulta por destino con todos los filtros (3 pedidos en total: amable con la API pública)."""
    filtros = [f for fs, _ in CATEGORIAS.values() for f in fs]
    partes = []
    for destino, bbox in BBOX.items():
        elementos = consultar(filtros, bbox)
        filas = [f for e in elementos if (cat := clasificar(e.get("tags", {}))) and (f := a_fila(e, destino, cat))]
        df = agregar_popularidad(pd.DataFrame(filas).drop_duplicates(["categoria", "nombre"]))
        for categoria, (_, maximo) in CATEGORIAS.items():
            sub = df[df["categoria"] == categoria].sort_values("relevancia", ascending=False).head(maximo)
            partes.append(sub)
            print(f"  {destino:9} {categoria:14} {int((df['categoria'] == categoria).sum()):5} → {len(sub)}")
        time.sleep(3)
    total = pd.concat(partes, ignore_index=True).drop_duplicates(["destino", "nombre"])
    total.to_parquet(PROCESSED / "actividades.parquet", index=False)
    print(f"Guardado: {len(total)} lugares → {PROCESSED / 'actividades.parquet'}")
    return total


if __name__ == "__main__":
    descargar()
