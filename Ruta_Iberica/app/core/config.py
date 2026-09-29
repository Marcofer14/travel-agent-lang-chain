"""Configuración central: rutas, modelos y precios de referencia para la simulación económica."""
import os
from getpass import getpass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
load_dotenv(ROOT / ".env")

# Modelos gratuitos de Groq. Cada modelo tiene su propia cuota diaria en el free tier,
# por eso el agente y el batch usan modelos distintos.
MODELO_AGENTE = os.getenv("MODELO_AGENTE", "openai/gpt-oss-120b")
MODELO_BATCH = os.getenv("MODELO_BATCH", "openai/gpt-oss-20b")

DESTINOS = {
    "barcelona": {"nombre": "Barcelona", "centro": (41.3874, 2.1686), "emoji": "🏛️"},
    "madrid": {"nombre": "Madrid", "centro": (40.4168, -3.7038), "emoji": "🎨"},
    "mallorca": {"nombre": "Mallorca", "centro": (39.6953, 3.0176), "emoji": "🏖️"},
}

# USD por millón de tokens (entrada, salida). El uso real es gratuito (free tier);
# estos precios de lista permiten simular cuánto costaría la solución en producción.
PRECIOS_USD_POR_MTOK = {
    "openai/gpt-oss-120b": (0.15, 0.60),
    "openai/gpt-oss-20b": (0.075, 0.30),
    "qwen/qwen3.8-27b": (0.29, 0.59),  # referencia: verificar en groq.com/pricing
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


def asegurar_api_key() -> None:
    """Pide la API key de Groq si no está en el entorno (nunca se escribe en el código)."""
    if not os.getenv("GROQ_API_KEY"):
        os.environ["GROQ_API_KEY"] = getpass("GROQ_API_KEY: ")
