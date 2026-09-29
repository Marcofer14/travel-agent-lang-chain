"""Agente de viajes: create_agent + tools propias + memoria por sesión (checkpointer con thread_id)."""
from datetime import date

from langchain.agents import create_agent
from langchain.agents.middleware import (ContextEditingMiddleware, ModelFallbackMiddleware,
                                         SummarizationMiddleware)
from langchain.agents.middleware.context_editing import ClearToolUsesEdit
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import InMemorySaver

from core.config import MODELO_BATCH
from core.nlp import llm_agente
from core.tools import TOOLS

SYSTEM_PROMPT = f"""Sos "Ruta Ibérica", asesor de viajes para Barcelona, Madrid y Mallorca con datos reales (Inside Airbnb,
OpenStreetMap). Hoy es {date.today():%Y-%m-%d}.

Cómo trabajás:
- Alojamiento: necesitás destino(s), fechas y huéspedes (si faltan, preguntá). buscar_opciones una vez por destino;
  si no dicen año, usá la próxima fecha futura; cerca_de si mencionan un lugar. Al elegir → seleccionar_alojamiento.
- Guías por perfil, actividades y clima NO requieren fechas: usalas de inmediato (recomendaciones_perfil destino='todos').
- Preguntas sobre un alojamiento → consultar_resenas; dudas entre opciones → comparar_opciones.
- Agendar → agendar_actividad (tentativa por defecto; reservar=True solo si pide reservar y hay fecha). Autos → reservar_auto.
- Al cerrar el viaje o si pide imprimir → generar_pdf_itinerario.
- Los ids son textos largos: copialos exactos y nunca los muestres. Si una tool falla, no la repitas igual.

Reglas:
- Solo afirmá lo que devuelven las tools; si no está, decí que no lo sabés.
- El usuario también edita el itinerario desde un panel: el estado vigente es el que devuelve resumen_viaje.
- La interfaz ya muestra tarjetas, mapas y gráficos: comentá diferencias en pocas frases, sin tablas ni fichas completas.
- Reservas SIMULADAS: aclaralo. Precios y disponibilidad según relevamiento de junio 2026.
Respondé en español neutro latinoamericano, cálido y concreto, en MÁXIMO 100 palabras."""

memoria = InMemorySaver()


def crear_agente(callbacks=None):
    """Agente con memoria por thread_id y dos middlewares pensados para el free tier de Groq:
    - ModelFallbackMiddleware: si el modelo principal agota su cuota por minuto, sigue con otro modelo (cada uno tiene su cuota).
    - ContextEditingMiddleware: limpia resultados viejos de tools para que el historial no crezca sin control
      (las búsquedas se conservan porque contienen los ids de los alojamientos)."""
    principal = llm_agente(callbacks=callbacks or [], max_retries=0)
    respaldos = [ChatGroq(model=MODELO_BATCH, temperature=0.2, reasoning_effort="low", max_retries=2),
                 ChatGroq(model="qwen/qwen3.8-27b", temperature=0.2, max_tokens=2048, max_retries=2)]
    return create_agent(
        model=principal,
        tools=TOOLS,
        system_prompt=SYSTEM_PROMPT,
        checkpointer=memoria,
        middleware=[
            ModelFallbackMiddleware(*respaldos),
            # Memoria acotada: si el historial crece, se resume (conserva huéspedes, fechas, presupuesto y elecciones)
            SummarizationMiddleware(model=ChatGroq(model=MODELO_BATCH, temperature=0, reasoning_effort="low"),
                                    trigger=("tokens", 3500), keep=("messages", 8)),
            ContextEditingMiddleware(edits=[ClearToolUsesEdit(trigger=2500, keep=2, exclude_tools=("buscar_opciones",),
                                                              placeholder="[resultado anterior resumido]")]),
        ],
    )
