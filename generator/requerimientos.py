"""Material sintético de S3.5 (ADR-010 §5, contrato C12): tres requerimientos y un expediente de tres
actuaciones, con su ground truth.

**Qué hay aquí y por qué.**

1. **Tres requerimientos, uno por origen** (`verificador`, `GA`, `CN`), cada uno con su documento PDF y la
   marca "DOCUMENTO SINTÉTICO – SOLO PRUEBAS" en cada página. Entre los cinco motivos hay, como exige el
   contrato: dos que mapean a una **regla** real de `spec/IND240_v1.1.yaml` (uno citando el identificador,
   otro solo por vocabulario), dos que mapean a un **tipo documental** real que falta, y uno que **no** se
   puede mapear con un léxico determinista —prosa administrativa sin regla ni documento— y que por tanto
   debe producir cero items y escalar a un humano. Si los tres fueran fáciles, el banco mentiría.
2. **Un expediente de tres actuaciones**, porque con una sola el contagio no se distingue de no contagiar.
   Se compone **reutilizando los casos A, E y F** del banco: son las tres únicas actuaciones que pueden
   llegar a `VERIFICADA_FAVORABLE` (las demás son `SUBSANABLE`, `BLOQUEADO` o `NO_ELEGIBLE`, y al expediente
   solo entra lo favorable, `docs/02` §5.1), comparten CCAA, año, sector y verificador —las cuatro claves que
   hacen un expediente (`CLAUDE.md` §3)— y tienen contenido distinto (1, 2 y 3 motores). No se genera ninguna
   actuación nueva: eso obligaría a tocar los siete casos y su ground truth.

Nada de esto modifica los casos A–G ni `expedientes/_resultados_esperados/`. El material cae en
`expedientes/_requerimientos/`, que es material de S3.5 y no ground truth de la Fase 0.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from engine.calculo import a_dict
from engine.spec_registry import Spec
from generator.calculo_caso import calcular_caso, cargar_spec_activa
from generator.casos import caso as caso_del_banco
from generator.documentos import requerimiento as doc_requerimiento
from generator.documentos.base import construir_pdf
from generator.marcas import MARCA
from generator.modelo_caso import cif_empresa
from generator.modelo_requerimiento import (
    ActuacionEnExpediente,
    Expediente,
    Motivo,
    Organismo,
    Requerimiento,
)

RAIZ = Path(__file__).resolve().parents[1]
SALIDA_POR_DEFECTO = RAIZ / "expedientes"
CARPETA_REQUERIMIENTOS = "_requerimientos"
FICHERO_GROUND_TRUTH = "requerimientos.json"

HUSO = timezone(timedelta(hours=2))
CASOS_DEL_EXPEDIENTE = ("A", "E", "F")
CCAA = "Aragón"  # la que corresponde a la dirección ficticia del banco (Zaragoza); no hay dato real detrás

# ---------------------------------------------------------------------------
# Organismos ficticios
# ---------------------------------------------------------------------------

VERIFICADOR = Organismo(
    nombre="Verificación Sintética Independiente, S.A. (entidad ficticia de pruebas)",
    papel="verificador",
    codigo="VER-SYN-007",
    nif=cif_empresa("A", 9900404),
)

ORGANO_GESTOR = Organismo(
    nombre="Órgano Gestor Autonómico Sintético de Certificados de Ahorro Energético (organismo ficticio)",
    papel="organo_gestor_autonomico",
    codigo="GA-SYN-050",
    nif=cif_empresa("S", 9900505),
)

COORDINACION_NACIONAL = Organismo(
    nombre="Coordinación Nacional Sintética del sistema CAE – Unidad de Revisión Formal (organismo ficticio)",
    papel="coordinacion_nacional",
    codigo="CN-SYN-001",
    nif=cif_empresa("S", 9900606),
)

# ---------------------------------------------------------------------------
# Identidades del expediente y de sus actuaciones
# ---------------------------------------------------------------------------

EXPEDIENTE_ID = "EXPD-SYN-2026-001"
ACTUACIONES = {
    "A": ("ACT-SYN-2026-001", "CAE-SYN-2026-0001"),
    "E": ("ACT-SYN-2026-002", "CAE-SYN-2026-0002"),
    "F": ("ACT-SYN-2026-003", "CAE-SYN-2026-0003"),
}

NOTA_SOLAPE = (
    "Las tres actuaciones se materializan con los casos A, E y F del banco, que comparten el motor "
    "MTR-SYN-0001 porque E y F son variaciones de A. Es un artefacto declarado de la reutilización: este "
    "expediente sirve para el contagio y no sirve como caso limpio de una futura regla de cruce entre "
    "actuaciones (duplicidad de número de serie en el mismo expediente, familia R-XCK de docs/04)."
)

CRONOLOGIA = (
    ("2026-03-02", "Fin de las tres actuaciones (fecha de puesta en marcha del modelo del banco)"),
    ("2026-05-04", "Las tres actuaciones se envían a verificación (ENVIADA_A_VERIFICACION)"),
    (
        "2026-05-12",
        "El verificador requiere rectificación de la actuación ACT-SYN-2026-001 (REQ-SYN-2026-001)",
    ),
    ("2026-06-10", "Las tres actuaciones quedan VERIFICADA_FAVORABLE"),
    ("2026-06-30", "Se presenta el expediente EXPD-SYN-2026-001 con las tres actuaciones"),
    ("2026-07-15", "El órgano gestor autonómico requiere subsanación en fase 3A (REQ-SYN-2026-002)"),
    ("2026-09-14", "Primera ronda de la coordinación nacional en fase 3B (no se materializa documento)"),
    ("2026-10-05", "Segunda ronda de la coordinación nacional (REQ-SYN-2026-003, ronda 2)"),
)

# ---------------------------------------------------------------------------
# Los motivos: el texto tal como lo emitiría quien requiere, y lo que debe reconocerse de él
# ---------------------------------------------------------------------------

MOTIVO_VERIFICADOR_REGLA = Motivo(
    numero=1,
    texto=(
        "Revisada la documentación de la actuación, el ahorro anual de energía final que figura en el "
        "apartado 4 del convenio CAE no se corresponde con el resultado de aplicar la fórmula de la ficha "
        "IND240 a los datos aportados. Procede rectificar el convenio CAE o justificar documentalmente la "
        "diferencia. Este punto figura identificado como R-CON-06 en el informe de prevalidación que "
        "acompaña a la actuación."
    ),
    dificultad="explicita",
    regla_esperada="R-CON-06",
    pistas=("ahorro anual de energía final", "convenio CAE", "R-CON-06"),
    nota=(
        "El motivo cita el identificador de la regla porque el verificador tiene a la vista el informe de "
        "prevalidación. Es el motivo fácil: garantiza un item con el que probar la reapertura."
    ),
)

MOTIVO_VERIFICADOR_DOCUMENTO = Motivo(
    numero=2,
    texto=(
        "No consta aportada la ficha técnica del equipo accionado correspondiente al motor con número de "
        "serie MTR-SYN-0001, necesaria para acreditar que el equipo accionado es rotodinámico y que la "
        "actuación queda incluida en el ámbito de la ficha. Se requiere su aportación."
    ),
    dificultad="lexica",
    documento_esperado="ficha_tecnica_equipo_accionado",
    pistas=("No consta aportada", "ficha técnica del equipo accionado", "MTR-SYN-0001"),
    nota=(
        "Tipo documental EVD-05 de la spec. El léxico tiene que reconocer el nombre del tipo y que se pide "
        "por ausencia; una regla admisible además del documento sería R-DOC-01 (documentos obligatorios)."
    ),
)

MOTIVO_GA_DOCUMENTO = Motivo(
    numero=1,
    texto=(
        "Del examen de la documentación obrante en el expediente no puede descartarse que la instalación de "
        "los variadores de velocidad haya sido ejecutada con personal propio del beneficiario. En tal "
        "supuesto resulta exigible el certificado de técnico competente, que no se ha aportado; en caso "
        "contrario deberá acreditarse que la ejecución correspondió a una empresa instaladora habilitada "
        "distinta del beneficiario."
    ),
    dificultad="lexica",
    documento_esperado="certificado_tecnico_competente",
    pistas=("certificado de técnico competente", "no se ha aportado"),
    nota=(
        "Tipo documental DOC-05B, obligatorio condicional. Engancha con la decisión abierta "
        "`instalacion_personal_propio` (CLAUDE.md §6)."
    ),
)

MOTIVO_GA_REGLA = Motivo(
    numero=2,
    texto=(
        "La inalterabilidad del registro de parámetros de funcionamiento se acredita únicamente mediante una "
        "huella SHA-256 declarada en el certificado de la propia empresa instaladora, sin sello de tiempo ni "
        "intervención de un tercero de confianza. Deberá acreditarse la integridad del registro aportado "
        "para cada una de las tres actuaciones que integran el expediente."
    ),
    dificultad="lexica",
    regla_esperada="R-EVD-03",
    pistas=("inalterabilidad del registro", "huella SHA-256", "tres actuaciones"),
    nota=(
        "Aquí no hay identificador de regla: el léxico tiene que reconocerla por el vocabulario "
        "('inalterabilidad', 'registro', 'huella'). La regla lleva INT-05, así que el motivo es además "
        "discutible en cuanto al fondo, como en la vida real."
    ),
)

MOTIVO_CN_NO_MAPEABLE = Motivo(
    numero=1,
    texto=(
        "Examinadas las alegaciones y la información remitida en contestación al requerimiento anterior, y "
        "sin perjuicio de lo que resulte de ulteriores comprobaciones, se aprecia que lo aportado no permite "
        "formar juicio bastante sobre la adecuación de lo actuado a lo declarado por el interesado. En "
        "consecuencia, se le requiere para que complete la información en los términos que estime "
        "procedentes, con advertencia de que, de no atenderse en el plazo señalado, se continuará el "
        "procedimiento con los datos que obren en poder de esta unidad."
    ),
    dificultad="no_mapeable",
    nota=(
        "Prosa administrativa: no cita ninguna regla ni ningún tipo documental. La interpretación correcta "
        "es cero items y escalado a un humano (ADR-010 §3, decisión 2). Un léxico que dispare aquí por "
        "'complete la información' produce un falso positivo, que es justo lo que este motivo mide."
    ),
)

# ---------------------------------------------------------------------------
# Los tres requerimientos
# ---------------------------------------------------------------------------

REQUERIMIENTO_VERIFICADOR = Requerimiento(
    id="REQ-SYN-2026-001",
    origen="verificador",
    organismo=VERIFICADOR,
    literal_plataforma="PDTE_RECTIFICACION_VER",
    fase="1B",
    asunto="Rectificación de la actuación ACT-SYN-2026-001",
    referencia_oficial="VER-SYN-007/2026/0031",
    recibido_en=datetime(2026, 5, 12, 10, 30, tzinfo=HUSO),
    plazo_dias=10,
    actuacion_id=ACTUACIONES["A"][0],
    expediente_id=None,
    grupo_id=None,
    motivos=(MOTIVO_VERIFICADOR_REGLA, MOTIVO_VERIFICADOR_DOCUMENTO),
    preambulo=(
        "Con carácter previo a la emisión del dictamen de verificación, y al amparo de lo previsto para la "
        "rectificación de actuaciones, se requiere al sujeto para que subsane los siguientes extremos:"
    ),
    advertencia=(
        "El plazo de contestación es de 10 días hábiles desde la notificación. Transcurrido dicho plazo sin "
        "atender el requerimiento, se emitirá el dictamen con la documentación obrante."
    ),
)

REQUERIMIENTO_GA = Requerimiento(
    id="REQ-SYN-2026-002",
    origen="GA",
    organismo=ORGANO_GESTOR,
    literal_plataforma="REQUERIDO_GA",
    fase="3A",
    asunto=f"Subsanación del expediente {EXPEDIENTE_ID} en validación técnica",
    referencia_oficial="GA-SYN-050/2026/EXP-0114",
    recibido_en=datetime(2026, 7, 15, 9, 15, tzinfo=HUSO),
    plazo_dias=15,
    actuacion_id=ACTUACIONES["E"][0],
    expediente_id=EXPEDIENTE_ID,
    grupo_id=None,
    motivos=(MOTIVO_GA_DOCUMENTO, MOTIVO_GA_REGLA),
    preambulo=(
        "En el curso de la validación técnica del expediente de referencia, que comprende tres actuaciones, "
        "se requiere al sujeto para que subsane los siguientes extremos. La subsanación afecta al expediente "
        "en su conjunto:"
    ),
    advertencia=(
        "El plazo de contestación es de 15 días hábiles desde la notificación. La falta de subsanación "
        "afecta a la totalidad del expediente, sin perjuicio del derecho a desistir."
    ),
)

REQUERIMIENTO_CN = Requerimiento(
    id="REQ-SYN-2026-003",
    origen="CN",
    organismo=COORDINACION_NACIONAL,
    literal_plataforma="REQUERIDO_CN",
    fase="3B",
    asunto=f"Segunda ronda de requerimiento sobre el expediente {EXPEDIENTE_ID}",
    referencia_oficial="CN-SYN-001/2026/RF-0407",
    recibido_en=datetime(2026, 10, 5, 11, 45, tzinfo=HUSO),
    plazo_dias=10,
    actuacion_id=ACTUACIONES["F"][0],
    expediente_id=EXPEDIENTE_ID,
    grupo_id=None,
    ronda=2,
    motivos=(MOTIVO_CN_NO_MAPEABLE,),
    preambulo=(
        "En la revisión formal del expediente de referencia, y en segunda ronda tras la contestación al "
        "requerimiento de 14 de septiembre de 2026, se hace constar lo siguiente:"
    ),
    advertencia=(
        "El plazo de contestación es de 10 días hábiles desde la notificación. Se advierte de que esta es la "
        "segunda y última ronda prevista en la tramitación de la que se ha dado traslado al interesado."
    ),
)

REQUERIMIENTOS = (REQUERIMIENTO_VERIFICADOR, REQUERIMIENTO_GA, REQUERIMIENTO_CN)


# ---------------------------------------------------------------------------
# Composición del expediente a partir de los casos del banco
# ---------------------------------------------------------------------------


def construir_expediente() -> Expediente:
    """Expediente de tres actuaciones sobre los casos A, E y F, con las cuatro claves comprobadas."""
    casos = [caso_del_banco(id) for id in CASOS_DEL_EXPEDIENTE]
    anios = {c.fechas.fin.year for c in casos}
    if len(anios) != 1:
        raise ValueError(f"las actuaciones del expediente no comparten año: {sorted(anios)}")
    localizaciones = {c.localizacion.referencia_catastral for c in casos}
    if len(localizaciones) != 1:
        raise ValueError("las actuaciones del expediente no comparten localización, luego tampoco CCAA")
    veredictos = {c.veredicto_esperado for c in casos}
    if veredictos != {"PREVALIDADO"}:
        raise ValueError(f"al expediente solo entra lo que puede ser favorable; hay {sorted(veredictos)}")
    spec = cargar_spec_activa()
    return Expediente(
        id=EXPEDIENTE_ID,
        ccaa=CCAA,
        anio=anios.pop(),
        sector=str(spec.datos["ficha"]["sector"]),
        verificador=VERIFICADOR,
        estado_plataforma="EN_VALIDACION_TECNICA",
        presentado_en=date(2026, 6, 30),
        actuaciones=tuple(
            ActuacionEnExpediente(
                actuacion_id=ACTUACIONES[c.id][0],
                codigo_identificativo_propio=ACTUACIONES[c.id][1],
                caso_id=c.id,
                carpeta=c.carpeta,
            )
            for c in casos
        ),
        nota_solape=NOTA_SOLAPE,
    )


# ---------------------------------------------------------------------------
# Generación de los documentos y del ground truth
# ---------------------------------------------------------------------------


@dataclass
class RequerimientoGenerado:
    """Un requerimiento con su PDF ya construido."""

    requerimiento: Requerimiento
    contenido: bytes

    @property
    def nombre(self) -> str:
        return self.requerimiento.nombre_fichero

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.contenido).hexdigest()


@dataclass
class MaterialGenerado:
    """Lo que produce este módulo: los tres documentos, el expediente y el ground truth de ambos."""

    requerimientos: list[RequerimientoGenerado]
    expediente: Expediente
    ground_truth: dict

    def generado(self, id: str) -> RequerimientoGenerado:
        for g in self.requerimientos:
            if g.requerimiento.id == id:
                return g
        raise KeyError(id)


def _pdf(requerimiento: Requerimiento) -> bytes:
    return construir_pdf([doc_requerimiento.seccion(requerimiento)])


def _item_esperado(motivo: Motivo) -> dict[str, object]:
    return {
        "texto_literal": motivo.texto,
        "regla_id": motivo.regla_esperada,
        "documento": motivo.documento_esperado,
        "variable": motivo.variable_esperada,
        "pistas": list(motivo.pistas),
    }


def _interpretacion_esperada(requerimiento: Requerimiento) -> dict[str, object]:
    items = [_item_esperado(m) for m in requerimiento.motivos if m.tipo_esperado != "nada"]
    sin_mapear = [m.numero for m in requerimiento.motivos if m.tipo_esperado == "nada"]
    return {
        "items": items,
        "motivos_sin_mapear": sin_mapear,
        "escala_a_humano": bool(sin_mapear),
        "confirmacion_humana_obligatoria": True,  # R-REQ-02: ninguna interpretación reabre sola
    }


def _contagio_esperado(requerimiento: Requerimiento, expediente: Expediente) -> list[dict[str, object]]:
    """A qué actuaciones alcanza el requerimiento (docs/03 §10.5, docs/02 §5.6).

    Se deriva del **alcance declarado**, no del origen: `expediente` contagia a todas; `grupo` sin grupo
    constituido alcanza solo a la actuación requerida.
    """
    if requerimiento.alcance == "expediente":
        alcanzadas: tuple[str, ...] = expediente.ids_actuacion
    elif requerimiento.grupo_id is None:
        alcanzadas = (requerimiento.actuacion_id,)
    else:
        raise RuntimeError(
            f"{requerimiento.id}: alcance de grupo con grupo constituido; el banco no modela grupos todavía"
        )
    return [
        {
            "actuacion_id": actuacion_id,
            "afectada_directamente": actuacion_id == requerimiento.actuacion_id,
            "ciclo_esperado": "PENDIENTE_SUBSANACION",
        }
        for actuacion_id in alcanzadas
    ]


def _requerimiento_gt(generado: RequerimientoGenerado, expediente: Expediente) -> dict[str, object]:
    r = generado.requerimiento
    return {
        "id": r.id,
        "origen": r.origen,
        "organismo": {
            "nombre": r.organismo.nombre,
            "papel": r.organismo.papel,
            "codigo": r.organismo.codigo,
            "nif": r.organismo.nif,
        },
        "fichero": generado.nombre,
        "informe_sha256": generado.sha256,
        "literal_plataforma": r.literal_plataforma,
        "fase": r.fase,
        "referencia_oficial": r.referencia_oficial,
        "recibido_en": r.recibido_en.isoformat(),
        "plazo_dias": r.plazo_dias,
        "ronda": r.ronda,
        "actuacion_id": r.actuacion_id,
        "expediente_id": r.expediente_id,
        "grupo_id": r.grupo_id,
        "alcance": r.alcance,
        "motivos": [
            {
                "numero": m.numero,
                "texto": m.texto,
                "tipo_esperado": m.tipo_esperado,
                "dificultad": m.dificultad,
                "regla_esperada": m.regla_esperada,
                "documento_esperado": m.documento_esperado,
                "variable_esperada": m.variable_esperada,
                "pistas": list(m.pistas),
                "nota": m.nota,
            }
            for m in r.motivos
        ],
        "interpretacion_esperada": _interpretacion_esperada(r),
        "contagio_esperado": _contagio_esperado(r, expediente),
    }


def _expediente_gt(expediente: Expediente, spec: Spec) -> dict[str, object]:
    actuaciones = []
    for a in expediente.actuaciones:
        caso = caso_del_banco(a.caso_id)
        calculo = calcular_caso(caso, spec)
        if calculo.total is None or calculo.total_cae is None:
            raise RuntimeError(f"caso {a.caso_id}: el cálculo de referencia falló")
        actuaciones.append(
            {
                "actuacion_id": a.actuacion_id,
                "codigo_identificativo_propio": a.codigo_identificativo_propio,
                "caso": a.caso_id,
                "carpeta": a.carpeta,
                "estado_plataforma": a.estado_plataforma,
                "veredicto_esperado": caso.veredicto_esperado,
                "n_motores": caso.n_motores,
                # `a_dict` normaliza el Decimal igual que el ground truth de los siete casos
                "aetotal_exacto": a_dict(calculo)["total"],
                "aetotal_cae": calculo.total_cae,
            }
        )
    return {
        "id": expediente.id,
        "ccaa": expediente.ccaa,
        "anio": expediente.anio,
        "sector": expediente.sector,
        "verificador": {
            "nombre": expediente.verificador.nombre,
            "codigo": expediente.verificador.codigo,
            "nif": expediente.verificador.nif,
        },
        "estado_plataforma": expediente.estado_plataforma,
        "presentado_en": expediente.presentado_en.isoformat(),
        "claves_de_agrupacion": ["ccaa", "anio", "sector", "verificador"],
        "actuaciones": actuaciones,
        "nota_solape": expediente.nota_solape,
    }


def _cobertura(requerimientos: list[RequerimientoGenerado]) -> dict[str, list[str]]:
    cobertura: dict[str, list[str]] = {"regla": [], "documento": [], "nada": []}
    for g in requerimientos:
        for m in g.requerimiento.motivos:
            cobertura[m.tipo_esperado].append(f"{g.requerimiento.id}#{m.numero}")
    return cobertura


def generar(spec: Spec | None = None) -> MaterialGenerado:
    """Construye en memoria los tres PDF, el expediente y el ground truth de todo ello."""
    spec = spec or cargar_spec_activa()
    expediente = construir_expediente()
    generados = [RequerimientoGenerado(r, _pdf(r)) for r in REQUERIMIENTOS]
    if len({g.nombre for g in generados}) != len(generados):
        raise RuntimeError("nombres de fichero repetidos entre requerimientos")
    ground_truth = {
        "marca": MARCA,
        "entregable": "S3.5",
        "contrato": "ADR-010 §5 (C12)",
        "generado_por": "python -m generator.requerimientos (generator/requerimientos.py)",
        "ficha": spec.datos["ficha"]["codigo"],
        "version_ficha": spec.datos["spec"]["version_ficha"],
        "version_spec": spec.datos["spec"]["version_spec"],
        "cronologia": [{"fecha": f, "hecho": h} for f, h in CRONOLOGIA],
        "expediente": _expediente_gt(expediente, spec),
        "cobertura_de_motivos": _cobertura(generados),
        "requerimientos": [_requerimiento_gt(g, expediente) for g in generados],
    }
    return MaterialGenerado(generados, expediente, ground_truth)


def escribir(salida: Path = SALIDA_POR_DEFECTO, material: MaterialGenerado | None = None) -> Path:
    """Escribe `<salida>/_requerimientos/` con los tres PDF y el ground truth."""
    material = material or generar()
    carpeta = salida / CARPETA_REQUERIMIENTOS
    if carpeta.exists():
        shutil.rmtree(carpeta)
    carpeta.mkdir(parents=True)
    for g in material.requerimientos:
        (carpeta / g.nombre).write_bytes(g.contenido)
    (carpeta / FICHERO_GROUND_TRUTH).write_text(
        json.dumps(material.ground_truth, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return carpeta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera los requerimientos sintéticos de S3.5.")
    parser.add_argument(
        "--salida", type=Path, default=SALIDA_POR_DEFECTO, help="Carpeta de salida (expedientes/)"
    )
    args = parser.parse_args(argv)
    material = generar()
    carpeta = escribir(args.salida, material)
    cobertura = material.ground_truth["cobertura_de_motivos"]
    for g in material.requerimientos:
        r = g.requerimiento
        print(
            f"{g.nombre}: origen {r.origen}, {len(r.motivos)} motivo(s), ronda {r.ronda}, "
            f"alcance {r.alcance}, sha256 {g.sha256[:12]}…"
        )
    print(
        f"{carpeta.name}/: expediente {material.expediente.id} con "
        f"{len(material.expediente.actuaciones)} actuaciones; motivos por tipo esperado "
        f"regla={len(cobertura['regla'])}, documento={len(cobertura['documento'])}, "
        f"nada={len(cobertura['nada'])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
