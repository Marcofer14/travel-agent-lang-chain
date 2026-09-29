"""Actividades reales (OSM), perfiles, reservas simuladas, auto e itinerario en PDF (sin LLM)."""
import json

import pytest

from core import actividades, itinerario


class Runtime:
    def __init__(self, thread):
        self.config = {"configurable": {"thread_id": thread}}


def test_catalogo_de_actividades():
    df = actividades.catalogo()
    assert len(df) > 1000
    assert set(df["destino"]) == {"barcelona", "madrid", "mallorca"}
    assert set(df["categoria"]) <= set(actividades.CATEGORIAS)
    assert df[["latitude", "longitude"]].notna().all().all()
    assert (df[(df["destino"] == "madrid")]["categoria"] != "playa").all()     # Madrid no tiene playas


def test_ranking_por_popularidad():
    assert "Museo del Prado" in list(actividades.buscar("madrid", "museo", n=3)["nombre"])
    assert actividades.buscar("mallorca", "playa", n=1).iloc[0]["nombre"] == "Playa de es Trenc"


def test_perfiles_y_busquedas():
    assert len(actividades.PERFILES) == 8
    assert actividades.normalizar_perfil("me encanta la comida") == "foodie"
    assert actividades.normalizar_perfil("🖼️ Fan de los museos") == "museos"
    playero = actividades.buscar("mallorca", perfil="playero", n=6)
    assert set(playero["categoria"]) <= set(actividades.PERFILES["playero"]["categorias"])
    assert playero["categoria"].value_counts().max() <= 3                         # variedad
    cerca = actividades.buscar("barcelona", "museo", cerca_de="Sagrada Familia", n=3)
    assert (cerca["dist_km"] < 3).all()
    assert actividades.encontrar("madrid", "reina sofia")["nombre"].startswith("Museo Nacional Centro de Arte Reina")


def test_recomendaciones_pregeneradas_ancladas_en_datos_reales():
    recs = actividades.recomendaciones_pregeneradas()
    assert {len(v) for v in recs.values()} == {8}                                # 3 destinos × 8 perfiles
    for destino, perfiles in recs.items():
        nombres = set(actividades.catalogo().query("destino == @destino")["nombre"])
        for rec in perfiles.values():
            assert len(rec["imperdibles"]) >= 3
            assert all(i["nombre"] in nombres for i in rec["imperdibles"])      # nada inventado


def test_flujo_completo_itinerario_y_pdf(sin_llm, tmp_path):
    rt = Runtime("pytest-itinerario")
    _, a = sin_llm.ejecutar_busqueda("madrid", "2026-10-13", "2026-10-16", 2, thread="pytest-itinerario")
    sin_llm.seleccionar_alojamiento.func("madrid", a["tarjetas"][0]["id"], rt)

    contenido, art = sin_llm.recomendaciones_perfil.func("museos", "madrid", rt)
    assert art["tipo"] == "recomendaciones_lista" and art["guias"][0]["imperdibles"][0].get("latitude")
    _, todas = sin_llm.recomendaciones_perfil.func("foodie", "todos", rt)
    assert [g["destino"] for g in todas["guias"]] == ["barcelona", "madrid", "mallorca"]
    contenido, art = sin_llm.buscar_actividades.func("madrid", "restaurante", None, None, "tapas")
    assert art["tipo"] == "actividades" and len(art["lugares"]) > 0

    msg, ok = sin_llm.agendar_actividad.func("madrid", "Museo del Prado", "2026-10-14", "10:00", True, None, rt)
    assert ok["item"]["estado"] == "reservada" and ok["item"]["codigo"].startswith("RI-")
    msg, _ = sin_llm.agendar_actividad.func("madrid", "Teatro Real", None, None, False, None, rt)
    assert "tentativa" in msg
    msg, _ = sin_llm.agendar_actividad.func("madrid", "Museo Sorolla", None, None, True, None, rt)
    assert "necesito la fecha" in msg                                             # no reserva sin fecha
    msg, fuera = sin_llm.agendar_actividad.func("madrid", "Parque del Retiro", "2026-10-30", None, False, None, rt)
    assert fuera["aviso"] and "no estás en Madrid" in fuera["aviso"]
    msg, auto = sin_llm.reservar_auto.func("madrid", "2026-10-13", "2026-10-16", "10:00", "18:00", None, None, rt)
    assert auto["item"]["categoria"] == "alquiler_auto" and auto["item"]["codigo"]
    msg, _ = sin_llm.quitar_del_itinerario.func("Parque del Retiro", rt)
    assert "Quitado" in msg

    _, plan = sin_llm.resumen_viaje.func(rt)
    assert len(plan["actividades"]) == 3 and len(plan["tramos"]) == 1
    _, pdf = sin_llm.generar_pdf_itinerario.func(rt)
    assert pdf["tipo"] == "pdf"
    from pathlib import Path
    datos = Path(pdf["ruta"]).read_bytes()
    assert datos.startswith(b"%PDF") and len(datos) > 20_000


def test_pdf_sin_datos_da_error_amigable(sin_llm):
    contenido, art = sin_llm.generar_pdf_itinerario.func(Runtime("pytest-vacio"))
    assert art["tipo"] == "error" and "No hay nada" in contenido


def test_componentes_nuevos_existen():
    from pathlib import Path
    elementos = {p.stem for p in Path("public/elements").glob("*.jsx")}
    assert {"Actividades", "RecomendacionesPerfil", "Confirmacion"} <= elementos


def test_artifacts_serializables_por_la_memoria_del_agente(sin_llm):
    """La memoria (checkpointer) guarda los ToolMessage con msgpack: nada de tipos numpy en los artifacts."""
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    serde, rt = JsonPlusSerializer(), Runtime("pytest-serde")
    _, a = sin_llm.ejecutar_busqueda("barcelona", "2026-10-10", "2026-10-13", 2, thread="pytest-serde")
    artifacts = [a,
                 sin_llm.recomendaciones_perfil.func("foodie", "todos", rt)[1],
                 sin_llm.buscar_actividades.func("barcelona", "museo", None, "Sagrada Familia", None)[1],
                 sin_llm.agendar_actividad.func("barcelona", "Museo Picasso", "2026-10-11", "11:00", True, None, rt)[1],
                 sin_llm.reservar_auto.func("barcelona", "2026-10-10", "2026-10-13", None, None, None, None, rt)[1],
                 sin_llm.comparar_opciones.func([t["id"] for t in a["tarjetas"]])[1]]
    for art in artifacts:
        serde.dumps_typed(art)
