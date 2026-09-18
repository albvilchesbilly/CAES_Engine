"""Los siete casos A–G como variaciones declaradas de un caso base (docs/05 §2.1–§2.2).

Toda variación es un cambio en el modelo de datos, nunca una edición del documento generado. Los parámetros de
los motores 2 y 3 (casos E y F) los fija este módulo (docs/05 §2.3, nota sobre E y F) y quedan registrados
en `docs/decisiones/ADR-002` §4:

| Motor | Equipo | PM | N1 | N2 | h_antes | h_despues | h |
|---|---|---|---|---|---|---|---|
| M1 `MTR-SYN-0001` | bomba centrífuga | 110 kW | 1.485 | 1.188 (80 %) | 6.000 | 6.570 (18 h/día) | 6.000 |
| M2 `MTR-SYN-0002` | ventilador radial | 55 kW | 1.480 | 1.110 (75 %) | 5.500 | 5.840 (16 h/día) | 5.500 |
| M3 `MTR-SYN-0003` | compresor centríf. | 160 kW | 2.960 | 2.516 (85 %) | 7.000 | 6.205 (17 h/día) | 6.205 |

55 kW y 160 kW tienen fila exacta en el cuadro 6 (3,12 y 8,82 kW), así que `R-CAL-02` cumple en E y F. En M3
`h_despues < h_antes` (regla del menor h). El registro de 36 días con paso de 15 min reproduce `h_despues`
exactamente cuando es `horas_marcha_diarias × 365` (ver `documentos/registro.py`).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from generator.modelo_caso import (
    Caso,
    Convenio,
    Empresa,
    EquipoAccionado,
    Fechas,
    Localizacion,
    Motor,
    Persona,
    Variaciones,
    cif_empresa,
    nif_persona,
)

# ---------------------------------------------------------------------------
# Entidades ficticias comunes
# ---------------------------------------------------------------------------

TITULAR = Empresa(
    razon_social="Industrias Sintéticas del Ebro, S.L.",
    nif=cif_empresa("B", 9900101),
    direccion="Polígono Industrial Ficticio, parcela 12, 50999 Villasintética (Zaragoza)",
    representante=Persona("Ana Ficticia Sintética", nif_persona(99000101), "Administradora única"),
)

INSTALADOR = Empresa(
    razon_social="Automatismos Sintéticos del Jalón, S.L.",
    nif=cif_empresa("B", 9900202),
    direccion="Calle Inventada 7, nave 3, 50998 Villasintética (Zaragoza)",
    representante=Persona("Luis Inventado Prueba", nif_persona(99000202), "Director técnico"),
)

SUJETO_DELEGADO = Empresa(
    razon_social="Delegado Sintético de Ahorro Energético, S.A.",
    nif=cif_empresa("A", 9900303),
    direccion="Avenida Imaginaria 100, planta 4, 28999 Madrid",
    representante=Persona("Marta Supuesta Ejemplo", nif_persona(99000303), "Apoderada"),
)

LOCALIZACION = Localizacion(
    utm_x=Decimal("612345"),
    utm_y=Decimal("4612345"),
    huso=30,
    referencia_catastral="9999901SY0000S0001ZZ",
    direccion="Polígono Industrial Ficticio, parcela 12, 50999 Villasintética (Zaragoza)",
)

FECHAS = Fechas(
    inicio=date(2026, 2, 10),
    fin=date(2026, 3, 2),
    registro_inicio=date(2026, 3, 5),
    registro_fin=date(2026, 4, 10),
    firma_convenio=date(2026, 4, 20),
    firma_ficha=date(2026, 4, 22),
    horas_previo_inicio=date(2025, 1, 1),
    horas_previo_fin=date(2025, 12, 31),
    evaluacion=date(2026, 9, 18),
)

FABRICANTE_MOTOR = "Motores Sintéticos Ibéricos, S.A."
FABRICANTE_VARIADOR = "Variadores Ficticios Europa, S.L."

# ---------------------------------------------------------------------------
# Motores
# ---------------------------------------------------------------------------

MOTOR_1 = Motor(
    num_serie_motor="MTR-SYN-0001",
    num_serie_variador="VSD-SYN-0001",
    tipo_equipo_accionado="bomba_dinamica",
    regimen_previo="constante_sin_modulacion",
    PM=Decimal("110"),
    N1=Decimal("1485"),
    N2=Decimal("1188"),
    P_prom=Decimal("60.0"),
    h_antes=Decimal("6000"),
    h_despues=Decimal("6570"),
    descripcion="Bomba centrífuga de impulsión de agua de proceso",
    fabricante_motor=FABRICANTE_MOTOR,
    modelo_motor="MSI-315M-4",
    tension_v=400,
    polos=4,
    fabricante_variador=FABRICANTE_VARIADOR,
    modelo_variador="VFE-110-T4",
    potencia_variador_kw=Decimal("110"),
    precio_variador=Decimal("8950.00"),
    equipo=EquipoAccionado(
        tipo="bomba_dinamica",
        fabricante="Bombas Ficticias del Norte, S.A.",
        modelo="BCN-250-400",
        num_serie="BMB-SYN-0001",
        descripcion="Bomba centrífuga horizontal de una etapa, impulsor cerrado",
    ),
    inicio_marcha_diaria=6,
    horas_marcha_diarias=18,
)

MOTOR_2 = Motor(
    num_serie_motor="MTR-SYN-0002",
    num_serie_variador="VSD-SYN-0002",
    tipo_equipo_accionado="ventilador_radial",
    regimen_previo="constante_sin_modulacion",
    PM=Decimal("55"),
    N1=Decimal("1480"),
    N2=Decimal("1110"),
    P_prom=Decimal("24.0"),
    h_antes=Decimal("5500"),
    h_despues=Decimal("5840"),
    descripcion="Ventilador radial de extracción de aire de secado",
    fabricante_motor=FABRICANTE_MOTOR,
    modelo_motor="MSI-250M-4",
    tension_v=400,
    polos=4,
    fabricante_variador=FABRICANTE_VARIADOR,
    modelo_variador="VFE-055-T4",
    potencia_variador_kw=Decimal("55"),
    precio_variador=Decimal("4720.00"),
    equipo=EquipoAccionado(
        tipo="ventilador_radial",
        fabricante="Ventiladores Imaginarios, S.L.",
        modelo="VRI-900-C",
        num_serie="VEN-SYN-0002",
        descripcion="Ventilador centrífugo de álabes curvados hacia atrás",
    ),
    inicio_marcha_diaria=8,
    horas_marcha_diarias=16,
)

MOTOR_3 = Motor(
    num_serie_motor="MTR-SYN-0003",
    num_serie_variador="VSD-SYN-0003",
    tipo_equipo_accionado="compresor_centrifugo",
    regimen_previo="constante_sin_modulacion",
    PM=Decimal("160"),
    N1=Decimal("2960"),
    N2=Decimal("2516"),
    P_prom=Decimal("98.0"),
    h_antes=Decimal("7000"),
    h_despues=Decimal("6205"),
    descripcion="Compresor centrífugo de aire comprimido de planta",
    fabricante_motor=FABRICANTE_MOTOR,
    modelo_motor="MSI-315L-2",
    tension_v=400,
    polos=2,
    fabricante_variador=FABRICANTE_VARIADOR,
    modelo_variador="VFE-160-T4",
    potencia_variador_kw=Decimal("160"),
    precio_variador=Decimal("12860.00"),
    equipo=EquipoAccionado(
        tipo="compresor_centrifugo",
        fabricante="Compresores Supuestos, S.A.",
        modelo="CSC-160-R",
        num_serie="CMP-SYN-0003",
        descripcion="Compresor centrífugo de una etapa con difusor de álabes",
    ),
    inicio_marcha_diaria=7,
    horas_marcha_diarias=17,
)

EQUIPO_TORNILLO = EquipoAccionado(
    tipo="bomba_desplazamiento_positivo",
    fabricante="Bombas Ficticias del Norte, S.A.",
    modelo="BTN-110-S",
    num_serie="BMB-SYN-0001",
    descripcion="Bomba de tornillo excéntrico (desplazamiento positivo) para fluidos viscosos",
)

CONVENIO = Convenio(
    sujeto_delegado=SUJETO_DELEGADO,
    titulo="Implantación de variador de velocidad en motor existente de bomba centrífuga (IND240)",
    tipo_contraprestacion="Económica: pago único por kWh de ahorro certificado",
    vida_util_anos=10,
    numero="CONV-SYN-2026-001",
)

# ---------------------------------------------------------------------------
# Caso base y variaciones
# ---------------------------------------------------------------------------


def caso_base() -> Caso:
    """Caso A: actuación perfecta, un motor de 110 kW (docs/05 §2.3)."""
    return Caso(
        id="A",
        carpeta="EXP001-A_completo",
        descripcion="Actuación perfecta, 1 motor 110 kW",
        titular=TITULAR,
        instalador=INSTALADOR,
        localizacion=LOCALIZACION,
        fechas=FECHAS,
        motores=(MOTOR_1,),
        convenio=CONVENIO,
        factura_numero="F-SYN-2026-0041",
    )


def variacion_b(base: Caso) -> Caso:
    """B: sin registro de funcionamiento; N2 y P_prom solo declarados."""
    return replace(
        base,
        id="B",
        carpeta="EXP001-B_falta_registro",
        descripcion="N2 solo declarado, sin registro de 30 días",
        variaciones=Variaciones(sin_registro=True),
        veredicto_esperado="SUBSANABLE",
        reglas_falladas_esperadas=("R-EVD-04", "R-DOC-01"),
        reglas_no_evaluables_esperadas=("R-EVD-01", "R-EVD-02", "R-EVD-03", "R-CON-03"),
    )


def variacion_c(base: Caso) -> Caso:
    """C: el certificado del instalador dice PM = 90 kW; el resto de fuentes, 110 kW."""
    return replace(
        base,
        id="C",
        carpeta="EXP001-C_contradictorio",
        descripcion="PM 110 kW en ficha técnica y placa frente a 90 kW en el certificado",
        variaciones=Variaciones(pm_certificado={MOTOR_1.num_serie_motor: Decimal("90")}),
        veredicto_esperado="BLOQUEADO",
        reglas_falladas_esperadas=("R-CON-01",),
        reglas_no_evaluables_esperadas=("R-CAL-03", "R-CON-06"),
    )


def variacion_d(base: Caso) -> Caso:
    """D: bomba de tornillo (desplazamiento positivo, EXC-03); ficha y convenio declaran ahorro igualmente."""
    motor = replace(
        MOTOR_1,
        tipo_equipo_accionado=EQUIPO_TORNILLO.tipo,
        equipo=EQUIPO_TORNILLO,
        descripcion="Bomba de tornillo de trasiego de fluidos viscosos",
    )
    convenio = replace(
        CONVENIO,
        titulo="Implantación de variador de velocidad en motor existente de bomba de tornillo (IND240)",
    )
    return replace(
        base,
        id="D",
        carpeta="EXP001-D_fuera_ambito",
        descripcion="Bomba de tornillo (desplazamiento positivo), exclusión EXC-03",
        motores=(motor,),
        convenio=convenio,
        variaciones=Variaciones(ficha_declara_ahorro=True),
        veredicto_esperado="NO_ELEGIBLE",
        reglas_falladas_esperadas=("R-AMB-01",),
    )


def variacion_e(base: Caso) -> Caso:
    """E: + M2 ventilador radial 55 kW."""
    return replace(
        base,
        id="E",
        carpeta="EXP001-E_dos_motores",
        descripcion="Dos motores: bomba centrífuga 110 kW + ventilador radial 55 kW",
        motores=(MOTOR_1, MOTOR_2),
        convenio=replace(
            CONVENIO,
            titulo="Implantación de variadores de velocidad en dos motores existentes (IND240)",
            numero="CONV-SYN-2026-002",
        ),
        factura_numero="F-SYN-2026-0042",
    )


def variacion_f(base: Caso) -> Caso:
    """F: + M3 compresor centrífugo 160 kW con h_despues < h_antes."""
    return replace(
        base,
        id="F",
        carpeta="EXP001-F_tres_motores",
        descripcion="Tres motores: + compresor centrífugo 160 kW con h_despues < h_antes",
        motores=(MOTOR_1, MOTOR_2, MOTOR_3),
        convenio=replace(
            CONVENIO,
            titulo="Implantación de variadores de velocidad en tres motores existentes (IND240)",
            numero="CONV-SYN-2026-003",
        ),
        factura_numero="F-SYN-2026-0043",
    )


def variacion_g(base: Caso) -> Caso:
    """G: los mismos datos que A con distinta forma (nombres genéricos, PDF combinado, escaneo, fotos)."""
    return replace(
        base,
        id="G",
        carpeta="EXP001-G_desordenado",
        descripcion=(
            "Mismos datos que A: nombres genéricos, PDF combinado, escaneo girado, fotos sueltas, irrelevante"
        ),
        variaciones=Variaciones(desordenado=True),
    )


VARIACIONES = {
    "A": lambda base: base,
    "B": variacion_b,
    "C": variacion_c,
    "D": variacion_d,
    "E": variacion_e,
    "F": variacion_f,
    "G": variacion_g,
}


def todos_los_casos() -> list[Caso]:
    base = caso_base()
    return [funcion(base) for funcion in VARIACIONES.values()]


def caso(id: str) -> Caso:
    return VARIACIONES[id](caso_base())
