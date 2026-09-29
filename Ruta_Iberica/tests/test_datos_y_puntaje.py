"""Datos procesados, filtros duros y modelo de puntaje (sin LLM)."""
import pandas as pd
import pytest

from core import lugares, scoring
from core.config import PROCESSED

VIAJE = dict(destino="barcelona", check_in="2026-10-10", check_out="2026-10-13", huespedes=3)


def test_archivos_procesados_completos():
    for nombre in ["pool", "calendar_pool", "price_ref", "reviews_pool", "reviews_qa", "reviews_enriched"]:
        assert (PROCESSED / f"{nombre}.parquet").exists(), nombre
    pool = pd.read_parquet(PROCESSED / "pool.parquet")
    assert pool["id"].is_unique
    assert pool.groupby("destino").size().to_dict() == {"barcelona": 500, "madrid": 500, "mallorca": 500}
    assert pool["price"].between(30, 5000).all()


def test_capacidad_siempre_suficiente():
    df = scoring.candidatos(**VIAJE)
    assert len(df) > 0
    assert (df["accommodates"] >= VIAJE["huespedes"]).all()


def test_disponible_todas_las_noches_y_estadia_minima():
    df = scoring.candidatos(**VIAJE)
    cal = scoring.datos()["cal"]
    noches = pd.date_range("2026-10-10", "2026-10-12")
    rango = cal[cal["listing_id"].isin(df["id"]) & cal["date"].isin(noches)]
    assert rango.groupby("listing_id")["available"].all().all()
    assert (rango.groupby("listing_id").size() == 3).all()
    primer_dia = rango[rango["date"] == noches[0]]
    assert (primer_dia["minimum_nights"] <= 3).all()


def test_presupuesto_respetado():
    df = scoring.candidatos(**VIAJE, presupuesto_max_noche=200)
    assert (df["price"] <= 200).all()


@pytest.mark.parametrize("kwargs, mensaje", [
    (dict(VIAJE, destino="paris"), "no disponible"),
    (dict(VIAJE, check_out="2026-10-09"), "posterior"),
])
def test_errores_de_entrada(kwargs, mensaje):
    with pytest.raises(ValueError, match=mensaje):
        scoring.candidatos(**kwargs)


def test_cuatro_opciones_distintas_y_coherentes():
    df = scoring.candidatos(**VIAJE)
    elegidas = dict(scoring.elegir_cuatro(df))
    assert set(elegidas) == {"recomendada", "mejor_rateada", "mas_barata", "mas_cara"}
    assert len({f["id"] for f in elegidas.values()}) == 4
    razonables = df[df["c_ajuste_capacidad"] >= 0.6]
    assert elegidas["recomendada"]["puntaje"] == razonables["puntaje"].max()
    assert elegidas["mas_cara"]["price"] >= elegidas["mas_barata"]["price"]


def test_puntaje_en_escala_1_a_10():
    df = scoring.candidatos(**VIAJE)
    assert df["puntaje"].between(1, 10).all()
    fila = df.iloc[0]
    assert set(scoring.detalle_puntaje(fila)) == set(scoring.PESOS)


def test_pesos_se_normalizan_y_cambian_el_ranking():
    assert sum(scoring.normalizar_pesos({"calidad": 10, "precio_calidad": 10}).values()) == pytest.approx(1)
    base = scoring.candidatos(**VIAJE)
    solo_precio = scoring.candidatos(**VIAJE, pesos={"calidad": 0, "resenas_nlp": 0, "precio_calidad": 10,
                                                      "ubicacion": 0, "ajuste_capacidad": 0})
    assert not base["puntaje"].equals(solo_precio["puntaje"])


def test_distancias_y_lugares():
    sol, prado = lugares.LUGARES["madrid"]["Puerta del Sol"], lugares.LUGARES["madrid"]["Museo del Prado"]
    assert lugares.haversine_km(*sol, *prado) == pytest.approx(1.0, abs=0.2)
    assert lugares.buscar_lugar("barcelona", "sagrada familia") == "Sagrada Família"
    assert lugares.buscar_lugar("mallorca", "el aeropuerto") == "Aeropuerto de Palma"
    assert lugares.buscar_lugar("madrid", "torre eiffel") is None
    assert lugares.buscar_lugar("madrid", "cerca de la puerta del sol") == "Puerta del Sol"
    assert lugares.buscar_lugar("madrid", "Gran via") == "Gran Vía"
    assert lugares.buscar_lugar("madrid", "el Prado") == "Museo del Prado"
    assert lugares.buscar_lugar("mallorca", "Palma") == "Catedral de Palma (casco antiguo)"
    assert lugares.buscar_lugar("mallorca", "soller") == "Sóller"
    assert lugares.texto_distancia(0.5, "madrid") == "6 min a pie"
    assert "en auto" in lugares.texto_distancia(20, "mallorca")
