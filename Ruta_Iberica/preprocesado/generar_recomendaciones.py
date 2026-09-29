"""Genera recomendaciones pregeneradas por perfil de viajero y destino (LCEL + Pydantic + .batch()).

Uso:  python preprocesado/generar_recomendaciones.py
Salida: app/data/processed/recomendaciones.json

Cada recomendación se ancla en datos reales: los lugares candidatos salen de OpenStreetMap (actividades.parquet)
y los barrios del catálogo de Inside Airbnb. Lo que el LLM nombre fuera de la lista se descarta (anti-alucinación).
"""
import json
import time

import pandas as pd
from langchain_core.prompts import ChatPromptTemplate

import _rutas  # noqa: F401  (agrega app/ al path)
from core.actividades import CATEGORIAS, PERFILES, buscar, encontrar
from core.config import DESTINOS, PROCESSED, asegurar_api_key
from core.metrics import MetricsTracker
from core.nlp import estructurado
from core.schemas import RecomendacionPerfil

PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Sos un curador de viajes. Armás una guía breve para un perfil de viajero en un destino.\n"
     "Reglas estrictas:\n"
     "- Los imperdibles deben ser nombres EXACTOS de la lista de lugares candidatos. No agregues otros.\n"
     "- Los barrios sugeridos deben salir de la lista de barrios provista.\n"
     "- No inventes precios, horarios ni datos que no estén en la lista.\n"
     "- Si en la lista NO hay lugares del tipo ideal para el perfil (p. ej. no hay playas porque la ciudad no tiene "
     "mar), decilo con honestidad en el titular y los consejos, y elegí las mejores alternativas QUE SÍ están en la "
     "lista. Nunca menciones mar, playas u otros lugares que no aparezcan.\n"
     "- Escribí en español neutro latinoamericano, tono cálido y concreto."),
    ("human",
     "Destino: {destino}\nPerfil: {perfil} ({descripcion})\n\n"
     "Lugares candidatos (categoría · nombre · datos):\n{candidatos}\n\n"
     "Barrios con mejores alojamientos (barrio · rating medio /10 · precio mediano €/noche):\n{barrios}"),
])


def entradas() -> list[dict]:
    pool = pd.read_parquet(PROCESSED / "pool.parquet")
    salida = []
    for destino, info in DESTINOS.items():
        barrios = (pool[pool["destino"] == destino].groupby("barrio")
                   .agg(n=("id", "size"), rating=("review_scores_rating", "mean"), precio=("price", "median"))
                   .query("n >= 8").sort_values("rating", ascending=False).head(8))
        texto_barrios = "\n".join(f"- {b} · {r.rating * 2:.1f} · {r.precio:.0f}" for b, r in barrios.iterrows())
        for clave, perfil in PERFILES.items():
            cands = buscar(destino, perfil=clave, n=18)
            texto = "\n".join(f"- {CATEGORIAS[c.categoria]} · {c.nombre}"
                              + (f" · cocina {c.cocina}" if isinstance(c.cocina, str) else "")
                              + (f" · {c.horario}" if isinstance(c.horario, str) else "")
                              for c in cands.itertuples())
            salida.append({"destino_clave": destino, "perfil_clave": clave, "destino": info["nombre"],
                           "perfil": perfil["nombre"], "descripcion": perfil["descripcion"],
                           "candidatos": texto, "barrios": texto_barrios,
                           "_nombres": set(cands["nombre"]), "_barrios": set(barrios.index)})
    return salida


def validar(imperdibles, d: dict) -> list:
    """Acepta solo lugares de la lista de candidatos (tolera prefijos como 'Mirador · ' o diferencias de tildes)."""
    validos = []
    for i in imperdibles:
        nombre = i.nombre.split("·")[-1].strip()
        if nombre not in d["_nombres"]:
            fila = encontrar(d["destino_clave"], nombre)
            nombre = fila["nombre"] if fila is not None and fila["nombre"] in d["_nombres"] else None
        if nombre and nombre not in {v.nombre for v in validos}:
            validos.append(i.model_copy(update={"nombre": nombre}))
    return validos


def main() -> None:
    """Incremental: conserva lo ya generado, reintenta cada caso y espacia las llamadas (cuota por minuto de Groq)."""
    asegurar_api_key()
    ruta = PROCESSED / "recomendaciones.json"
    salida = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    cadena = PROMPT | estructurado(RecomendacionPerfil)
    tracker, descartados = MetricsTracker(), 0
    pendientes = [d for d in entradas() if d["perfil_clave"] not in salida.get(d["destino_clave"], {})]
    print(f"Pendientes: {len(pendientes)} de 24")
    # .batch() en tandas chicas: paraleliza sin superar los 8K tokens/minuto del free tier
    for n in range(0, len(pendientes), 2):
        tanda = pendientes[n:n + 2]
        for intento in range(3):
            resultados = cadena.batch([{k: v for k, v in d.items() if not k.startswith("_")} for d in tanda],
                                      config={"max_concurrency": 2, "callbacks": [tracker]}, return_exceptions=True)
            fallidos = []
            for d, r in zip(tanda, resultados):
                if isinstance(r, Exception):
                    fallidos.append(d)
                    continue
                validos = validar(r.imperdibles, d)
                descartados += len(r.imperdibles) - len(validos)
                salida.setdefault(d["destino_clave"], {})[d["perfil_clave"]] = r.model_dump() | {
                    "imperdibles": [i.model_dump() for i in validos],
                    "barrios_sugeridos": [b for b in r.barrios_sugeridos if b in d["_barrios"]]}
                print(f"  ✔ {d['destino']:9} {d['perfil']:22} {len(validos)} imperdibles")
            ruta.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
            if not fallidos:
                break
            tanda = fallidos
            time.sleep(20 * (intento + 1))
        else:
            for d in tanda:
                print(f"  ✘ {d['destino']} / {d['perfil']}: sin respuesta válida tras 3 intentos")
        time.sleep(12)
    total = sum(len(v) for v in salida.values())
    print(f"Guías disponibles: {total} de 24 · lugares inventados descartados: {descartados}")
    print(tracker.resumen(n_unidades=max(len(pendientes), 1)))


if __name__ == "__main__":
    main()
