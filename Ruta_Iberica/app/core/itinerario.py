"""Itinerario por sesión (hospedajes, actividades, auto) y exportación a PDF."""
import io
import random
import re
import string
import tempfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from core.config import DESTINOS

# Estado por sesión (thread_id)
HOSPEDAJES: dict[str, dict[str, dict]] = defaultdict(dict)   # destino → tarjeta del alojamiento elegido
ACTIVIDADES: dict[str, list[dict]] = defaultdict(list)       # actividades, restaurantes y autos
PERFILES_SESION: dict[str, str] = {}

TERRACOTA, AZUL, ARENA = colors.HexColor("#C8553D"), colors.HexColor("#1F5673"), colors.HexColor("#F4E9D8")
NOMBRE_DESTINO = {k: v["nombre"] for k, v in DESTINOS.items()}


def codigo_reserva() -> str:
    return "RI-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


CONTADOR: dict[str, int] = defaultdict(int)


def agregar(thread: str, item: dict) -> dict:
    CONTADOR[thread] += 1  # ids estables aunque se quiten actividades
    item = {"id": f"A{CONTADOR[thread]}"} | item
    if item.get("estado") == "reservada" and not item.get("codigo"):
        item["codigo"] = codigo_reserva()
    ACTIVIDADES[thread].append(item)
    return item


def quitar(thread: str, texto: str) -> dict | None:
    texto = texto.lower()
    for item in ACTIVIDADES[thread]:
        if texto in item["nombre"].lower() or texto == item["id"].lower():
            ACTIVIDADES[thread].remove(item)
            return item
    return None


def editar(thread: str, item_id: str, **cambios) -> dict | None:
    """Edición desde el panel del itinerario: fecha, hora, notas o estado (tentativa ↔ reservada)."""
    item = next((a for a in ACTIVIDADES[thread] if a["id"] == item_id), None)
    if item is None:
        return None
    for campo in ("fecha", "hora", "notas", "fecha_devolucion", "hora_devolucion"):
        if campo in cambios:
            item[campo] = cambios[campo] or None
    if cambios.get("estado") in ("reservada", "tentativa"):
        item["estado"] = cambios["estado"]
        item["codigo"] = (item.get("codigo") or codigo_reserva()) if item["estado"] == "reservada" else None
    return item


def quitar_id(thread: str, item_id: str) -> dict | None:
    item = next((a for a in ACTIVIDADES[thread] if a["id"] == item_id), None)
    if item:
        ACTIVIDADES[thread].remove(item)
    return item


def quitar_hospedaje(thread: str, destino: str) -> dict | None:
    return HOSPEDAJES[thread].pop(destino, None)


def rango_viaje(thread: str) -> tuple[str, str] | None:
    hosp = HOSPEDAJES[thread].values()
    return (min(h["check_in"] for h in hosp), max(h["check_out"] for h in hosp)) if hosp else None


def fechas_destino(thread: str, destino: str) -> tuple[str, str] | None:
    h = HOSPEDAJES[thread].get(destino)
    return (h["check_in"], h["check_out"]) if h else None


def validar_fecha(thread: str, destino: str, fecha: str | None) -> str | None:
    """Devuelve un aviso si la fecha no cae dentro de la estadía en ese destino."""
    if not fecha:
        return None
    try:
        f = date.fromisoformat(fecha)
    except ValueError:
        return f"La fecha '{fecha}' no tiene formato AAAA-MM-DD."
    rango = fechas_destino(thread, destino)
    if rango and not (date.fromisoformat(rango[0]) <= f <= date.fromisoformat(rango[1])):
        return f"Ojo: el {fecha} no estás en {NOMBRE_DESTINO.get(destino, destino)} (estadía {rango[0]} → {rango[1]})."
    return None


def resumen(thread: str) -> dict:
    hospedajes = sorted(HOSPEDAJES[thread].values(), key=lambda t: t["check_in"])
    actividades = sorted(ACTIVIDADES[thread], key=lambda a: (a.get("fecha") or "9999", a.get("hora") or "99"))
    return {"hospedajes": hospedajes, "actividades": actividades, "perfil": PERFILES_SESION.get(thread),
            "total_alojamiento": round(sum(h["total"] for h in hospedajes), 2),
            "reservadas": sum(a["estado"] == "reservada" for a in actividades),
            "tentativas": sum(a["estado"] == "tentativa" for a in actividades)}


# ------------------------------------------------------------------ PDF

def _limpiar(texto) -> str:
    """Las fuentes estándar del PDF no tienen emojis: se quitan para evitar cuadraditos."""
    if texto is None:
        return ""
    texto = re.sub(r"[\U00010000-\U0010FFFF☀-➿️‍]", "", str(texto)).strip()
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _foto(url: str | None, ancho=5.2 * cm, alto=3.5 * cm):
    if not url:
        return ""
    try:
        r = requests.get(f"{url}?im_w=480", timeout=8)
        r.raise_for_status()
        return Image(io.BytesIO(r.content), width=ancho, height=alto)
    except Exception:
        return ""


def _fecha_larga(iso: str) -> str:
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
             "noviembre", "diciembre"]
    d = date.fromisoformat(iso)
    return f"{dias[d.weekday()].capitalize()} {d.day} de {meses[d.month - 1]}"


def _tabla(filas, anchos, cabecera=True):
    t = Table(filas, colWidths=anchos, repeatRows=1 if cabecera else 0)
    estilo = [("FONTSIZE", (0, 0), (-1, -1), 8.5), ("VALIGN", (0, 0), (-1, -1), "TOP"),
              ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D9CFC1")),
              ("ROWBACKGROUNDS", (0, 1 if cabecera else 0), (-1, -1), [colors.white, colors.HexColor("#FBF7F1")]),
              ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if cabecera:
        estilo += [("BACKGROUND", (0, 0), (-1, 0), AZUL), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                   ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    t.setStyle(TableStyle(estilo))
    return t


def generar_pdf(thread: str, destino_pdf: Path | None = None) -> Path:
    datos = resumen(thread)
    hosp, acts = datos["hospedajes"], datos["actividades"]
    ruta = destino_pdf or Path(tempfile.gettempdir()) / "ruta_iberica" / f"itinerario_{thread[:8]}.pdf"
    ruta.parent.mkdir(parents=True, exist_ok=True)

    base = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=base["Title"], textColor=AZUL, fontSize=24, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=base["Heading2"], textColor=TERRACOTA, spaceBefore=10, spaceAfter=4)
    h3 = ParagraphStyle("h3", parent=base["Heading3"], textColor=AZUL, spaceBefore=6, spaceAfter=2)
    txt = ParagraphStyle("txt", parent=base["BodyText"], fontSize=9.5, leading=12.5)
    chico = ParagraphStyle("chico", parent=txt, fontSize=8, leading=10, textColor=colors.HexColor("#6B5E50"))
    celda = ParagraphStyle("celda", parent=txt, fontSize=8.5, leading=10.5)
    centro = ParagraphStyle("centro", parent=txt, alignment=TA_CENTER)
    P = lambda t, s=celda: Paragraph(_limpiar(t), s)  # noqa: E731

    doc = SimpleDocTemplate(str(ruta), pagesize=A4, leftMargin=1.6 * cm, rightMargin=1.6 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm, title="Ruta Ibérica - Itinerario",
                            author="Ruta Ibérica")
    h = []

    # ---- portada / resumen
    destinos_txt = " → ".join(NOMBRE_DESTINO[x["destino"]] for x in hosp) or "Viaje en armado"
    h += [Paragraph("Ruta Ibérica · Itinerario de viaje", h1), Paragraph(_limpiar(destinos_txt), h2)]
    rango = rango_viaje(thread)
    linea = [f"Generado el {datetime.now():%d/%m/%Y %H:%M}"]
    if rango:
        noches = (date.fromisoformat(rango[1]) - date.fromisoformat(rango[0])).days
        linea.insert(0, f"Del {_fecha_larga(rango[0])} al {_fecha_larga(rango[1])} · {noches} noches")
    if datos["perfil"]:
        linea.append(f"Perfil de viajero: {datos['perfil']}")
    h += [Paragraph(" · ".join(_limpiar(x) for x in linea), txt), Spacer(1, 8)]

    kpis = [[P("Alojamiento total", centro), P("Actividades reservadas", centro), P("Actividades tentativas", centro)],
            [Paragraph(f"<b>{datos['total_alojamiento']:,.0f} EUR</b>".replace(",", "."), centro),
             Paragraph(f"<b>{datos['reservadas']}</b>", centro), Paragraph(f"<b>{datos['tentativas']}</b>", centro)]]
    h.append(_tabla(kpis, [5.9 * cm] * 3, cabecera=False))

    # ---- hospedajes
    h.append(Paragraph("Hospedaje", h2))
    if not hosp:
        h.append(Paragraph("Todavía no elegiste alojamientos.", txt))
    for x in hosp:
        detalle = [
            Paragraph(f"<b>{_limpiar(x['name'])}</b>", txt),
            Paragraph(_limpiar(f"{NOMBRE_DESTINO[x['destino']]} · {x['barrio']} · hasta {x['accommodates']} huéspedes"), chico),
            Paragraph(_limpiar(f"Check-in {x['check_in']} · Check-out {x['check_out']} · {x['noches']} noches"), txt),
            Paragraph(f"<b>{x['price']:.0f} EUR/noche · total {x['total']:.0f} EUR</b> · puntaje Ruta Ibérica "
                      f"{x['puntaje']}/10 · rating Airbnb {x['rating_airbnb_10']}/10", txt),
        ]
        if x.get("resumen"):
            detalle.append(Paragraph(f"<i>{_limpiar(x['resumen'])}</i>", chico))
        cerca = ", ".join(f"{c['lugar']} ({c['texto']})" for c in (x.get("cercanias") or [])[:3])
        if cerca:
            detalle.append(Paragraph(_limpiar(f"Cerca de: {cerca}"), chico))
        detalle.append(Paragraph(f'<link href="{x["listing_url"]}" color="#1F5673">{x["listing_url"]}</link>', chico))
        fila = Table([[_foto(x.get("picture_url")), detalle]], colWidths=[5.6 * cm, 12.2 * cm])
        fila.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        h += [KeepTogether([fila]), Spacer(1, 6)]

    # ---- auto
    autos = [a for a in acts if a["categoria"] == "alquiler_auto"]
    if autos:
        h.append(Paragraph("Alquiler de auto", h2))
        filas = [[P("Empresa"), P("Retiro"), P("Devolución"), P("Vehículo"), P("Estado")]]
        for a in autos:
            filas.append([Paragraph(f"<b>{_limpiar(a['nombre'])}</b><br/>{_limpiar(a.get('direccion'))}", celda),
                          P(f"{a.get('fecha') or '-'} {a.get('hora') or ''}"),
                          P(f"{a.get('fecha_devolucion') or '-'} {a.get('hora_devolucion') or ''}"),
                          P(a.get("tipo_auto") or "a definir"),
                          Paragraph(a["estado"] + (f"<br/>código {a['codigo']}" if a.get("codigo") else ""), celda)])
        h.append(_tabla(filas, [5.2 * cm, 3.1 * cm, 3.1 * cm, 3 * cm, 3.4 * cm]))

    # ---- día por día
    h.append(Paragraph("Día por día", h2))
    if rango:
        dia, fin = date.fromisoformat(rango[0]), date.fromisoformat(rango[1])
        while dia <= fin:
            iso = dia.isoformat()
            donde = next((x for x in hosp if x["check_in"] <= iso < x["check_out"]), None)
            del_dia = [a for a in acts if a.get("fecha") == iso and a["categoria"] != "alquiler_auto"]
            eventos = [f"Check-out de {x['name']}" for x in hosp if x["check_out"] == iso]
            eventos += [f"Check-in en {x['name']}" for x in hosp if x["check_in"] == iso]
            eventos += [f"Retiro de auto ({a['nombre']}) {a.get('hora') or ''}" for a in autos if a.get("fecha") == iso]
            eventos += [f"Devolución de auto {a.get('hora_devolucion') or ''}" for a in autos if a.get("fecha_devolucion") == iso]
            bloque = [Paragraph(_limpiar(f"{_fecha_larga(iso)}" + (f" · {NOMBRE_DESTINO[donde['destino']]}" if donde else "")), h3)]
            for e in eventos:
                bloque.append(Paragraph("• " + _limpiar(e), txt))
            for a in sorted(del_dia, key=lambda a: a.get("hora") or "99"):
                marca = f"[{a['estado'].upper()}{' ' + a['codigo'] if a.get('codigo') else ''}]"
                bloque.append(Paragraph(f"• {a.get('hora') or 'Sin hora'} · <b>{_limpiar(a['nombre'])}</b> "
                                        f"({_limpiar(a['tipo_texto'])}) {marca}", txt))
            if len(bloque) == 1:
                bloque.append(Paragraph("Día libre.", chico))
            h.append(KeepTogether(bloque))
            dia += timedelta(days=1)
    else:
        h.append(Paragraph("Elegí al menos un alojamiento para armar el calendario.", txt))

    # ---- actividades por destino (incluye tentativas sin fecha)
    otras = [a for a in acts if a["categoria"] != "alquiler_auto"]
    if otras:
        h.append(Paragraph("Actividades y reservas", h2))
        for dest in dict.fromkeys(a["destino"] for a in otras):
            h.append(Paragraph(NOMBRE_DESTINO.get(dest, dest), h3))
            filas = [[P("Cuándo"), P("Actividad"), P("Dirección / horario"), P("Estado")]]
            for a in [x for x in otras if x["destino"] == dest]:
                cuando = " ".join(filter(None, [a.get("fecha"), a.get("hora")])) or "Sin fecha"
                info = "<br/>".join(filter(None, [_limpiar(a.get("direccion")), _limpiar(a.get("horario")),
                                                  f'<link href="{a["web"]}" color="#1F5673">{_limpiar(a["web"])}</link>'
                                                  if a.get("web") else None, _limpiar(a.get("notas"))]))
                estado = a["estado"] + (f"<br/>{a['codigo']}" if a.get("codigo") else "")
                filas.append([P(cuando), Paragraph(f"<b>{_limpiar(a['nombre'])}</b><br/>{_limpiar(a['tipo_texto'])}", celda),
                              Paragraph(info or "-", celda), Paragraph(estado, celda)])
            h.append(_tabla(filas, [2.8 * cm, 5.2 * cm, 6.8 * cm, 3 * cm]))

    # ---- notas
    h += [Spacer(1, 10), Paragraph("Notas importantes", h2), Paragraph(
        "Las reservas marcadas como <b>reservada</b> son una simulación registrada en Ruta Ibérica: confirmalas "
        "directamente con cada proveedor. Precios y disponibilidad de alojamientos según el relevamiento de "
        "Inside Airbnb de junio de 2026. Lugares y horarios: © colaboradores de OpenStreetMap (ODbL); verificá "
        "horarios antes de ir.", chico)]

    def pie(canvas, doc_):
        canvas.saveState()
        canvas.setFillColor(ARENA)
        canvas.rect(0, 0, A4[0], 1.0 * cm, stroke=0, fill=1)
        canvas.setFillColor(AZUL)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(1.6 * cm, 0.38 * cm, "Ruta Ibérica · asesor de viajes con IA · Barcelona · Madrid · Mallorca")
        canvas.drawRightString(A4[0] - 1.6 * cm, 0.38 * cm, f"Página {doc_.page}")
        canvas.restoreState()

    doc.build(h, onFirstPage=pie, onLaterPages=pie)
    return ruta
