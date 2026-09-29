"""Corre el batch NLP sobre el catálogo en tandas, priorizando los alojamientos con más chances de mostrarse.

Uso:  python preprocesado/enrich_runner.py --limite 150 --modelo openai/gpt-oss-20b
Cada modelo de Groq tiene su propia cuota diaria gratuita: se puede repartir el trabajo entre modelos.
"""
import argparse
import time

import pandas as pd
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_groq import ChatGroq

import _rutas  # noqa: F401  (agrega app/ al path)
from core import scoring
from core.config import PROCESSED, asegurar_api_key
from core.metrics import MetricsTracker
from core.nlp import cargar_enriquecido, enriquecer, guardar_enriquecido, preparar_entradas


def prioridad(pool: pd.DataFrame) -> pd.DataFrame:
    """Ranking dentro de cada destino y capacidad: extremos de precio, mejor rating y mejor puntaje preliminar."""
    g = pool.groupby(["destino", "cap_bucket"])
    rangos = pd.concat([
        g["price"].rank(method="first"),
        g["price"].rank(method="first", ascending=False),
        g["rating_bayes"].rank(method="first", ascending=False),
        g["c_precio_calidad"].rank(method="first", ascending=False),
    ], axis=1)
    return pool.assign(prioridad=rangos.min(axis=1)).sort_values(["prioridad", "destino"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limite", type=int, default=100)
    parser.add_argument("--modelo", default="openai/gpt-oss-20b")
    parser.add_argument("--rps", type=float, default=0.1, help="requests por segundo (8K tokens/min en free tier)")
    args = parser.parse_args()
    asegurar_api_key()

    pool = prioridad(scoring.datos()["pool"])
    hechos = set(cargar_enriquecido()["listing_id"])
    pendientes = pool[~pool["id"].isin(hechos)].head(args.limite)
    resenas = pd.read_parquet(PROCESSED / "reviews_pool.parquet")
    entradas = preparar_entradas(pendientes, resenas[resenas["listing_id"].isin(pendientes["id"])])
    print(f"Pendientes totales: {len(pool) - len(hechos)} · esta tanda: {len(entradas)} con {args.modelo}")

    extra = {"reasoning_effort": "low"} if "gpt-oss" in args.modelo else {}
    llm = ChatGroq(model=args.modelo, temperature=0, max_tokens=900, max_retries=8, **extra,
                   rate_limiter=InMemoryRateLimiter(requests_per_second=args.rps, max_bucket_size=1))
    tracker = MetricsTracker()
    for i in range(0, len(entradas), 20):  # guarda cada 20 para no perder avance si se corta la cuota
        t0 = time.perf_counter()
        df = enriquecer(entradas[i:i + 20], callbacks=[tracker], max_concurrency=2, llm=llm)
        total = guardar_enriquecido(df)
        errores = int(df["error"].notna().sum()) if "error" in df else 0
        print(f"  tanda {i // 20 + 1}: {len(df) - errores} ok, {errores} errores, {time.perf_counter() - t0:.0f}s "
              f"· acumulado {len(total)} analizados")
        if errores == len(df):
            print("  Todas fallaron (¿cuota diaria agotada?). Corto acá.")
            break
    print(tracker.resumen(n_unidades=len(entradas)))


if __name__ == "__main__":
    main()
