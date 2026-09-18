"""Imágenes sintéticas con PIL: fotos ANTES/DESPUÉS, placa de características (legible por OCR), foto
irrelevante y el "escaneo" de la ficha técnica del variador (caso G). Todas llevan la marca dibujada y en el
EXIF.

Determinismo: fuente Bitstream Vera incluida en reportlab (no depende del sistema), JPEG con calidad fija, sin
metadatos variables. Los valores de la placa solo existen en la imagen (OCR), nunca en texto nativo del PDF.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import reportlab
from PIL import Image, ImageDraw, ImageFont

from generator.marcas import MARCA, exif_sintetico
from generator.modelo_caso import Motor, fmt_es

RUTA_FUENTES = Path(reportlab.__file__).resolve().parent / "fonts"
CALIDAD_JPEG = 85


def fuente(tamano: int, negrita: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(RUTA_FUENTES / ("VeraBd.ttf" if negrita else "Vera.ttf")), tamano)


def _a_jpeg(imagen: Image.Image, papel: str, *detalles: str) -> bytes:
    buffer = BytesIO()
    imagen.save(buffer, "JPEG", quality=CALIDAD_JPEG, exif=exif_sintetico(papel, *detalles))
    return buffer.getvalue()


def _marca_en_imagen(dibujo: ImageDraw.ImageDraw, ancho: int, alto: int, tamano: int = 22) -> None:
    f = fuente(tamano, negrita=True)
    caja = dibujo.textbbox((0, 0), MARCA, font=f)
    dibujo.rectangle((0, alto - (caja[3] + 16), ancho, alto), fill="#202020")
    dibujo.text((12, alto - (caja[3] + 10)), MARCA, font=f, fill="white")


def _silueta_motor(dibujo: ImageDraw.ImageDraw, x: int, y: int, con_variador: bool) -> None:
    """Un motor esquemático (carcasa, aletas, eje) y, si procede, un armario de variador al lado."""
    dibujo.rounded_rectangle((x, y, x + 300, y + 170), radius=25, fill="#5b6c7a", outline="#2b3440", width=4)
    for i in range(7):
        dibujo.line((x + 30 + i * 38, y + 12, x + 30 + i * 38, y + 158), fill="#3c4854", width=6)
    dibujo.rectangle((x + 300, y + 70, x + 360, y + 100), fill="#9aa5ae", outline="#2b3440", width=3)
    dibujo.rectangle((x + 100, y - 40, x + 200, y), fill="#7a8791", outline="#2b3440", width=3)
    if con_variador:
        dibujo.rectangle((x + 400, y - 60, x + 540, y + 170), fill="#d9dde1", outline="#2b3440", width=4)
        dibujo.rectangle((x + 420, y - 40, x + 520, y + 20), fill="#1d2b3a")
        dibujo.text((x + 428, y - 30), "VSD", font=fuente(28, True), fill="#7cf2a0")
        dibujo.line((x + 360, y + 85, x + 400, y + 85), fill="#2b3440", width=5)


def foto_motor(motor: Motor, momento: str) -> bytes:
    """Foto ANTES o DESPUÉS del motor (`momento` ∈ {"ANTES", "DESPUES"})."""
    ancho, alto = 900, 640
    img = Image.new("RGB", (ancho, alto), "#c9c2b5" if momento == "ANTES" else "#b9c6cf")
    d = ImageDraw.Draw(img)
    d.rectangle((0, 420, ancho, alto), fill="#8d8478")
    _silueta_motor(d, 120, 250, con_variador=(momento != "ANTES"))
    etiqueta = "ANTES" if momento == "ANTES" else "DESPUÉS"
    d.text((30, 25), etiqueta, font=fuente(64, True), fill="#111111")
    d.text((30, 105), f"motor {motor.num_serie_motor}", font=fuente(36, True), fill="#111111")
    if momento != "ANTES":
        d.text((30, 150), f"con variador {motor.num_serie_variador}", font=fuente(30, True), fill="#111111")
    d.text((30, 200), f"{motor.descripcion}", font=fuente(20), fill="#333333")
    _marca_en_imagen(d, ancho, alto)
    papel = "foto ANTES" if momento == "ANTES" else "foto DESPUÉS"
    detalles = (f"motor {motor.num_serie_motor}",)
    if momento != "ANTES":
        detalles += (f"variador {motor.num_serie_variador}",)
    return _a_jpeg(img, papel, *detalles)


def foto_placa(motor: Motor) -> bytes:
    """Placa de características: texto grande y alto contraste para OCR. Los valores solo viven aquí."""
    ancho, alto = 1000, 640
    img = Image.new("RGB", (ancho, alto), "#e8e8e4")
    d = ImageDraw.Draw(img)
    d.rectangle((40, 40, ancho - 40, alto - 80), fill="#f7f7f5", outline="#111111", width=6)
    for cx, cy in ((70, 70), (ancho - 70, 70), (70, alto - 110), (ancho - 70, alto - 110)):
        d.ellipse((cx - 12, cy - 12, cx + 12, cy + 12), fill="#555555")
    d.text((110, 70), motor.fabricante_motor.upper(), font=fuente(30, True), fill="#111111")
    d.text((110, 115), f"MOTOR {motor.num_serie_motor}", font=fuente(52, True), fill="#111111")
    d.text((110, 200), f"TIPO {motor.modelo_motor}", font=fuente(32), fill="#111111")
    d.text((110, 260), f"{fmt_es(motor.PM)} kW", font=fuente(60, True), fill="#111111")
    d.text((520, 260), f"{motor.N1} rpm", font=fuente(60, True), fill="#111111")
    d.text((110, 350), f"{motor.tension_v} V   50 Hz   IE3", font=fuente(44, True), fill="#111111")
    d.text((110, 420), f"{motor.polos} POLOS   IP55   S1", font=fuente(36), fill="#111111")
    d.text((110, 480), "PLACA DE CARACTERISTICAS", font=fuente(26), fill="#333333")
    _marca_en_imagen(d, ancho, alto)
    return _a_jpeg(img, "placa de características", f"motor {motor.num_serie_motor}")


def foto_irrelevante() -> bytes:
    """Foto sin relación con la actuación (caso G): vista general de la nave."""
    ancho, alto = 900, 640
    img = Image.new("RGB", (ancho, alto), "#cfd8dc")
    d = ImageDraw.Draw(img)
    d.rectangle((0, 380, ancho, alto), fill="#9e9e9e")
    d.polygon(
        [(60, 380), (60, 150), (450, 60), (840, 150), (840, 380)], fill="#8fa3b0", outline="#37474f", width=4
    )
    for i in range(5):
        d.rectangle((110 + i * 150, 220, 200 + i * 150, 300), fill="#e3f2fd", outline="#37474f", width=3)
    d.text((30, 25), "Vista general de la nave", font=fuente(40, True), fill="#111111")
    d.text((30, 80), "Fotografía sin relación con la actuación", font=fuente(22), fill="#333333")
    _marca_en_imagen(d, ancho, alto)
    return _a_jpeg(img, "vista general de la nave (sin relación con la actuación)")


def imagen_escaneo(lineas: list[tuple[str, str]], titulo: str, texto_previo: list[str]) -> Image.Image:
    """Página "escaneada" (imagen, sin capa de texto) con título, prosa y filas etiqueta/valor, girada 90°."""
    ancho, alto = 1240, 1754  # A4 a 150 ppp
    img = Image.new("RGB", (ancho, alto), "white")
    d = ImageDraw.Draw(img)
    d.text((60, 40), MARCA, font=fuente(30, True), fill="black")
    d.text((60, 130), titulo, font=fuente(44, True), fill="black")
    y = 220
    for linea in texto_previo:
        d.text((60, y), linea, font=fuente(26), fill="black")
        y += 40
    y += 30
    x_valor = 760  # columna ancha: una etiqueta larga pegada al valor hace que el OCR se coma el numero
    d.line((60, y, ancho - 60, y), fill="black", width=3)
    for etiqueta, valor in lineas:
        f_etiqueta = fuente(28, True)
        while d.textlength(etiqueta, font=f_etiqueta) > x_valor - 110 and f_etiqueta.size > 16:
            f_etiqueta = fuente(f_etiqueta.size - 2, True)
        d.text((70, y + 14), etiqueta, font=f_etiqueta, fill="black")
        d.text((x_valor, y + 14), valor, font=fuente(28), fill="black")
        y += 64
        d.line((60, y, ancho - 60, y), fill="black", width=2)
    d.line((x_valor - 20, y - 64 * len(lineas), x_valor - 20, y), fill="black", width=2)
    d.line((60, y - 64 * len(lineas), 60, y), fill="black", width=3)
    d.line((ancho - 60, y - 64 * len(lineas), ancho - 60, y), fill="black", width=3)
    d.text(
        (60, alto - 90), f"{MARCA} · escaneo sintético girado 90 grados", font=fuente(24, True), fill="black"
    )
    return img.rotate(90, expand=True)


def jpeg_de(imagen: Image.Image, papel: str, *detalles: str) -> bytes:
    return _a_jpeg(imagen, papel, *detalles)
