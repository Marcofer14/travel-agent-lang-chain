"""Tools del agente e interfaz (sin LLM: el análisis en vivo se desactiva con el fixture sin_llm)."""
import json

import pytest


def test_busqueda_devuelve_cuatro_tarjetas_completas(sin_llm):
    contenido, artifact = sin_llm.ejecutar_busqueda("madrid", "2026-10-13", "2026-10-16", 2,
                                                    cerca_de="Museo del Prado", thread="t1")
    datos = json.loads(contenido)
    assert artifact["tipo"] == "opciones" and len(artifact["tarjetas"]) == 4
    assert datos["cerca_de"] == "Museo del Prado"
    for t in artifact["tarjetas"]:
        assert isinstance(t["id"], str) and t["id"].isdigit()      # ids como texto (19 dígitos)
        assert t["accommodates"] >= 2
        assert t["picture_url"].startswith("https://") and t["listing_url"].startswith("https://www.airbnb")
        assert 1 <= t["puntaje"] <= 10
        assert t["cercanias"][0]["lugar"] == "Museo del Prado"
        assert t["total"] == pytest.approx(t["price"] * 3, rel=1e-6)


def test_id_redondeado_se_recupera(sin_llm):
    pool = sin_llm.scoring.datos()["pool"]
    largo = int(pool[pool["id"] > 2**53].iloc[0]["id"])
    redondeado = int(float(largo))                                 # lo que pasa al viajar como número JSON
    assert redondeado != largo
    assert sin_llm._id(str(redondeado)) == largo
    assert sin_llm._id(str(largo)) == largo
    assert sin_llm._id("no-es-un-id") is None


def test_flujo_elegir_y_resumen(sin_llm):
    class Runtime:
        config = {"configurable": {"thread_id": "t-plan"}}

    _, art = sin_llm.ejecutar_busqueda("barcelona", "2026-10-10", "2026-10-13", 2, thread="t-plan")
    elegida = art["tarjetas"][0]
    contenido, sel = sin_llm.seleccionar_alojamiento.func("barcelona", elegida["id"], Runtime())
    assert sel["tipo"] == "seleccion" and "Guardado" in contenido
    contenido, plan = sin_llm.resumen_viaje.func(Runtime())
    assert plan["total"] == pytest.approx(elegida["total"])
    error, _ = sin_llm.seleccionar_alojamiento.func("madrid", elegida["id"], Runtime())
    assert "no está entre las últimas opciones" in error


def test_errores_amigables(sin_llm):
    contenido, art = sin_llm.ejecutar_busqueda("madrid", "2026-10-13", "2026-10-16", 2, cerca_de="Torre Eiffel")
    assert art["tipo"] == "error" and "Lugares disponibles" in contenido
    contenido, art = sin_llm.ejecutar_busqueda("roma", "2026-10-13", "2026-10-16", 2)
    assert art["tipo"] == "error"
    contenido, _ = sin_llm.detalle_alojamiento.func("123")
    assert "No encontré" in contenido


def test_comparar_opciones_y_barrios(sin_llm):
    _, art = sin_llm.ejecutar_busqueda("mallorca", "2026-10-16", "2026-10-20", 4)
    ids = [t["id"] for t in art["tarjetas"]]
    _, comp = sin_llm.comparar_opciones.func(ids)
    assert len(comp["opciones"]) == 4
    assert all(0 <= v <= 10 for o in comp["opciones"] for v in o["aspectos"].values() if v is not None)
    _, barrios = sin_llm.comparar_barrios.func("madrid", 2)
    assert len(barrios["tabla"]) > 0


def test_clima_open_meteo():
    from core.clima import clima
    c = clima("barcelona", "2026-10-10", "2026-10-13")
    assert len(c["dias"]) == 4 and c["max_promedio"] > c["min_promedio"]


def test_graficos_de_la_interfaz(sin_llm):
    import app
    _, art = sin_llm.ejecutar_busqueda("barcelona", "2026-10-10", "2026-10-13", 2, cerca_de="Sagrada Familia")
    assert app.mapa_opciones(art["tarjetas"], "barcelona", art["cerca_de"]).data
    _, comp = sin_llm.comparar_opciones.func([t["id"] for t in art["tarjetas"]])
    assert len(app.radar_opciones(comp["opciones"]).data) == 4
    _, cli = sin_llm.clima_destino.func("madrid", "2026-10-13", "2026-10-16")
    assert app.grafico_clima(cli).data
    assert app.mapa_ruta(art["tarjetas"][:3]).data


def test_componentes_react_existen():
    from pathlib import Path
    elementos = {p.stem for p in Path("public/elements").glob("*.jsx")}
    assert {"OpcionesAlojamiento", "PlanViaje", "Metricas", "RespuestaResenas"} <= elementos
