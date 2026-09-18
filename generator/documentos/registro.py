"""Registro de funcionamiento (EVD-01): xlsx por motor con intervalos de 15 min durante 36 días y huella
SHA-256.

Hoja `registro`: columnas `fecha_hora`, `estado` (MARCHA/PARO), `velocidad_rpm`, `potencia_kw`, una fila cada
15 minutos desde `registro_inicio 00:00` hasta `registro_fin 00:00` (exclusivo). Cada día el motor está en
MARCHA `horas_marcha_diarias` horas seguidas desde `inicio_marcha_diaria`; así:

    h_despues = horas_MARCHA × 8760 / horas_periodo = (36 × k) × 8760 / 864 = k × 365      (INT-04)

y el registro reproduce `h_despues` exactamente (el modelo lo exige en `Motor.__post_init__`). En MARCHA la
velocidad sigue un ciclo de 4 valores simétrico alrededor de N2 (N2-6, N2+2, N2+6, N2-2) y la potencia otro
alrededor de P_prom (±1,2 / ±0,4 kW), de modo que las medias en MARCHA son **exactamente** N2 y P_prom
(INT-03):
las filas MARCHA de cada día son múltiplo de 4. En PARO velocidad y potencia valen 0.

**Datos canónicos** (INT-05; lo que se hashea y lo que el certificado declara):

    una línea por fila de la hoja `registro`, en su orden, sin cabecera, unidas por "\\n" (sin salto final),
    codificadas en UTF-8:  fecha_hora;estado;velocidad_rpm;potencia_kw
    - fecha_hora: ISO 8601 con segundos, sin zona (`2026-03-05T00:00:00`)
    - estado: `MARCHA` | `PARO`
    - velocidad_rpm: entero sin decimales (`1188`)
    - potencia_kw: número con exactamente un decimal y punto decimal (`59.6`, `0.0`)

`FORMATO_CANONICO` describe este formato y se copia al ground truth (`registro.formato_canonico`) y a la hoja
`metadatos` del xlsx. La hoja `metadatos` lleva también `num_serie_motor`, `num_serie_variador`, `inicio`,
`fin`, `intervalo_min`, `sistema` y `sha256_datos_canonicos`.

Determinismo: `created`/`modified` fijos y el zip se reescribe con fecha fija en todas las entradas (openpyxl
usa la hora actual en las cabeceras zip).
"""

from __future__ import annotations

import hashlib
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook

from generator.marcas import MARCA
from generator.modelo_caso import Caso, Motor

INTERVALO_MIN = 15
FILAS_POR_DIA = 24 * 60 // INTERVALO_MIN
CICLO_VELOCIDAD = (Decimal(-6), Decimal(2), Decimal(6), Decimal(-2))
CICLO_POTENCIA = (Decimal("-1.2"), Decimal("0.4"), Decimal("1.2"), Decimal("-0.4"))
SISTEMA = "SCADA sintético"
FECHA_FIJA_XLSX = datetime(2026, 4, 10, 8, 0, 0)
FORMATO_CANONICO = (
    "una línea por fila de la hoja 'registro', en su orden, sin cabecera, unidas por '\\n' sin salto final, "
    "UTF-8: fecha_hora;estado;velocidad_rpm;potencia_kw — fecha_hora ISO 8601 con segundos y sin zona "
    "(AAAA-MM-DDTHH:MM:SS); estado MARCHA|PARO; velocidad_rpm entero; potencia_kw con exactamente un decimal "
    "y punto decimal. SHA-256 hexadecimal en minúsculas."
)


@dataclass(frozen=True)
class Fila:
    fecha_hora: datetime
    estado: str
    velocidad_rpm: Decimal
    potencia_kw: Decimal

    def canonica(self) -> str:
        return (
            f"{self.fecha_hora.strftime('%Y-%m-%dT%H:%M:%S')};{self.estado};"
            f"{int(self.velocidad_rpm)};{self.potencia_kw.quantize(Decimal('0.1'))}"
        )


@dataclass(frozen=True)
class RegistroGenerado:
    motor: Motor
    filas: tuple[Fila, ...]
    xlsx: bytes
    sha256_canonico: str
    n_marcha: int

    @property
    def media_velocidad_marcha(self) -> Decimal:
        marcha = [f.velocidad_rpm for f in self.filas if f.estado == "MARCHA"]
        return sum(marcha, Decimal(0)) / len(marcha)

    @property
    def media_potencia_marcha(self) -> Decimal:
        marcha = [f.potencia_kw for f in self.filas if f.estado == "MARCHA"]
        return sum(marcha, Decimal(0)) / len(marcha)

    @property
    def h_despues_extrapolada(self) -> Decimal:
        horas_marcha = Decimal(self.n_marcha) * INTERVALO_MIN / 60
        horas_periodo = Decimal(len(self.filas)) * INTERVALO_MIN / 60
        return horas_marcha * 8760 / horas_periodo


def filas_registro(caso: Caso, motor: Motor) -> tuple[Fila, ...]:
    inicio = datetime.combine(caso.fechas.registro_inicio, datetime.min.time())
    fin = datetime.combine(caso.fechas.registro_fin, datetime.min.time())
    primera = motor.inicio_marcha_diaria * 60 // INTERVALO_MIN
    ultima = primera + motor.horas_marcha_diarias * 60 // INTERVALO_MIN
    filas: list[Fila] = []
    marcha_idx = 0
    t = inicio
    while t < fin:
        indice_dia = (t.hour * 60 + t.minute) // INTERVALO_MIN
        if primera <= indice_dia < ultima:
            k = marcha_idx % 4
            filas.append(Fila(t, "MARCHA", motor.N2 + CICLO_VELOCIDAD[k], motor.P_prom + CICLO_POTENCIA[k]))
            marcha_idx += 1
        else:
            filas.append(Fila(t, "PARO", Decimal(0), Decimal("0.0")))
        t += timedelta(minutes=INTERVALO_MIN)
    return tuple(filas)


def datos_canonicos(filas: tuple[Fila, ...]) -> bytes:
    return "\n".join(f.canonica() for f in filas).encode("utf-8")


def sha256_canonico(filas: tuple[Fila, ...]) -> str:
    return hashlib.sha256(datos_canonicos(filas)).hexdigest()


def _zip_determinista(contenido: bytes) -> bytes:
    """Reescribe el zip (xlsx) con fecha fija en cada entrada y en `docProps/core.xml` (openpyxl sobrescribe
    `modified` con la hora actual al guardar); el resto del contenido no cambia."""
    origen = zipfile.ZipFile(BytesIO(contenido))
    salida = BytesIO()
    fecha_iso = FECHA_FIJA_XLSX.strftime("%Y-%m-%dT%H:%M:%SZ")
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as destino:
        for info in origen.infolist():
            datos = origen.read(info.filename)
            if info.filename == "docProps/core.xml":
                texto = datos.decode("utf-8")
                for etiqueta in ("dcterms:created", "dcterms:modified"):
                    texto = re.sub(
                        rf"(<{etiqueta}[^>]*>)[^<]*(</{etiqueta}>)", rf"\g<1>{fecha_iso}\g<2>", texto
                    )
                datos = texto.encode("utf-8")
            nuevo = zipfile.ZipInfo(info.filename, date_time=FECHA_FIJA_XLSX.timetuple()[:6])
            nuevo.compress_type = zipfile.ZIP_DEFLATED
            nuevo.external_attr = info.external_attr
            destino.writestr(nuevo, datos)
    return salida.getvalue()


def generar_registro(caso: Caso, motor: Motor) -> RegistroGenerado:
    filas = filas_registro(caso, motor)
    huella = sha256_canonico(filas)
    wb = Workbook()
    ws = wb.active
    ws.title = "registro"
    ws.append(["fecha_hora", "estado", "velocidad_rpm", "potencia_kw"])
    for f in filas:
        ws.append([f.fecha_hora, f.estado, int(f.velocidad_rpm), f.potencia_kw.quantize(Decimal("0.1"))])
    ws.column_dimensions["A"].width = 20
    meta = wb.create_sheet("metadatos")
    inicio = datetime.combine(caso.fechas.registro_inicio, datetime.min.time())
    fin = datetime.combine(caso.fechas.registro_fin, datetime.min.time())
    for clave, valor in (
        ("marca", MARCA),
        ("num_serie_motor", motor.num_serie_motor),
        ("num_serie_variador", motor.num_serie_variador),
        ("inicio", inicio.strftime("%Y-%m-%dT%H:%M:%S")),
        ("fin", fin.strftime("%Y-%m-%dT%H:%M:%S")),
        ("intervalo_min", INTERVALO_MIN),
        ("filas", len(filas)),
        ("zona_horaria", "UTC"),
        ("sistema", SISTEMA),
        ("fichero_exportado", caso.nombre_registro(motor)),
        ("sha256_datos_canonicos", huella),
        ("formato_canonico", FORMATO_CANONICO),
    ):
        meta.append([clave, valor])
    meta.column_dimensions["A"].width = 26
    wb.properties.creator = SISTEMA
    wb.properties.lastModifiedBy = SISTEMA
    wb.properties.created = FECHA_FIJA_XLSX
    wb.properties.modified = FECHA_FIJA_XLSX
    buffer = BytesIO()
    wb.save(buffer)
    xlsx = _zip_determinista(buffer.getvalue())
    n_marcha = sum(1 for f in filas if f.estado == "MARCHA")
    registro = RegistroGenerado(motor, filas, xlsx, huella, n_marcha)
    if registro.media_velocidad_marcha != motor.N2 or registro.media_potencia_marcha != motor.P_prom:
        raise RuntimeError(f"{motor.num_serie_motor}: el registro no reproduce N2/P_prom exactamente")
    if registro.h_despues_extrapolada != motor.h_despues:
        raise RuntimeError(f"{motor.num_serie_motor}: el registro no reproduce h_despues exactamente")
    return registro
