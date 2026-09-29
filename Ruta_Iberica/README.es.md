# 🧭 Ruta Ibérica — asesor de viajes con IA

🌐 [English](README.md) · **Español**

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![LangChain](https://img.shields.io/badge/LangChain-1.x-1C3C3C?logo=langchain&logoColor=white)
![Chainlit](https://img.shields.io/badge/Chainlit-2.x-F80061)
![Groq](https://img.shields.io/badge/LLM-Groq%20free%20tier-F55036)

Agente conversacional que planifica **dónde dormir y qué hacer** en un viaje por **Barcelona, Madrid y Mallorca**.
Entiende destinos, fechas, cantidad de huéspedes y presupuesto; busca alojamientos reales de Inside Airbnb, **lee sus reseñas** (en más de 6 idiomas), recomienda actividades según tu perfil de viajero y arma el **itinerario completo en PDF**.

> Proyecto del **Primer Parcial de NLP** (Desafío LangChain + Chainlit).

---

## ✨ Funcionalidades

Para cada destino el agente presenta **4 opciones**, siempre **disponibles todas las noches** y con **capacidad para todo el grupo**:

| Opción | Criterio |
|---|---|
| 🧭 Recomendada | mayor puntaje Ruta Ibérica (1 a 10) |
| ⭐ Mejor rateada | rating de Airbnb con promedio bayesiano |
| 💸 Más barata | menor precio por noche |
| 💎 Más cara | mayor precio por noche (dentro del presupuesto) |

Además:

- 💬 **Preguntas sobre reseñas** respondidas con citas textuales.
- 🧳 **Guías por tipo de viajero** (8 perfiles: 🏖️ playero, 🖼️ museos, 🍷 foodie, 🎭 cultural, 🚶 caminador, 👨‍👩‍👧 familiar, 🌙 noctámbulo, 🌍 generalista), pregeneradas con LLM y ancladas en lugares reales.
- 📍 **Actividades reales** (museos, teatros, restaurantes, mercados, playas, parques, miradores, vida nocturna) con horario, web y mapa.
- 📅 **Reservas simuladas** (con código de confirmación) o **tentativas**, con o sin día y hora, y **alquiler de auto** con agencias reales.
- 📄 **Itinerario en PDF** con hospedajes (y fotos), plan día por día, actividades, auto y notas.
- 📊 Distancias a puntos de interés, comparador radar, clima de las fechas y pesos del modelo ajustables.
- 🖥️ **Interfaz en tres columnas**: guía de uso con ejemplos cliqueables · chat · **itinerario en vivo editable** (cambiar fechas y horarios, pasar de tentativa a reservada, quitar ítems, descargar el PDF). El agente se entera de cada cambio.

### ¿Cómo se calcula el puntaje?

| Componente | Peso |
|---|---|
| Calidad percibida (rating de Airbnb con ajuste bayesiano) | 30 % |
| Análisis de reseñas con IA (limpieza, tranquilidad, anfitrión, fidelidad al anuncio, sentimiento) | 30 % |
| Relación precio/calidad frente a la mediana del barrio | 20 % |
| Ubicación | 10 % |
| Ajuste de capacidad al tamaño del grupo | 10 % |

---

## 🛠️ Stack y componentes técnicos

| Concepto | Implementación |
|---|---|
| LCEL con el operador `\|` | `app/core/nlp.py` — análisis de reseñas, interpretación del pedido, preguntas sobre reseñas |
| Pydantic + `with_structured_output` | `app/core/schemas.py` — `AnalisisResenas`, `SolicitudViaje`, `PalabrasClave`, `RespuestaResenas`, `RecomendacionPerfil` |
| `RunnableParallel` | `cadena_analisis()` — LLM estructurado, señales léxicas y estadísticas sobre la misma entrada |
| `.batch()` + DataFrame enriquecido | `enriquecer()` y `preprocesado/enrich_runner.py` → `reviews_enriched.parquet` |
| Memoria | checkpointer con `thread_id` por sesión + `RunnableWithMessageHistory` (notebook, sección 9) |
| Agente `create_agent` | `app/core/agent.py`, con middlewares de *fallback* de modelo y edición de contexto |
| 14 tools propias | `app/core/tools.py` — buscar alojamiento, detalle, reseñas, comparar, clima, barrios, seleccionar, guías por perfil, actividades, agendar, auto, quitar, resumen, PDF |
| Métricas y costos | `app/core/metrics.py` — tokens de entrada/salida, tiempo, costo total y promedio |
| Interfaz | `app/app.py` + `app/public/` (componentes React propios, tema, logo) |

**LLM:** free tier de [Groq](https://console.groq.com/) — `openai/gpt-oss-120b` para el agente y `openai/gpt-oss-20b` / `qwen/qwen3.8-27b` para el procesamiento batch. El costo real es **US$ 0**; el costo se simula con precios de lista y se compara con Claude Sonnet 5.

---

## 📂 Estructura

```
Ruta_Iberica/
├── app/                          ← todo lo necesario para correr el bot
│   ├── app.py                    interfaz Chainlit
│   ├── core/                     agente, tools, cadenas LCEL, puntaje, métricas, clima, lugares
│   ├── data/processed/           catálogo curado + resultados del batch NLP (parquet, ~12 MB)
│   ├── public/                   componentes React (.jsx), CSS, tema, logo
│   ├── .chainlit/config.toml     configuración de la interfaz
│   ├── chainlit.md               panel "Léeme" de la interfaz
│   ├── requirements.txt
│   └── .env.example              plantilla para la API key
├── preprocesado/                 ← cómo se generaron los datos (no hace falta para correr la app)
│   ├── download_data.py          descarga Inside Airbnb (~420 MB → data/raw/)
│   ├── data_prep.py              arma el catálogo curado → app/data/processed/
│   ├── enrich_runner.py          batch NLP por tandas → reviews_enriched.parquet
│   ├── descargar_actividades.py  lugares de OpenStreetMap + popularidad Wikidata → actividades.parquet
│   ├── generar_recomendaciones.py  guías por perfil (LCEL + Pydantic + batch) → recomendaciones.json
│   └── build_notebook.py         genera Ruta_Iberica.ipynb a partir del código fuente
├── tests/                        pruebas automáticas (pytest)
├── Ruta_Iberica.ipynb            notebook completa
├── README.md                     English
└── README.es.md                  Español
```

---

## 🚀 Cómo ejecutar

Necesitás una API key de Groq (gratuita): <https://console.groq.com/keys>

### Opción A — Google Colab

1. Abrir `Ruta_Iberica.ipynb` en Colab.
2. Cargar la key en **Secrets** como `GROQ_API_KEY` (si no está, la notebook la pide con `getpass`).
3. `Entorno de ejecución → Ejecutar todas`.
4. La última celda levanta Chainlit, crea un túnel con `cloudflared` e imprime el enlace `https://….trycloudflare.com`.

### Opción B — Local (los datos ya vienen procesados)

Requiere **Python 3.12** (Chainlit no funciona con Python 3.14).

```bash
git clone https://github.com/Marcofer14/Ruta_Iberica.git
cd Ruta_Iberica/app
python -m venv .venv
.venv\Scripts\activate            # Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # Linux/Mac: cp .env.example .env  → completar GROQ_API_KEY
chainlit run app.py               # abre http://localhost:8000
```

> 💡 En Windows conviene crear el entorno virtual **fuera de OneDrive**: la sincronización bloquea archivos del venv.

Variables opcionales en `.env`: `MODELO_AGENTE` y `MODELO_BATCH` para cambiar los modelos por defecto.

### Regenerar los datos (opcional)

Desde la raíz del proyecto, con el mismo entorno:

```bash
pip install -r preprocesado/requirements.txt
python preprocesado/download_data.py                  # CSV crudos de Inside Airbnb
python preprocesado/data_prep.py                      # catálogo curado (~2 min)
python preprocesado/enrich_runner.py --limite 150     # análisis NLP de reseñas en tandas (free tier: ~150/día por modelo)
python preprocesado/descargar_actividades.py          # lugares y actividades de OpenStreetMap (~3 min)
python preprocesado/generar_recomendaciones.py        # 24 guías (3 destinos × 8 perfiles)
```

---

## 🧪 Pruebas

```bash
pip install -r tests/requirements.txt
pytest tests                  # 25 pruebas offline: datos, filtros, puntaje, tools, actividades, PDF, gráficos
RUN_LLM=1 pytest tests        # + 4 pruebas con Groq: salida estructurada, RunnableParallel, reseñas, agente con memoria
```

---

## 🗺️ Fuentes de datos

- **[Inside Airbnb](https://insideairbnb.com/get-the-data/)** — relevamientos de junio de 2026: Barcelona (24/06), Madrid (20/06), Mallorca (23/06). Archivos `listings`, `calendar` y `reviews`. Catálogo curado de **1.500 alojamientos** (500 por destino).
- **[OpenStreetMap](https://www.openstreetmap.org/)** (API Overpass, © colaboradores de OSM, licencia ODbL) — 1.609 lugares y actividades; popularidad según cantidad de Wikipedias en [Wikidata](https://www.wikidata.org/).
- **[Open-Meteo](https://open-meteo.com/)** — clima (pronóstico o histórico), API gratuita y sin key.

---

## ⚠️ Limitaciones conocidas

- Las **reservas son simuladas**: no hay APIs públicas y gratuitas para reservar autos, teatro o restaurantes. Quedan registradas con un código de Ruta Ibérica y el PDF indica confirmarlas con cada proveedor.
- Disponibilidad y precios corresponden al relevamiento de Inside Airbnb, **no son en tiempo real**. La interfaz lo aclara y enlaza a Airbnb para confirmar.
- El free tier de Groq limita los tokens por minuto: el agente cambia de modelo automáticamente al agotarse la cuota, y el análisis del catálogo se hace en tandas.

> 🔐 Ninguna API key está en el repositorio: se leen de variables de entorno, de `app/.env` (ignorado por git) o de `getpass`.

---

## 👥 Integrantes

- Guillermo Prieto
- Marco Fernandez
- Javier Alonso Desimone
- Rodrigo Sanchez Lopez
- Ignacio Mititieri
