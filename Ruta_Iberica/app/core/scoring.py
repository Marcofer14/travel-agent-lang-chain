"""Puntaje propio (1-10) y selección de las 4 opciones por destino."""
from datetime import date
from functools import lru_cache

import numpy as np
import pandas as pd

from core.config import DESTINOS, PROCESSED
from core.nlp import cargar_enriquecido

PESOS = {"calidad": 0.30, "resenas_nlp": 0.30, "precio_calidad": 0.20, "ubicacion": 0.10, "ajuste_capacidad": 0.10}
M_BAYES = 20  # reseñas "virtuales" con el promedio del destino: evita que 5.0 con pocas reseñas gane


@lru_cache(maxsize=1)
def datos() -> dict[str, pd.DataFrame]:
    pool = pd.read_parquet(PROCESSED / "pool.parquet")
    cal = pd.read_parquet(PROCESSED / "calendar_pool.parquet")
    cal["date"] = pd.to_datetime(cal["date"])
    ref = pd.read_parquet(PROCESSED / "price_ref.parquet")
    nlp = cargar_enriquecido()
    pool = pool.merge(nlp, left_on="id", right_on="listing_id", how="left")
    return {"pool": _puntajes_base(pool, ref), "cal": cal}


def recargar() -> None:
    datos.cache_clear()


def _clip01(x):
    return np.clip(x, 0, 1)


def _puntajes_base(pool: pd.DataFrame, ref: pd.DataFrame) -> pd.DataFrame:
    """Componentes que no dependen del pedido del usuario."""
    df = pool.copy()
    media_destino = df.groupby("destino")["review_scores_rating"].transform("mean")
    v = df["number_of_reviews"]
    df["rating_bayes"] = (v * df["review_scores_rating"] + M_BAYES * media_destino) / (v + M_BAYES)
    df["c_calidad"] = _clip01((df["rating_bayes"] - 4.0) / 1.0)

    aspectos = ["puntaje_limpieza", "puntaje_ubicacion", "puntaje_tranquilidad", "puntaje_anfitrion", "puntaje_fidelidad"]
    for a in aspectos:
        if a not in df:
            df[a] = np.nan
    sentimiento = df.get("sentimiento_general", pd.Series(index=df.index, dtype=object)).map(
        {"muy positivo": 1.0, "positivo": 0.8, "mixto": 0.45, "negativo": 0.1}
    )
    promedio_aspectos = df[aspectos].mean(axis=1) / 10
    # Sin análisis NLP disponible se usan las subcategorías numéricas de Airbnb como respaldo.
    respaldo = df[["review_scores_cleanliness", "review_scores_communication", "review_scores_accuracy"]].mean(axis=1) / 5
    df["c_resenas_nlp"] = (0.6 * promedio_aspectos + 0.4 * sentimiento).fillna(respaldo)
    df["c_resenas_nlp"] = df["c_resenas_nlp"] - np.where(df.get("alerta").notna() if "alerta" in df else False, 0.25, 0)
    df["c_resenas_nlp"] = _clip01(df["c_resenas_nlp"])
    df["tiene_nlp"] = df["sentimiento_general"].notna() if "sentimiento_general" in df else False

    df = df.merge(ref[["destino", "barrio", "cap_bucket", "precio_mediano"]], on=["destino", "barrio", "cap_bucket"], how="left")
    por_capacidad = ref.groupby(["destino", "cap_bucket"])["precio_mediano"].median().rename("mediana_cap")
    df = df.join(por_capacidad, on=["destino", "cap_bucket"])
    df["precio_ref"] = df["precio_mediano"].fillna(df["mediana_cap"])
    ratio = df["price"] / df["precio_ref"]
    # Relación precio/calidad: barato respecto de su zona y con buen rating puntúa alto.
    df["c_precio_calidad"] = _clip01(1 - (ratio - 0.5) / 1.5) * (0.5 + 0.5 * df["c_calidad"])

    ubic_nlp = df["puntaje_ubicacion"] / 10
    ubic_airbnb = _clip01((df["review_scores_location"] - 4.0) / 1.0)
    df["c_ubicacion"] = ubic_airbnb.where(ubic_nlp.isna(), 0.5 * ubic_airbnb + 0.5 * ubic_nlp).fillna(0.5)
    return df


def _ajuste_capacidad(capacidad: pd.Series, huespedes: int) -> pd.Series:
    exceso = capacidad - huespedes
    return _clip01(1 - 0.2 * (exceso - 1).clip(lower=0))


def normalizar_pesos(pesos: dict | None) -> dict:
    """Acepta pesos en cualquier escala (p. ej. sliders 0-10) y los lleva a suma 1."""
    pesos = {k: float((pesos or {}).get(k, v)) for k, v in PESOS.items()}
    total = sum(pesos.values())
    return {k: v / total for k, v in pesos.items()} if total > 0 else dict(PESOS)


def puntuar(df: pd.DataFrame, huespedes: int, pesos: dict | None = None) -> pd.DataFrame:
    df = df.copy()
    pesos = normalizar_pesos(pesos)
    df["c_ajuste_capacidad"] = _ajuste_capacidad(df["accommodates"], huespedes)
    total = sum(pesos[k] * df[f"c_{k}"] for k in PESOS)
    df["puntaje"] = (1 + 9 * total).round(1)
    df["rating_airbnb_10"] = (df["review_scores_rating"] * 2).round(1)
    return df


def disponibles(destino: str, check_in: str, check_out: str) -> set[int]:
    """IDs disponibles todas las noches del rango y cuya estadía mínima permite la reserva."""
    cal = datos()["cal"]
    ini, fin = pd.Timestamp(check_in), pd.Timestamp(check_out)
    noches = (fin - ini).days
    ids_destino = set(datos()["pool"].query("destino == @destino")["id"])
    rango = cal[cal["listing_id"].isin(ids_destino) & (cal["date"] >= ini) & (cal["date"] < fin)]
    completos = rango.groupby("listing_id").agg(n=("available", "size"), libres=("available", "sum"))
    ok = completos[(completos["n"] == noches) & (completos["libres"] == noches)].index
    minimo = cal[(cal["date"] == ini) & cal["listing_id"].isin(ok)].set_index("listing_id")["minimum_nights"]
    return set(minimo[minimo <= noches].index)


def candidatos(destino: str, check_in: str, check_out: str, huespedes: int,
               presupuesto_max_noche: float | None = None, pesos: dict | None = None) -> pd.DataFrame:
    destino = destino.lower().strip()
    if destino not in DESTINOS:
        raise ValueError(f"Destino '{destino}' no disponible. Opciones: {', '.join(DESTINOS)}")
    if date.fromisoformat(check_out) <= date.fromisoformat(check_in):
        raise ValueError("La fecha de salida debe ser posterior a la de entrada.")
    pool = datos()["pool"]
    df = pool[(pool["destino"] == destino) & (pool["accommodates"] >= huespedes)]
    df = df[df["id"].isin(disponibles(destino, check_in, check_out))]
    if presupuesto_max_noche:
        df = df[df["price"] <= presupuesto_max_noche]
    return puntuar(df, huespedes, pesos)


def elegir_cuatro(df: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    """Recomendada por el modelo, mejor rateada, más barata y más cara (siempre alojamientos distintos)."""
    elegidos, usados = [], set()
    # Evita proponer, por ejemplo, una casa para 15 personas a un grupo de 3 (hasta 3 plazas de más).
    razonables = df[df["c_ajuste_capacidad"] >= 0.6]
    if len(razonables) >= 4:
        df = razonables

    def tomar(etiqueta, ordenado):
        for _, fila in ordenado.iterrows():
            if fila["id"] not in usados:
                usados.add(fila["id"])
                elegidos.append((etiqueta, fila))
                return

    tomar("recomendada", df.sort_values(["puntaje", "number_of_reviews"], ascending=False))
    tomar("mejor_rateada", df.sort_values(["rating_bayes", "number_of_reviews"], ascending=False))
    tomar("mas_barata", df.sort_values("price"))
    tomar("mas_cara", df.sort_values("price", ascending=False))
    return elegidos


def detalle_puntaje(fila: pd.Series) -> dict:
    return {k: round(float(fila[f"c_{k}"]) * 10, 1) for k in PESOS}
