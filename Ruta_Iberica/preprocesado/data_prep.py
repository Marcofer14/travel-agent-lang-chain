"""Construye el catálogo curado de alojamientos (pool) a partir de los CSV crudos de Inside Airbnb.

Uso:  python preprocesado/data_prep.py      (requiere haber corrido preprocesado/download_data.py)

Salidas en app/data/processed/ (lo único que necesita la app):
- pool.parquet          alojamientos activos seleccionados por destino
- calendar_pool.parquet disponibilidad diaria de los alojamientos del pool
- reviews_pool.parquet  últimas reseñas de cada alojamiento del pool (entrada del batch NLP)
- reviews_qa.parquet    hasta 40 reseñas por alojamiento (base de la tool "preguntale a las reseñas")
- price_ref.parquet     precio mediano por destino, barrio y capacidad (referencia de relación precio/calidad)
"""
import numpy as np
import pandas as pd

from _rutas import PROCESSED, RAW

CIUDADES = ["barcelona", "madrid", "mallorca"]
POOL_POR_CIUDAD = 500
RESENAS_POR_ALOJAMIENTO = 8
RESENAS_QA = 40
MAX_CHARS_QA = 600
MAX_CHARS_RESENA = 300
FECHA_ACTIVIDAD = "2026-01-01"
SEED = 42

COLUMNAS = [
    "id", "name", "listing_url", "picture_url", "neighbourhood_cleansed", "neighbourhood_group_cleansed",
    "latitude", "longitude", "property_type", "room_type", "accommodates", "bedrooms", "beds",
    "bathrooms_text", "amenities", "price", "minimum_nights", "number_of_reviews", "number_of_reviews_ltm",
    "last_review", "review_scores_rating", "review_scores_accuracy", "review_scores_cleanliness",
    "review_scores_checkin", "review_scores_communication", "review_scores_location", "review_scores_value",
    "host_name", "host_is_superhost", "instant_bookable", "description",
]


def bucket_capacidad(n: pd.Series) -> pd.Series:
    return pd.cut(n, bins=[0, 2, 4, 6, 100], labels=["1-2", "3-4", "5-6", "7+"])


def cargar_listings(ciudad: str) -> pd.DataFrame:
    df = pd.read_csv(RAW / f"{ciudad}_listings.csv.gz", usecols=COLUMNAS)
    df["price"] = pd.to_numeric(df["price"].astype(str).str.replace(r"[$,€]", "", regex=True), errors="coerce")
    df["last_review"] = pd.to_datetime(df["last_review"])
    df["destino"] = ciudad
    df["barrio"] = df["neighbourhood_cleansed"]
    df["cap_bucket"] = bucket_capacidad(df["accommodates"])
    return df


def filtrar_activos(df: pd.DataFrame) -> pd.DataFrame:
    """Alojamientos con actividad reciente, precio publicado y suficientes reseñas para analizarlas."""
    p99 = df["price"].quantile(0.99)
    return df[
        (df["number_of_reviews"] >= 15)
        & (df["last_review"] >= FECHA_ACTIVIDAD)
        & df["price"].between(30, p99)
        & df["review_scores_rating"].notna()
        & (df["room_type"] != "Shared room")
    ]


def muestrear_pool(activos: pd.DataFrame, n: int) -> pd.DataFrame:
    """Muestra estratificada por capacidad y quintil de precio para cubrir todo tipo de viaje."""
    activos = activos.copy()
    activos["price_q"] = pd.qcut(activos["price"], 5, labels=False, duplicates="drop")
    por_celda = int(np.ceil(n / (activos["cap_bucket"].nunique() * activos["price_q"].nunique())))
    muestra = (
        activos.sample(frac=1, random_state=SEED)
        .groupby(["cap_bucket", "price_q"], observed=True).head(por_celda)
    )
    if len(muestra) < n:  # completar celdas vacías (p. ej. pocos monoambientes en Mallorca)
        resto = activos.drop(muestra.index)
        muestra = pd.concat([muestra, resto.sample(min(len(resto), n - len(muestra)), random_state=SEED)])
    return muestra.sample(min(n, len(muestra)), random_state=SEED).drop(columns="price_q")


def construir() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    pools, refs, calendarios, resenas, resenas_qa = [], [], [], [], []
    for ciudad in CIUDADES:
        listings = cargar_listings(ciudad)
        activos = filtrar_activos(listings)
        refs.append(
            activos.groupby(["destino", "barrio", "cap_bucket"], observed=True)["price"]
            .agg(precio_mediano="median", n="size").reset_index()
        )
        pool = muestrear_pool(activos, POOL_POR_CIUDAD)
        pools.append(pool)
        ids = set(pool["id"])

        cal = pd.read_csv(RAW / f"{ciudad}_calendar.csv.gz", usecols=["listing_id", "date", "available", "minimum_nights"])
        cal = cal[cal["listing_id"].isin(ids)]
        cal["available"] = cal["available"].eq("t")
        calendarios.append(cal)

        rev = pd.read_csv(RAW / f"{ciudad}_reviews.csv.gz", usecols=["listing_id", "id", "date", "comments"])
        rev = rev[rev["listing_id"].isin(ids)].dropna(subset=["comments"])
        rev["comments"] = (
            rev["comments"].str.replace(r"<br\s*/?>", " ", regex=True).str.replace(r"\s+", " ", regex=True).str.strip()
        )
        rev = rev[rev["comments"].str.len() >= 20].sort_values("date").rename(columns={"id": "review_id"})
        qa = rev.groupby("listing_id").tail(RESENAS_QA)
        resenas_qa.append(qa.assign(comments=qa["comments"].str[:MAX_CHARS_QA]))
        ultimas = rev.groupby("listing_id").tail(RESENAS_POR_ALOJAMIENTO)
        resenas.append(ultimas.assign(comments=ultimas["comments"].str[:MAX_CHARS_RESENA]))
        print(f"{ciudad}: {len(listings)} listings → {len(activos)} activos → pool {len(pool)}")

    pool = pd.concat(pools, ignore_index=True)
    pool["cap_bucket"] = pool["cap_bucket"].astype(str)
    pool.to_parquet(PROCESSED / "pool.parquet", index=False)
    ref = pd.concat(refs, ignore_index=True)
    ref["cap_bucket"] = ref["cap_bucket"].astype(str)
    ref.to_parquet(PROCESSED / "price_ref.parquet", index=False)
    pd.concat(calendarios, ignore_index=True).to_parquet(PROCESSED / "calendar_pool.parquet", index=False)
    pd.concat(resenas, ignore_index=True).to_parquet(PROCESSED / "reviews_pool.parquet", index=False)
    pd.concat(resenas_qa, ignore_index=True).to_parquet(PROCESSED / "reviews_qa.parquet", index=False)
    print("Archivos generados en", PROCESSED)


if __name__ == "__main__":
    construir()
