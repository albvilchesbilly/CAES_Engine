"""Modelo de datos de un caso sintético (docs/01 §3.4): un solo modelo produce todos los documentos y el
ground truth, de modo que no pueden discrepar. Todo `Decimal` / `date`; nada de `float`.

Todo lo que contiene es inventado: empresas, personas, NIF (formato válido, ficticios), números de serie,
coordenadas, referencias catastrales. Ningún dato real, nunca.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

# ---------------------------------------------------------------------------
# Identificadores ficticios con formato válido
# ---------------------------------------------------------------------------

LETRAS_NIF = "TRWAGMYFPDXBNJZSQVHLCKE"
LETRAS_CONTROL_CIF = "JABCDEFGHI"


def nif_persona(numero: int) -> str:
    """NIF de persona física ficticio con letra de control correcta (mod 23)."""
    return f"{numero:08d}{LETRAS_NIF[numero % 23]}"


def cif_empresa(letra: str, numero: int) -> str:
    """CIF ficticio con dígito/letra de control calculado según el algoritmo oficial."""
    digitos = f"{numero:07d}"
    suma = 0
    for i, ch in enumerate(digitos):
        d = int(ch)
        if i % 2 == 0:  # posiciones impares (1ª, 3ª, ...): doble y suma de cifras
            doble = d * 2
            suma += doble // 10 + doble % 10
        else:
            suma += d
    control = (10 - suma % 10) % 10
    if letra in "KPQSNW":
        return f"{letra}{digitos}{LETRAS_CONTROL_CIF[control]}"
    return f"{letra}{digitos}{control}"


# ---------------------------------------------------------------------------
# Formato español de números y fechas (texto de los documentos)
# ---------------------------------------------------------------------------


def fmt_es(valor: Decimal | int, decimales: int | None = None) -> str:
    """`Decimal("1485")` → `1.485`; `Decimal("3.90")` → `3,90`; `Decimal("5.55")` → `5,55`."""
    d = Decimal(valor)
    if decimales is not None:
        d = d.quantize(Decimal(1).scaleb(-decimales))
    texto = f"{d:,f}"  # separador de miles ',' y decimal '.' → se invierten
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def fmt_fecha(fecha: date) -> str:
    return fecha.strftime("%d/%m/%Y")


# ---------------------------------------------------------------------------
# Entidades
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Persona:
    nombre: str
    nif: str
    cargo: str


@dataclass(frozen=True)
class Empresa:
    razon_social: str  # forma canónica, p. ej. "Industrias Sintéticas del Ebro, S.L."
    nif: str
    direccion: str
    representante: Persona

    def razon_social_variante(self) -> str:
        """Misma razón social con otra puntuación ("S.L." → "SL", sin coma) para ejercitar
        `cruce: normalizado`."""
        return self.razon_social.replace(", S.L.", " SL").replace(", S.A.", " SA")


@dataclass(frozen=True)
class Localizacion:
    utm_x: Decimal
    utm_y: Decimal
    huso: int
    referencia_catastral: str
    direccion: str


TIPOS_EQUIPO_TEXTO = {
    "bomba_dinamica": "Bomba dinámica (centrífuga)",
    "ventilador_axial": "Ventilador axial",
    "ventilador_radial": "Ventilador radial",
    "compresor_centrifugo": "Compresor centrífugo",
    "compresor_axial": "Compresor axial",
    "bomba_desplazamiento_positivo": "Bomba de desplazamiento positivo (tornillo)",
    "compresor_desplazamiento_positivo": "Compresor de desplazamiento positivo",
}

REGIMEN_TEXTO = {
    "constante_sin_modulacion": "Régimen constante sin modulación",
    "con_modulacion": "Régimen con modulación",
}


@dataclass(frozen=True)
class EquipoAccionado:
    tipo: str  # enumerado de la spec (ambito.tipos_equipo_*)
    fabricante: str
    modelo: str
    num_serie: str
    descripcion: str  # texto libre del fabricante

    @property
    def tipo_texto(self) -> str:
        return TIPOS_EQUIPO_TEXTO[self.tipo]


@dataclass(frozen=True)
class Motor:
    num_serie_motor: str
    num_serie_variador: str
    tipo_equipo_accionado: str
    regimen_previo: str
    PM: Decimal  # kW
    N1: Decimal  # rpm
    N2: Decimal  # rpm (media en MARCHA del registro; también declarada en certificado y ficha)
    P_prom: Decimal  # kW (media de potencia en MARCHA)
    h_antes: Decimal  # h/año (registro de horas previo)
    h_despues: Decimal  # h/año (extrapolado del registro: horas MARCHA/día × 365)
    descripcion: str
    fabricante_motor: str
    modelo_motor: str
    tension_v: int
    polos: int
    fabricante_variador: str
    modelo_variador: str
    potencia_variador_kw: Decimal
    precio_variador: Decimal
    equipo: EquipoAccionado
    perdidas_declaradas_variador: Decimal = Decimal("3.90")
    rendimiento_variador_pct: Decimal = Decimal("97.5")
    inicio_marcha_diaria: int = 6  # hora del día (0-23) en que arranca el turno registrado
    horas_marcha_diarias: int = (
        18  # h_despues = horas_marcha_diarias × 365 (registro de 36 días, paso 15 min)
    )

    def __post_init__(self) -> None:
        for nombre in ("PM", "N1", "N2", "P_prom", "h_antes", "h_despues"):
            valor = getattr(self, nombre)
            if not isinstance(valor, Decimal):
                raise TypeError(f"{nombre} debe ser Decimal, no {type(valor).__name__}")
        if self.h_despues != Decimal(self.horas_marcha_diarias) * 365:
            raise ValueError(
                f"{self.num_serie_motor}: h_despues ({self.h_despues}) debe ser horas_marcha_diarias × 365 "
                f"({self.horas_marcha_diarias * 365}) para que el registro la reproduzca exactamente"
            )
        if self.inicio_marcha_diaria + self.horas_marcha_diarias > 24:
            raise ValueError(f"{self.num_serie_motor}: el turno registrado no cabe en el día")

    @property
    def h(self) -> Decimal:
        return min(self.h_antes, self.h_despues)


@dataclass(frozen=True)
class Fechas:
    inicio: date  # pedido / factura
    fin: date  # certificado y puesta en marcha
    registro_inicio: date
    registro_fin: date  # exclusivo: el registro cubre [registro_inicio 00:00, registro_fin 00:00)
    firma_convenio: date
    firma_ficha: date
    horas_previo_inicio: date
    horas_previo_fin: date
    evaluacion: date

    @property
    def dias_registro(self) -> int:
        return (self.registro_fin - self.registro_inicio).days


@dataclass(frozen=True)
class Convenio:
    sujeto_delegado: Empresa
    titulo: str
    tipo_contraprestacion: str
    vida_util_anos: int
    numero: str


@dataclass(frozen=True)
class Variaciones:
    """Variaciones declaradas de cada caso sobre el base (docs/05 §2.2). Todas a `False`/vacío en A."""

    sin_registro: bool = False  # B: se omite registro_funcionamiento
    pm_certificado: dict[str, Decimal] = field(default_factory=dict)  # C: PM distinto en el certificado
    ficha_declara_ahorro: bool = False  # D: la ficha cumplimentada declara ahorro anual
    desordenado: bool = False  # G: nombres genéricos, PDF combinado, escaneo, fotos sueltas, irrelevante


PREFIJO_REGISTRO = "06_"


@dataclass(frozen=True)
class Caso:
    id: str  # "A".."G"
    carpeta: str  # "EXP001-A_completo"
    descripcion: str
    titular: Empresa
    instalador: Empresa
    localizacion: Localizacion
    fechas: Fechas
    motores: tuple[Motor, ...]
    convenio: Convenio
    factura_numero: str
    variaciones: Variaciones = field(default_factory=Variaciones)
    veredicto_esperado: str = "PREVALIDADO"
    reglas_falladas_esperadas: tuple[str, ...] = ()
    reglas_no_evaluables_esperadas: tuple[str, ...] = ()

    @property
    def n_motores(self) -> int:
        return len(self.motores)

    def motor(self, num_serie: str) -> Motor:
        for m in self.motores:
            if m.num_serie_motor == num_serie:
                return m
        raise KeyError(num_serie)

    def pm_en_certificado(self, motor: Motor) -> Decimal:
        return self.variaciones.pm_certificado.get(motor.num_serie_motor, motor.PM)

    def nombre_registro(self, motor: Motor) -> str:
        """Nombre del registro que declara el certificado. En A–F coincide con el fichero entregado; en G el
        certificado declara el nombre de exportación del SCADA y el fichero entregado se llama `datos.xlsx`
        (trampa: vinculación por hash, no por nombre)."""
        exportado = f"registro_funcionamiento_{motor.num_serie_motor}.xlsx"
        return exportado if self.variaciones.desordenado else f"{PREFIJO_REGISTRO}{exportado}"

    @property
    def calcula(self) -> bool:
        return self.veredicto_esperado in ("PREVALIDADO", "SUBSANABLE")
