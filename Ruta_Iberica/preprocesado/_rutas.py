"""Rutas compartidas del preprocesado.

Los scripts de esta carpeta reutilizan el paquete `core` de la app y escriben sus resultados en app/data/processed,
que es lo único que la app necesita para funcionar.
"""
import sys
from pathlib import Path

PREPROCESADO = Path(__file__).resolve().parent
RAIZ = PREPROCESADO.parent
APP = RAIZ / "app"
RAW = PREPROCESADO / "data" / "raw"

if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from core.config import PROCESSED  # noqa: E402  (requiere APP en sys.path)

__all__ = ["APP", "PREPROCESADO", "PROCESSED", "RAIZ", "RAW"]
