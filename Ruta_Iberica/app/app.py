"""Ruta Ibérica — interfaz Chainlit del agente de viajes (Barcelona · Madrid · Mallorca)."""
import asyncio
import json
import os
import time
import traceback

import chainlit as cl
import groq
import plotly.graph_objects as go
from chainlit.input_widget import Slider
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from core import actividades, itinerario, tools
from core.agent import crear_agente
from core.config import DESTINOS
from core.lugares import LUGARES
from core.metrics import MetricsTracker
from core.scoring import PESOS


COLORES = {"recomendada": "#B85C38", "mejor_rateada": "#D9A441", "mas_barata": "#6E7D4F", "mas_cara": "#7A4E6B"}
NOMBRES_TOOLS = {
    "buscar_opciones": "🔎 Buscando alojamientos",
    "detalle_alojamiento": "📝 Analizando reseñas",
    "comparar_barrios": "📊 Comparando barrios",
    "consultar_resenas": "🔍 Buscando en las reseñas",
    "comparar_opciones": "⚖️ Comparando opciones",
    "clima_destino": "🌤️ Consultando el clima",
    "recomendaciones_perfil": "🧭 Armando tu guía",
    "buscar_actividades": "🎟️ Buscando actividades",
    "agendar_actividad": "🗓️ Agendando",
    "reservar_auto": "🚗 Reservando auto",
    "quitar_del_itinerario": "🗑️ Quitando del itinerario",
    "generar_pdf_itinerario": "🧾 Generando el PDF",
    "seleccionar_alojamiento": "📌 Guardando elección",
    "resumen_viaje": "🧳 Armando el resumen",
}
SUGERENCIAS = [
    ("🗺️ Ruta completa", "Somos 2, queremos hacer Barcelona del 10 al 13 de octubre, Madrid del 13 al 16 y Mallorca del 16 al 20."),
    ("👨‍👩‍👧 Familia en Mallorca", "Vamos 4 personas (2 adultos y 2 chicos) a Mallorca del 2 al 9 de noviembre, hasta 250 € por noche."),
    ("🖼️ Cerca del Prado", "Busco algo para 1 persona en Madrid del 5 al 8 de diciembre, cerca del Museo del Prado. ¿Qué clima hace esos días?"),
    ("📍 ¿Dónde alojarme?", "¿Qué barrios de Barcelona me recomendás para 3 personas? Comparalos."),
]

BIENVENIDA = """
<div class="ri-hero">
  <h2>Hola, soy Ruta Ibérica 🧭</h2>
  <p>Te ayudo a planificar tu viaje por España eligiendo dónde dormir en cada destino, con datos reales de
  <b>Inside Airbnb</b> y miles de reseñas de huéspedes analizadas con IA.</p>
  <div class="ri-dest"><span>🏛️ Barcelona</span><span>🎨 Madrid</span><span>🏖️ Mallorca</span></div>
</div>
<div class="ri-pasos">
  <div class="ri-paso"><b>1 · Contame tu viaje</b>Destinos, fechas, cuántos viajan y, si querés, tu presupuesto por noche.</div>
  <div class="ri-paso"><b>2 · Te muestro 4 opciones</b>Recomendada por el modelo, mejor rateada, más barata y más cara, con puntaje de 1 a 10.</div>
  <div class="ri-paso"><b>3 · Elegís y armamos la ruta</b>Guardo tus elecciones y te doy el resumen con el costo total.</div>
</div>

También podés preguntarme **qué dicen las reseñas** de una opción (*"¿es ruidoso de noche?"*), **comparar** opciones,
consultar **el clima**, buscar **museos, teatros, restaurantes o playas**, **reservar un auto** y, al final,
**descargar el itinerario en PDF**. Con el ícono ⚙️ ajustás qué pesa más en el puntaje del modelo.

Probá con una de estas ideas 👇
"""


def mapa_opciones(tarjetas: list[dict], destino: str, cerca_de: str | None = None) -> go.Figure:
    fig = go.Figure()
    for t in tarjetas:
        fig.add_trace(go.Scattermapbox(
            lat=[t["latitude"]], lon=[t["longitude"]], mode="markers", name=t["titulo_etiqueta"],
            marker=dict(size=17, color=COLORES.get(t["etiqueta"], "#1F5673")),
            text=f"{t['name']}<br>{t['price']:.0f} €/noche · {t['puntaje']}/10", hoverinfo="text",
        ))
    lats, lons = [t["latitude"] for t in tarjetas], [t["longitude"] for t in tarjetas]
    if cerca_de:
        lat_l, lon_l = LUGARES[destino][cerca_de]
        fig.add_trace(go.Scattermapbox(lat=[lat_l], lon=[lon_l], mode="markers+text", name=f"📍 {cerca_de}",
                                       marker=dict(size=13, color="#111827"), text=[cerca_de],
                                       textposition="top center", hoverinfo="text"))
        lats, lons = lats + [lat_l], lons + [lon_l]
    extension = max(max(lats) - min(lats), max(lons) - min(lons))
    zoom = 13 if extension < 0.015 else 12 if extension < 0.04 else 11 if extension < 0.12 else 8.3
    fig.update_layout(
        mapbox=dict(style="open-street-map", center=dict(lat=sum(lats) / len(lats), lon=sum(lons) / len(lons)), zoom=zoom),
        margin=dict(l=0, r=0, t=0, b=0), height=340, legend=dict(orientation="h", y=-0.05),
    )
    return fig


def grafico_barrios(tabla: list[dict], destino: str) -> go.Figure:
    tabla = sorted(tabla, key=lambda r: r["precio_mediano"])
    fig = go.Figure(go.Bar(
        x=[r["precio_mediano"] for r in tabla], y=[r["barrio"] for r in tabla], orientation="h",
        marker=dict(color=[r["rating_10"] for r in tabla], colorscale=[[0, "#D9A441"], [1, "#6E7D4F"]],
                    colorbar=dict(title="Rating /10")),
        text=[f"{r['precio_mediano']:.0f} € · ⭐ {r['rating_10']}" for r in tabla], textposition="auto",
    ))
    fig.update_layout(title=f"Precio mediano por noche en {DESTINOS[destino]['nombre']}", xaxis_title="€ / noche",
                      margin=dict(l=10, r=10, t=40, b=10), height=380)
    return fig


def mapa_ruta(tramos: list[dict]) -> go.Figure:
    fig = go.Figure(go.Scattermapbox(
        lat=[t["latitude"] for t in tramos], lon=[t["longitude"] for t in tramos], mode="lines+markers+text",
        line=dict(width=3, color="#B85C38"), marker=dict(size=14, color="#2F5D73"),
        text=[f"{i + 1}. {t['destino'].title()}" for i, t in enumerate(tramos)], textposition="top right",
    ))
    fig.update_layout(mapbox=dict(style="open-street-map", center=dict(lat=40.3, lon=0.5), zoom=4.6),
                      margin=dict(l=0, r=0, t=0, b=0), height=300, showlegend=False)
    return fig


def radar_opciones(opciones: list[dict]) -> go.Figure:
    paleta = ["#B85C38", "#2F5D73", "#6E7D4F", "#D9A441"]
    fig = go.Figure()
    for color, o in zip(paleta, opciones):
        ejes = [k for k, v in o["aspectos"].items() if v is not None]
        valores = [o["aspectos"][k] for k in ejes]
        fig.add_trace(go.Scatterpolar(r=valores + valores[:1], theta=ejes + ejes[:1], fill="toself", opacity=0.55,
                                      name=f"{o['name'][:32]} · {o['price']:.0f} €", line=dict(color=color)))
    fig.update_layout(polar=dict(radialaxis=dict(range=[0, 10], tickvals=[2, 4, 6, 8, 10])),
                      legend=dict(orientation="h", y=-0.12), margin=dict(l=40, r=40, t=40, b=30), height=440,
                      title="Comparación por aspecto (1-10)")
    return fig


def grafico_clima(c: dict) -> go.Figure:
    fechas = [f"{d['fecha'][8:10]}/{d['fecha'][5:7]}" for d in c["dias"]]
    fig = go.Figure()
    fig.add_bar(x=fechas, y=[d["lluvia"] for d in c["dias"]], name="Lluvia (mm)", marker_color="#2F5D73",
                opacity=0.45, yaxis="y2")
    fig.add_scatter(x=fechas, y=[d["max"] for d in c["dias"]], name="Máx °C", mode="lines+markers",
                    line=dict(color="#B85C38", width=3))
    fig.add_scatter(x=fechas, y=[d["min"] for d in c["dias"]], name="Mín °C", mode="lines+markers",
                    line=dict(color="#6E7D4F", width=3))
    fig.update_layout(title=dict(text=f"🌤️ {DESTINOS[c['destino']]['nombre']}: {c['max_promedio']}° / {c['min_promedio']}° · "
                                      f"{c['dias_con_lluvia']} día(s) con lluvia<br><sup>Fuente: Open-Meteo, {c['fuente']}</sup>"),
                      xaxis=dict(type="category"), yaxis=dict(title="°C"), yaxis2=dict(title="mm", overlaying="y", side="right", showgrid=False),
                      legend=dict(orientation="h", y=-0.2), margin=dict(l=10, r=10, t=50, b=10), height=320)
    return fig


async def renderizar(artifact: dict | None) -> None:
    """Convierte el artifact de cada tool en elementos visuales."""
    if not artifact:
        return
    tipo = artifact.get("tipo")
    if tipo == "opciones":
        destino = artifact["destino"].lower()
        t0 = artifact["tarjetas"][0]
        titulo = f"{DESTINOS[destino]['emoji']} {DESTINOS[destino]['nombre']} · {t0['check_in']} → {t0['check_out']}"
        await cl.Message(
            content=f"### {titulo}",
            elements=[
                cl.CustomElement(name="OpcionesAlojamiento", display="inline",
                                 props={"tarjetas": artifact["tarjetas"], "titulo": titulo,
                                        "candidatos": artifact["candidatos"], "huespedes": artifact["huespedes"],
                                        "cerca_de": artifact.get("cerca_de"), "relevamiento": artifact["relevamiento"]}),
                cl.Plotly(name=f"mapa_{destino}", figure=mapa_opciones(artifact["tarjetas"], destino, artifact.get("cerca_de")), display="inline"),
            ],
        ).send()
    elif tipo == "barrios":
        await cl.Message(content="", elements=[
            cl.Plotly(name="barrios", figure=grafico_barrios(artifact["tabla"], artifact["destino"]), display="inline")
        ]).send()
    elif tipo == "respuesta_resenas":
        await cl.Message(content="", elements=[
            cl.CustomElement(name="RespuestaResenas", display="inline",
                             props={k: v for k, v in artifact.items() if k != "tipo"})
        ]).send()
    elif tipo == "comparacion":
        await cl.Message(content="", elements=[
            cl.Plotly(name="comparacion", figure=radar_opciones(artifact["opciones"]), display="inline")
        ]).send()
    elif tipo == "clima":
        await cl.Message(content="", elements=[
            cl.Plotly(name=f"clima_{artifact['destino']}", figure=grafico_clima(artifact), display="inline")
        ]).send()
    elif tipo == "recomendaciones_lista":
        for guia in artifact["guias"]:
            await cl.Message(content="", elements=[
                cl.CustomElement(name="RecomendacionesPerfil", display="inline",
                                 props={k: v for k, v in guia.items() if k != "tipo"}),
                cl.Plotly(name=f"guia_{guia['destino']}", figure=mapa_lugares(guia["imperdibles"], guia["destino"]),
                          display="inline"),
            ]).send()
    elif tipo == "actividades":
        await cl.Message(content="", elements=[
            cl.CustomElement(name="Actividades", display="inline",
                             props={"lugares": artifact["lugares"], "destino": artifact["destino"]}),
            cl.Plotly(name=f"lugares_{artifact['destino']}", figure=mapa_lugares(artifact["lugares"], artifact["destino"]),
                      display="inline"),
        ]).send()
    elif tipo == "actividad_agendada":
        await cl.Message(content="", elements=[
            cl.CustomElement(name="Confirmacion", display="inline",
                             props={"item": artifact["item"], "aviso": artifact.get("aviso")})
        ]).send()
    elif tipo == "pdf":
        ruta = artifact["ruta"]
        await cl.Message(content="🧾 **Tu itinerario está listo.** Podés verlo acá o descargarlo.", elements=[
            cl.Pdf(name="Itinerario Ruta Ibérica", path=ruta, display="inline"),
            cl.File(name="Itinerario_Ruta_Iberica.pdf", path=ruta, display="inline"),
        ]).send()
    elif tipo == "plan" and (artifact.get("tramos") or artifact.get("actividades")):
        elementos = [cl.CustomElement(name="PlanViaje", display="inline",
                                      props={"tramos": artifact["tramos"], "total": artifact["total"],
                                             "actividades": artifact.get("actividades", [])})]
        if artifact["tramos"]:
            elementos.append(cl.Plotly(name="ruta", figure=mapa_ruta(artifact["tramos"]), display="inline"))
        await cl.Message(content="", elements=elementos,
                         actions=[cl.Action(name="pdf", payload={}, label="🧾 Descargar itinerario en PDF")]).send()


async def actualizar_itinerario() -> None:
    """Panel derecho: el itinerario en vivo (editable). Se refresca tras cada respuesta o edición."""
    datos = itinerario.resumen(cl.context.session.id)
    props = {"hospedajes": datos["hospedajes"], "actividades": datos["actividades"], "perfil": datos["perfil"],
             "total": datos["total_alojamiento"], "reservadas": datos["reservadas"], "tentativas": datos["tentativas"]}
    await cl.ElementSidebar.set_title("🧳 Tu itinerario")
    await cl.ElementSidebar.set_elements([cl.CustomElement(name="Itinerario", props=props, display="side")])


def acciones_sugeridas() -> list[cl.Action]:
    return [cl.Action(name="sugerencia", payload={"texto": texto}, label=etiqueta) for etiqueta, texto in SUGERENCIAS]


def acciones_perfil() -> list[cl.Action]:
    return [cl.Action(name="perfil", payload={"perfil": clave}, label=p["nombre"])
            for clave, p in actividades.PERFILES.items()]


def mapa_lugares(lugares: list[dict], destino: str) -> go.Figure:
    con_coords = [x for x in lugares if x.get("latitude")]
    fig = go.Figure(go.Scattermapbox(
        lat=[x["latitude"] for x in con_coords], lon=[x["longitude"] for x in con_coords], mode="markers",
        marker=dict(size=13, color="#B85C38"), text=[f"{x.get('tipo', '')} {x['nombre']}" for x in con_coords],
        hoverinfo="text"))
    lats, lons = [x["latitude"] for x in con_coords], [x["longitude"] for x in con_coords]
    extension = max(max(lats) - min(lats), max(lons) - min(lons)) if con_coords else 1
    zoom = 13 if extension < 0.02 else 12 if extension < 0.06 else 11 if extension < 0.15 else 8.3
    centro = (sum(lats) / len(lats), sum(lons) / len(lons)) if con_coords else DESTINOS[destino]["centro"]
    fig.update_layout(mapbox=dict(style="open-street-map", center=dict(lat=centro[0], lon=centro[1]), zoom=zoom),
                      margin=dict(l=0, r=0, t=0, b=0), height=300, showlegend=False)
    return fig


NOMBRES_PESOS = {
    "calidad": "⭐ Calidad (rating de Airbnb)",
    "resenas_nlp": "🧠 Reseñas analizadas con IA",
    "precio_calidad": "💶 Relación precio/calidad",
    "ubicacion": "📍 Ubicación",
    "ajuste_capacidad": "👥 Ajuste al tamaño del grupo",
}


@cl.on_chat_start
async def inicio():
    tracker = MetricsTracker()
    cl.user_session.set("tracker", tracker)
    cl.user_session.set("consultas", 0)
    cl.user_session.set("pesos", {k: v * 10 for k, v in PESOS.items()})
    await cl.ChatSettings([
        Slider(id=k, label=etiqueta, initial=PESOS[k] * 10, min=0, max=10, step=0.5,
               description="Cuánto pesa este componente en el puntaje de 1 a 10 del modelo")
        for k, etiqueta in NOMBRES_PESOS.items()
    ]).send()
    await cl.Message(content=BIENVENIDA, actions=acciones_sugeridas()).send()
    await cl.Message(content="**¿Qué tipo de viajero sos?** Te armo una guía con lugares reales para cada destino 👇",
                     actions=acciones_perfil()).send()
    await actualizar_itinerario()
    if not os.getenv("GROQ_API_KEY"):
        await cl.ErrorMessage(content="🔑 Falta configurar GROQ_API_KEY (archivo .env o variable de entorno). "
                                      "Podés ver las opciones, pero el asistente no puede responder todavía.").send()
        return
    cl.user_session.set("agente", crear_agente())


@cl.on_settings_update
async def on_settings(settings: dict):
    """Al mover los sliders se recalculan en vivo las últimas búsquedas, sin volver a llamar al agente."""
    pesos = {k: float(settings.get(k, PESOS[k] * 10)) for k in PESOS}
    cl.user_session.set("pesos", pesos)
    thread = cl.context.session.id
    busquedas = list(tools.ULTIMAS_BUSQUEDAS[thread].values())
    total = sum(pesos.values()) or 1
    resumen = " · ".join(f"{NOMBRES_PESOS[k].split(' ', 1)[1]} {v / total:.0%}" for k, v in pesos.items())
    if not busquedas:
        await cl.Message(content=f"⚙️ Pesos del modelo actualizados: {resumen}. Se aplican a tu próxima búsqueda.").send()
        return
    await cl.Message(content=f"⚙️ Pesos actualizados ({resumen}). Recalculo tus opciones…").send()
    for b in busquedas:
        _, artifact = await asyncio.to_thread(tools.ejecutar_busqueda, **b, pesos=pesos, thread=thread,
                                              callbacks=[cl.user_session.get("tracker")])
        await renderizar(artifact)


@cl.action_callback("sugerencia")
async def on_sugerencia(action: cl.Action):
    texto = action.payload["texto"]
    await cl.Message(content=texto, type="user_message").send()
    await responder(texto)


@cl.action_callback("perfil")
async def on_perfil(action: cl.Action):
    nombre = actividades.PERFILES[action.payload["perfil"]]["nombre"]
    texto = f"Soy un viajero {nombre}. ¿Qué me recomendás hacer en Barcelona, Madrid y Mallorca?"
    await cl.Message(content=texto, type="user_message").send()
    await responder(texto)


def registrar_cambio(texto: str) -> None:
    """Los cambios hechos a mano en el panel se le informan al agente en el próximo mensaje (memoria coherente)."""
    cambios = cl.user_session.get("cambios_panel") or []
    cl.user_session.set("cambios_panel", cambios + [texto])


@cl.action_callback("it_editar")
async def on_it_editar(action: cl.Action):
    p = action.payload
    item = itinerario.editar(cl.context.session.id, p["id"], **{p["campo"]: p.get("valor")})
    if item:
        registrar_cambio(f"{item['nombre']}: {p['campo']} = {p.get('valor') or 'vacío'}")
    if item and itinerario.validar_fecha(cl.context.session.id, item["destino"], item.get("fecha")):
        await cl.Message(content=f"⚠️ {itinerario.validar_fecha(cl.context.session.id, item['destino'], item['fecha'])}").send()
    await actualizar_itinerario()


@cl.action_callback("it_quitar")
async def on_it_quitar(action: cl.Action):
    item = itinerario.quitar_id(cl.context.session.id, action.payload["id"])
    if item:
        registrar_cambio(f"quitó {item['nombre']}")
        await cl.Message(content=f"🗑️ Quité **{item['nombre']}** del itinerario.").send()
    await actualizar_itinerario()


@cl.action_callback("it_quitar_hospedaje")
async def on_it_quitar_hospedaje(action: cl.Action):
    h = itinerario.quitar_hospedaje(cl.context.session.id, action.payload["destino"])
    if h:
        registrar_cambio(f"quitó el alojamiento {h['name']} en {h['destino']}")
        await cl.Message(content=f"🗑️ Quité el alojamiento **{h['name']}**. Podés pedirme otras opciones.").send()
    await actualizar_itinerario()


@cl.action_callback("pdf")
async def on_pdf(action: cl.Action):
    """Genera el PDF directamente (sin pasar por el LLM): instantáneo y sin gastar tokens."""
    thread = cl.context.session.id
    _, artifact = await asyncio.to_thread(tools.generar_pdf_itinerario.func, _Runtime(thread))
    if artifact.get("tipo") == "pdf":
        await renderizar(artifact)
    else:
        await cl.ErrorMessage(content="Todavía no hay nada en el itinerario para exportar.").send()


class _Runtime:
    """Adaptador mínimo para invocar una tool fuera del agente con el thread de la sesión."""

    def __init__(self, thread: str):
        self.config = {"configurable": {"thread_id": thread}}


@cl.action_callback("metricas")
async def on_metricas(action: cl.Action):
    tracker: MetricsTracker = cl.user_session.get("tracker")
    consultas = cl.user_session.get("consultas") or 1
    resumen = tracker.resumen(n_unidades=consultas) | {"consultas": consultas,
                                                       "segundos": round(sum(r.segundos for r in tracker.registros), 1),
                                                       "titulo": "📊 Métricas acumuladas de la sesión"}
    await cl.Message(content="", elements=[cl.CustomElement(name="Metricas", props=resumen, display="inline")]).send()


@cl.on_message
async def on_message(message: cl.Message):
    await responder(message.content)


async def responder(texto: str) -> None:
    agente = cl.user_session.get("agente")
    if agente is None:
        await cl.ErrorMessage(content="🔑 El asistente no está configurado: falta GROQ_API_KEY.").send()
        return
    tracker: MetricsTracker = cl.user_session.get("tracker")
    config = {"configurable": {"thread_id": cl.context.session.id, "pesos": cl.user_session.get("pesos")},
              "callbacks": [tracker]}
    n_previos = len(tracker.registros)
    inicio = time.perf_counter()
    respuesta = cl.Message(content="")
    pasos: dict[str, cl.Step] = {}

    cambios = cl.user_session.get("cambios_panel") or []
    if cambios:
        cl.user_session.set("cambios_panel", [])
        texto = (f"[Nota: el usuario editó el itinerario desde el panel: {'; '.join(cambios)}. "
                 f"Lo anterior sobre esos ítems ya no vale.]\n{texto}")

    try:
        async for modo, dato in agente.astream({"messages": [{"role": "user", "content": texto}]},
                                               config=config, stream_mode=["messages", "updates"]):
            if modo == "messages":
                chunk, meta = dato
                if isinstance(chunk, AIMessageChunk) and meta.get("langgraph_node") == "model" and isinstance(chunk.content, str) and chunk.content:
                    await respuesta.stream_token(chunk.content)
                continue
            for actualizacion in dato.values():
                for msg in (actualizacion or {}).get("messages", []):
                    if isinstance(msg, AIMessage) and msg.tool_calls:
                        for llamada in msg.tool_calls:
                            paso = cl.Step(name=NOMBRES_TOOLS.get(llamada["name"], llamada["name"]), type="tool")
                            paso.input = json.dumps(llamada["args"], ensure_ascii=False, indent=1)
                            await paso.send()
                            pasos[llamada["id"]] = paso
                    elif isinstance(msg, ToolMessage):
                        paso = pasos.get(msg.tool_call_id)
                        if paso:
                            paso.output = str(msg.content)[:2000]
                            await paso.update()
                        if respuesta.content:  # cerrar el texto previo para que las tarjetas queden en orden
                            await respuesta.send()
                            respuesta = cl.Message(content="")
                        await renderizar(msg.artifact)
    except groq.RateLimitError:
        await cl.ErrorMessage(content="⏳ Alcanzamos el límite gratuito de consultas por minuto de Groq. "
                                      "Esperá unos segundos y volvé a intentarlo.").send()
        return
    except groq.APIConnectionError:
        await cl.ErrorMessage(content="🌐 No pude conectarme con el modelo. Revisá tu conexión e intentá de nuevo.").send()
        return
    except Exception as e:  # cualquier otro error se informa sin romper la sesión
        traceback.print_exc()
        await cl.ErrorMessage(content=f"😕 Algo salió mal procesando tu pedido: {type(e).__name__}. Probá reformularlo.").send()
        return

    consultas = (cl.user_session.get("consultas") or 0) + 1
    cl.user_session.set("consultas", consultas)
    nuevos = MetricsTracker(registros=tracker.registros[n_previos:]).resumen(n_unidades=1)
    segundos = time.perf_counter() - inicio
    pie = (f"\n\n<span class='ri-metricas'>⚡ {segundos:.1f} s · {nuevos['tokens_totales']:,} tokens "
           f"({nuevos['tokens_entrada']:,} entrada / {nuevos['tokens_salida']:,} salida) · "
           f"US$ {nuevos['costo_total_usd']:.4f} simulado</span>").replace(",", ".")
    await respuesta.stream_token(pie)
    await actualizar_itinerario()
    respuesta.actions = [cl.Action(name="metricas", payload={}, label="📊 Métricas de la sesión")]
    if itinerario.HOSPEDAJES[cl.context.session.id] or itinerario.ACTIVIDADES[cl.context.session.id]:
        respuesta.actions.append(cl.Action(name="pdf", payload={}, label="🧾 Itinerario en PDF"))
    await respuesta.send()
