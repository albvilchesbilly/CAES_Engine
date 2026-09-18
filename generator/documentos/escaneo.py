"""Caso G: la ficha técnica del variador como escaneo (imagen girada 90°, sin capa de texto) en un PDF."""

from __future__ import annotations

from io import BytesIO

from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from generator.documentos import ficha_tecnica_variador
from generator.documentos.imagenes import imagen_escaneo, jpeg_de
from generator.modelo_caso import Motor


def imagen_ficha_variador(motor: Motor) -> bytes:
    """JPEG de la ficha del variador "escaneada" y girada 90°, con la marca dibujada y en el EXIF."""
    img = imagen_escaneo(
        ficha_tecnica_variador.filas(motor),
        ficha_tecnica_variador.TITULO,
        ["Documento escaneado. Datos del fabricante (inventado).", ficha_tecnica_variador.prosa(motor)[:95]],
    )
    return jpeg_de(img, "escaneo de ficha técnica del variador", f"variador {motor.num_serie_variador}")


def pdf_escaneo(jpeg: bytes) -> bytes:
    """PDF de una página que solo contiene la imagen (sin texto nativo)."""
    lector = ImageReader(BytesIO(jpeg))
    ancho, alto = lector.getSize()
    escala = 595.0 / ancho if ancho >= alto else 842.0 / alto
    tamano = (ancho * escala, alto * escala)
    buffer = BytesIO()
    c = Canvas(buffer, pagesize=tamano, invariant=1, pageCompression=1)
    c.setTitle("scan")
    c.drawImage(lector, 0, 0, width=tamano[0], height=tamano[1])
    c.showPage()
    c.save()
    return buffer.getvalue()
