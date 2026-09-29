"""Configuración común de las pruebas: agrega app/ al path y define el marcador de pruebas con LLM."""
import os
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))
os.chdir(APP)  # igual que al correr `chainlit run app.py` desde app/


def pytest_configure(config):
    config.addinivalue_line("markers", "llm: llama a Groq (gasta cuota); correr con RUN_LLM=1")


def pytest_collection_modifyitems(config, items):
    if os.getenv("RUN_LLM") == "1":
        return
    saltar = pytest.mark.skip(reason="prueba con LLM: ejecutar con RUN_LLM=1")
    for item in items:
        if "llm" in item.keywords:
            item.add_marker(saltar)


@pytest.fixture
def sin_llm(monkeypatch):
    """Evita el análisis NLP en vivo dentro de las tools para que las pruebas offline no llamen a Groq."""
    from core import tools
    monkeypatch.setattr(tools, "_enriquecer_faltantes", lambda filas, callbacks=None: None)
    return tools
