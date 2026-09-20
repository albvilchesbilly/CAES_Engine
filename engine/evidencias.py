"""Evidence Store (N4) y consolidacion de evidencias: de N evidencias con cita a un `valor_consumido`.

Contrato de ADR-002 §2.1 (`Evidencia`, `DatoConsolidado`, `ActuacionConsolidada`, `consolidar`) y semantica
de docs/03 §8 (agrupar, normalizar, comparar, OCR, conflicto, declarado ≠ demostrado). Determinista, sin
modelos, sin `eval`, sin `float`; no conoce ninguna ficha: todo lo que decide sale de la spec (`cruce`,
`cruce_con`, `clave_union`, `fuente_primaria`, `tipo`, `nivel`, `valores`/`valores_ref`, `rango_plausible`)
o de convenciones de nombre documentadas aqui.

Tres capas por dato (docs/03 §5.3; regla de oro 3):

1. Documento: `DatoConsolidado.evidencias` (doc_id, pagina, texto literal, metodo, confianza, extractor).
2. Interpretacion: `valor_normalizado`, `tipo_evidencia`, `fuente_primaria`, `interpretacion`, `unidad`,
   `valores_por_fuente`, `valores_por_tipo_evidencia`, `tratable_por_plataforma`.
3. Calculo: `valor_consumido` tipado (`Decimal`, `date`, `bool`, `str`, `list`) o `None` si conflicto.

Pasos de `consolidar` (docs/03 §8), en este orden:

1. **Agrupar por unidad.** Las claves de union son las variables de la spec con `clave_union: true` cuyo
   nombre coincide con un atributo de `Evidencia` (`num_serie_motor`, `num_serie_variador`). Un par
   (motor, variador) observado junto en una evidencia define la unidad; una evidencia que solo trae el
   variador se asigna a la unidad que tiene ese variador; una que solo trae el motor, a esa unidad. La
   clave de `ActuacionConsolidada.unidades` es `CLAVE_UNIDAD` (`num_serie_motor`). Una evidencia de nivel
   unidad sin ninguna clave se intenta vincular **por huella** (paso 1 bis) y, si no, deja aviso y no se
   asigna. Una evidencia de la propia variable de clave (`num_serie_motor` sin `num_serie_motor=`) usa su
   `valor` como clave. Nivel de una evidencia: el `nivel` de la variable en la spec; si no esta en la spec,
   nivel unidad si trae clave o si la raiz de su nombre (`registro` en `registro.dias`) es prefijo de tipos
   de documento citados solo por variables de nivel unidad; en otro caso, nivel actuacion.
   **1 bis. Vinculacion por huella** (nunca por nombre de fichero): una evidencia `<raiz>.hash_declarado`
   asignada a una unidad declara la SHA-256 de un documento de esa unidad. Un documento cuya `sha256`,
   `doc_id` o SHA-256 de alguno de sus valores extraidos (sus datos canonicos) coincide con esa huella
   queda vinculado a la unidad, y sus evidencias sin clave se asignan a ella. Si el nombre del fichero no es
   el esperado (`<raiz>.nombre_declarado` si existe; si no, que contenga la raiz), aviso informativo
   (caso G). Un documento de derivacion (`derivacion.fuente` de una variable de unidad) con evidencias sin
   clave que no se vincula ni por serie ni por huella → aviso.
2. **Normalizar** segun `cruce`: `exacto` (recorte de espacios; numeros a texto canonico `Decimal` sin
   ceros de mas, "110" ≡ "110,0" ≡ "110.00"; fechas a ISO) o `normalizado` (ademas mayusculas, sin tildes,
   solo letras y cifras: "Industrias Sintéticas del Ebro, S.L." ≡ "INDUSTRIAS SINTETICAS DEL EBRO SL").
   Sin `cruce` declarado → `exacto`. Hechos documentales (nombre con punto) → `exacto`.
3. **Comparar** todas las fuentes fiables (`confianza >= 1` o `metodo != "ocr"`): `valores_por_fuente`
   (`tipo_doc → valor normalizado`; un mismo tipo con dos valores distintos entra como `tipo_doc#2`).
   Tolerancias: una variable con `cruce_con` (N2, P_prom) no cruza declarado ↔ derivado aqui; eso es de
   la regla (`R-CON-03`) y el consolidador expone ambos en `valores_por_tipo_evidencia`. El conflicto se
   busca entonces **dentro de cada tipo de evidencia**; para el resto, entre todas las fuentes fiables.
4. **OCR** (`metodo == "ocr"` con confianza < 1): si coincide con una fuente fiable refuerza (entra en
   `valores_por_fuente`); si discrepa va a `posibles_errores_ocr` y no bloquea. Si solo hay OCR, se
   consume con aviso "solo evidencia OCR".
   **4 bis. Correccion humana** (`metodo == "correccion_humana"`, `METODO_CORRECCION`): una fuente mas,
   con la **maxima precedencia** (`ADR-013` §2 regla 2). Desplaza a las demas fuentes de esa variable en ese
   ambito —manda la ultima, porque el log es solo-anadir— y con ellas desaparece el conflicto: eso es
   resolverlo, no borrarlo. Las evidencias desplazadas siguen enteras en `evidencias` con su cita y un aviso
   nombra lo que habia. Este modulo no sabe de donde sale una correccion ni quien la firmo: eso es de
   `engine.correcciones`, que si importa este.
5. **Conflicto** entre fuentes fiables → `valor_consumido = None`, `conflicto = True`, todas las
   evidencias conservadas, el dato en `ActuacionConsolidada.conflictos`. Nunca se elige (regla de oro 6).
   `fuente_primaria` marca la capa 2 pero no rompe el empate.
6. **Declarado ≠ demostrado ≠ derivado**: `valor_consumido` toma el mejor disponible con prioridad
   `derivado > demostrado > declarado`; `tipo_evidencia` dice cual se consumio. Si la spec exige `derivado`
   y solo hay `declarado`, el dato entra marcado `declarado` (lo recoge `R-EVD-04`).
7. **Tipado** segun `variables[].tipo`: `decimal` → `Decimal`; `date` → `date`; `enum` → `str` validado
   contra `valores`/`valores_ref` (fuera del enumerado → aviso y `None`); `string` → `str`. Sin entrada en
   `variables` (hechos documentales): `"true"`/`"false"` → `bool`; JSON de lista → `list` (numeros como
   `Decimal`); ISO `AAAA-MM-DD` → `date`; numerico → `Decimal`; resto → `str`. Nunca `float`.
8. **Colecciones**: una variable que alguna `logica` usa como argumento directo de `count(...)`/`sum(...)`
   o en posicion `where` (`foto.antes`, `foto.despues`) se consolida como lista de valores (sin conflicto).
   `n_unidades` es el numero de unidades construidas; el recuento por fuente de cualquier variable de
   actuacion esta en `valores_por_fuente` (`valores_por_fuente_de(x)` → `x_por_fuente`).
9. `rango_plausible` incumplido → aviso en el dato y en la actuacion (ni conflicto ni `None`).
10. Documentos: `documentos` tal cual y `documentos_por_tipo` (para `presente(doc)`). Los avisos de
    ingesta/clasificacion no son de este modulo (los añade `motor.py`).
11. `a_dict()` / `EvidenceStore.a_json()`: `Decimal` y `date` como cadena, `NO_EVALUABLE`/`None` → null.

No importa `ingesta`, `calculo` ni `reglas`; los documentos se tipan con el `Protocol` `DocumentoLike`.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field, fields
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol

from engine.expresiones import NO_EVALUABLE
from engine.spec_registry import NIVELES_VARIABLE_UNIDAD, PREFIJO_TABLA, Spec

TIPOS_EVIDENCIA = ("demostrado", "declarado", "derivado")
PRIORIDAD_TIPO_EVIDENCIA: dict[str, int] = {"derivado": 0, "demostrado": 1, "declarado": 2}
METODO_OCR = "ocr"
#: Metodo de una evidencia que no sale de un documento sino de una persona (`ADR-013`; `engine.correcciones`
#: la construye). Es el espejo de `METODO_OCR`: alli una fuente que vale menos que las nativas, aqui una que
#: vale mas que todas. El consolidador solo necesita saber esto; quien la crea y con que cita, no es cosa
#: suya (por eso este modulo no importa `engine.correcciones`, que si importa este).
METODO_CORRECCION = "correccion_humana"
CONFIANZA_FIABLE = Decimal("1")
CRUCE_EXACTO = "exacto"
CRUCE_NORMALIZADO = "normalizado"
CRUCES = (CRUCE_EXACTO, CRUCE_NORMALIZADO)
CLAVE_UNION = "clave_union"
CLAVE_UNIDAD = "num_serie_motor"  # atributo de `Evidencia` que indexa `ActuacionConsolidada.unidades`
CLAVE_SECUNDARIA = "num_serie_variador"
NIVEL_UNIDAD = "unidad"
NIVEL_ACTUACION = "actuacion"
SUFIJO_HASH_DECLARADO = ".hash_declarado"
SUFIJO_NOMBRE_DECLARADO = ".nombre_declarado"
SEPARADOR_FUENTE_REPETIDA = "#"
TIPO_DECIMAL = "decimal"
TIPO_DATE = "date"
TIPO_ENUM = "enum"
TIPO_STRING = "string"
PATRON_NUMERO = r"^[-+]?\d+(?:[.,]\d+)?$"
PATRON_FECHA_ISO = r"^\d{4}-\d{2}-\d{2}$"
PATRON_FECHA_ES = r"^(\d{1,2})/(\d{1,2})/(\d{4})$"
PATRON_COLECCION_CONTADA = r"\b(?:count|sum)\(\s*([A-Za-z_][\w.]*)\s*\)"
AVISO_SOLO_OCR = "solo evidencia OCR"


class ErrorEvidencia(Exception):
    """Evidencia mal construida (valor no textual, confianza no Decimal, tipo de evidencia desconocido)."""


class ErrorConsolidacion(Exception):
    """Spec o entradas incompatibles con la consolidacion (clave de union sin atributo, cruce desconocido)."""


class DocumentoLike(Protocol):
    """Lo que la consolidacion necesita de un documento de ingesta (ADR-002 §2.2), sin importar `ingesta`."""

    doc_id: str
    sha256: str
    tipo: str | None
    nombre: str
    origen: str | None
    subtipo: str | None


# ---------------------------------------------------------------------------
# Contrato ADR-002 §2.1
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Evidencia:
    """Capa 1: un valor leido de un documento, con cita literal. Sin cita no entra (regla de oro 2)."""

    variable: (
        str  # nombre de la spec (`PM`) o hecho documental con punto (`factura.campos_minimos_presentes`)
    )
    valor: str  # valor crudo normalizado a texto ("110", "1188", "true", "2026-03-02")
    doc_id: str  # sha256 del documento (o de la parte separada)
    tipo_doc: str  # tipo de documento segun la spec
    pagina: int  # 1-based; 0 si no aplica (xlsx)
    texto_literal: str  # fragmento literal del documento del que sale el valor
    metodo: str  # "tabla" | "regex" | "ocr" | "xlsx" | "exif" | "llm"
    confianza: Decimal  # 1 para nativo; Decimal("0.75") para OCR
    extractor_version: str
    tipo_evidencia: str  # "demostrado" | "declarado" | "derivado"
    num_serie_motor: str | None = None
    num_serie_variador: str | None = None
    unidad: str | None = None
    interpretacion: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.variable, str) or not self.variable.strip():
            raise ErrorEvidencia("una evidencia necesita `variable`")
        if not isinstance(self.valor, str):
            raise ErrorEvidencia(
                f"{self.variable}: `valor` debe ser texto (la extraccion normaliza a texto), no "
                f"{type(self.valor).__name__}"
            )
        if isinstance(self.confianza, bool) or not isinstance(self.confianza, Decimal | int):
            raise ErrorEvidencia(
                f"{self.variable}: `confianza` debe ser Decimal, no {type(self.confianza).__name__}"
            )
        if not isinstance(self.confianza, Decimal):
            object.__setattr__(self, "confianza", Decimal(self.confianza))
        if self.tipo_evidencia not in TIPOS_EVIDENCIA:
            raise ErrorEvidencia(
                f"{self.variable}: tipo_evidencia {self.tipo_evidencia!r} no esta en {TIPOS_EVIDENCIA}"
            )
        if not isinstance(self.pagina, int) or isinstance(self.pagina, bool):
            raise ErrorEvidencia(f"{self.variable}: `pagina` debe ser entero")

    @property
    def fiable(self) -> bool:
        """Fuente fiable: nativa o con confianza plena. Solo el OCR con confianza < 1 no lo es."""
        return self.confianza >= CONFIANZA_FIABLE or self.metodo != METODO_OCR

    @property
    def raiz(self) -> str:
        return self.variable.split(".", 1)[0]

    def a_dict(self) -> dict[str, object]:
        return {f.name: _serializar(getattr(self, f.name)) for f in fields(self)}


@dataclass
class DatoConsolidado:
    """Tres capas por dato (docs/03 §5.3). Primero los campos del contrato; el resto, añadidos de F0.8."""

    variable: str
    evidencias: list[Evidencia]  # capa 1
    valor_normalizado: str | None  # capa 2 (texto canonico; Decimal como cadena)
    tipo_evidencia: str | None  # demostrado | declarado | derivado (el consumido)
    fuente_primaria: str | None
    interpretacion: str | None
    valores_por_fuente: dict[str, str]  # tipo_doc → valor normalizado (para unique(...))
    valor_consumido: Decimal | date | str | bool | list | None  # capa 3; None si conflicto o ausente
    conflicto: bool
    posibles_errores_ocr: list[Evidencia]  # OCR que discrepa de una fuente fiable (no bloquea)
    valores_por_tipo_evidencia: dict[str, str] = field(default_factory=dict)  # {"declarado": "1188", ...}
    valores_tipados_por_tipo_evidencia: dict[str, object] = field(default_factory=dict)  # lo mismo, tipado
    nivel: str = NIVEL_ACTUACION  # "unidad" | "actuacion"
    num_serie_motor: str | None = None  # unidad a la que pertenece (nivel unidad)
    unidad: str | None = None  # "kW", "rpm", ... (capa 2)
    tipo: str | None = None  # `variables[].tipo` de la spec o el inferido ("bool", "list", ...)
    avisos: list[str] = field(default_factory=list)
    tratable_por_plataforma: bool = False  # reservado para R-XCK (S3); en F0 siempre False

    @property
    def presente(self) -> bool:
        return self.valor_consumido is not None

    def a_dict(self) -> dict[str, object]:
        return {f.name: _serializar(getattr(self, f.name)) for f in fields(self)}


@dataclass
class ActuacionConsolidada:
    """Resultado de `consolidar`. `unidades`: num_serie_motor → variable → dato; `variables`: actuacion."""

    documentos: list[DocumentoLike]
    unidades: dict[str, dict[str, DatoConsolidado]]
    variables: dict[str, DatoConsolidado]
    conflictos: list[DatoConsolidado]
    avisos: list[str]
    documentos_por_tipo: dict[str, list[DocumentoLike]] = field(default_factory=dict)
    vinculos_por_huella: dict[str, str] = field(default_factory=dict)  # doc_id → num_serie_motor
    evidencias_no_asignadas: list[Evidencia] = field(default_factory=list)

    @property
    def n_unidades(self) -> int:
        return len(self.unidades)

    def dato(self, variable: str, num_serie_motor: str | None = None) -> DatoConsolidado | None:
        if num_serie_motor is None:
            return self.variables.get(variable)
        return self.unidades.get(num_serie_motor, {}).get(variable)

    def valores_por_fuente_de(self, variable: str) -> dict[str, str]:
        """`<variable>_por_fuente` de nivel actuacion (p. ej. `n_motores_por_fuente`); vacio si no hay."""
        dato = self.variables.get(variable)
        return dict(dato.valores_por_fuente) if dato is not None else {}

    def a_dict(self) -> dict[str, object]:
        return {
            "documentos": [_documento_a_dict(d) for d in self.documentos],
            "documentos_por_tipo": {t: [d.doc_id for d in ds] for t, ds in self.documentos_por_tipo.items()},
            "n_unidades": self.n_unidades,
            "unidades": {
                serie: {nombre: dato.a_dict() for nombre, dato in datos.items()}
                for serie, datos in self.unidades.items()
            },
            "variables": {nombre: dato.a_dict() for nombre, dato in self.variables.items()},
            "conflictos": [
                {
                    "variable": d.variable,
                    "num_serie_motor": d.num_serie_motor,
                    "valores_por_fuente": dict(d.valores_por_fuente),
                }
                for d in self.conflictos
            ],
            "vinculos_por_huella": dict(self.vinculos_por_huella),
            "evidencias_no_asignadas": [e.a_dict() for e in self.evidencias_no_asignadas],
            "avisos": list(self.avisos),
        }


# ---------------------------------------------------------------------------
# Serializacion
# ---------------------------------------------------------------------------


def _serializar(valor: object) -> object:
    """JSON-compatible: Decimal/date → cadena, NO_EVALUABLE → None, dataclasses del modulo → dict."""
    if valor is None or valor is NO_EVALUABLE:
        return None
    if isinstance(valor, bool | str):
        return valor
    if isinstance(valor, Decimal):
        return _decimal_canonico(valor)
    if isinstance(valor, int):
        return valor
    if isinstance(valor, datetime):
        return valor.isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, Evidencia | DatoConsolidado | ActuacionConsolidada):
        return valor.a_dict()
    if isinstance(valor, Mapping):
        return {str(k): _serializar(v) for k, v in valor.items()}
    if isinstance(valor, list | tuple | set | frozenset):
        return [_serializar(v) for v in valor]
    return str(valor)


def _documento_a_dict(doc: DocumentoLike) -> dict[str, object]:
    return {
        atributo: getattr(doc, atributo, None)
        for atributo in ("doc_id", "sha256", "tipo", "nombre", "origen", "subtipo")
    }


# ---------------------------------------------------------------------------
# Evidence Store (en memoria; docs/03 §14 e)
# ---------------------------------------------------------------------------


class EvidenceStore:
    """Almacen en memoria de evidencias, solo-añadir, consultable por variable, unidad y documento."""

    def __init__(self, evidencias: Iterable[Evidencia] = ()) -> None:
        self._evidencias: list[Evidencia] = []
        for ev in evidencias:
            self.agregar(ev)

    def agregar(self, ev: Evidencia) -> Evidencia:
        if not isinstance(ev, Evidencia):
            raise ErrorEvidencia(f"solo se almacenan Evidencia, no {type(ev).__name__}")
        self._evidencias.append(ev)
        return ev

    def agregar_varias(self, evidencias: Iterable[Evidencia]) -> None:
        for ev in evidencias:
            self.agregar(ev)

    def todas(self) -> list[Evidencia]:
        return list(self._evidencias)

    def __len__(self) -> int:
        return len(self._evidencias)

    def __iter__(self) -> Iterator[Evidencia]:
        return iter(list(self._evidencias))

    def por_variable(self, nombre: str) -> list[Evidencia]:
        return [e for e in self._evidencias if e.variable == nombre]

    def por_unidad(self, num_serie_motor: str) -> list[Evidencia]:
        """Evidencias que llevan esa clave de motor (sin resolver el variador: eso lo hace `consolidar`)."""
        return [e for e in self._evidencias if e.num_serie_motor == num_serie_motor]

    def por_documento(self, doc_id: str) -> list[Evidencia]:
        return [e for e in self._evidencias if e.doc_id == doc_id]

    def consolidar(self, documentos: list[DocumentoLike], spec: Spec) -> ActuacionConsolidada:
        return consolidar(self.todas(), documentos, spec)

    def a_json(self) -> dict[str, object]:
        return {"n_evidencias": len(self._evidencias), "evidencias": [e.a_dict() for e in self._evidencias]}


# ---------------------------------------------------------------------------
# Normalizacion y tipado
# ---------------------------------------------------------------------------


def _decimal_canonico(valor: Decimal) -> str:
    """Texto canonico sin ceros de mas ni exponente: 110.00 → "110", 3.90 → "3.9", 0.0500 → "0.05"."""
    if not valor.is_finite():
        return str(valor)
    if valor == 0:
        return "0"
    return format(valor.normalize(), "f")


def _numero(texto: str) -> Decimal | None:
    if not re.fullmatch(PATRON_NUMERO, texto):
        return None
    try:
        return Decimal(texto.replace(",", "."))
    except InvalidOperation:
        return None


def _fecha(texto: str) -> date | None:
    if re.fullmatch(PATRON_FECHA_ISO, texto):
        try:
            return date.fromisoformat(texto)
        except ValueError:
            return None
    partes = re.fullmatch(PATRON_FECHA_ES, texto)
    if partes:
        try:
            return date(int(partes.group(3)), int(partes.group(2)), int(partes.group(1)))
        except ValueError:
            return None
    return None


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def normalizar(valor: str, cruce: str = CRUCE_EXACTO, tipo: str | None = None) -> str:
    """Capa 2: texto canonico segun `cruce` y `tipo` de la spec (paso 2 de docs/03 §8)."""
    if cruce not in CRUCES:
        raise ErrorConsolidacion(f"cruce desconocido {cruce!r}; la spec admite {CRUCES}")
    texto = valor.strip()
    if tipo == TIPO_DECIMAL:
        numero = _numero(texto)
        return _decimal_canonico(numero) if numero is not None else texto
    if tipo == TIPO_DATE:
        fecha = _fecha(texto)
        return fecha.isoformat() if fecha is not None else texto
    if tipo is None:
        numero = _numero(texto)
        if numero is not None:
            return _decimal_canonico(numero)
        fecha = _fecha(texto)
        if fecha is not None:
            return fecha.isoformat()
    if cruce == CRUCE_NORMALIZADO:
        return "".join(c for c in _sin_tildes(texto).upper() if c.isalnum())
    return texto


def _valores_enum(decl: Mapping[str, object], spec: Spec) -> tuple[str, ...] | None:
    """`valores` o `valores_ref` ("ambito.lista_a + ambito.lista_b") resueltos contra la spec."""
    valores = decl.get("valores")
    if isinstance(valores, list):
        return tuple(str(v) for v in valores)
    ref = decl.get("valores_ref")
    if not isinstance(ref, str):
        return None
    resultado: list[str] = []
    for trozo in ref.split("+"):
        actual: object = spec.datos
        for parte in trozo.strip().split("."):
            actual = actual.get(parte) if isinstance(actual, Mapping) else None
        if isinstance(actual, list):
            resultado.extend(str(v) for v in actual)
    return tuple(resultado)


def _inferir(texto: str) -> tuple[object, str]:
    """Inferencia cerrada para hechos sin entrada en `variables` (paso 7). Devuelve (valor, tipo inferido)."""
    if texto == "true":
        return True, "bool"
    if texto == "false":
        return False, "bool"
    if texto.startswith("["):
        try:
            lista = json.loads(texto, parse_float=Decimal, parse_int=Decimal)
        except ValueError:
            return texto, TIPO_STRING
        if isinstance(lista, list):
            return lista, "list"
        return texto, TIPO_STRING
    fecha = _fecha(texto)
    if fecha is not None:
        return fecha, TIPO_DATE
    numero = _numero(texto)
    if numero is not None:
        return numero, TIPO_DECIMAL
    return texto, TIPO_STRING


def tipar(
    valor_normalizado: str, decl: Mapping[str, object] | None, spec: Spec, crudo: str | None = None
) -> tuple[object, str | None, list[str]]:
    """Capa 3: (valor tipado o None, tipo, avisos). `crudo` es el texto original para `string` normalizado."""
    if decl is None:
        valor, tipo = _inferir(valor_normalizado)
        return valor, tipo, []
    tipo = decl.get("tipo")
    if tipo == TIPO_DECIMAL:
        numero = _numero(valor_normalizado)
        if numero is None:
            return None, tipo, [f"valor no numerico {valor_normalizado!r}"]
        return numero, tipo, []
    if tipo == TIPO_DATE:
        fecha = _fecha(valor_normalizado)
        if fecha is None:
            return None, tipo, [f"fecha no reconocida {valor_normalizado!r}"]
        return fecha, tipo, []
    if tipo == TIPO_ENUM:
        admitidos = _valores_enum(decl, spec)
        if admitidos is not None and valor_normalizado not in admitidos:
            return None, tipo, [f"valor {valor_normalizado!r} fuera del enumerado {list(admitidos)}"]
        return valor_normalizado, tipo, []
    if tipo in (TIPO_STRING, None):
        return (crudo if crudo is not None else valor_normalizado), TIPO_STRING, []
    return valor_normalizado, str(tipo), [f"tipo de spec {tipo!r} sin regla de tipado; se entrega como texto"]


def _rango_plausible(decl: Mapping[str, object] | None) -> tuple[Decimal, Decimal] | None:
    if decl is None:
        return None
    rango = decl.get("rango_plausible")
    if not isinstance(rango, list) or len(rango) != 2:
        return None
    try:
        return Decimal(str(rango[0])), Decimal(str(rango[1]))
    except InvalidOperation:
        return None


# ---------------------------------------------------------------------------
# Consolidacion de un grupo (una variable en un ambito)
# ---------------------------------------------------------------------------


def _clave_fuente(valores_por_fuente: dict[str, str], tipo_doc: str, valor: str) -> str | None:
    """Clave de `valores_por_fuente`: `tipo_doc`, o `tipo_doc#2`, ... si ese tipo ya aporto otro valor."""
    if tipo_doc not in valores_por_fuente:
        return tipo_doc
    n = 1
    clave = tipo_doc
    while clave in valores_por_fuente:
        if valores_por_fuente[clave] == valor:
            return None  # mismo tipo, mismo valor: refuerza sin nueva clave
        n += 1
        clave = f"{tipo_doc}{SEPARADOR_FUENTE_REPETIDA}{n}"
    return clave


def _mejor_tipo(tipos: Iterable[str]) -> str | None:
    candidatos = sorted(set(tipos), key=lambda t: PRIORIDAD_TIPO_EVIDENCIA.get(t, 99))
    return candidatos[0] if candidatos else None


def _consolidar_coleccion(variable: str, evidencias: list[Evidencia], spec: Spec) -> DatoConsolidado:
    """Paso 8: valores de varias evidencias (fotos) como lista de identificadores, sin conflicto."""
    valores: list[str] = []
    por_fuente: dict[str, list[str]] = {}
    for ev in evidencias:
        texto = ev.valor.strip()
        if texto not in valores:
            valores.append(texto)
        por_fuente.setdefault(ev.tipo_doc, [])
        if texto not in por_fuente[ev.tipo_doc]:
            por_fuente[ev.tipo_doc].append(texto)
    tipo = _mejor_tipo(ev.tipo_evidencia for ev in evidencias)
    return DatoConsolidado(
        variable=variable,
        evidencias=list(evidencias),
        valor_normalizado=json.dumps(valores, ensure_ascii=False),
        tipo_evidencia=tipo,
        fuente_primaria=None,
        interpretacion=next((ev.interpretacion for ev in evidencias if ev.interpretacion), None),
        valores_por_fuente={t: json.dumps(v, ensure_ascii=False) for t, v in por_fuente.items()},
        valor_consumido=list(valores),
        conflicto=False,
        posibles_errores_ocr=[],
        valores_por_tipo_evidencia={tipo: json.dumps(valores, ensure_ascii=False)} if tipo else {},
        valores_tipados_por_tipo_evidencia={tipo: list(valores)} if tipo else {},
        tipo="list",
        unidad=next((ev.unidad for ev in evidencias if ev.unidad), None),
    )


def _consolidar_grupo(variable: str, evidencias: list[Evidencia], spec: Spec) -> DatoConsolidado:
    """Pasos 2–7 de docs/03 §8 sobre las evidencias de una variable en un ambito (unidad o actuacion)."""
    decl = spec.variables.get(variable)
    cruce = str(decl.get("cruce")) if decl and decl.get("cruce") else CRUCE_EXACTO
    tipo_spec = str(decl["tipo"]) if decl and decl.get("tipo") else None
    tiene_cruce_con = bool(decl and decl.get("cruce_con"))
    fuente_primaria = str(decl["fuente_primaria"]) if decl and decl.get("fuente_primaria") else None
    avisos: list[str] = []

    normalizados = {id(ev): normalizar(ev.valor, cruce, tipo_spec) for ev in evidencias}
    fiables = [ev for ev in evidencias if ev.fiable]
    ocr = [ev for ev in evidencias if not ev.fiable]
    solo_ocr = not fiables
    base = fiables if fiables else ocr
    if solo_ocr:
        avisos.append(AVISO_SOLO_OCR)

    # precedencia: una correccion humana desplaza a las demas fuentes de esta variable (`ADR-013` §2).
    # Manda la ultima (el log es solo-anadir: corregir dos veces es cambiar de opinion) y las demas
    # evidencias se conservan enteras en el dato: el conflicto no se borra, se resuelve.
    correcciones = [ev for ev in base if ev.metodo == METODO_CORRECCION]
    if correcciones:
        base = [correcciones[-1]]
        aviso = _aviso_correccion(correcciones[-1], evidencias, normalizados)
        if aviso is not None:
            avisos.append(aviso)

    # capa 2: valores por fuente (fiables; el OCR solo si coincide con una fuente fiable)
    valores_por_fuente: dict[str, str] = {}
    for ev in base:
        clave = _clave_fuente(valores_por_fuente, ev.tipo_doc, normalizados[id(ev)])
        if clave is not None:
            valores_por_fuente[clave] = normalizados[id(ev)]
    valores_fiables = {normalizados[id(ev)] for ev in base}
    posibles_errores_ocr: list[Evidencia] = []
    if not solo_ocr:
        for ev in ocr:
            if normalizados[id(ev)] in valores_fiables:
                clave = _clave_fuente(valores_por_fuente, ev.tipo_doc, normalizados[id(ev)])
                if clave is not None:
                    valores_por_fuente[clave] = normalizados[id(ev)]
            else:
                posibles_errores_ocr.append(ev)

    # conflicto: dentro de cada tipo de evidencia si la variable declara `cruce_con`; si no, global
    por_tipo: dict[str, dict[str, list[Evidencia]]] = {}
    for ev in base:
        por_tipo.setdefault(ev.tipo_evidencia, {}).setdefault(normalizados[id(ev)], []).append(ev)
    if tiene_cruce_con:
        conflicto = any(len(grupo) > 1 for grupo in por_tipo.values())
    else:
        conflicto = len(valores_fiables) > 1
    valores_por_tipo: dict[str, str] = {}
    tipados_por_tipo: dict[str, object] = {}
    for tipo_ev, grupo in por_tipo.items():
        if len(grupo) == 1 and (tiene_cruce_con or not conflicto):
            (valor_norm, evs) = next(iter(grupo.items()))
            valores_por_tipo[tipo_ev] = valor_norm
            tipado, _, _ = tipar(valor_norm, decl, spec, crudo=_crudo_de(evs, fuente_primaria))
            tipados_por_tipo[tipo_ev] = tipado

    # capa 3
    valor_consumido: object = None
    tipo_consumido: str | None = None
    valor_normalizado: str | None = None
    interpretacion: str | None = None
    tipo_dato: str | None = tipo_spec
    if conflicto:
        avisos.append(
            "conflicto entre fuentes fiables: " + ", ".join(f"{k}={v}" for k, v in valores_por_fuente.items())
        )
    else:
        tipo_consumido = _mejor_tipo(t for t in por_tipo if t in valores_por_tipo)
        if tipo_consumido is not None:
            valor_normalizado = valores_por_tipo[tipo_consumido]
            evs = por_tipo[tipo_consumido][valor_normalizado]
            valor_consumido, tipo_dato, avisos_tipado = tipar(
                valor_normalizado, decl, spec, crudo=_crudo_de(evs, fuente_primaria)
            )
            avisos.extend(avisos_tipado)
            interpretacion = next((ev.interpretacion for ev in evs if ev.interpretacion), None)
            if interpretacion is None and tipo_consumido == "derivado" and decl:
                derivacion = decl.get("derivacion")
                if isinstance(derivacion, Mapping) and derivacion.get("interpretacion"):
                    interpretacion = str(derivacion["interpretacion"])
            rango = _rango_plausible(decl)
            if rango is not None and isinstance(valor_consumido, Decimal):
                if not (rango[0] <= valor_consumido <= rango[1]):
                    avisos.append(
                        f"valor {_decimal_canonico(valor_consumido)} fuera del rango plausible "
                        f"[{_decimal_canonico(rango[0])}, {_decimal_canonico(rango[1])}]"
                    )

    presente_primaria = fuente_primaria if any(ev.tipo_doc == fuente_primaria for ev in evidencias) else None
    unidad = str(decl["unidad"]) if decl and decl.get("unidad") else None
    if unidad is None:
        unidad = next((ev.unidad for ev in evidencias if ev.unidad), None)
    return DatoConsolidado(
        variable=variable,
        evidencias=list(evidencias),
        valor_normalizado=valor_normalizado,
        tipo_evidencia=tipo_consumido,
        fuente_primaria=presente_primaria,
        interpretacion=interpretacion,
        valores_por_fuente=valores_por_fuente,
        valor_consumido=valor_consumido,
        conflicto=conflicto,
        posibles_errores_ocr=posibles_errores_ocr,
        valores_por_tipo_evidencia=valores_por_tipo,
        valores_tipados_por_tipo_evidencia=tipados_por_tipo,
        unidad=unidad,
        tipo=tipo_dato,
        avisos=avisos,
    )


def _aviso_correccion(
    correccion: Evidencia, evidencias: list[Evidencia], normalizados: dict[int, str]
) -> str | None:
    """Que se descarto al aplicar una correccion humana: el conflicto se resuelve **a la vista**.

    Sin este aviso, un dato corregido se leeria igual que uno que nunca tuvo discusion. Las evidencias
    desplazadas siguen enteras en `DatoConsolidado.evidencias` con su cita; esto solo lo nombra.
    """
    elegido = normalizados[id(correccion)]
    desplazados: list[str] = []
    for ev in evidencias:
        if ev.metodo == METODO_CORRECCION or not ev.fiable:
            continue
        texto = f"{ev.tipo_doc}={normalizados[id(ev)]}"
        if texto not in desplazados:
            desplazados.append(texto)
    if not desplazados:
        return None
    return (
        f"valor fijado por correccion humana ({elegido}) por {correccion.extractor_version}; "
        "fuentes documentales: " + ", ".join(desplazados)
    )


def _crudo_de(evidencias: list[Evidencia], fuente_primaria: str | None) -> str:
    """Texto crudo (recortado) de la fuente primaria si esta entre las evidencias; si no, de la primera."""
    for ev in evidencias:
        if fuente_primaria is not None and ev.tipo_doc == fuente_primaria:
            return ev.valor.strip()
    return evidencias[0].valor.strip()


# ---------------------------------------------------------------------------
# Lectura de la spec: claves, niveles, colecciones, documentos de derivacion
# ---------------------------------------------------------------------------


def _claves_union(spec: Spec) -> list[str]:
    """Variables `clave_union: true` que existen como atributo de `Evidencia`; otra clave → error."""
    atributos = {f.name for f in fields(Evidencia)}
    claves = [n for n, v in spec.variables.items() if v.get(CLAVE_UNION) is True]
    ajenas = [c for c in claves if c not in atributos]
    if ajenas:
        raise ErrorConsolidacion(
            f"la spec declara claves de union {ajenas} que `Evidencia` no tiene como atributo (ADR-002 §2.1)"
        )
    return claves


def _fuentes_de(decl: Mapping[str, object]) -> list[str]:
    fuentes = [str(f) for f in (decl.get("fuentes") or [])]
    derivacion = decl.get("derivacion")
    if isinstance(derivacion, Mapping):
        fuente = derivacion.get("fuente")
        if isinstance(fuente, str) and not fuente.startswith(PREFIJO_TABLA):
            fuentes.append(fuente)
    return fuentes


def _tipos_documento_unidad(spec: Spec) -> tuple[set[str], set[str]]:
    """(tipos citados solo por variables de unidad, tipos `derivacion.fuente` de una variable de unidad)."""
    citas: dict[str, list[bool]] = {}
    derivacion: set[str] = set()
    for decl in spec.variables.values():
        es_unidad = decl.get("nivel") in NIVELES_VARIABLE_UNIDAD
        for fuente in _fuentes_de(decl):
            citas.setdefault(fuente, []).append(es_unidad)
        deriv = decl.get("derivacion")
        if es_unidad and isinstance(deriv, Mapping):
            fuente = deriv.get("fuente")
            if isinstance(fuente, str) and not fuente.startswith(PREFIJO_TABLA):
                derivacion.add(fuente)
    solo_unidad = {t for t, niveles in citas.items() if all(niveles)}
    return solo_unidad, derivacion


def _raiz_es_unidad(raiz: str, tipos_unidad: set[str], tipos_documento: Iterable[str]) -> bool:
    """La raiz de un hecho documental es de unidad si todos los tipos con ese prefijo son de unidad."""
    tipos = [t for t in tipos_documento if t == raiz or t.startswith(raiz + "_")]
    return bool(tipos) and all(t in tipos_unidad for t in tipos)


def colecciones_de_spec(spec: Spec) -> frozenset[str]:
    """Variables que alguna `logica` usa como coleccion (`count(x)`, `sum(x)`, `x where ...`).

    Se leen de la propia regla porque `Expresion` no expone el arbol; el patron es cerrado (un nombre como
    unico argumento). Un nombre de `variables` nunca es coleccion.
    """
    nombres: set[str] = set()
    for regla in spec.reglas:
        nombres |= set(re.findall(PATRON_COLECCION_CONTADA, regla.logica))
        nombres |= set(regla.expresion.colecciones_ligadas)
    return frozenset(n for n in nombres if n not in spec.variables)


# ---------------------------------------------------------------------------
# consolidar
# ---------------------------------------------------------------------------


def _claves_de(ev: Evidencia, claves: Iterable[str]) -> dict[str, str | None]:
    """Claves de union efectivas: el atributo, o el propio valor si la evidencia es de esa variable."""
    resultado: dict[str, str | None] = {}
    for clave in claves:
        valor = getattr(ev, clave, None)
        if valor is None and ev.variable == clave:
            valor = ev.valor.strip() or None
        resultado[clave] = valor.strip() if isinstance(valor, str) and valor.strip() else None
    return resultado


def _nivel_de(ev: Evidencia, spec: Spec, claves: dict[str, str | None], raices_unidad: set[str]) -> str:
    decl = spec.variables.get(ev.variable)
    if decl is not None:
        return NIVEL_UNIDAD if decl.get("nivel") in NIVELES_VARIABLE_UNIDAD else NIVEL_ACTUACION
    if any(claves.values()):
        return NIVEL_UNIDAD
    return NIVEL_UNIDAD if ev.raiz in raices_unidad else NIVEL_ACTUACION


def _huellas_candidatas(doc: DocumentoLike, evidencias_doc: list[Evidencia]) -> set[str]:
    """Huellas por las que un documento puede coincidir con un `*.hash_declarado`."""
    huellas = {str(doc.sha256).lower(), str(doc.doc_id).lower()}
    for ev in evidencias_doc:
        huellas.add(hashlib.sha256(ev.valor.encode("utf-8")).hexdigest())
        huellas.add(hashlib.sha256(ev.valor.strip().encode("utf-8")).hexdigest())
    return huellas


def _resumen_doc(doc: DocumentoLike | None, doc_id: str) -> str:
    if doc is None:
        return f"documento {doc_id[:12]}"
    return f"'{doc.nombre}' ({doc.tipo or 'sin tipo'}, {doc_id[:12]})"


def consolidar(
    evidencias: list[Evidencia],
    documentos: list[DocumentoLike],
    spec: Spec,
    colecciones: Iterable[str] | None = None,
) -> ActuacionConsolidada:
    """De N evidencias a datos consolidados por unidad y por actuacion (docs/03 §8; cabecera del modulo).

    `colecciones`: variables que se consolidan como lista (por defecto, `colecciones_de_spec(spec)`).
    """
    avisos: list[str] = []
    claves = _claves_union(spec)
    if CLAVE_UNIDAD not in claves:
        avisos.append(
            f"la spec no declara `{CLAVE_UNIDAD}` como clave de union; las unidades se indexan por ella"
        )
    tipos_unidad, tipos_derivacion = _tipos_documento_unidad(spec)
    tipos_documento = [str(d.get("tipo")) for d in spec.documentacion if d.get("tipo")]
    raices_unidad = {
        ev.raiz
        for ev in evidencias
        if "." in ev.variable and _raiz_es_unidad(ev.raiz, tipos_unidad, tipos_documento)
    }
    nombres_coleccion = frozenset(colecciones) if colecciones is not None else colecciones_de_spec(spec)
    docs_por_id: dict[str, DocumentoLike] = {}
    for doc in documentos:
        docs_por_id.setdefault(doc.doc_id, doc)
        if doc.sha256:
            docs_por_id.setdefault(doc.sha256, doc)
    documentos_por_tipo: dict[str, list[DocumentoLike]] = {}
    for doc in documentos:
        if doc.tipo:
            documentos_por_tipo.setdefault(doc.tipo, []).append(doc)

    # --- paso 1: agrupar por unidad -----------------------------------------------------------------
    info = [(ev, _claves_de(ev, claves)) for ev in evidencias]
    motores_de_variador: dict[str, list[str]] = {}
    for _ev, cl in info:
        motor, variador = cl.get(CLAVE_UNIDAD), cl.get(CLAVE_SECUNDARIA)
        if motor and variador and motor not in motores_de_variador.setdefault(variador, []):
            motores_de_variador[variador].append(motor)

    unidades_ev: dict[str, list[Evidencia]] = {}
    actuacion_ev: list[Evidencia] = []
    pendientes: list[Evidencia] = []  # nivel unidad sin clave: candidatas a vinculacion por huella
    for ev, cl in info:
        nivel = _nivel_de(ev, spec, cl, raices_unidad)
        if nivel == NIVEL_ACTUACION:
            actuacion_ev.append(ev)
            continue
        motor, variador = cl.get(CLAVE_UNIDAD), cl.get(CLAVE_SECUNDARIA)
        if motor:
            unidades_ev.setdefault(motor, []).append(ev)
        elif variador:
            motores = motores_de_variador.get(variador, [])
            if len(motores) == 1:
                unidades_ev.setdefault(motores[0], []).append(ev)
            elif not motores:
                avisos.append(
                    f"evidencia '{ev.variable}' de {_resumen_doc(docs_por_id.get(ev.doc_id), ev.doc_id)}: "
                    f"variador {variador!r} no asociado a ningun motor; no asignada"
                )
                pendientes.append(ev)
            else:
                avisos.append(
                    f"evidencia '{ev.variable}' de {_resumen_doc(docs_por_id.get(ev.doc_id), ev.doc_id)}: "
                    f"variador {variador!r} asociado a varios motores {motores}; no asignada"
                )
                pendientes.append(ev)
        else:
            pendientes.append(ev)

    # --- paso 1 bis: vinculacion por huella ---------------------------------------------------------
    huellas_declaradas: dict[str, tuple[str, str]] = {}  # huella → (num_serie_motor, raiz)
    huellas_ambiguas: set[str] = set()
    for serie, evs in unidades_ev.items():
        for ev in evs:
            if ev.variable.endswith(SUFIJO_HASH_DECLARADO):
                huella = ev.valor.strip().lower()
                previo = huellas_declaradas.get(huella)
                if previo is not None and previo[0] != serie:
                    huellas_ambiguas.add(huella)
                huellas_declaradas.setdefault(huella, (serie, ev.raiz))
    vinculos: dict[str, str] = {}
    evidencias_por_doc: dict[str, list[Evidencia]] = {}
    for ev in evidencias:
        evidencias_por_doc.setdefault(ev.doc_id, []).append(ev)
    no_asignadas: list[Evidencia] = []
    docs_pendientes: dict[str, list[Evidencia]] = {}
    for ev in pendientes:
        docs_pendientes.setdefault(ev.doc_id, []).append(ev)
    for doc_id, evs in docs_pendientes.items():
        doc = docs_por_id.get(doc_id)
        candidatas = _huellas_candidatas(doc, evidencias_por_doc.get(doc_id, [])) if doc else set()
        coincidencias = [(h, huellas_declaradas[h]) for h in sorted(candidatas) if h in huellas_declaradas]
        if coincidencias and not any(h in huellas_ambiguas for h, _ in coincidencias):
            _, (serie, raiz) = coincidencias[0]
            vinculos[doc_id] = serie
            unidades_ev.setdefault(serie, []).extend(evs)
            esperado = _nombre_esperado(unidades_ev[serie], raiz)
            if doc is not None and esperado is not None and not _nombre_coincide(doc.nombre, esperado):
                avisos.append(
                    f"registro vinculado por huella a la unidad {serie!r}: el fichero se llama "
                    f"{doc.nombre!r} y se esperaba {esperado!r} (informativo: la vinculacion es por SHA-256)"
                )
            continue
        if coincidencias:
            avisos.append(
                f"{_resumen_doc(doc, doc_id)}: su huella la declaran varias unidades; no se vincula"
            )
        no_asignadas.extend(evs)
        tipo_doc = doc.tipo if doc is not None else evs[0].tipo_doc
        if tipo_doc in tipos_derivacion:
            avisos.append(
                f"registro {_resumen_doc(doc, doc_id)} no vinculable a ninguna unidad ni por numero de "
                f"serie ni por huella declarada; sus {len(evs)} evidencias no se asignan"
            )
        else:
            variables = sorted({ev.variable for ev in evs})
            avisos.append(
                f"evidencia sin clave de union: {_resumen_doc(doc, doc_id)} aporta {variables} de nivel "
                "unidad sin numero de serie ni huella; no asignada"
            )

    # --- pasos 2–9: consolidar cada variable en su ambito -------------------------------------------
    unidades: dict[str, dict[str, DatoConsolidado]] = {}
    conflictos: list[DatoConsolidado] = []
    for serie, evs in unidades_ev.items():
        datos: dict[str, DatoConsolidado] = {}
        for variable, grupo in _agrupar(evs).items():
            dato = _consolidar_variable(variable, grupo, spec, nombres_coleccion)
            dato.nivel = NIVEL_UNIDAD
            dato.num_serie_motor = serie
            datos[variable] = dato
            _recoger(dato, f"unidad {serie!r}", conflictos, avisos)
        unidades[serie] = datos
    variables: dict[str, DatoConsolidado] = {}
    for variable, grupo in _agrupar(actuacion_ev).items():
        dato = _consolidar_variable(variable, grupo, spec, nombres_coleccion)
        variables[variable] = dato
        _recoger(dato, "actuacion", conflictos, avisos)

    return ActuacionConsolidada(
        documentos=list(documentos),
        unidades=unidades,
        variables=variables,
        conflictos=conflictos,
        avisos=avisos,
        documentos_por_tipo=documentos_por_tipo,
        vinculos_por_huella=vinculos,
        evidencias_no_asignadas=no_asignadas,
    )


def _agrupar(evidencias: list[Evidencia]) -> dict[str, list[Evidencia]]:
    grupos: dict[str, list[Evidencia]] = {}
    for ev in evidencias:
        grupos.setdefault(ev.variable, []).append(ev)
    return grupos


def _consolidar_variable(
    variable: str, grupo: list[Evidencia], spec: Spec, colecciones: frozenset[str]
) -> DatoConsolidado:
    if variable in colecciones:
        return _consolidar_coleccion(variable, grupo, spec)
    return _consolidar_grupo(variable, grupo, spec)


def _recoger(
    dato: DatoConsolidado, ambito: str, conflictos: list[DatoConsolidado], avisos: list[str]
) -> None:
    if dato.conflicto:
        conflictos.append(dato)
    for aviso in dato.avisos:
        avisos.append(f"{dato.variable} ({ambito}): {aviso}")


def _nombre_esperado(evidencias_unidad: list[Evidencia], raiz: str) -> str | None:
    for ev in evidencias_unidad:
        if ev.variable == raiz + SUFIJO_NOMBRE_DECLARADO and ev.valor.strip():
            return ev.valor.strip()
    return raiz


def _nombre_coincide(nombre: str, esperado: str) -> bool:
    """Coincide si es el nombre declarado (sin distinguir mayusculas) o contiene la raiz esperada."""
    return esperado.lower() in nombre.lower()
