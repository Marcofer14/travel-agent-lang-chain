"""Tools del agente. Devuelven (contenido para el LLM, artifact para la interfaz) con response_format='content_and_artifact':
el LLM recibe un resumen compacto (ahorra tokens) y Chainlit recibe los datos completos para dibujar tarjetas y gráficos."""
import json
from collections import defaultdict
from datetime import date

import pandas as pd
from langchain.tools import ToolRuntime, tool

from core import actividades, itinerario, lugares, scoring
from core.clima import clima
from core.config import DESTINOS, PROCESSED
from core.nlp import cadena_preguntas, enriquecer, guardar_enriquecido, preparar_entradas

ETIQUETAS_CORTAS = {"recomendada": "🧭 Recomendada", "mejor_rateada": "⭐ Mejor rateada",
                    "mas_barata": "💸 Más barata", "mas_cara": "💎 Más cara"}
ETIQUETAS = {
    "recomendada": "🧭 Recomendada por nuestro modelo",
    "mejor_rateada": "⭐ Mejor rateada",
    "mas_barata": "💸 Más barata",
    "mas_cara": "💎 Más cara",
}
FECHA_RELEVAMIENTO = {"barcelona": "24/06/2026", "madrid": "20/06/2026", "mallorca": "23/06/2026"}

# Estado por sesión (thread_id): últimas opciones mostradas y últimos parámetros de búsqueda
# (el plan elegido — hospedajes, actividades y auto — vive en core/itinerario.py)
ULTIMAS_OPCIONES: dict[str, dict[str, list[dict]]] = defaultdict(dict)
ULTIMAS_BUSQUEDAS: dict[str, dict[str, dict]] = defaultdict(dict)


def _callbacks(runtime: ToolRuntime | None):
    """Propaga el MetricsTracker de la sesión a las llamadas al LLM que se hacen dentro de las tools."""
    try:
        return runtime.config.get("callbacks")
    except Exception:
        return None


def _thread(runtime: ToolRuntime | None) -> str:
    try:
        return runtime.config["configurable"]["thread_id"]
    except Exception:
        return "default"


def _pesos(runtime: ToolRuntime | None) -> dict | None:
    """Pesos del puntaje elegidos por el usuario con los sliders de la interfaz."""
    try:
        return runtime.config["configurable"].get("pesos")
    except Exception:
        return None


def _limpio(valor):
    if isinstance(valor, float) and pd.isna(valor):
        return None
    if hasattr(valor, "tolist"):
        return valor.tolist()
    return valor


def _id(listing_id) -> int | None:
    """Los ids de Airbnb tienen hasta 19 dígitos: se manejan como texto porque como número JSON pierden precisión."""
    texto = str(listing_id).strip().strip('"').split(".")[0]
    if not texto.isdigit():
        return None
    ids = scoring.datos()["pool"]["id"]
    if int(texto) in set(ids):
        return int(texto)
    # Recuperación si el id llegó redondeado (p. ej. ...712600 en vez de ...712747): coincidencia por prefijo
    candidatos = ids[ids.astype(str).str.startswith(texto[:15])] if len(texto) >= 16 else ids.iloc[0:0]
    return int(candidatos.iloc[0]) if len(candidatos) == 1 else None


def _fila(listing_id) -> pd.Series | None:
    lid = _id(listing_id)
    if lid is None:
        return None
    pool = scoring.datos()["pool"]
    return pool[pool["id"] == lid].iloc[0]


def _tarjeta(etiqueta: str, fila, noches: int, check_in: str, check_out: str, cerca_de: str | None) -> dict:
    campos = ["id", "name", "destino", "barrio", "latitude", "longitude", "room_type", "property_type", "accommodates",
              "bedrooms", "beds", "bathrooms_text", "price", "picture_url", "listing_url", "puntaje", "rating_airbnb_10",
              "number_of_reviews", "host_is_superhost", "sentimiento_general", "resumen", "pros", "contras",
              "ideal_para", "alerta", "cita_textual", "tiene_nlp"]
    t = {c: _limpio(fila.get(c)) for c in campos}
    t["id"] = str(int(t["id"]))
    cerca = lugares.cercanias(fila, t["destino"])
    if cerca_de:
        km = float(lugares.haversine_km(float(fila["latitude"]), float(fila["longitude"]),
                                        *lugares.LUGARES[t["destino"]][cerca_de]))
        cerca = [{"lugar": cerca_de, "km": round(km, 2), "texto": lugares.texto_distancia(km, t["destino"])}] + \
                [c for c in cerca if c["lugar"] != cerca_de][:2]
    t |= {"etiqueta": etiqueta, "titulo_etiqueta": ETIQUETAS[etiqueta],
          "etiqueta_corta": ETIQUETAS_CORTAS[etiqueta], "noches": noches, "check_in": check_in,
          "check_out": check_out, "total": round(float(fila["price"]) * noches, 2),
          "detalle_puntaje": scoring.detalle_puntaje(fila), "cercanias": cerca}
    return t


def _enriquecer_faltantes(filas: list, callbacks=None) -> None:
    """Análisis NLP en el momento (con .batch) para las opciones que todavía no estaban analizadas."""
    faltan = [f for f in filas if not bool(f.get("tiene_nlp"))]
    if not faltan:
        return
    resenas = pd.read_parquet(PROCESSED / "reviews_pool.parquet")
    pool = pd.DataFrame(faltan)[["id", "destino", "name"]]
    entradas = preparar_entradas(pool, resenas[resenas["listing_id"].isin(pool["id"])])
    try:
        guardar_enriquecido(enriquecer(entradas, max_concurrency=4, callbacks=callbacks, limitar=False))
    except Exception as e:  # sin análisis NLP las tarjetas se muestran igual, con el puntaje de respaldo
        print(f"[aviso] no se pudo enriquecer en vivo: {e}")
        return
    scoring.recargar()


def _resumen_llm(t: dict) -> dict:
    """Versión compacta para el LLM (la interfaz recibe la tarjeta completa por el artifact)."""
    datos = {k: t[k] for k in ["etiqueta", "id", "name", "barrio", "price", "puntaje"] if k in t}
    if t.get("resumen"):
        datos["resumen"] = t["resumen"][:110]
    if t.get("alerta"):
        datos["alerta"] = t["alerta"][:80]
    if t.get("cercanias"):
        datos["cerca"] = f"{t['cercanias'][0]['lugar']}: {t['cercanias'][0]['texto']}"
    return datos


def ejecutar_busqueda(destino: str, check_in: str, check_out: str, huespedes: int,
                      presupuesto_max_noche: float | None = None, cerca_de: str | None = None,
                      pesos: dict | None = None, thread: str = "default", callbacks=None) -> tuple[str, dict]:
    """Lógica de búsqueda compartida por la tool y por la interfaz (recalcular al mover los sliders)."""
    destino = destino.lower().strip()
    try:
        df = scoring.candidatos(destino, check_in, check_out, huespedes, presupuesto_max_noche, pesos)
    except ValueError as e:
        return f"Error: {e}", {"tipo": "error", "mensaje": str(e)}

    lugar = None
    if cerca_de:
        lugar = lugares.buscar_lugar(destino, cerca_de)
        if lugar is None:
            opciones = ", ".join(lugares.LUGARES[destino])
            return (f"No reconozco '{cerca_de}' en {destino}. Lugares disponibles: {opciones}.",
                    {"tipo": "error", "mensaje": f"Lugar desconocido: {cerca_de}"})
        lat, lon = lugares.LUGARES[destino][lugar]
        df = df.assign(dist_km=lugares.haversine_km(df["latitude"], df["longitude"], lat, lon))
        cerca = df[df["dist_km"] <= lugares.RADIO_CERCA_KM[destino]]
        df = cerca if len(cerca) >= 4 else df.nsmallest(12, "dist_km")

    noches = (date.fromisoformat(check_out) - date.fromisoformat(check_in)).days
    if df.empty:
        msg = (f"No hay alojamientos disponibles en {destino} del {check_in} al {check_out} para {huespedes} "
               f"huéspedes{' con ese presupuesto' if presupuesto_max_noche else ''}. Sugerí cambiar fechas o presupuesto.")
        return msg, {"tipo": "sin_resultados", "mensaje": msg}

    elegidas = scoring.elegir_cuatro(df)
    _enriquecer_faltantes([f for _, f in elegidas], callbacks)
    ids = [f["id"] for _, f in elegidas]
    actualizados = scoring.puntuar(scoring.datos()["pool"].query("id in @ids"), huespedes, pesos).set_index("id")
    tarjetas = [_tarjeta(et, actualizados.loc[f["id"]].to_dict() | {"id": f["id"]}, noches, check_in, check_out, lugar)
                for et, f in elegidas]
    ULTIMAS_OPCIONES[thread][destino] = tarjetas
    ULTIMAS_BUSQUEDAS[thread][destino] = {"destino": destino, "check_in": check_in, "check_out": check_out,
                                          "huespedes": huespedes, "presupuesto_max_noche": presupuesto_max_noche,
                                          "cerca_de": cerca_de}

    contenido = {
        "destino": destino, "check_in": check_in, "check_out": check_out, "noches": noches, "huespedes": huespedes,
        "cerca_de": lugar, "candidatos_evaluados": len(df), "opciones": [_resumen_llm(t) for t in tarjetas],
    }
    artifact = {"tipo": "opciones", "destino": destino, "huespedes": huespedes, "candidatos": len(df),
                "tarjetas": tarjetas, "cerca_de": lugar, "relevamiento": FECHA_RELEVAMIENTO[destino],
                "pesos": scoring.normalizar_pesos(pesos)}
    return json.dumps(contenido, ensure_ascii=False, default=str), artifact


@tool(response_format="content_and_artifact")
def buscar_opciones(destino: str, check_in: str, check_out: str, huespedes: int,
                    presupuesto_max_noche: float | None = None, cerca_de: str | None = None,
                    runtime: ToolRuntime = None):
    """Busca alojamientos disponibles (destino: barcelona/madrid/mallorca; fechas YYYY-MM-DD) para todos los huéspedes. Devuelve 4 opciones con puntaje 1-10. cerca_de: punto de interés opcional. Una llamada por destino."""
    return ejecutar_busqueda(destino, check_in, check_out, huespedes, presupuesto_max_noche, cerca_de,
                             _pesos(runtime), _thread(runtime), _callbacks(runtime))


@tool(response_format="content_and_artifact")
def detalle_alojamiento(listing_id: str, runtime: ToolRuntime = None):
    """Análisis general de reseñas de un alojamiento (pros, contras, perfiles, alertas)."""
    fila = _fila(listing_id)
    if fila is None:
        return (f"No encontré el alojamiento {listing_id}. Usá exactamente uno de los ids (texto) devueltos por "
                f"buscar_opciones; no reintentes con el mismo id."), {"tipo": "error"}
    if not bool(fila.get("tiene_nlp")):
        _enriquecer_faltantes([fila], _callbacks(runtime))
        fila = _fila(listing_id)
    info_id = str(int(fila["id"]))
    campos = ["name", "destino", "barrio", "sentimiento_general", "resumen", "pros", "contras", "ideal_para",
              "alerta", "cita_textual", "puntaje_limpieza", "puntaje_ubicacion", "puntaje_tranquilidad",
              "puntaje_anfitrion", "puntaje_fidelidad", "number_of_reviews", "listing_url"]
    info = {"id": info_id} | {c: _limpio(fila.get(c)) for c in campos}
    info["cerca_de"] = lugares.cercanias(fila, fila["destino"], n=3)
    return json.dumps(info, ensure_ascii=False, default=str), {"tipo": "detalle", "info": info}


@tool(response_format="content_and_artifact")
def consultar_resenas(listing_id: str, pregunta: str, runtime: ToolRuntime = None):
    """Responde una pregunta puntual sobre un alojamiento (ruido, ascensor, limpieza...) citando reseñas reales."""
    fila = _fila(listing_id)
    if fila is None:
        return f"No encontré el alojamiento {listing_id} en el catálogo.", {"tipo": "error"}
    resenas = pd.read_parquet(PROCESSED / "reviews_qa.parquet", filters=[("listing_id", "==", int(fila["id"]))])
    if resenas.empty:
        return "Ese alojamiento no tiene reseñas disponibles.", {"tipo": "error"}
    try:
        salida = cadena_preguntas().invoke(
            {"pregunta": pregunta, "nombre": fila["name"], "resenas": resenas},
            config={"callbacks": _callbacks(runtime)},
        )
    except Exception as e:
        return f"No pude analizar las reseñas en este momento ({type(e).__name__}).", {"tipo": "error"}
    r = salida["respuesta"]
    info = {"listing_id": str(int(fila["id"])), "nombre": fila["name"], "pregunta": pregunta, "veredicto": r.veredicto,
            "respuesta": r.respuesta, "evidencia": [c.model_dump() for c in r.evidencia],
            "n_relevantes": salida["n_relevantes"], "n_total": salida["n_total"], "palabras": salida["palabras"]}
    contenido = {k: info[k] for k in ["veredicto", "respuesta", "evidencia", "n_relevantes", "n_total"]}
    return json.dumps(contenido, ensure_ascii=False), {"tipo": "respuesta_resenas", **info}


@tool(response_format="content_and_artifact")
def comparar_opciones(listing_ids: list[str]):
    """Compara 2 a 4 alojamientos por aspecto (gráfico radar)."""
    aspectos = {"Limpieza": ("puntaje_limpieza", "review_scores_cleanliness"),
                "Ubicación": ("puntaje_ubicacion", "review_scores_location"),
                "Tranquilidad": ("puntaje_tranquilidad", None),
                "Anfitrión": ("puntaje_anfitrion", "review_scores_communication"),
                "Fidelidad al anuncio": ("puntaje_fidelidad", "review_scores_accuracy")}
    filas = [f for f in (_fila(i) for i in listing_ids[:4]) if f is not None]
    if len(filas) < 2:
        return "Necesito al menos 2 alojamientos válidos para comparar.", {"tipo": "error"}
    comparacion = []
    for f in filas:
        valores = {}
        for nombre, (col_nlp, col_airbnb) in aspectos.items():
            v = f.get(col_nlp)
            if (v is None or pd.isna(v)) and col_airbnb:
                v = f.get(col_airbnb) * 2  # respaldo: subrating de Airbnb llevado a escala 10
            valores[nombre] = None if v is None or pd.isna(v) else round(float(v), 1)
        valores["Precio/calidad"] = round(float(f["c_precio_calidad"]) * 10, 1)
        comparacion.append({"id": str(int(f["id"])), "name": f["name"], "destino": f["destino"], "price": float(f["price"]),
                            "rating_airbnb_10": round(float(f["review_scores_rating"]) * 2, 1), "aspectos": valores})
    return json.dumps(comparacion, ensure_ascii=False), {"tipo": "comparacion", "opciones": comparacion}


@tool(response_format="content_and_artifact")
def clima_destino(destino: str, check_in: str, check_out: str):
    """Clima esperado en un destino para las fechas (pronóstico o histórico)."""
    destino = destino.lower().strip()
    if destino not in DESTINOS:
        return f"Destino no disponible. Opciones: {', '.join(DESTINOS)}", {"tipo": "error"}
    try:
        datos = clima(destino, check_in, check_out)
    except Exception as e:
        return f"No pude consultar el clima ahora ({type(e).__name__}).", {"tipo": "error"}
    contenido = {k: v for k, v in datos.items() if k != "dias"}
    return json.dumps(contenido, ensure_ascii=False), {"tipo": "clima", **datos}


@tool(response_format="content_and_artifact")
def comparar_barrios(destino: str, huespedes: int = 2):
    """Compara barrios de un destino: precio mediano y rating."""
    destino = destino.lower().strip()
    if destino not in DESTINOS:
        return f"Destino no disponible. Opciones: {', '.join(DESTINOS)}", {"tipo": "error"}
    pool = scoring.datos()["pool"]
    df = pool[(pool["destino"] == destino) & (pool["accommodates"] >= huespedes)]
    tabla = (df.groupby("barrio").agg(alojamientos=("id", "size"), precio_mediano=("price", "median"),
                                     rating_10=("review_scores_rating", lambda s: round(s.mean() * 2, 2)),
                                     ubicacion_10=("review_scores_location", lambda s: round(s.mean() * 2, 2)))
             .query("alojamientos >= 5").sort_values("rating_10", ascending=False).round(1).reset_index())
    top = tabla.head(10)
    return (json.dumps({"destino": destino, "barrios": top.to_dict("records")}, ensure_ascii=False),
            {"tipo": "barrios", "destino": destino, "tabla": top.to_dict("records")})


@tool(response_format="content_and_artifact")
def seleccionar_alojamiento(destino: str, listing_id: str, runtime: ToolRuntime = None):
    """Registra el alojamiento elegido por el usuario para un destino."""
    thread = _thread(runtime)
    opciones = ULTIMAS_OPCIONES[thread].get(destino.lower(), [])
    lid = _id(listing_id)
    elegida = next((t for t in opciones if lid is not None and int(t["id"]) == lid), None)
    if elegida is None:
        return ("Ese alojamiento no está entre las últimas opciones mostradas para ese destino. "
                "Buscá opciones primero."), {"tipo": "error"}
    itinerario.HOSPEDAJES[thread][destino.lower()] = elegida
    return (f"Guardado: {elegida['name']} en {destino} ({elegida['noches']} noches, {elegida['total']} €).",
            {"tipo": "seleccion", "tarjeta": elegida})


# ------------------------------------------------------------------ actividades, perfiles y reservas

def _guia(destino: str, clave: str) -> dict | None:
    rec = actividades.recomendaciones_pregeneradas().get(destino, {}).get(clave)
    if not rec:
        return None
    imperdibles = []
    for imp in rec["imperdibles"]:
        fila = actividades.encontrar(destino, imp["nombre"])
        imperdibles.append((actividades.ficha(fila) if fila is not None else {"nombre": imp["nombre"]}) | imp)
    return {"tipo": "recomendaciones", "destino": destino, "perfil": actividades.PERFILES[clave]["nombre"],
            **rec, "imperdibles": imperdibles}


@tool(response_format="content_and_artifact")
def recomendaciones_perfil(perfil: str, destino: str = "todos", runtime: ToolRuntime = None):
    """Guía por tipo de viajero (playero, museos, foodie, cultural, caminador, familiar, nocturno, generalista). destino: barcelona/madrid/mallorca o 'todos'."""
    clave = actividades.normalizar_perfil(perfil)
    destino = (destino or "todos").lower().strip()
    destinos = list(DESTINOS) if destino not in DESTINOS else [destino]
    if clave is None:
        return f"Perfil no reconocido. Opciones: {', '.join(actividades.PERFILES)}.", {"tipo": "error"}
    itinerario.PERFILES_SESION[_thread(runtime)] = actividades.PERFILES[clave]["nombre"]
    guias = [g for d in destinos if (g := _guia(d, clave))]
    if not guias:
        return "No hay recomendaciones pregeneradas para ese perfil; usá buscar_actividades.", {"tipo": "error"}
    contenido = {"perfil": actividades.PERFILES[clave]["nombre"], "guias": [
        {"destino": g["destino"], "titular": g["titular"], "imperdibles": [i["nombre"] for i in g["imperdibles"]],
         "barrios": g["barrios_sugeridos"]} for g in guias]}
    return json.dumps(contenido, ensure_ascii=False), {"tipo": "recomendaciones_lista", "guias": guias}


@tool(response_format="content_and_artifact")
def buscar_actividades(destino: str, categoria: str | None = None, perfil: str | None = None,
                       cerca_de: str | None = None, texto: str | None = None):
    """Busca lugares reales. categoria: museo, galeria, teatro, monumento, mirador, restaurante, mercado, playa, parque, vida_nocturna, familiar, alquiler_auto. texto: nombre o cocina. cerca_de: punto de interés."""
    destino = destino.lower().strip()
    if destino not in DESTINOS:
        return f"Destino no disponible. Opciones: {', '.join(DESTINOS)}", {"tipo": "error"}
    if categoria and categoria not in actividades.CATEGORIAS:
        return f"Categoría no válida. Opciones: {', '.join(actividades.CATEGORIAS)}", {"tipo": "error"}
    df = actividades.buscar(destino, categoria, actividades.normalizar_perfil(perfil), cerca_de, texto)
    if df.empty:
        return "No encontré lugares con esos filtros.", {"tipo": "sin_resultados"}
    fichas = [actividades.ficha(f) for _, f in df.iterrows()]
    contenido = [{k: f[k] for k in ["nombre", "tipo", "horario", "cocina", "dist_km"] if f.get(k)} for f in fichas]
    return (json.dumps({"destino": destino, "lugares": contenido,
                        }, ensure_ascii=False),
            {"tipo": "actividades", "destino": destino, "lugares": fichas})


@tool(response_format="content_and_artifact")
def agendar_actividad(destino: str, nombre: str, fecha: str | None = None, hora: str | None = None,
                      reservar: bool = False, notas: str | None = None, runtime: ToolRuntime = None):
    """Agrega una actividad al itinerario. reservar=True la deja reservada (simulada, requiere fecha); si no, tentativa. fecha YYYY-MM-DD y hora HH:MM opcionales."""
    destino, thread = destino.lower().strip(), _thread(runtime)
    if destino not in DESTINOS:
        return f"Destino no disponible. Opciones: {', '.join(DESTINOS)}", {"tipo": "error"}
    if reservar and not fecha:
        return "Para reservar necesito la fecha (y idealmente la hora). Preguntásela al usuario.", {"tipo": "error"}
    fila = actividades.encontrar(destino, nombre)
    datos = actividades.ficha(fila) if fila is not None else {"nombre": nombre, "categoria": "otra", "destino": destino}
    item = itinerario.agregar(thread, datos | {
        "tipo_texto": actividades.CATEGORIAS.get(datos.get("categoria"), "Actividad"), "fecha": fecha, "hora": hora,
        "estado": "reservada" if reservar else "tentativa", "notas": notas})
    aviso = itinerario.validar_fecha(thread, destino, fecha)
    texto = (f"{'Reservado (simulado, código ' + item['codigo'] + ')' if reservar else 'Agregado como tentativa'}: "
             f"{item['nombre']}" + (f" el {fecha}" if fecha else "") + (f" a las {hora}" if hora else "") + ".")
    if datos.get("horario"):
        texto += f" Horario publicado: {datos['horario']}."
    if aviso:
        texto += " " + aviso
    return texto, {"tipo": "actividad_agendada", "item": item, "aviso": aviso}


@tool(response_format="content_and_artifact")
def reservar_auto(destino: str, fecha_retiro: str, fecha_devolucion: str, hora_retiro: str | None = None,
                  hora_devolucion: str | None = None, empresa: str | None = None, tipo_auto: str | None = None,
                  runtime: ToolRuntime = None):
    """Reserva simulada de auto de alquiler (fechas YYYY-MM-DD, horas HH:MM opcionales)."""
    destino, thread = destino.lower().strip(), _thread(runtime)
    agencias = actividades.buscar(destino, "alquiler_auto", cerca_de=None if empresa else "aeropuerto",
                                  texto=empresa, n=5)
    if agencias.empty:
        return "No encontré agencias de alquiler de autos en ese destino.", {"tipo": "error"}
    agencia = actividades.ficha(agencias.iloc[0])
    item = itinerario.agregar(thread, agencia | {
        "tipo_texto": "Alquiler de auto", "fecha": fecha_retiro, "hora": hora_retiro,
        "fecha_devolucion": fecha_devolucion, "hora_devolucion": hora_devolucion,
        "tipo_auto": tipo_auto, "estado": "reservada"})
    return (f"Auto reservado (simulado) con {agencia['nombre']}, código {item['codigo']}: retiro {fecha_retiro} "
            f"{hora_retiro or ''}, devolución {fecha_devolucion} {hora_devolucion or ''}. "
            f"Otras agencias: {', '.join(agencias['nombre'].iloc[1:4])}.",
            {"tipo": "actividad_agendada", "item": item})


@tool(response_format="content_and_artifact")
def quitar_del_itinerario(nombre: str, runtime: ToolRuntime = None):
    """Quita del itinerario una actividad o auto por nombre."""
    item = itinerario.quitar(_thread(runtime), nombre)
    if item is None:
        return f"No encontré '{nombre}' en el itinerario.", {"tipo": "error"}
    return f"Quitado del itinerario: {item['nombre']}.", {"tipo": "quitado", "item": item}


@tool(response_format="content_and_artifact")
def resumen_viaje(runtime: ToolRuntime = None):
    """Plan completo: alojamientos, actividades, auto y costo."""
    datos = itinerario.resumen(_thread(runtime))
    if not datos["hospedajes"] and not datos["actividades"]:
        return "Todavía no hay nada en el plan.", {"tipo": "plan", "tramos": []}
    contenido = {"alojamientos": [{k: t[k] for k in ["destino", "name", "check_in", "check_out", "noches", "total"]}
                                  for t in datos["hospedajes"]],
                 "actividades": [{k: a.get(k) for k in ["destino", "nombre", "fecha", "hora", "estado"]}
                                 for a in datos["actividades"]],
                 "costo_alojamiento_eur": datos["total_alojamiento"]}
    return json.dumps(contenido, ensure_ascii=False), {"tipo": "plan", "tramos": datos["hospedajes"],
                                                      "total": datos["total_alojamiento"],
                                                      "actividades": datos["actividades"]}


@tool(response_format="content_and_artifact")
def generar_pdf_itinerario(runtime: ToolRuntime = None):
    """Genera el PDF final del itinerario."""
    thread = _thread(runtime)
    datos = itinerario.resumen(thread)
    if not datos["hospedajes"] and not datos["actividades"]:
        return "No hay nada en el itinerario todavía: elegí alojamientos o actividades primero.", {"tipo": "error"}
    try:
        ruta = itinerario.generar_pdf(thread)
    except Exception as e:
        return f"No pude generar el PDF ({type(e).__name__}).", {"tipo": "error"}
    return (f"PDF generado con {len(datos['hospedajes'])} alojamientos y {len(datos['actividades'])} actividades.",
            {"tipo": "pdf", "ruta": str(ruta)})


TOOLS = [buscar_opciones, detalle_alojamiento, consultar_resenas, comparar_opciones, clima_destino, comparar_barrios,
         seleccionar_alojamiento, recomendaciones_perfil, buscar_actividades, agendar_actividad, reservar_auto,
         quitar_del_itinerario, resumen_viaje, generar_pdf_itinerario]
