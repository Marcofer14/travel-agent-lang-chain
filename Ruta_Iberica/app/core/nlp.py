"""Cadenas LCEL: análisis multidimensional de reseñas (RunnableParallel + batch) e interpretación de pedidos."""
import re
from collections import Counter
from datetime import date

import pandas as pd
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_core.runnables import RunnableLambda, RunnableParallel, RunnablePassthrough
from langchain_groq import ChatGroq

from core.config import MODELO_AGENTE, MODELO_BATCH, PROCESSED
from core.schemas import AnalisisResenas, PalabrasClave, RespuestaResenas, SolicitudViaje

ENRIQUECIDO = PROCESSED / "reviews_enriched.parquet"

# El free tier de Groq permite 8K tokens/minuto por modelo: ~1K tokens por alojamiento → ~6 llamadas/min.
limitador_batch = InMemoryRateLimiter(requests_per_second=0.1, check_every_n_seconds=0.5, max_bucket_size=1)


def llm_batch() -> ChatGroq:
    return ChatGroq(model=MODELO_BATCH, temperature=0, reasoning_effort="low", max_retries=6,
                    rate_limiter=limitador_batch)


def llm_agente(**kwargs) -> ChatGroq:
    kwargs = {"max_retries": 4} | kwargs
    return ChatGroq(model=MODELO_AGENTE, temperature=0.2, reasoning_effort="low", **kwargs)


MODELO_RESPALDO = "qwen/qwen3.8-27b"


def estructurado(schema, llm=None, rate_limiter=None):
    """LLM con salida estructurada. Sin llm explícito arma una cascada de modelos gratuitos (cada uno con su propia
    cuota en Groq): si el primero agota su cuota por minuto o por día, la cadena sigue con el siguiente."""
    if llm is not None:
        return llm.with_structured_output(schema)
    modelos = [
        ChatGroq(model=MODELO_BATCH, temperature=0, reasoning_effort="low", max_retries=0, rate_limiter=rate_limiter),
        ChatGroq(model=MODELO_RESPALDO, temperature=0, max_tokens=900, max_retries=0),
        ChatGroq(model=MODELO_AGENTE, temperature=0, reasoning_effort="low", max_retries=2),
    ]
    principal, *respaldos = [m.with_structured_output(schema) for m in modelos]
    return principal.with_fallbacks(respaldos)


# ---------------------------------------------------------------- análisis de reseñas

PROMPT_RESENAS = ChatPromptTemplate.from_messages([
    ("system",
     "Sos un analista de hospitalidad. Recibís reseñas reales de huéspedes de un alojamiento de Airbnb "
     "en {destino}, escritas en distintos idiomas.\n"
     "Reglas:\n"
     "- Basate EXCLUSIVAMENTE en el texto de las reseñas; no inventes datos ni supongas.\n"
     "- Si un aspecto no se menciona, dejá su puntaje en null.\n"
     "- Los puntajes van de 1 a 10 con un decimal.\n"
     "- Pros, contras, alerta y resumen SIEMPRE en español neutro: traducí lo que esté en otros idiomas.\n"
     "- La cita_textual debe copiarse literal de alguna reseña, en su idioma original, máximo 25 palabras."),
    ("human", "Alojamiento: {nombre}\n\nReseñas:\n{resenas}"),
])

LEXICO = {
    "ruido": r"\b(ruid|noise|noisy|loud|laut|lärm|bruit|bruyant|rumor)",
    "transporte": r"\b(metro|subte|subway|u-bahn|bus|estaci|station|tren|train|tram)",
    "playa": r"\b(playa|platja|beach|strand|plage|spiaggia|mar |sea)",
    "limpieza": r"\b(limpi|clean|sauber|propre|pulit)",
    "suciedad": r"\b(suci|dirty|schmutz|sale |sporc)",
    "wifi": r"\b(wifi|wi-fi|internet)",
}
IDIOMAS = {
    "es": {"el", "la", "muy", "con", "que", "todo", "para", "piso", "estancia"},
    "en": {"the", "and", "was", "very", "great", "place", "stay", "with"},
    "de": {"und", "die", "der", "sehr", "war", "wir", "wohnung", "ist"},
    "fr": {"et", "très", "le", "les", "nous", "appartement", "était", "séjour"},
    "it": {"molto", "e", "il", "della", "casa", "appartamento", "ottimo", "tutto"},
    "ca": {"molt", "i", "amb", "pis", "tot", "estada", "gràcies"},
    "nl": {"en", "het", "een", "zeer", "was", "mooi", "fijn", "prima"},
    "sv": {"och", "mycket", "var", "vi", "boende", "fint", "bra"},
}


def detectar_idioma(texto: str) -> str:
    palabras = set(re.findall(r"\w+", texto.lower()))
    puntajes = {idioma: len(palabras & vocab) for idioma, vocab in IDIOMAS.items()}
    mejor = max(puntajes, key=puntajes.get)
    return mejor if puntajes[mejor] >= 2 else "otro"


def senales_lexicas(entrada: dict) -> dict:
    """Análisis sin LLM: menciones de temas clave por léxico multilingüe."""
    texto = entrada["resenas"].lower()
    return {tema: len(re.findall(patron, texto)) for tema, patron in LEXICO.items()}


def estadisticas(entrada: dict) -> dict:
    """Análisis sin LLM: idiomas y volumen del texto analizado."""
    lineas = [l for l in entrada["resenas"].split("\n") if l.strip()]
    idiomas = Counter(detectar_idioma(l) for l in lineas)
    return {"n_resenas": len(lineas), "idiomas": dict(idiomas), "caracteres": len(entrada["resenas"])}


def cadena_analisis(llm=None, limitar: bool = True):
    """RunnableParallel: tres análisis sobre la misma entrada (LLM estructurado + léxico + estadísticas)."""
    return RunnableParallel(
        nlp=PROMPT_RESENAS | estructurado(AnalisisResenas, llm, limitador_batch if limitar else None),
        senales=RunnableLambda(senales_lexicas),
        stats=RunnableLambda(estadisticas),
    )


def preparar_entradas(pool: pd.DataFrame, resenas: pd.DataFrame) -> list[dict]:
    agrupadas = resenas.groupby("listing_id")["comments"].apply(lambda s: "\n".join(f"- {c}" for c in s))
    return [
        {"listing_id": int(r.id), "destino": r.destino.title(), "nombre": r.name, "resenas": agrupadas.get(r.id, "")}
        for r in pool.itertuples()
        if r.id in agrupadas.index
    ]


def aplanar(entrada: dict, salida: dict | Exception) -> dict:
    fila = {"listing_id": entrada["listing_id"]}
    if isinstance(salida, Exception):
        return fila | {"error": str(salida)[:200]}
    nlp: AnalisisResenas = salida["nlp"]
    fila |= nlp.model_dump()
    fila |= {f"menciones_{k}": v for k, v in salida["senales"].items()}
    fila |= {"n_resenas": salida["stats"]["n_resenas"], "idiomas": salida["stats"]["idiomas"]}
    return fila


def enriquecer(entradas: list[dict], callbacks=None, max_concurrency: int = 2, llm=None,
               limitar: bool = True) -> pd.DataFrame:
    """Procesa con .batch() y devuelve un DataFrame enriquecido. Los errores quedan registrados, no cortan el batch."""
    cadena = cadena_analisis(llm, limitar)
    salidas = cadena.batch(
        entradas, config={"max_concurrency": max_concurrency, "callbacks": callbacks or []}, return_exceptions=True
    )
    return pd.DataFrame([aplanar(e, s) for e, s in zip(entradas, salidas)])


def cargar_enriquecido() -> pd.DataFrame:
    if ENRIQUECIDO.exists():
        return pd.read_parquet(ENRIQUECIDO)
    return pd.DataFrame(columns=["listing_id"])


def guardar_enriquecido(nuevo: pd.DataFrame) -> pd.DataFrame:
    """Acumula resultados (cache): permite correr el batch en tandas respetando la cuota diaria."""
    previo = cargar_enriquecido()
    ok = nuevo[nuevo.get("error").isna()] if "error" in nuevo else nuevo
    total = pd.concat([previo, ok], ignore_index=True).drop_duplicates("listing_id", keep="last")
    total["idiomas"] = total["idiomas"].astype(str)
    total.to_parquet(ENRIQUECIDO, index=False)
    return total


# ---------------------------------------------------------------- interpretación del pedido

PROMPT_SOLICITUD = ChatPromptTemplate.from_messages([
    ("system",
     "Convertís pedidos de viaje en datos estructurados. Hoy es {hoy}. Destinos válidos: barcelona, madrid, mallorca.\n"
     "- Si el usuario no indica el año, usá la próxima ocurrencia futura de esa fecha.\n"
     "- Si indica cantidad de noches en vez de fecha de salida, calculala.\n"
     "- Si los tramos son consecutivos, el check_out de uno es el check_in del siguiente.\n"
     "- No inventes presupuesto ni preferencias que el usuario no mencionó."),
    ("human", "{pedido}"),
])


def cadena_solicitud(llm=None):
    llm = llm or llm_agente()
    return (
        RunnableLambda(lambda pedido: {"pedido": pedido, "hoy": date.today().isoformat()})
        | PROMPT_SOLICITUD
        | llm.with_structured_output(SolicitudViaje)
    )


# ---------------------------------------------------------------- preguntas sobre las reseñas (RAG liviano)

PROMPT_PALABRAS = ChatPromptTemplate.from_messages([
    ("system", "Generás términos de búsqueda para encontrar reseñas de alojamientos que hablen de un tema. "
               "Usá raíces cortas que funcionen como subcadenas e incluí al menos 2 términos en cada idioma: "
               "español, inglés, francés, alemán e italiano (p. ej. 'limpi', 'clean', 'propre', 'sauber', 'pulit')."),
    ("human", "Pregunta del viajero: {pregunta}"),
])

PROMPT_RESPUESTA = ChatPromptTemplate.from_messages([
    ("system",
     "Respondés preguntas de viajeros sobre un alojamiento usando EXCLUSIVAMENTE las reseñas provistas.\n"
     "- El veredicto valora el ASPECTO consultado, no la pregunta: si elogian la limpieza es 'positivo' aunque "
     "pregunten '¿tiene problemas de limpieza?'; si se quejan del ruido es 'negativo'. Opiniones divididas → 'mixto'.\n"
     "- Si las reseñas no mencionan el tema, el veredicto es 'sin información' y lo decís claramente.\n"
     "- No generalices a partir de una sola reseña: indicá cuántas lo mencionan.\n"
     "- Las citas deben copiarse literalmente de las reseñas, con su fecha."),
    ("human", "Alojamiento: {nombre}\nPregunta: {pregunta}\n\n"
              "Reseñas relevantes ({n_relevantes} de {n_total} analizadas):\n{fragmentos}"),
])


def _recuperar(entrada: dict, k: int = 12) -> dict:
    """Recupera las reseñas con más coincidencias de palabras clave (si no hay, las más recientes)."""
    resenas: pd.DataFrame = entrada["resenas"]
    palabras = [p.lower().strip() for p in entrada["palabras"].palabras if len(p.strip()) >= 3]
    texto = resenas["comments"].str.lower()
    coincidencias = sum(texto.str.count(re.escape(p)) for p in palabras) if palabras else 0
    relevantes = resenas.assign(score=coincidencias).query("score > 0")
    elegidas = relevantes.sort_values(["score", "date"], ascending=False).head(k)
    if elegidas.empty:
        elegidas = resenas.sort_values("date", ascending=False).head(k)
    fragmentos = "\n".join(f"- [{r.date}] {r.comments}" for r in elegidas.itertuples())
    return {"fragmentos": fragmentos, "n_relevantes": len(relevantes), "n_total": len(resenas)}


def cadena_preguntas(llm=None):
    """LCEL: expandir la pregunta a palabras clave multilingües → recuperar reseñas → responder con evidencia."""
    expandir = PROMPT_PALABRAS | estructurado(PalabrasClave, llm)
    return (
        RunnablePassthrough.assign(palabras=expandir)
        | RunnablePassthrough.assign(recuperado=RunnableLambda(_recuperar))
        | RunnableLambda(lambda x: {**x, **x["recuperado"]})
        | RunnableParallel(
            respuesta=PROMPT_RESPUESTA | estructurado(RespuestaResenas, llm),
            n_relevantes=RunnableLambda(lambda x: x["n_relevantes"]),
            n_total=RunnableLambda(lambda x: x["n_total"]),
            palabras=RunnableLambda(lambda x: x["palabras"].palabras),
        )
    )
