"""Construcción de PDF con reportlab (platypus): secciones, tablas etiqueta/valor y marca en cada página.

Decisiones:
- Fuentes estándar (Helvetica): sin dependencia de fuentes del sistema y texto extraíble por `pdfplumber`.
  Solo se usan caracteres WinAnsi (nada de "≥", "≤", "→"): se escribe ">=" o "al menos".
- **Etiqueta y valor en tablas** con rejilla: la extracción lee tablas antes que texto (docs/05 §4.4.1). Algún
  dato se repite en prosa para que el respaldo por regex tenga sentido.
- `MarcadorPagina`: flowable sin tamaño que anota en qué página absoluta se dibuja cada bloque (por motor y
  por sección). Con ello el ground truth sabe documento y página esperados de cada variable y las partes de un
  PDF combinado (caso G) sin volver a leer el PDF.
- `invariant=1`: fecha e id del PDF fijos → dos generaciones producen los mismos bytes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from generator.marcas import marcar_pagina

CLAVE_INICIO = "__inicio__"
CLAVE_FIN = "__fin__"

ESTILO_TITULO = ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=15, leading=19, spaceAfter=6)
ESTILO_SUBTITULO = ParagraphStyle(
    "subtitulo", fontName="Helvetica-Bold", fontSize=11, leading=14, spaceBefore=8, spaceAfter=4
)
ESTILO_NORMAL = ParagraphStyle(
    "normal", fontName="Helvetica", fontSize=9.5, leading=12.5, alignment=TA_JUSTIFY
)
ESTILO_PEQUENO = ParagraphStyle(
    "pequeno", fontName="Helvetica", fontSize=8, leading=10, textColor=colors.HexColor("#444444")
)
ESTILO_CELDA = ParagraphStyle("celda", fontName="Helvetica", fontSize=9, leading=11)
ESTILO_CELDA_ETIQUETA = ParagraphStyle("celda_etiqueta", fontName="Helvetica-Bold", fontSize=9, leading=11)
ESTILO_CELDA_MONO = ParagraphStyle("celda_mono", fontName="Courier", fontSize=7.4, leading=9.5)


class MarcadorPagina(Flowable):
    """Anota la página absoluta en la que se dibuja. No ocupa espacio."""

    def __init__(self, destino: dict[str, int], clave: str) -> None:
        super().__init__()
        self.destino = destino
        self.clave = clave

    def wrap(self, aw: float, ah: float) -> tuple[float, float]:
        return (0, 0)

    def draw(self) -> None:
        self.destino[self.clave] = self.canv.getPageNumber()


@dataclass
class Seccion:
    """Un documento lógico: tipo de la spec (o `None` si es irrelevante), título y flowables."""

    tipo: str | None
    titulo: str
    flowables: list = field(default_factory=list)
    paginas: dict[str, int] = field(default_factory=dict)

    def marcador(self, clave: str) -> MarcadorPagina:
        return MarcadorPagina(self.paginas, clave)

    @property
    def pagina_inicio(self) -> int:
        return self.paginas[CLAVE_INICIO]

    @property
    def pagina_fin(self) -> int:
        return self.paginas[CLAVE_FIN]

    def pagina_de(self, clave: str) -> int:
        return self.paginas[clave]


def p(texto: str, estilo: ParagraphStyle = ESTILO_NORMAL) -> Paragraph:
    return Paragraph(escape(texto), estilo)


def titulo(texto: str) -> Paragraph:
    return Paragraph(escape(texto), ESTILO_TITULO)


def subtitulo(texto: str) -> Paragraph:
    return Paragraph(escape(texto), ESTILO_SUBTITULO)


def nota(texto: str) -> Paragraph:
    return Paragraph(escape(texto), ESTILO_PEQUENO)


def espacio(alto_mm: float = 4) -> Spacer:
    return Spacer(1, alto_mm * mm)


def _estilo_tabla(con_cabecera: bool) -> TableStyle:
    ordenes = [
        ("GRID", (0, 0), (-1, -1), 0.6, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]
    if con_cabecera:
        ordenes.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6e6e6")))
    return TableStyle(ordenes)


def mono(texto: str) -> Paragraph:
    """Valor en monoespaciada pequeña (huellas SHA-256) para que quepa en una sola línea de la celda."""
    return Paragraph(escape(texto), ESTILO_CELDA_MONO)


def tabla_campos(filas: Sequence[tuple[str, str | Paragraph]], ancho_etiqueta_mm: float = 62) -> Table:
    """Tabla de dos columnas Campo | Valor con rejilla (lo que la extracción lee antes que el texto)."""
    datos = [[Paragraph("Campo", ESTILO_CELDA_ETIQUETA), Paragraph("Valor", ESTILO_CELDA_ETIQUETA)]]
    for etiqueta, valor in filas:
        celda = valor if isinstance(valor, Paragraph) else Paragraph(escape(valor), ESTILO_CELDA)
        datos.append([Paragraph(escape(etiqueta), ESTILO_CELDA_ETIQUETA), celda])
    ancho_total = A4[0] - 40 * mm
    t = Table(datos, colWidths=[ancho_etiqueta_mm * mm, ancho_total - ancho_etiqueta_mm * mm], repeatRows=1)
    t.setStyle(_estilo_tabla(True))
    return t


def tabla(cabecera: Sequence[str], filas: Sequence[Sequence[str]], anchos_mm: Sequence[float]) -> Table:
    datos = [[Paragraph(escape(c), ESTILO_CELDA_ETIQUETA) for c in cabecera]]
    for fila in filas:
        datos.append([Paragraph(escape(str(v)), ESTILO_CELDA) for v in fila])
    t = Table(datos, colWidths=[a * mm for a in anchos_mm], repeatRows=1)
    t.setStyle(_estilo_tabla(True))
    return t


def bloque(*flowables: Flowable) -> KeepTogether:
    return KeepTogether(list(flowables))


def construir_pdf(secciones: Sequence[Seccion], tamano: tuple[float, float] = A4) -> bytes:
    """PDF con una sección tras otra (cada una empieza en página nueva) y la marca en cada página."""
    if not secciones:
        raise ValueError("construir_pdf necesita al menos una sección")
    flowables: list[Flowable] = []
    for i, seccion in enumerate(secciones):
        if i > 0:
            flowables.append(PageBreak())
        flowables.append(seccion.marcador(CLAVE_INICIO))
        flowables.append(titulo(seccion.titulo))
        flowables.extend(seccion.flowables)
        flowables.append(seccion.marcador(CLAVE_FIN))
    cabecera = (
        secciones[0].titulo if len(secciones) == 1 else "Documentación de la actuación (varios documentos)"
    )

    def decorar(canvas, doc) -> None:
        marcar_pagina(canvas, cabecera, tamano)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=tamano,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=22 * mm,
        bottomMargin=20 * mm,
        title=cabecera,
        author="generator sintético CAE Engine",
        subject="DOCUMENTO SINTÉTICO – SOLO PRUEBAS",
        invariant=1,
    )
    doc.build(flowables, onFirstPage=decorar, onLaterPages=decorar)
    for seccion in secciones:
        if CLAVE_INICIO not in seccion.paginas or CLAVE_FIN not in seccion.paginas:
            raise RuntimeError(f"la sección {seccion.titulo!r} no registró sus páginas")
    return buffer.getvalue()
