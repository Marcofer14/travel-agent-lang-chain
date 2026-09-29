"""Registro de tokens, tiempos y costo simulado de cada llamada al LLM."""
import time
from dataclasses import dataclass, field
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from core.config import PRECIOS_USD_POR_MTOK


def costo_usd(modelo: str, tokens_in: int, tokens_out: int) -> float:
    precio_in, precio_out = PRECIOS_USD_POR_MTOK.get(modelo, (0.0, 0.0))
    return (tokens_in * precio_in + tokens_out * precio_out) / 1_000_000


@dataclass
class RegistroLLM:
    modelo: str
    tokens_in: int
    tokens_out: int
    segundos: float

    @property
    def costo(self) -> float:
        return costo_usd(self.modelo, self.tokens_in, self.tokens_out)


@dataclass(eq=False)  # eq=False: LangChain necesita que el callback sea hasheable
class MetricsTracker(BaseCallbackHandler):
    """Callback que acumula el uso de cada llamada al modelo (sirve para batch, cadenas y agente)."""

    registros: list[RegistroLLM] = field(default_factory=list)
    _inicios: dict = field(default_factory=dict)

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs: Any) -> None:
        self._inicios[run_id] = time.perf_counter()

    def on_llm_start(self, serialized, prompts, *, run_id, **kwargs: Any) -> None:
        self._inicios[run_id] = time.perf_counter()

    def on_llm_end(self, response: LLMResult, *, run_id, **kwargs: Any) -> None:
        segundos = time.perf_counter() - self._inicios.pop(run_id, time.perf_counter())
        for generaciones in response.generations:
            for gen in generaciones:
                msg = getattr(gen, "message", None)
                uso = getattr(msg, "usage_metadata", None) or {}
                modelo = (getattr(msg, "response_metadata", {}) or {}).get("model_name", "desconocido")
                self.registros.append(
                    RegistroLLM(modelo, uso.get("input_tokens", 0), uso.get("output_tokens", 0), segundos)
                )

    def resumen(self, n_unidades: int | None = None) -> dict:
        """n_unidades: registros procesados o consultas, para calcular el costo promedio."""
        tin = sum(r.tokens_in for r in self.registros)
        tout = sum(r.tokens_out for r in self.registros)
        costo = sum(r.costo for r in self.registros)
        n = n_unidades or max(len(self.registros), 1)
        return {
            "llamadas": len(self.registros),
            "tokens_entrada": tin,
            "tokens_salida": tout,
            "tokens_totales": tin + tout,
            "segundos_llm": round(sum(r.segundos for r in self.registros), 2),
            "costo_total_usd": round(costo, 6),
            "costo_promedio_usd": round(costo / n, 6),
            "costo_si_fuera_claude_sonnet_usd": round(costo_usd("claude-sonnet-5", tin, tout), 4),
        }

    def reset(self) -> None:
        self.registros.clear()
