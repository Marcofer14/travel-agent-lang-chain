# 🧭 Ruta Ibérica — AI travel advisor

🌐 **English** · [Español](README.es.md)

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![LangChain](https://img.shields.io/badge/LangChain-1.x-1C3C3C?logo=langchain&logoColor=white)
![Chainlit](https://img.shields.io/badge/Chainlit-2.x-F80061)
![Groq](https://img.shields.io/badge/LLM-Groq%20free%20tier-F55036)

Conversational agent that plans **where to stay and what to do** on a trip through **Barcelona, Madrid and Mallorca**.
It understands destinations, dates, number of guests and budget; searches real Inside Airbnb listings, **reads their reviews** (in 6+ languages), recommends activities based on your traveler profile and builds the **full itinerary as a PDF**.

> Project for the **NLP Midterm** (LangChain + Chainlit Challenge).
>
> The app interface and the agent speak **Spanish**.

---

## ✨ Features

For each destination the agent shows **4 options**, always **available every night** of the stay and with **room for the whole group**:

| Option | Criterion |
|---|---|
| 🧭 Recommended | highest Ruta Ibérica score (1 to 10) |
| ⭐ Best rated | Airbnb rating with a Bayesian average |
| 💸 Cheapest | lowest price per night |
| 💎 Most expensive | highest price per night (within budget) |

Plus:

- 💬 **Questions about reviews**, answered with verbatim quotes.
- 🧳 **Guides by traveler type** (8 profiles: 🏖️ beach, 🖼️ museums, 🍷 foodie, 🎭 culture, 🚶 walker, 👨‍👩‍👧 family, 🌙 night owl, 🌍 general), pre-generated with an LLM and grounded in real places.
- 📍 **Real activities** (museums, theaters, restaurants, markets, beaches, parks, viewpoints, nightlife) with opening hours, website and map.
- 📅 **Simulated bookings** (with a confirmation code) or **tentative plans**, with or without date and time, plus **car rental** with real agencies.
- 📄 **PDF itinerary** with accommodations (and photos), a day-by-day plan, activities, car and notes.
- 📊 Distances to points of interest, radar comparison chart, weather for the travel dates and adjustable model weights.
- 🖥️ **Three-column interface**: usage guide with clickable examples · chat · **live, editable itinerary** (change dates and times, turn a tentative plan into a booking, remove items, download the PDF). The agent is notified of every change.

### How is the score computed?

| Component | Weight |
|---|---|
| Perceived quality (Airbnb rating with Bayesian adjustment) | 30 % |
| AI review analysis (cleanliness, quietness, host, accuracy of the listing, sentiment) | 30 % |
| Value for money vs. the neighborhood median | 20 % |
| Location | 10 % |
| Capacity fit for the group size | 10 % |

---

## 🛠️ Stack and technical components

| Concept | Implementation |
|---|---|
| LCEL with the `\|` operator | `app/core/nlp.py` — review analysis, request parsing, questions about reviews |
| Pydantic + `with_structured_output` | `app/core/schemas.py` — `AnalisisResenas`, `SolicitudViaje`, `PalabrasClave`, `RespuestaResenas`, `RecomendacionPerfil` |
| `RunnableParallel` | `cadena_analisis()` — structured LLM output, lexical signals and statistics over the same input |
| `.batch()` + enriched DataFrame | `enriquecer()` and `preprocesado/enrich_runner.py` → `reviews_enriched.parquet` |
| Memory | checkpointer with a per-session `thread_id` + `RunnableWithMessageHistory` (notebook, section 9) |
| `create_agent` agent | `app/core/agent.py`, with model *fallback* and context-editing middlewares |
| 14 custom tools | `app/core/tools.py` — search listings, details, reviews, compare, weather, neighborhoods, select, profile guides, activities, schedule, car, remove, summary, PDF |
| Metrics and costs | `app/core/metrics.py` — input/output tokens, latency, total and average cost |
| Interface | `app/app.py` + `app/public/` (custom React components, theme, logo) |

**LLM:** [Groq](https://console.groq.com/) free tier — `openai/gpt-oss-120b` for the agent and `openai/gpt-oss-20b` / `qwen/qwen3.8-27b` for batch processing. The actual cost is **US$ 0**; cost is simulated with list prices and compared against Claude Sonnet 5.

---

## 📂 Project structure

```
Ruta_Iberica/
├── app/                          ← everything needed to run the bot
│   ├── app.py                    Chainlit interface
│   ├── core/                     agent, tools, LCEL chains, scoring, metrics, weather, places
│   ├── data/processed/           curated catalog + NLP batch results (parquet, ~12 MB)
│   ├── public/                   React components (.jsx), CSS, theme, logo
│   ├── .chainlit/config.toml     interface configuration
│   ├── chainlit.md               in-app "Readme" panel
│   ├── requirements.txt
│   └── .env.example              API key template
├── preprocesado/                 ← how the data was generated (not needed to run the app)
│   ├── download_data.py          downloads Inside Airbnb (~420 MB → data/raw/)
│   ├── data_prep.py              builds the curated catalog → app/data/processed/
│   ├── enrich_runner.py          batched NLP → reviews_enriched.parquet
│   ├── descargar_actividades.py  OpenStreetMap places + Wikidata popularity → actividades.parquet
│   ├── generar_recomendaciones.py  profile guides (LCEL + Pydantic + batch) → recomendaciones.json
│   └── build_notebook.py         generates Ruta_Iberica.ipynb from the source code
├── tests/                        automated tests (pytest)
├── Ruta_Iberica.ipynb            full notebook
├── README.md                     English
└── README.es.md                  Español
```

---

## 🚀 Getting started

You need a (free) Groq API key: <https://console.groq.com/keys>

### Option A — Google Colab

1. Open `Ruta_Iberica.ipynb` in Colab.
2. Add the key to **Secrets** as `GROQ_API_KEY` (if it's missing, the notebook asks for it via `getpass`).
3. `Runtime → Run all`.
4. The last cell starts Chainlit, opens a `cloudflared` tunnel and prints the `https://….trycloudflare.com` link.

### Option B — Local (data is already processed)

Requires **Python 3.12** (Chainlit does not work with Python 3.14).

```bash
git clone https://github.com/Marcofer14/Ruta_Iberica.git
cd Ruta_Iberica/app
python -m venv .venv
.venv\Scripts\activate            # Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # Linux/Mac: cp .env.example .env  → fill in GROQ_API_KEY
chainlit run app.py               # opens http://localhost:8000
```

> 💡 On Windows, create the virtual environment **outside OneDrive**: syncing locks files inside the venv.

Optional `.env` variables: `MODELO_AGENTE` and `MODELO_BATCH` to override the default models.

### Regenerating the data (optional)

From the project root, using the same environment:

```bash
pip install -r preprocesado/requirements.txt
python preprocesado/download_data.py                  # raw Inside Airbnb CSVs
python preprocesado/data_prep.py                      # curated catalog (~2 min)
python preprocesado/enrich_runner.py --limite 150     # batched NLP review analysis (free tier: ~150/day per model)
python preprocesado/descargar_actividades.py          # places and activities from OpenStreetMap (~3 min)
python preprocesado/generar_recomendaciones.py        # 24 guides (3 destinations × 8 profiles)
```

---

## 🧪 Tests

```bash
pip install -r tests/requirements.txt
pytest tests                  # 25 offline tests: data, filters, scoring, tools, activities, PDF, charts
RUN_LLM=1 pytest tests        # + 4 Groq tests: structured output, RunnableParallel, reviews, agent with memory
```

---

## 🗺️ Data sources

- **[Inside Airbnb](https://insideairbnb.com/get-the-data/)** — June 2026 snapshots: Barcelona (06/24), Madrid (06/20), Mallorca (06/23). Files `listings`, `calendar` and `reviews`. Curated catalog of **1,500 listings** (500 per destination).
- **[OpenStreetMap](https://www.openstreetmap.org/)** (Overpass API, © OSM contributors, ODbL license) — 1,609 places and activities; popularity based on the number of Wikipedia articles in [Wikidata](https://www.wikidata.org/).
- **[Open-Meteo](https://open-meteo.com/)** — weather (forecast or historical), free API with no key.

---

## ⚠️ Known limitations

- **Bookings are simulated**: there are no free public APIs to book cars, theaters or restaurants. They are stored with a Ruta Ibérica code, and the PDF says to confirm them with each provider.
- Availability and prices come from the Inside Airbnb snapshot and are **not real-time**. The interface says so and links to Airbnb for confirmation.
- The Groq free tier limits tokens per minute: the agent switches models automatically when the quota runs out, and the catalog analysis runs in batches.

> 🔐 No API keys are stored in the repository: they are read from environment variables, `app/.env` (git-ignored) or `getpass`.

---

## 👥 Team

- Guillermo Prieto
- Marco Fernandez
- Javier Alonso Desimone
- Rodrigo Sanchez Lopez
- Ignacio Mititieri
