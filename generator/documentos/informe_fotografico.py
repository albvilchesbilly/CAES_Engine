"""DOC-04: informe fotográfico con foto ANTES y DESPUÉS por motor y la placa de características. Los pies de
foto son texto nativo; los valores de la placa solo están en la imagen (OCR)."""

from __future__ import annotations

from io import BytesIO

from reportlab.lib.units import mm
from reportlab.platypus import Image as ImagenPDF

from generator.documentos.base import Seccion, bloque, espacio, nota, p, subtitulo, tabla_campos
from generator.documentos.imagenes import foto_motor, foto_placa
from generator.modelo_caso import Caso, fmt_fecha

TIPO = "informe_fotografico"
TITULO = "Informe fotográfico de la actuación – motor antes y después"
ANCHO_FOTO_MM = 105


def _imagen(datos: bytes) -> ImagenPDF:
    img = ImagenPDF(BytesIO(datos))
    escala = ANCHO_FOTO_MM * mm / img.imageWidth
    img.drawWidth = img.imageWidth * escala
    img.drawHeight = img.imageHeight * escala
    return img


def seccion(caso: Caso) -> Seccion:
    s = Seccion(TIPO, TITULO)
    f = s.flowables
    f.append(
        tabla_campos(
            [
                ("Titular", f"{caso.titular.razon_social} ({caso.titular.nif})"),
                ("Instalación", caso.localizacion.direccion),
                ("Fecha de las fotografías DESPUÉS", fmt_fecha(caso.fechas.fin)),
                ("Número de motores fotografiados", str(caso.n_motores)),
                ("Fotografías por motor", "3 (ANTES, DESPUÉS, placa de características)"),
            ]
        )
    )
    f.append(
        p(
            f"Se documentan {caso.n_motores} motor(es). Para cada uno se aporta una fotografía anterior a la "
            "instalación del variador, otra posterior con el variador instalado y una de la placa de "
            "características del motor."
        )
    )
    n = 0
    for i, m in enumerate(caso.motores, start=1):
        f.append(subtitulo(f"Motor {i}: {m.num_serie_motor} ({m.descripcion})"))
        f.append(s.marcador(m.num_serie_motor))
        f.append(
            tabla_campos(
                [
                    ("Nº de serie del motor", m.num_serie_motor),
                    ("Nº de serie del variador instalado", m.num_serie_variador),
                ]
            )
        )
        n += 1
        f.append(
            bloque(
                s.marcador(f"{m.num_serie_motor}|antes"),
                _imagen(foto_motor(m, "ANTES")),
                p(f"Foto {n} – ANTES – motor {m.num_serie_motor} (sin variador)"),
                espacio(2),
            )
        )
        n += 1
        f.append(
            bloque(
                s.marcador(f"{m.num_serie_motor}|despues"),
                _imagen(foto_motor(m, "DESPUES")),
                p(f"Foto {n} – DESPUÉS – motor {m.num_serie_motor} con variador {m.num_serie_variador}"),
                espacio(2),
            )
        )
        n += 1
        f.append(
            bloque(
                s.marcador(f"{m.num_serie_motor}|placa"),
                _imagen(foto_placa(m)),
                p(f"Foto {n} – Placa de características – motor {m.num_serie_motor}"),
                espacio(2),
            )
        )
    f.append(
        nota("Documento sintético generado para pruebas del CAE Engine. Las imágenes son dibujos generados.")
    )
    return s
