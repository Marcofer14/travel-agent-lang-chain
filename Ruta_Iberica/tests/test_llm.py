"""Pruebas que llaman a Groq (gastan cuota del free tier). Ejecutar con:  RUN_LLM=1 pytest -m llm"""
import pytest
from langchain_core.messages import AIMessage

from core.metrics import MetricsTracker

pytestmark = pytest.mark.llm


def test_salida_estructurada_del_pedido():
    from core.nlp import cadena_solicitud
    s = cadena_solicitud().invoke("Somos 3, Barcelona del 10 al 13 de octubre y después Madrid 3 noches, "
                                  "hasta 150 euros la noche")
    assert s.huespedes == 3 and s.presupuesto_max_noche == 150
    assert [t.destino for t in s.tramos] == ["barcelona", "madrid"]
    assert s.tramos[1].check_in == s.tramos[0].check_out


def test_runnable_parallel_de_resenas():
    import pandas as pd
    from core import scoring
    from core.config import PROCESSED
    from core.nlp import cadena_analisis, preparar_entradas
    pool = scoring.datos()["pool"].head(1)
    entrada = preparar_entradas(pool, pd.read_parquet(PROCESSED / "reviews_pool.parquet"))[0]
    tracker = MetricsTracker()
    r = cadena_analisis(limitar=False).invoke(entrada, config={"callbacks": [tracker]})
    assert set(r) == {"nlp", "senales", "stats"}
    assert r["nlp"].resumen and r["stats"]["n_resenas"] > 0
    assert tracker.resumen()["tokens_totales"] > 0


def test_preguntar_a_las_resenas_con_evidencia():
    from core import tools
    c, art = tools.consultar_resenas.func("1436093714181712747", "¿tiene problemas de limpieza?")
    assert art["tipo"] == "respuesta_resenas", c
    assert art["veredicto"] in {"positivo", "mixto"}  # las reseñas elogian la limpieza
    assert art["n_total"] == 40


def test_agente_usa_tools_y_recuerda():
    from core.agent import crear_agente
    agente, tracker = crear_agente(), MetricsTracker()
    cfg = {"configurable": {"thread_id": "pytest-memoria"}, "callbacks": [tracker]}
    r1 = agente.invoke({"messages": [{"role": "user", "content":
                        "Somos 2, Madrid del 13 al 16 de octubre, hasta 200 euros la noche"}]}, config=cfg)
    llamadas = [tc["name"] for m in r1["messages"] if isinstance(m, AIMessage) for tc in m.tool_calls]
    assert "buscar_opciones" in llamadas
    r2 = agente.invoke({"messages": [{"role": "user", "content": "¿Cuántos viajamos y qué presupuesto te dije?"}]},
                       config=cfg)
    texto = r2["messages"][-1].content
    assert "2" in texto and "200" in texto
    assert tracker.resumen()["costo_total_usd"] >= 0
