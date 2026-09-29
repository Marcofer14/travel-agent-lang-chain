"""Modelos Pydantic usados con with_structured_output."""
from typing import Literal, Optional

from pydantic import BaseModel, Field

Destino = Literal["barcelona", "madrid", "mallorca"]
PerfilViajero = Literal[
    "parejas", "familias", "grupos de amigos", "viajeros solos", "trabajo remoto", "viajeros con auto"
]


class AnalisisResenas(BaseModel):
    """Análisis de las reseñas recientes de un alojamiento."""

    sentimiento_general: Literal["muy positivo", "positivo", "mixto", "negativo"]
    puntaje_limpieza: Optional[float] = Field(None, ge=1, le=10, description="1-10; null si las reseñas no lo mencionan")
    puntaje_ubicacion: Optional[float] = Field(None, ge=1, le=10, description="1-10; null si no se menciona")
    puntaje_tranquilidad: Optional[float] = Field(
        None, ge=1, le=10, description="10 = muy silencioso, 1 = muy ruidoso; null si no se menciona"
    )
    puntaje_anfitrion: Optional[float] = Field(None, ge=1, le=10, description="trato y comunicación; null si no se menciona")
    puntaje_fidelidad: Optional[float] = Field(
        None, ge=1, le=10, description="¿el lugar coincide con el anuncio y las fotos?; null si no se menciona"
    )
    pros: list[str] = Field(description="Hasta 3 puntos fuertes, en español, frases cortas")
    contras: list[str] = Field(description="Hasta 3 puntos débiles mencionados; lista vacía si no hay")
    ideal_para: list[PerfilViajero] = Field(description="Perfiles de viajero para los que se recomienda")
    alerta: Optional[str] = Field(None, description="Problema serio y recurrente (seguridad, plagas, estafa); null si no hay")
    resumen: str = Field(description="Una o dos frases en español que resuman la experiencia de los huéspedes")
    cita_textual: str = Field(description="Fragmento literal (sin traducir) de una reseña que respalde el resumen")


class TramoViaje(BaseModel):
    destino: Destino
    check_in: str = Field(description="Fecha de entrada YYYY-MM-DD")
    check_out: str = Field(description="Fecha de salida YYYY-MM-DD")


class SolicitudViaje(BaseModel):
    """Pedido de viaje interpretado a partir del lenguaje natural del usuario."""

    tramos: list[TramoViaje]
    huespedes: int = Field(ge=1, le=16)
    presupuesto_max_noche: Optional[float] = Field(None, description="Euros por noche; null si no se indicó")
    preferencias: list[str] = Field(default_factory=list, description="p. ej. 'tranquilo', 'cerca de la playa'")


class PalabrasClave(BaseModel):
    """Términos para buscar en reseñas escritas en varios idiomas."""

    palabras: list[str] = Field(
        description="8 a 15 palabras o raíces cortas relacionadas con la pregunta, en español, inglés, francés, "
                    "alemán, italiano y catalán (p. ej. 'ruid', 'noise', 'bruit', 'laut')"
    )


class Cita(BaseModel):
    texto: str = Field(description="Fragmento literal de la reseña, en su idioma original, máximo 30 palabras")
    fecha: str = Field(description="Fecha de la reseña YYYY-MM-DD")


class RespuestaResenas(BaseModel):
    """Respuesta a una pregunta sobre un alojamiento, fundamentada en reseñas reales."""

    veredicto: Literal["positivo", "negativo", "mixto", "sin información"] = Field(
        description="Cómo viven los huéspedes el aspecto consultado, sin importar cómo esté formulada la pregunta: "
                    "positivo = buena experiencia (limpio, silencioso, bien ubicado...), negativo = mala experiencia, "
                    "mixto = opiniones divididas, sin información = las reseñas no lo mencionan"
    )
    respuesta: str = Field(description="2 a 4 frases en español que respondan la pregunta usando solo las reseñas")
    evidencia: list[Cita] = Field(description="1 a 3 citas textuales que respaldan la respuesta; vacía si no hay")


class Imperdible(BaseModel):
    nombre: str = Field(description="Nombre EXACTO de un lugar de la lista de candidatos")
    por_que: str = Field(description="Una frase en español de por qué le gusta a este tipo de viajero")
    momento: str = Field(description="Uno de: mañana, tarde, noche, cualquier momento")


class RecomendacionPerfil(BaseModel):
    """Guía breve para un tipo de viajero en un destino, basada solo en lugares reales provistos."""

    titular: str = Field(description="Frase gancho de máximo 12 palabras")
    barrios_sugeridos: list[str] = Field(description="1 a 3 barrios/zonas de la lista provista para alojarse")
    imperdibles: list[Imperdible] = Field(description="4 a 6 lugares de la lista de candidatos, variados")
    plan_dia_tipo: str = Field(description="2 o 3 frases con un día ideal combinando algunos imperdibles")
    consejos: list[str] = Field(description="2 o 3 consejos prácticos y generales, sin inventar precios ni horarios")
