"""Genera Ruta_Iberica.ipynb a partir de los archivos fuente del proyecto.

Cada módulo se incluye como celda %%writefile: la notebook es autocontenida (en Colab recrea todo el proyecto)
y el código que se ve en la notebook es exactamente el que ejecuta app.py.
"""
from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
nb = nbf.v4.new_notebook()
celdas = []


def md(texto: str) -> None:
    celdas.append(nbf.v4.new_markdown_cell(texto.strip()))


def code(texto: str) -> None:
    celdas.append(nbf.v4.new_code_cell(texto.strip()))


def archivo(ruta: str) -> None:
    contenido = (ROOT / ruta).read_text(encoding="utf-8").rstrip()
    code(f"%%writefile {ruta}\n{contenido}")


# ------------------------------------------------------------------ portada
md("""
# 🧭 Ruta Ibérica: asesor de viajes con IA para Barcelona, Madrid y Mallorca
**Primer Parcial de NLP · Desafío LangChain + Chainlit**

**Integrantes:** Guillermo Prieto · Marco Fernandez · Javier Alonso Desimone · Rodrigo Sanchez Lopez · Ignacio Mititieri

## Problema
Planificar un viaje por varias ciudades implica revisar cientos de alojamientos y miles de reseñas en distintos idiomas.
**Ruta Ibérica** es un agente conversacional que, para cada destino del viaje, filtra alojamientos **disponibles** y con
**capacidad para todo el grupo**, **lee las reseñas por el viajero** y presenta **4 opciones**:
🧭 recomendada por nuestro modelo · ⭐ mejor rateada · 💸 más barata · 💎 más cara, cada una con un **puntaje de 1 a 10**.

## Datos
[Inside Airbnb](https://insideairbnb.com/get-the-data/) (fuente pública y rastreable), relevamientos de junio de 2026:
`listings` (precio, capacidad, ubicación, ratings, foto), `calendar` (disponibilidad diaria por 12 meses) y
`reviews` (texto de las reseñas, en más de 6 idiomas). Complemento: clima de [Open-Meteo](https://open-meteo.com/) (API gratuita).

## Arquitectura
```
CSV Inside Airbnb ─► data_prep ─► catálogo curado (1.500 alojamientos) + calendario + reseñas
                                        │
      LCEL: prompt | LLM.with_structured_output(Pydantic)                 ◄── RunnableParallel (LLM + léxico + estadísticas)
      .batch() sobre el catálogo ─► DataFrame enriquecido (reviews_enriched.parquet)
                                        │
      Modelo de puntaje 1-10 (calidad bayesiana · reseñas IA · precio/calidad · ubicación · capacidad)
                                        │
      Agente create_agent + 8 tools + memoria por sesión (checkpointer, thread_id) + métricas (callback)
                                        │
      Interfaz Chainlit: streaming, tarjetas con fotos, mapas, radar, clima, sliders de pesos, métricas
```
LLM: **Groq free tier** (`openai/gpt-oss-120b` para el agente, `openai/gpt-oss-20b` / `qwen/qwen3.8-27b` para el batch):
el uso real cuesta US$ 0 y el costo se **simula** con precios de lista.
""")

# ------------------------------------------------------------------ setup
md("## 0 · Configuración del entorno")
code("""
import os, sys
IN_COLAB = "google.colab" in sys.modules
if IN_COLAB:
    %pip install -q "langchain>=1.4" "langchain-core>=1.6" "langchain-groq>=1.1" "langgraph>=1.0" "chainlit>=2.12" \\
        "plotly==5.24.1" pyarrow python-dotenv requests
    os.makedirs("/content/ruta_iberica", exist_ok=True)
    %cd /content/ruta_iberica
for carpeta in ["core", "data/raw", "data/processed", "public/elements", ".chainlit"]:
    os.makedirs(carpeta, exist_ok=True)
print("Directorio de trabajo:", os.getcwd())
""")
code("""
# La API key NUNCA se escribe en la notebook: se toma del entorno, de los Secrets de Colab o se pide con getpass.
from getpass import getpass
if not os.getenv("GROQ_API_KEY"):
    try:
        from google.colab import userdata
        os.environ["GROQ_API_KEY"] = userdata.get("GROQ_API_KEY")
    except Exception:
        from dotenv import load_dotenv
        load_dotenv()
if not os.getenv("GROQ_API_KEY"):
    os.environ["GROQ_API_KEY"] = getpass("GROQ_API_KEY (https://console.groq.com/keys): ")
print("API key cargada ✔")
""")

md("""
## 1 · Módulos del proyecto
Cada celda escribe un archivo del paquete `core/` (la app de Chainlit importa exactamente este código).
""")
for ruta in ["core/__init__.py", "core/config.py", "core/schemas.py", "core/metrics.py", "data/download_data.py",
             "core/data_prep.py", "core/nlp.py", "core/scoring.py", "core/lugares.py", "core/clima.py",
             "core/tools.py", "core/agent.py", "core/enrich_runner.py"]:
    archivo(ruta)

# ------------------------------------------------------------------ datos
md("""
## 2 · Dataset: descarga y construcción del catálogo
Se descargan los CSV de Inside Airbnb (~420 MB) y se arma un catálogo curado de **500 alojamientos activos por destino**
(≥15 reseñas, reseña reciente, precio publicado), muestreado de forma estratificada por capacidad y rango de precio.
""")
code("""
from data.download_data import descargar
from core import data_prep
if not (data_prep.PROCESSED / "pool.parquet").exists():
    descargar()
    data_prep.construir()
else:
    print("Catálogo ya construido ✔")
""")
code("""
import pandas as pd
pd.set_option("display.max_colwidth", 80)
pool = pd.read_parquet("data/processed/pool.parquet")
cal = pd.read_parquet("data/processed/calendar_pool.parquet")
rev = pd.read_parquet("data/processed/reviews_pool.parquet")
print(f"Alojamientos: {len(pool)} · días de calendario: {len(cal):,} · reseñas para el batch: {len(rev):,}")
pool.groupby("destino").agg(alojamientos=("id", "size"), precio_mediano=("price", "median"),
                            rating_medio=("review_scores_rating", "mean"), capacidad_media=("accommodates", "mean"),
                            barrios=("barrio", "nunique")).round(2)
""")
code("""
from core.nlp import detectar_idioma
idiomas = rev["comments"].map(detectar_idioma).value_counts(normalize=True).round(3)
print("Idiomas detectados en las reseñas (heurística por stopwords):")
idiomas
""")

# ------------------------------------------------------------------ LCEL
md("""
## 3 · Pipeline LCEL: prompt | modelo | parser
Primer ejemplo mínimo con el operador `|`: prompt con reglas → LLM → `StrOutputParser` → transformación.
""")
code("""
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from core.metrics import MetricsTracker
from core.nlp import llm_agente

tracker = MetricsTracker()   # callback que registra tokens, tiempo y costo de TODAS las llamadas
prompt = ChatPromptTemplate.from_messages([
    ("system", "Sos un asesor de viajes. Respondé en una sola frase y solo con información general conocida; "
               "si no sabés algo, decilo."),
    ("human", "¿Qué zona de {ciudad} conviene para un viajero que busca {perfil}?"),
])
cadena = prompt | llm_agente() | StrOutputParser() | RunnableLambda(lambda s: "🧭 " + s.strip())
print(cadena.invoke({"ciudad": "Madrid", "perfil": "museos y vida nocturna"}, config={"callbacks": [tracker]}))
""")

md("""
## 4 · Salida estructurada con Pydantic: interpretar el pedido del viajero
`with_structured_output(SolicitudViaje)` convierte lenguaje natural en datos validados (tramos, fechas, huéspedes, presupuesto).
""")
code("""
from core.nlp import cadena_solicitud
solicitud = cadena_solicitud().invoke(
    "Somos 3, arrancamos en Barcelona el 10 de octubre, 3 noches, después Madrid 3 noches y terminamos con 4 en Mallorca. "
    "No más de 180 euros la noche, algo tranquilo.", config={"callbacks": [tracker]})
solicitud
""")

md("""
## 5 · Procesamiento multidimensional con RunnableParallel
Sobre las reseñas de un mismo alojamiento corren **tres análisis en paralelo**:
1. `nlp`: LLM con salida estructurada `AnalisisResenas` (sentimiento, 5 puntajes por aspecto, pros, contras, perfiles, alerta, cita textual).
2. `senales`: detección léxica multilingüe de temas (ruido, transporte, playa, limpieza...).
3. `stats`: idiomas y volumen del texto.
""")
code("""
from core.nlp import cadena_analisis, preparar_entradas
ejemplo = preparar_entradas(pool[pool["destino"] == "madrid"].head(1), rev)[0]
print(ejemplo["nombre"], "\\n", ejemplo["resenas"][:600], "...")
resultado = cadena_analisis().invoke(ejemplo, config={"callbacks": [tracker]})
print("\\nSEÑALES:", resultado["senales"], "\\nSTATS:", resultado["stats"])
resultado["nlp"]
""")

md("""
## 6 · Procesamiento del dataset con `.batch()` → DataFrame enriquecido
Se analiza una muestra de alojamientos en paralelo (`max_concurrency`), con manejo de errores por registro
(`return_exceptions=True`) y un *rate limiter* para respetar la cuota gratuita (8K tokens/minuto).
El catálogo completo se procesa en tandas con `core/enrich_runner.py` y se cachea en `reviews_enriched.parquet`.
""")
code("""
import time
from core.nlp import enriquecer, guardar_enriquecido, cargar_enriquecido
tracker_batch = MetricsTracker()
ya = set(cargar_enriquecido()["listing_id"])
muestra = pool[~pool["id"].isin(ya)].groupby("destino").head(4)          # 12 alojamientos nuevos (4 por destino)
entradas = preparar_entradas(muestra, rev)
t0 = time.perf_counter()
df_batch = enriquecer(entradas, callbacks=[tracker_batch], max_concurrency=2)
print(f"{len(df_batch)} alojamientos en {time.perf_counter() - t0:.1f}s")
enriquecido = guardar_enriquecido(df_batch)
df_batch[["listing_id", "sentimiento_general", "puntaje_limpieza", "puntaje_tranquilidad", "pros", "contras", "resumen"]].head(8)
""")
code("""
metricas_batch = tracker_batch.resumen(n_unidades=len(entradas))
pd.Series(metricas_batch, name="batch de reseñas")
""")
code("""
# DataFrame enriquecido completo (muestra + tandas previas) unido al catálogo
enriquecido = cargar_enriquecido()
df_rico = pool.merge(enriquecido, left_on="id", right_on="listing_id")
print(f"Alojamientos con análisis NLP: {len(df_rico)} de {len(pool)}")
df_rico.groupby("destino").agg(n=("id", "size"), limpieza=("puntaje_limpieza", "mean"),
                               tranquilidad=("puntaje_tranquilidad", "mean"),
                               con_alerta=("alerta", lambda s: s.notna().sum())).round(2)
""")
md("""
**Validación del análisis NLP.** Si el LLM lee bien las reseñas, sus puntajes por aspecto deberían correlacionar
con los sub-ratings numéricos que los huéspedes cargan en Airbnb (que el modelo **no** ve).
""")
code("""
pares = {"puntaje_limpieza": "review_scores_cleanliness", "puntaje_ubicacion": "review_scores_location",
         "puntaje_anfitrion": "review_scores_communication", "puntaje_fidelidad": "review_scores_accuracy"}
pd.DataFrame({
    "correlación de Spearman": {k: round(df_rico[k].rank().corr(df_rico[v].rank()), 3) for k, v in pares.items()},
    "n": {k: int(df_rico[[k, v]].dropna().shape[0]) for k, v in pares.items()},
})
""")

# ------------------------------------------------------------------ scoring
md("""
## 7 · Modelo de puntaje (1 a 10) y selección de las 4 opciones
| Componente | Peso | Cómo se calcula |
|---|---|---|
| Calidad | 30 % | rating de Airbnb con **promedio bayesiano** (evita que un 5.0 con 3 reseñas gane) |
| Reseñas IA | 30 % | puntajes por aspecto + sentimiento del batch NLP (penaliza alertas) |
| Precio/calidad | 20 % | precio vs. mediana de su barrio y capacidad |
| Ubicación | 10 % | rating de ubicación + puntaje de ubicación NLP |
| Ajuste de capacidad | 10 % | penaliza alojamientos sobredimensionados para el grupo |

Filtros duros: **capacidad ≥ huéspedes**, **disponible todas las noches** (calendario) y estadía mínima compatible.
""")
code("""
from core import scoring
scoring.recargar()
cands = scoring.candidatos("barcelona", "2026-10-10", "2026-10-13", huespedes=2)
print(f"Candidatos disponibles: {len(cands)}")
pd.DataFrame([{"opción": et, "alojamiento": f["name"][:45], "€/noche": f["price"], "puntaje": f["puntaje"],
               "rating Airbnb /10": f["rating_airbnb_10"], **scoring.detalle_puntaje(f)}
              for et, f in scoring.elegir_cuatro(cands)])
""")

# ------------------------------------------------------------------ tools
md("""
## 8 · Tools propias del agente
| Tool | Operación real |
|---|---|
| `buscar_opciones` | filtra catálogo + calendario + capacidad (+ cercanía a un punto de interés) y devuelve las 4 opciones |
| `detalle_alojamiento` | análisis NLP de un alojamiento (lo calcula en vivo si falta) |
| `consultar_resenas` | RAG liviano: palabras clave multilingües → recuperación → respuesta con citas |
| `comparar_opciones` | comparación por aspecto (gráfico radar en la interfaz) |
| `clima_destino` | Open-Meteo: pronóstico o histórico para las fechas |
| `comparar_barrios` | KPIs por barrio |
| `seleccionar_alojamiento` | registra la elección en el plan de la sesión |
| `resumen_viaje` | plan final con costo total |

Las tools usan `response_format="content_and_artifact"`: el LLM recibe un resumen compacto (menos tokens) y la interfaz
recibe el *artifact* completo para dibujar tarjetas y gráficos.
""")
code("""
import json
from core import tools
contenido, artifact = tools.ejecutar_busqueda("madrid", "2026-10-13", "2026-10-16", 2, cerca_de="Museo del Prado")
print(json.dumps(json.loads(contenido)["opciones"], ensure_ascii=False, indent=1)[:1500])
""")
code("""
contenido, art = tools.clima_destino.func("mallorca", "2026-10-16", "2026-10-20")
print(contenido)
""")
code("""
id_recomendada = artifact["tarjetas"][0]["id"]
contenido, art = tools.consultar_resenas.func(id_recomendada, "¿Se escucha ruido de la calle a la noche?")
print(json.dumps(art, ensure_ascii=False, indent=1) if art.get("tipo") == "respuesta_resenas" else contenido)
""")

# ------------------------------------------------------------------ memoria
md("""
## 9 · Memoria conversacional
**a) `RunnableWithMessageHistory`** sobre una cadena LCEL: el historial se guarda por `session_id`.
""")
code("""
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.prompts import MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory

historiales = {}
def obtener_historial(session_id: str):
    return historiales.setdefault(session_id, InMemoryChatMessageHistory())

prompt_chat = ChatPromptTemplate.from_messages([
    ("system", "Sos Ruta Ibérica, asesor de viajes. Respondé breve."),
    MessagesPlaceholder("historial"),
    ("human", "{mensaje}"),
])
chat = RunnableWithMessageHistory(prompt_chat | llm_agente() | StrOutputParser(), obtener_historial,
                                  input_messages_key="mensaje", history_messages_key="historial")
cfg = {"configurable": {"session_id": "viajero-42"}, "callbacks": [tracker]}
print(chat.invoke({"mensaje": "Hola, me llamo Lucía y viajo con mi perro."}, config=cfg))
print(chat.invoke({"mensaje": "¿Cómo me llamo y con quién viajo?"}, config=cfg))
""")
md("**b) El agente** usa un *checkpointer* de LangGraph: cada sesión de Chainlit es un `thread_id` distinto.")

# ------------------------------------------------------------------ agente
md("""
## 10 · Agente inteligente (`create_agent`)
El agente decide qué tools usar y en qué orden. Mostramos las decisiones (tool calls) de una conversación de varios turnos.
""")
code("""
from langchain_core.messages import AIMessage, ToolMessage
from core.agent import crear_agente
agente = crear_agente()
tracker_agente = MetricsTracker()
cfg_agente = {"configurable": {"thread_id": "demo-notebook"}, "callbacks": [tracker_agente]}

def conversar(texto):
    print(f"\\n👤 {texto}")
    n0, t0 = len(tracker_agente.registros), time.perf_counter()
    for paso in agente.stream({"messages": [{"role": "user", "content": texto}]}, config=cfg_agente, stream_mode="updates"):
        for actualizacion in paso.values():
            for m in (actualizacion or {}).get("messages", []):
                if isinstance(m, AIMessage) and m.tool_calls:
                    for tc in m.tool_calls:
                        print(f"   🔧 decide usar {tc['name']}({json.dumps(tc['args'], ensure_ascii=False)})")
                elif isinstance(m, AIMessage) and m.content:
                    print(f"🤖 {m.content}")
    r = MetricsTracker(registros=tracker_agente.registros[n0:]).resumen(1)
    print(f"   ⚡ {time.perf_counter() - t0:.1f}s · {r['tokens_totales']} tokens · US$ {r['costo_total_usd']:.5f} (simulado)")

conversar("Hola! Somos 2 y queremos ir a Madrid del 13 al 16 de octubre, cerca del Museo del Prado, hasta 200 euros la noche.")
""")
code("""conversar("¿La recomendada es ruidosa de noche?")""")
code("""conversar("Me quedo con la recomendada. ¿Qué clima vamos a tener? Y mostrame el plan.")""")
code("""conversar("¿Te acordás cuántos viajamos y cuál era nuestro presupuesto?")""")

# ------------------------------------------------------------------ métricas
md("""
## 11 · Métricas de funcionamiento y simulación económica
El uso real es **gratuito** (free tier de Groq). Para evaluar la viabilidad en producción se simula el costo con los
precios de lista de los mismos modelos y se compara con un proveedor premium (Claude Sonnet 5).
""")
code("""
from core.metrics import costo_usd
filas = {
    "Cadenas LCEL (secciones 3-5 y 9)": tracker.resumen(),
    "Batch de reseñas (sección 6)": tracker_batch.resumen(n_unidades=len(entradas)),
    "Agente (sección 10)": tracker_agente.resumen(n_unidades=4),
}
tabla = pd.DataFrame(filas).T[["llamadas", "tokens_entrada", "tokens_salida", "tokens_totales", "segundos_llm",
                                "costo_total_usd", "costo_promedio_usd", "costo_si_fuera_claude_sonnet_usd"]]
tabla.columns = ["llamadas", "tokens in", "tokens out", "tokens totales", "tiempo LLM (s)",
                 "costo total US$", "costo prom. por registro/consulta US$", "con Claude Sonnet 5 US$"]
tabla
""")
code("""
# Proyección: catálogo completo (1.500 alojamientos) + 1.000 consultas al mes
por_registro = tracker_batch.resumen(n_unidades=len(entradas))["costo_promedio_usd"]
por_consulta = tracker_agente.resumen(n_unidades=4)["costo_promedio_usd"]
pd.Series({
    "Analizar todo el catálogo (1.500 alojamientos)": round(por_registro * 1500, 4),
    "1.000 consultas de usuarios / mes": round(por_consulta * 1000, 4),
    "Total mensual estimado (US$)": round(por_registro * 1500 + por_consulta * 1000, 4),
}, name="US$ con precios de lista de Groq")
""")

# ------------------------------------------------------------------ interfaz
md("""
## 12 · Interfaz Chainlit
Archivos de la interfaz: `app.py`, componentes React propios (`public/elements/*.jsx`), estilos, tema y configuración.
""")
for ruta in ["app.py", "public/elements/OpcionesAlojamiento.jsx", "public/elements/PlanViaje.jsx",
             "public/elements/Metricas.jsx", "public/elements/RespuestaResenas.jsx", "public/custom.css",
             "public/theme.json", "public/logo_light.svg", "public/logo_dark.svg", "public/favicon.svg",
             "chainlit.md", ".chainlit/config.toml"]:
    archivo(ruta)

md("""
## 13 · Iniciar Chainlit y generar el enlace de acceso
- **En Colab:** la celda levanta Chainlit en segundo plano y crea un túnel público con `cloudflared` (no requiere cuenta).
  El enlace `https://....trycloudflare.com` aparece abajo.
- **En local:** ejecutar en una terminal `chainlit run app.py` y abrir http://localhost:8000
""")
code("""
import subprocess, re, time, os
if IN_COLAB:
    if not os.path.exists("cloudflared"):
        !wget -q -O cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
        !chmod +x cloudflared
    chainlit = subprocess.Popen(["chainlit", "run", "app.py", "--headless", "--port", "8000"],
                                stdout=open("chainlit.log", "w"), stderr=subprocess.STDOUT)
    time.sleep(8)
    tunel = subprocess.Popen(["./cloudflared", "tunnel", "--url", "http://localhost:8000", "--no-autoupdate"],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for linea in tunel.stdout:
        url = re.search(r"https://[a-z0-9-]+\\.trycloudflare\\.com", linea)
        if url:
            print("🧭 Ruta Ibérica disponible en:", url.group(0))
            break
else:
    print("Local: ejecutá  `chainlit run app.py`  en la carpeta del proyecto y abrí http://localhost:8000")
""")

nb["cells"] = celdas
nb["metadata"] = {"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
                  "language_info": {"name": "python"}, "colab": {"provenance": []}}
destino = ROOT / "Ruta_Iberica.ipynb"
nbf.write(nb, destino)
print("Notebook generada:", destino, f"({len(celdas)} celdas)")
