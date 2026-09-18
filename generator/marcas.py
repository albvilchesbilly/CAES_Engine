"""Marca "DOCUMENTO SINTÉTICO – SOLO PRUEBAS" en cada página de PDF y en el EXIF de cada foto (docs/05 §4.2).

- En PDF la marca es **texto nativo** (cabecera y pie de cada página, más una marca de agua vertical en el
  margen izquierdo, también como texto). Así la lee `pdfplumber` sin OCR y, de paso, el texto plano de la
  página queda desordenado (los caracteres girados se intercalan entre las líneas) como en un documento real
  con marca de agua (decisión de diseño 1 de docs/05 §4.4: tablas antes que texto). La marca de agua va en el
  margen, fuera del marco de contenido, para que no se cuele dentro de las celdas de las tablas (una letra
  intercalada en una huella SHA-256 sería una trampa no declarada en docs/05 §4.3).
- En imágenes la marca va en el EXIF `ImageDescription` (0x010E) junto con el papel de la foto, y además
  dibujada en la propia imagen (para que un escaneo sin capa de texto siga llevándola).

Codificación del EXIF: `ImageDescription` es un campo ASCII según la norma EXIF; se escribe en UTF-8 (uso de
hecho generalizado). Pillow lo devuelve decodificado como latin-1, así que quien lo lea debe re-codificar:
`texto.encode("latin-1").decode("utf-8")` (`decodificar_exif`). Los demás campos EXIF son fijos para que dos
generaciones produzcan los mismos bytes.
"""

from __future__ import annotations

from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

MARCA = "DOCUMENTO SINTÉTICO – SOLO PRUEBAS"
SEPARADOR_EXIF = " | "
EXIF_IMAGE_DESCRIPTION = 0x010E
EXIF_SOFTWARE = 0x0131
EXIF_DATETIME = 0x0132
EXIF_ARTIST = 0x013B
SOFTWARE_EXIF = "CAE Engine generator (sintetico)"
FECHA_EXIF = "2026:03:02 10:00:00"
AUTOR_EXIF = "generator sintetico"


def descripcion_exif(papel: str, *detalles: str) -> str:
    """Texto completo de `ImageDescription`: marca, papel de la foto y detalles (números de serie, etc.)."""
    partes = [MARCA, papel, *[d for d in detalles if d]]
    return SEPARADOR_EXIF.join(partes)


def exif_sintetico(papel: str, *detalles: str) -> bytes:
    """Bloque EXIF listo para `Image.save(..., exif=...)`, con la marca y campos fijos (determinista)."""
    exif = Image.Exif()
    exif[EXIF_IMAGE_DESCRIPTION] = descripcion_exif(papel, *detalles).encode("utf-8")
    exif[EXIF_SOFTWARE] = SOFTWARE_EXIF
    exif[EXIF_DATETIME] = FECHA_EXIF
    exif[EXIF_ARTIST] = AUTOR_EXIF
    return exif.tobytes()


def decodificar_exif(texto: str | bytes | None) -> str:
    """Devuelve el `ImageDescription` tal como se escribió (UTF-8), a partir de lo que devuelve Pillow."""
    if texto is None:
        return ""
    if isinstance(texto, bytes):
        return texto.rstrip(b"\0").decode("utf-8", "replace")
    try:
        return texto.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return texto


def leer_descripcion_exif(imagen: Image.Image) -> str:
    return decodificar_exif(imagen.getexif().get(EXIF_IMAGE_DESCRIPTION))


def marcar_pagina(canvas: Canvas, titulo: str, tamano: tuple[float, float] = A4) -> None:
    """Dibuja la marca en cabecera y pie (texto nativo) y una marca de agua vertical en el margen
    izquierdo."""
    ancho, alto = tamano
    canvas.saveState()
    canvas.setFont("Helvetica-Bold", 9)
    canvas.setFillGray(0.2)
    canvas.drawString(15 * 2.835, alto - 12 * 2.835, MARCA)
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(ancho - 15 * 2.835, alto - 12 * 2.835, titulo[:80])
    canvas.drawString(15 * 2.835, 10 * 2.835, f"{MARCA} · página {canvas.getPageNumber()}")
    canvas.drawRightString(
        ancho - 15 * 2.835, 10 * 2.835, "Datos inventados; ninguna empresa ni persona real"
    )
    canvas.setFillGray(0.75)
    canvas.setFont("Helvetica-Bold", 20)
    canvas.translate(9 * 2.835, alto / 2)
    canvas.rotate(90)
    canvas.drawCentredString(0, 0, MARCA)
    canvas.restoreState()
