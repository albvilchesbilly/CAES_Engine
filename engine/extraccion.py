"""Extraccion de evidencias (A2 en la Fase 0): de `Documento` a `Evidencia` con cita, metodo y confianza.

`Extractor` es la interfaz (`version` + `extraer`); `ExtractorReglas` es la implementacion determinista por
reglas de la Fase 0. En el Sprint 3 el extractor LLM entra **detras de esta misma interfaz** y la doble
extraccion compara sus salidas; con el LLM apagado todo funciona igual.

Reglas que este modulo cumple (`CLAUDE.md` §2, docs/05 §4.4):

1. **Sin cita no hay evidencia.** Toda `Evidencia` sale con `doc_id`, `pagina`, `texto_literal`, `metodo`,
   `confianza` y `extractor_version`. Lo que no se puede citar no se emite.
2. **Tablas antes que texto.** Primero se buscan las celdas etiqueta/valor de las tablas de la pagina
   (`metodo = "tabla"`); el texto plano es **respaldo** (`metodo = "regex"`). La marca de agua y los saltos
   de pagina separan etiqueta y valor en el texto extraido: leerlo primero seria leer mal.
3. **OCR con menos confianza**: lo que sale de una placa fotografiada o de un escaneo entra con
   `metodo = "ocr"` y `confianza = 0,75`; lo nativo, con 1.
4. **Declarado ≠ demostrado ≠ derivado.** El `tipo_evidencia` lo fija el lexico por campo: `N2` y `P_prom`
   leidos del certificado o de la ficha son `declarado`; los mismos valores derivados del registro son
   `derivado` (INT-03/INT-04, que se leen de la spec). El extractor **no** calcula nada de la formula.
5. **La spec manda sobre el lexico.** Un campo solo se emite si el tipo de documento esta entre las
   `fuentes` (o `cruce_con`, o `derivacion.fuente`) que la spec declara para esa variable. El lexico puede
   conocer mas etiquetas que las que la ficha admite; la que decide es la ficha. Asi `P_prom` de la ficha
   cumplimentada no entra (la spec solo la cruza con el certificado) sin ninguna rama por ficha.
6. **La trampa de la ficha del variador**: `Perdidas declaradas por el fabricante 3,90 kW` se emite como
   `perdidas_declaradas_variador` (informativo) y **jamas** como `perdidas_ref_kw` ni `p`, que solo salen
   del cuadro 6 en `calculo.py`.

Normalizacion de valores (el consolidador no interpreta separadores: es trabajo de aqui):

| En el documento | `Evidencia.valor` | `unidad` |
|---|---|---|
| `110 kW` | `110` | `kW` |
| `1.485 rpm` | `1485` | `rpm` |
| `6.000 h` | `6000` | `h` |
| `60,0 kW` | `60.0` | `kW` |
| `305.829 kWh` | `305829` | `kWh` |
| `02/03/2026` | `2026-03-02` | — |
| `Bomba dinamica (centrifuga) (bomba_dinamica)` | `bomba_dinamica` | — |

Heuristicas declaradas (van a `docs/03` §8):

- **Claves de union por tabla**: los numeros de serie que aparecen en la **misma tabla** que el valor son
  sus claves; si la tabla no los trae, se heredan los ultimos vistos en la pagina y, en su defecto, en el
  documento. Todas las tablas por motor de los documentos multimotor (E y F) traen ambos numeros, asi que
  la herencia solo actua en documentos de un motor.
- **Respaldo por texto**: una etiqueta se busca por sus palabras significativas (>= 4 letras o con digito,
  sin lo que va entre parentesis); el valor es lo que queda en esa linea o, si no queda nada, la siguiente
  linea no vacia. Es tambien como se leen las paginas escaneadas (el OCR no da tablas).
- **Categoria de una linea de factura**: la decide **que se factura**, no que palabra va antes (H1 de
  `/contrastar`, 20/09/2026). Primero se mira si la linea **adquiere** un equipo (senal de compra en el
  mismo segmento, o `nuevo`/`nueva` pegado al sustantivo, y sin marca de `existente`): entonces es del
  equipo aunque empiece por "Montaje". Si no, una senal de mano de obra en la **cabeza** (hasta la primera
  coma o parentesis) la hace `instalacion`. Si no, es del primer equipo que nombre la cabeza, por posicion.
  Lo que va tras "no incluye" se descarta antes de mirar nada, y cada `nuevo`/`existente` califica al
  sustantivo que tiene al lado: "instalacion sobre motor existente MTR-SYN-0001" no convierte una linea de
  variador en una linea de motor (trampa de docs/05 §4.3), y "no incluye suministro de motor" tampoco.
  El lexico de compra es amplio a proposito porque EXC-02 excluye la sustitucion "total o parcial"; el de
  mano de obra es estrecho, para no llamar compra a un trabajo sobre el equipo que ya esta ahi.
- **Placa de caracteristicas**: el OCR de una pagina con fotos (o de una foto suelta) cuyo texto habla de
  una placa se emite con `tipo_doc = "placa_caracteristicas_foto"`, que es la fuente que la spec declara
  para `PM` y `N1`; el resto de tipos documentales quedan como estan.
- **`n_motores` por fuente**: el campo explicito del documento si lo hay ("Numero de motores incluidos",
  "N.o de variadores facturados", ...); si el tipo no declara ninguno (registro de funcionamiento, fotos
  sueltas), el numero de **numeros de serie de motor distintos** observados en documentos de ese tipo.
- Un documento sin tipo (el `notas.pdf` del caso G) **no** se extrae: no hay lexico que aplicar.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Protocol, runtime_checkable

from engine.clasificacion import (
    SUBTIPO_FOTO_ANTES,
    SUBTIPO_FOTO_DESPUES,
    TIPO_INFORME_FOTOGRAFICO,
)
from engine.evidencias import Evidencia
from engine.ingesta import Documento, Pagina
from engine.registro_xlsx import RegistroFuncionamiento, leer_registro

VERSION_EXTRACTOR = "reglas-0.1.0"
METODO_TABLA = "tabla"
METODO_REGEX = "regex"
METODO_OCR = "ocr"
METODO_XLSX = "xlsx"
METODO_EXIF = "exif"
CONFIANZA_NATIVA = Decimal("1")
CONFIANZA_OCR = Decimal("0.75")
DEMOSTRADO = "demostrado"
DECLARADO = "declarado"
DERIVADO = "derivado"

CLAVE_MOTOR = "num_serie_motor"
CLAVE_VARIADOR = "num_serie_variador"
TIPO_PLACA = "placa_caracteristicas_foto"
RAIZ_REGISTRO = "registro"

# Patrones como texto: en `engine/` no se llama a la funcion de compilacion de `re` (ya cachea por dentro)
SERIE = r"[A-Z]{2,4}(?:-[A-Z0-9]{2,6}){1,4}"
PATRON_SERIE = rf"\b{SERIE}\b"
PATRON_HASH = r"(?i)\b[0-9a-f]{64}\b"
PATRON_NUMERO = r"[-+]?\d[\d.,]*"
PATRON_UNIDAD = r"[-+]?\d[\d.,]*\s*([A-Za-z%/][A-Za-z%/°º]*)"
PATRON_FECHA = r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"
PATRON_FECHA_ISO = r"\b(\d{4})-(\d{2})-(\d{2})\b"
PATRON_FOTO = r"(?i)Foto\s+(\d+)\s*[–—-]\s*(ANTES|DESPU[EÉ]S)\s*[–—-]\s*motor\s+([A-Z0-9-]+)"
PATRON_SERIE_EN_TEXTO = rf"(?i)n[oº°ø*?]?\s*(?:de\s+)?serie\s+({SERIE})"
PATRON_MOTOR_EN_TEXTO = rf"(?i)motor\s+existente\s+({SERIE})"
PATRON_SERIE_TRAS_MOTOR = rf"(?i)\bmotor\s+({SERIE})\b"
PATRON_VALOR_PLACA = r"(?i)([-+]?\d[\d.,]*)\s*{unidad}\b"

# Tipos de documento que pueden atestiguar cuantos motores tiene la actuacion (ADR-002 §2.3)
FUENTES_N_MOTORES = (
    "factura",
    "certificado_instalador",
    "ficha_cumplimentada",
    "informe_fotografico",
    "registro_funcionamiento",
)
CATEGORIAS_LINEA = (
    "variador",
    "instalacion",
    "motor",
    "bomba",
    "ventilador",
    "compresor",
    "equipo_completo",
    "otro",
)  # categorias admitidas para `factura.lineas` (ADR-002 §2.3)

# --- Lexico de lineas de factura (consume `R-AMB-02`, BLOQUEANTE_AMBITO; EXC-01 y EXC-02) ---------------
#
# La categoria responde a **que se factura**, no a que palabra aparece antes. Una linea que **adquiere** el
# equipo es del equipo aunque empiece por "Montaje"; una linea que solo hace **trabajo** sobre un equipo que
# ya esta ahi es `instalacion` aunque nombre el motor. Decidir por la cabeza de la linea daba las dos cosas
# mal: "Suministro e instalacion de motor nuevo" salia `instalacion` (H1 de `/contrastar` 20/09/2026) y
# reordenar las senales habria dado `motor` a "Instalacion de variador sobre motor existente", que es el caso
# de uso central del producto.

# Sustantivos de equipo. `variador` esta aparte en `ORDEN_EQUIPOS`: comprar el variador es la actuacion, no
# una exclusion; lo que excluyen EXC-01/EXC-02 es comprar el equipo accionado o el conjunto.
SENALES_EQUIPO: dict[str, tuple[str, ...]] = {
    "equipo_completo": ("equipo completo", "grupo completo", "conjunto motobomba", "grupo motobomba"),
    "motor": ("motor",),
    "bomba": ("bomba", "electrobomba", "motobomba", "grupo de bombeo"),
    "ventilador": ("ventilador", "soplante", "extractor de aire"),
    "compresor": ("compresor", "turbocompresor"),
    "variador": ("variador", "convertidor de frecuencia", "vsd"),
}
# Precedencia cuando una linea adquiere mas de un equipo: el accionado manda sobre el variador.
ORDEN_EQUIPOS: tuple[str, ...] = ("equipo_completo", "motor", "bomba", "ventilador", "compresor", "variador")

# Adquisicion: amplio a proposito. EXC-02 excluye la sustitucion "total o parcial" del equipo existente, de
# modo que comprar una parte ya es exclusion (las exclusiones las declara la spec, no este modulo).
SENALES_ADQUISICION: tuple[str, ...] = (
    "suministro",
    "suministra",
    "suministrado",
    "venta",
    "vendido",
    "compra",
    "adquisicion",
    "adquirido",
    "sustitucion",
    "sustituye",
    "sustituido",
    "reposicion",
    "repuesto",
    "renovacion",
    "reemplazo",
    "cambio de",
    "provision",
    "entrega de",
)
# Trabajo sobre un equipo que ya esta ahi: estrecho a proposito (no marcar como compra la mano de obra).
SENALES_TRABAJO: tuple[str, ...] = (
    "instalacion",
    "instalado",
    "montaje",
    "puesta en marcha",
    "puesta en servicio",
    "parametrizacion",
    "programacion",
    "configuracion",
    "mano de obra",
    "conexionado",
    "cableado",
    "desmontaje",
    "desinstalacion",
    "retirada",
    "ajuste",
    "revision",
    "mantenimiento",
    "reparacion",
    "rebobinado",
    "asistencia tecnica",
    "horas de tecnico",
)
# Clausulas que niegan lo que viene detras hasta el final de su segmento ("no incluye suministro de motor").
SENALES_EXCLUSION: tuple[str, ...] = (
    "no incluye",
    "no se incluye",
    "no incluido",
    "no comprende",
    "sin suministro",
    "excluye",
    "excluido",
    "salvo",
)
# Subconjunto de `SENALES_ADQUISICION`: EXC-02 excluye la sustitucion "del equipo existente", de modo que
# con estas el `existente` no dice que no se compre; lo dice el `nuevo` que venga detras en el mismo segmento.
SENALES_SUSTITUCION: tuple[str, ...] = (
    "sustitucion",
    "sustituye",
    "sustituido",
    "reemplazo",
    "reposicion",
    "renovacion",
    "cambio de",
)


def _patron_de(senales: tuple[str, ...]) -> str:
    """Alternativa anclada al principio de palabra: `venta` no puede casar dentro de `ventilador`."""
    return r"\b(?:" + "|".join(re.escape(senal) for senal in senales) + ")"


PATRON_ADQUISICION = _patron_de(SENALES_ADQUISICION)
PATRON_TRABAJO = _patron_de(SENALES_TRABAJO)
PATRON_SUSTITUCION = _patron_de(SENALES_SUSTITUCION)
PATRON_EXCLUSION = _patron_de(SENALES_EXCLUSION)
MARCA_NUEVO = r"\bnuev[oa]s?\b|\bsin estrenar\b|\ba estrenar\b"
MARCA_EXISTENTE = r"\bpre-?existentes?\b|\bexistentes?\b|\bya instalad[oa]s?\b"
VENTANA_PRE = 15  # caracteres antes del sustantivo donde cuenta "nueva bomba"
VENTANA_POS = 45  # caracteres despues donde cuentan "motor existente" y "bomba centrifuga nueva"
SEPARADORES_SEGMENTO = r"[(),;]"


class ErrorExtraccion(Exception):
    """Lexico o spec incompatibles con la extraccion (tipo de valor desconocido)."""


# ---------------------------------------------------------------------------
# Lexico: que etiqueta da que variable, en que documento
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Campo:
    """Una etiqueta de un tipo de documento y la variable que produce."""

    variable: str
    etiquetas: tuple[str, ...]
    tipo_evidencia: str = DEMOSTRADO
    valor: str = "numero"  # numero | entero | fecha | texto | serie | hash | enum
    clave: bool = False  # ademas de variable, es clave de union
    solo_clave: bool = False  # solo clave de union: no se emite como variable
    respaldo: bool = True  # se busca tambien en el texto si la tabla no lo trae


def _c(*args, **kwargs) -> Campo:
    return Campo(*args, **kwargs)


CAMPOS: dict[str, tuple[Campo, ...]] = {
    "ficha_cumplimentada": (
        _c("titular_razon_social", ("propietario inicial del ahorro (titular)", "titular"), valor="texto"),
        _c("titular_nif", ("nif del titular",), valor="texto"),
        _c("fecha_inicio_actuacion", ("fecha de inicio de la actuacion",), valor="fecha"),
        _c("fecha_fin_actuacion", ("fecha de fin de la actuacion",), valor="fecha"),
        _c("n_motores", ("numero de motores incluidos",), valor="entero"),
        _c(CLAVE_MOTOR, ("no de serie del motor",), valor="serie", clave=True),
        _c(CLAVE_VARIADOR, ("no de serie del variador",), valor="serie", clave=True),
        _c("tipo_equipo_accionado", ("equipo accionado",), valor="enum"),
        _c("PM", ("potencia nominal del motor pm",), valor="numero"),
        _c("N1", ("velocidad antes de la actuacion n1",), valor="numero"),
        _c("N2", ("velocidad media con variador n2 (declarada)",), tipo_evidencia=DECLARADO),
        _c("P_prom", ("potencia promedio con variador p_prom (declarada)",), tipo_evidencia=DECLARADO),
        _c("h_antes", ("horas anuales de funcionamiento previas",)),
        _c(
            "ficha_cumplimentada.ahorro_declarado_kwh",
            ("ahorro anual estimado", "ahorro anual de energia final"),
            tipo_evidencia=DECLARADO,
            valor="entero",
        ),
    ),
    "declaracion_responsable": (
        _c("titular_razon_social", ("razon social del titular",), valor="texto"),
        _c("titular_nif", ("nif del titular",), valor="texto"),
    ),
    "factura": (
        _c("titular_razon_social", ("receptor (cliente)", "receptor"), valor="texto"),
        _c("titular_nif", ("nif del receptor",), valor="texto"),
        _c("fecha_inicio_actuacion", ("fecha de factura", "fecha de pedido"), valor="fecha"),
        _c("n_motores", ("no de variadores facturados", "numero de motores"), valor="entero"),
    ),
    "informe_fotografico": (
        _c(CLAVE_MOTOR, ("no de serie del motor",), valor="serie", clave=True),
        _c(
            CLAVE_VARIADOR,
            ("no de serie del variador instalado", "no de serie del variador"),
            valor="serie",
            clave=True,
        ),
        _c("n_motores", ("numero de motores fotografiados",), valor="entero"),
    ),
    "certificado_instalador": (
        _c("titular_razon_social", ("titular de la instalacion",), valor="texto"),
        _c("titular_nif", ("nif del titular",), valor="texto"),
        _c("fecha_fin_actuacion", ("fecha de puesta en marcha (fin de la actuacion)",), valor="fecha"),
        _c("n_motores", ("numero de motores intervenidos",), valor="entero"),
        _c(CLAVE_MOTOR, ("no de serie del motor",), valor="serie", clave=True),
        _c(CLAVE_VARIADOR, ("no de serie del variador",), valor="serie", clave=True),
        _c("tipo_equipo_accionado", ("tipo de equipo accionado",), valor="enum"),
        _c("regimen_previo", ("regimen de funcionamiento previo",), valor="enum"),
        _c("PM", ("a) potencia nominal del motor pm (segun ficha tecnica)",)),
        _c("N1", ("a) velocidad nominal n1 (segun ficha tecnica)",)),
        _c("P_prom", ("b) potencia promedio con variador p_prom",), tipo_evidencia=DECLARADO),
        _c("N2", ("b) velocidad media con variador n2",), tipo_evidencia=DECLARADO),
        _c(
            f"{RAIZ_REGISTRO}.hash_declarado",
            ("b) sha-256 del registro", "sha-256 del registro"),
            tipo_evidencia=DECLARADO,
            valor="hash",
        ),
        _c(
            f"{RAIZ_REGISTRO}.nombre_declarado",
            ("b) registro de funcionamiento (fichero)", "registro de funcionamiento (fichero)"),
            tipo_evidencia=DECLARADO,
            valor="texto",
        ),
    ),
    "registro_horas_previo": (
        _c(CLAVE_MOTOR, ("no de serie del motor",), valor="serie", clave=True),
        _c("h_antes", ("horas anuales de funcionamiento (h_antes)", "horas anuales de funcionamiento")),
        _c("regimen_previo", ("regimen de funcionamiento",), valor="enum"),
    ),
    "ficha_tecnica_motor": (
        _c(CLAVE_MOTOR, ("no de serie del motor",), valor="serie", clave=True),
        _c("PM", ("potencia nominal pm", "potencia nominal")),
        _c("N1", ("velocidad nominal n1", "velocidad nominal")),
    ),
    "ficha_tecnica_variador": (
        _c(CLAVE_VARIADOR, ("no de serie del variador",), valor="serie", clave=True),
        _c(CLAVE_MOTOR, ("motor asociado (no de serie)",), valor="serie", clave=True, solo_clave=True),
        _c(
            "perdidas_declaradas_variador",
            ("perdidas declaradas por el fabricante", "perdidas declaradas"),
            tipo_evidencia=DECLARADO,
        ),
    ),
    "ficha_tecnica_equipo_accionado": (
        _c("tipo_equipo_accionado", ("tipo de equipo",), valor="enum"),
        _c(CLAVE_MOTOR, ("motor asociado (no de serie)",), valor="serie", clave=True, solo_clave=True),
    ),
    "convenio_cae": (
        _c(
            "titular_razon_social",
            ("propietario inicial del ahorro (razon social)", "propietario inicial del ahorro"),
            valor="texto",
        ),
        _c("titular_nif", ("nif del propietario inicial",), valor="texto"),
        _c(
            "convenio.ahorro_kwh",
            ("ahorro anual de energia final",),
            tipo_evidencia=DECLARADO,
            valor="entero",
        ),
        _c("convenio.fecha_firma", ("fecha de firma del convenio",), valor="fecha"),
    ),
    "pedido": (
        _c("titular_razon_social", ("cliente", "receptor"), valor="texto"),
        _c("titular_nif", ("nif del cliente",), valor="texto"),
        _c("fecha_inicio_actuacion", ("fecha de pedido",), valor="fecha"),
    ),
}

# Campos que se leen del OCR de una placa de caracteristicas (el texto no existe en ninguna otra parte)
CAMPOS_PLACA: tuple[Campo, ...] = (
    _c("PM", ("kw",)),
    _c("N1", ("rpm",)),
)


# ---------------------------------------------------------------------------
# Normalizacion
# ---------------------------------------------------------------------------


def normalizar(texto: str) -> str:
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn"
    )
    return " ".join(sin_tildes.lower().replace("º", "o").replace("°", "o").split())


def numero_canonico(texto: str) -> str | None:
    """`1.485 rpm` → `1485`; `60,0 kW` → `60.0`; `3,90` → `3.90`. Formato espanol: `.` miles, `,` decimal."""
    encontrado = re.search(PATRON_NUMERO, texto or "")
    if encontrado is None:
        return None
    crudo = encontrado.group(0).strip().rstrip(".,")
    if not crudo:
        return None
    limpio = crudo.replace(".", "").replace(",", ".") if "," in crudo else crudo.replace(".", "")
    if "," in crudo and crudo.count(",") > 1:
        return None
    try:
        Decimal(limpio)
    except InvalidOperation:
        return None
    return limpio


def unidad_de(texto: str) -> str | None:
    encontrado = re.search(PATRON_UNIDAD, texto or "")
    if encontrado is None:
        return None
    unidad = encontrado.group(1).strip()
    return unidad or None


def fecha_iso(texto: str) -> str | None:
    """`dd/mm/aaaa` → ISO. Ya en ISO, se respeta."""
    encontrado = re.search(PATRON_FECHA, texto or "")
    if encontrado is not None:
        dia, mes, ano = encontrado.groups()
        return f"{ano}-{int(mes):02d}-{int(dia):02d}"
    iso = re.search(PATRON_FECHA_ISO, texto or "")
    return iso.group(0) if iso else None


def serie_de(texto: str) -> str | None:
    encontrado = re.search(PATRON_SERIE, (texto or "").upper())
    return encontrado.group(0) if encontrado else None


def hash_de(texto: str) -> str | None:
    encontrado = re.search(PATRON_HASH, texto or "")
    return encontrado.group(0).lower() if encontrado else None


def _enumerados(variable: str, spec: object) -> tuple[str, ...]:
    """Valores admitidos de una variable `enum` segun la spec (`valores` o `valores_ref`)."""
    declaracion = _declaracion(variable, spec)
    if declaracion is None:
        return ()
    valores = declaracion.get("valores")
    if isinstance(valores, Sequence) and not isinstance(valores, str):
        return tuple(str(v) for v in valores)
    referencia = declaracion.get("valores_ref")
    if not isinstance(referencia, str):
        return ()
    datos = getattr(spec, "datos", None) or {}
    recogidos: list[str] = []
    for camino in referencia.split("+"):
        actual: object = datos
        for tramo in camino.strip().split("."):
            if isinstance(actual, Mapping):
                actual = actual.get(tramo)
            else:
                actual = None
                break
        if isinstance(actual, Sequence) and not isinstance(actual, str):
            recogidos.extend(str(v) for v in actual)
    return tuple(recogidos)


def enum_de(texto: str, valores: Iterable[str]) -> str | None:
    """Valor del enumerado que aparece en la celda (gana el mas largo: `bomba_desplazamiento_positivo`)."""
    normalizado = normalizar(texto)
    candidatos = [v for v in valores if normalizar(v) in normalizado]
    if not candidatos:
        return None
    return max(candidatos, key=len)


def convertir(campo: Campo, crudo: str, spec: object) -> tuple[str | None, str | None]:
    """Celda cruda → (valor canonico, unidad). `None` si la celda no contiene lo que el campo espera."""
    texto = " ".join((crudo or "").split())
    if campo.valor == "texto":
        return (texto or None), None
    if campo.valor == "fecha":
        return fecha_iso(texto), None
    if campo.valor == "serie":
        return serie_de(texto), None
    if campo.valor == "hash":
        return hash_de(texto), None
    if campo.valor == "enum":
        return enum_de(texto, _enumerados(campo.variable, spec)), None
    if campo.valor == "entero":
        numero = numero_canonico(texto)
        if numero is None:
            return None, None
        try:
            entero = int(Decimal(numero))
        except (InvalidOperation, ValueError):
            return None, None
        return str(entero), unidad_de(texto)
    if campo.valor == "numero":
        return numero_canonico(texto), unidad_de(texto)
    raise ErrorExtraccion(f"tipo de valor desconocido en el lexico: {campo.valor!r}")


# ---------------------------------------------------------------------------
# Que admite la spec
# ---------------------------------------------------------------------------


def _declaracion(variable: str, spec: object) -> Mapping[str, object] | None:
    variables = getattr(spec, "variables", None) or {}
    declaracion = variables.get(variable)
    return declaracion if isinstance(declaracion, Mapping) else None


def fuentes_admitidas(variable: str, spec: object) -> frozenset[str] | None:
    """Tipos de documento que la spec admite como fuente de la variable. `None` = la spec no la declara."""
    declaracion = _declaracion(variable, spec)
    if declaracion is None:
        return None
    fuentes: set[str] = set()
    for clave in ("fuentes", "cruce_con"):
        valores = declaracion.get(clave)
        if isinstance(valores, Sequence) and not isinstance(valores, str):
            fuentes.update(str(v) for v in valores)
    derivacion = declaracion.get("derivacion")
    if isinstance(derivacion, Mapping):
        fuente = derivacion.get("fuente")
        if isinstance(fuente, str) and not fuente.startswith("tabla:"):
            fuentes.add(fuente)
    return frozenset(fuentes) if fuentes else frozenset()


def admite(variable: str, tipo_doc: str, spec: object) -> bool:
    """La spec decide: un campo del lexico solo entra si su tipo de documento es fuente de la variable."""
    fuentes = fuentes_admitidas(variable, spec)
    if fuentes is None:  # hecho documental o variable fuera de la spec (n_motores, factura.*, registro.*)
        return True
    return tipo_doc in fuentes


def interpretacion_de(variable: str, spec: object) -> str | None:
    declaracion = _declaracion(variable, spec)
    if declaracion is None:
        return None
    derivacion = declaracion.get("derivacion")
    if isinstance(derivacion, Mapping):
        valor = derivacion.get("interpretacion")
        return str(valor) if valor else None
    return None


def unidad_declarada(variable: str, spec: object) -> str | None:
    declaracion = _declaracion(variable, spec)
    if declaracion is None:
        return None
    unidad = declaracion.get("unidad")
    return str(unidad) if unidad else None


# ---------------------------------------------------------------------------
# Tablas y texto
# ---------------------------------------------------------------------------


def pares_de_tabla(tabla: Sequence[Sequence[str]]) -> list[tuple[str, str]]:
    """Filas etiqueta/valor de una tabla de dos columnas (`Campo | Valor`)."""
    pares: list[tuple[str, str]] = []
    for fila in tabla:
        celdas = [c for c in fila]
        if len(celdas) < 2:
            continue
        etiqueta = " ".join((celdas[0] or "").split())
        valor = " ".join((celdas[1] or "").split())
        if not etiqueta:
            continue
        pares.append((etiqueta, valor))
    return pares


def es_tabla_de_lineas(tabla: Sequence[Sequence[str]]) -> bool:
    if not tabla:
        return False
    cabecera = normalizar(" ".join(c or "" for c in tabla[0]))
    return "descripcion" in cabecera


VACIAS = frozenset(
    {
        "de",
        "del",
        "la",
        "el",
        "los",
        "las",
        "y",
        "o",
        "a",
        "al",
        "en",
        "por",
        "con",
        "un",
        "una",
        "segun",
        "no",
        "n",
        "num",
        "numero",
    }  # "no" viene de "N.o"; "numero" no distingue etiquetas
)


def _plano(texto: str) -> str:
    """Minusculas y sin tildes **conservando la longitud** (para poder cortar sobre el texto original)."""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn"
    )
    return sin_tildes.lower().replace("º", "o").replace("°", "o")


def palabras_clave(etiqueta: str) -> tuple[str, ...]:
    """Palabras significativas de una etiqueta para buscarla en texto plano (sin parentesis ni vacias).

    "Fecha de fin de la actuacion" → ("fecha", "fin", "actuacion"): sin "fin" la etiqueta casaria tambien
    con la fecha de inicio, que es justo el error que este filtro evita.
    """
    sin_parentesis = re.sub(r"\([^)]*\)", " ", etiqueta)
    palabras = re.findall(r"[\wÀ-ſ]+", normalizar(sin_parentesis))
    return tuple(p for p in palabras if p not in VACIAS and len(p) >= 2)


def candidatos_en_texto(lineas: Sequence[str], etiqueta: str) -> list[tuple[str, str]]:
    """Valores candidatos de una etiqueta, en orden: (valor crudo, linea literal).

    Primero lo que queda en la linea tras la etiqueta y despues la siguiente linea no vacia: en una pagina
    escaneada (y en una tabla que el OCR deshace) la etiqueta y su valor caen en lineas distintas. Quien
    llama prueba los candidatos hasta que uno convierte al tipo que el campo espera.
    """
    claves = palabras_clave(etiqueta)
    if not claves:
        return []
    for indice, linea in enumerate(lineas):
        plana = _plano(linea)
        if not all(clave in plana for clave in claves):
            continue
        corte = max(plana.rfind(clave) + len(clave) for clave in claves)
        resto = linea[corte:].strip(" :-–—.")
        candidatos: list[tuple[str, str]] = []
        if resto:
            candidatos.append((resto, linea.strip()))
        for siguiente in lineas[indice + 1 : indice + 2]:
            if siguiente.strip():
                candidatos.append((siguiente.strip(), f"{linea.strip()} | {siguiente.strip()}"))
        return candidatos
    return []


def buscar_en_texto(lineas: Sequence[str], etiqueta: str) -> tuple[str, str] | None:
    """Primer candidato de `candidatos_en_texto`."""
    candidatos = candidatos_en_texto(lineas, etiqueta)
    return candidatos[0] if candidatos else None


def _primer_valor(
    campo: Campo, candidatos: Sequence[tuple[str, str]], spec: object
) -> tuple[str, str | None, str] | None:
    """Primer candidato que convierte al tipo que el campo espera: (valor, unidad, texto literal)."""
    for crudo, literal in candidatos:
        valor, unidad = convertir(campo, crudo, spec)
        if valor is not None:
            return valor, unidad, literal
    return None


# ---------------------------------------------------------------------------
# Interfaz
# ---------------------------------------------------------------------------


@runtime_checkable
class Extractor(Protocol):
    """Contrato de todo extractor (reglas hoy, LLM en el Sprint 3, siempre con cita)."""

    version: str

    def extraer(self, doc: Documento, spec: object) -> list[Evidencia]: ...


class ExtractorReglas:
    """Extractor determinista por reglas: tablas antes que texto, regex de respaldo, OCR al 0,75."""

    version = VERSION_EXTRACTOR

    # -- utilidades internas -------------------------------------------------

    def _evidencia(
        self,
        *,
        variable: str,
        valor: str,
        doc: Documento,
        tipo_doc: str,
        pagina: int,
        texto_literal: str,
        metodo: str,
        tipo_evidencia: str,
        claves: Mapping[str, str | None],
        unidad: str | None = None,
        interpretacion: str | None = None,
    ) -> Evidencia:
        confianza = CONFIANZA_OCR if metodo == METODO_OCR else CONFIANZA_NATIVA
        return Evidencia(
            variable=variable,
            valor=valor,
            doc_id=doc.doc_id,
            tipo_doc=tipo_doc,
            pagina=pagina,
            texto_literal=" ".join((texto_literal or "").split())[:400],
            metodo=metodo,
            confianza=confianza,
            extractor_version=self.version,
            tipo_evidencia=tipo_evidencia,
            num_serie_motor=claves.get(CLAVE_MOTOR),
            num_serie_variador=claves.get(CLAVE_VARIADOR),
            unidad=unidad,
            interpretacion=interpretacion,
        )

    # -- entrada publica -----------------------------------------------------

    def extraer(self, doc: Documento, spec: object) -> list[Evidencia]:
        """Evidencias de un documento. Un combinado no se extrae: se extraen sus partes."""
        if doc.es_combinado or not doc.tipo:
            return []
        if doc.formato == "xlsx":
            return self._extraer_registro(doc, spec)
        if doc.formato == "imagen":
            return self._extraer_imagen(doc, spec)
        return self._extraer_paginado(doc, spec)

    # -- PDF -----------------------------------------------------------------

    def _extraer_paginado(self, doc: Documento, spec: object) -> list[Evidencia]:
        """Dos pasadas: **primero todas las tablas** del documento y solo despues el texto como respaldo."""
        tipo_doc = doc.tipo or ""
        campos = CAMPOS.get(tipo_doc, ())
        evidencias: list[Evidencia] = []
        claves_doc: dict[str, str | None] = {CLAVE_MOTOR: None, CLAVE_VARIADOR: None}
        claves_por_pagina: dict[int, dict[str, str | None]] = {}
        for pagina in doc.paginas:
            claves_pagina = dict(claves_doc)
            evidencias.extend(self._de_tablas(doc, pagina, campos, spec, claves_pagina))
            claves_por_pagina[pagina.numero] = dict(claves_pagina)
            claves_doc.update({k: v for k, v in claves_pagina.items() if v})
        encontradas = {ev.variable for ev in evidencias}
        for pagina in doc.paginas:
            claves_pagina = claves_por_pagina.get(pagina.numero, dict(claves_doc))
            respaldo = self._de_texto(doc, pagina, campos, spec, claves_pagina, encontradas)
            evidencias.extend(respaldo)
            encontradas.update(ev.variable for ev in respaldo)
            evidencias.extend(self._hechos(doc, pagina, spec, claves_pagina))
            evidencias.extend(self._de_ocr(doc, pagina, campos, spec, claves_pagina))
        return evidencias

    def _de_tablas(
        self,
        doc: Documento,
        pagina: Pagina,
        campos: Sequence[Campo],
        spec: object,
        claves_pagina: dict[str, str | None],
    ) -> list[Evidencia]:
        tipo_doc = doc.tipo or ""
        evidencias: list[Evidencia] = []
        for tabla in pagina.tablas:
            if es_tabla_de_lineas(tabla):
                continue
            pares = pares_de_tabla(tabla)
            if not pares:
                continue
            claves = dict(claves_pagina)
            claves.update(self._claves_de_pares(pares, campos, spec))
            for etiqueta, crudo in pares:
                normalizada = normalizar(etiqueta)
                for campo in campos:
                    if normalizada not in campo.etiquetas:
                        continue
                    if campo.solo_clave or not admite(campo.variable, tipo_doc, spec):
                        continue
                    valor, unidad = convertir(campo, crudo, spec)
                    if valor is None:
                        continue
                    evidencias.append(
                        self._evidencia(
                            variable=campo.variable,
                            valor=valor,
                            doc=doc,
                            tipo_doc=tipo_doc,
                            pagina=pagina.numero,
                            texto_literal=f"{etiqueta} {crudo}",
                            metodo=METODO_TABLA,
                            tipo_evidencia=campo.tipo_evidencia,
                            claves=claves,
                            unidad=unidad or unidad_declarada(campo.variable, spec),
                            interpretacion=None,
                        )
                    )
            claves_pagina.update({k: v for k, v in claves.items() if v})
        return evidencias

    def _claves_de_pares(
        self, pares: Sequence[tuple[str, str]], campos: Sequence[Campo], spec: object
    ) -> dict[str, str | None]:
        """Numeros de serie que aparecen en la misma tabla que el valor (claves de union)."""
        claves: dict[str, str | None] = {}
        for etiqueta, crudo in pares:
            normalizada = normalizar(etiqueta)
            for campo in campos:
                if not campo.clave or normalizada not in campo.etiquetas:
                    continue
                serie = serie_de(crudo)
                if serie:
                    claves[campo.variable] = serie
        return claves

    def _de_texto(
        self,
        doc: Documento,
        pagina: Pagina,
        campos: Sequence[Campo],
        spec: object,
        claves_pagina: dict[str, str | None],
        encontradas: set[str],
    ) -> list[Evidencia]:
        """Respaldo por texto: solo para lo que las tablas no dieron (tablas antes que texto).

        Una pagina sin capa de texto no pasa por aqui: su texto **es** OCR y lo lee `_de_ocr` con 0,75.
        """
        tipo_doc = doc.tipo or ""
        if not pagina.texto or pagina.metodo == METODO_OCR:
            return []
        lineas = [linea for linea in pagina.texto.splitlines() if linea.strip()]
        evidencias: list[Evidencia] = []
        claves = dict(claves_pagina)
        for campo in campos:
            if campo.solo_clave or not campo.respaldo or campo.variable in encontradas:
                continue
            if not admite(campo.variable, tipo_doc, spec):
                continue
            for etiqueta in campo.etiquetas:
                hallado = _primer_valor(campo, candidatos_en_texto(lineas, etiqueta), spec)
                if hallado is None:
                    continue
                valor, unidad, literal = hallado
                evidencias.append(
                    self._evidencia(
                        variable=campo.variable,
                        valor=valor,
                        doc=doc,
                        tipo_doc=tipo_doc,
                        pagina=pagina.numero,
                        texto_literal=literal,
                        metodo=METODO_REGEX,
                        tipo_evidencia=campo.tipo_evidencia,
                        claves=claves,
                        unidad=unidad or unidad_declarada(campo.variable, spec),
                    )
                )
                encontradas.add(campo.variable)
                break
        return evidencias

    def _de_ocr(
        self,
        doc: Documento,
        pagina: Pagina,
        campos: Sequence[Campo],
        spec: object,
        claves_pagina: Mapping[str, str | None],
    ) -> list[Evidencia]:
        """Lo que solo esta en una imagen: placa de caracteristicas y paginas escaneadas (confianza 0,75)."""
        texto = pagina.texto if pagina.metodo == METODO_OCR else pagina.texto_ocr
        if not texto:
            return []
        lineas = [linea for linea in texto.splitlines() if linea.strip()]
        if "placa de caracteristicas" in normalizar(texto):
            return self._de_placa(doc, pagina, lineas, spec, claves_pagina)
        return self._de_escaneo(doc, pagina, lineas, campos, spec, claves_pagina)

    def _de_placa(
        self,
        doc: Documento,
        pagina: Pagina,
        lineas: Sequence[str],
        spec: object,
        claves_pagina: Mapping[str, str | None],
    ) -> list[Evidencia]:
        """Placa de caracteristicas: sin etiquetas, el valor va pegado a su unidad (`110 kW`, `1485 rpm`).

        Una misma pagina puede llevar varias placas (E y F): la linea `MOTOR <serie>` abre cada bloque y
        los valores que siguen son de ese motor.
        """
        evidencias: list[Evidencia] = []
        claves: dict[str, str | None] = dict(claves_pagina)
        for linea in lineas:
            serie = re.search(PATRON_SERIE_TRAS_MOTOR, linea)
            if serie is not None:
                claves = dict(claves_pagina)
                claves[CLAVE_MOTOR] = serie.group(1).upper()
                claves[CLAVE_VARIADOR] = None
            plana = normalizar(linea)
            for campo in CAMPOS_PLACA:
                if not admite(campo.variable, TIPO_PLACA, spec):
                    continue
                for etiqueta in campo.etiquetas:
                    encontrado = re.search(PATRON_VALOR_PLACA.format(unidad=re.escape(etiqueta)), plana)
                    if encontrado is None:
                        continue
                    valor, unidad = convertir(campo, f"{encontrado.group(1)} {etiqueta}", spec)
                    if valor is None:
                        continue
                    evidencias.append(
                        self._evidencia(
                            variable=campo.variable,
                            valor=valor,
                            doc=doc,
                            tipo_doc=TIPO_PLACA,
                            pagina=pagina.numero,
                            texto_literal=linea.strip(),
                            metodo=METODO_OCR,
                            tipo_evidencia=campo.tipo_evidencia,
                            claves=claves,
                            unidad=unidad or unidad_declarada(campo.variable, spec),
                        )
                    )
                    break
        return evidencias

    def _de_escaneo(
        self,
        doc: Documento,
        pagina: Pagina,
        lineas: Sequence[str],
        campos: Sequence[Campo],
        spec: object,
        claves_pagina: Mapping[str, str | None],
    ) -> list[Evidencia]:
        """Pagina escaneada: el lexico del tipo de documento, buscado por etiqueta sobre el texto del OCR."""
        tipo_doc = doc.tipo or ""
        claves: dict[str, str | None] = dict(claves_pagina)
        for campo in campos:  # primero las claves de union, para que las citen los demas valores
            if not campo.clave:
                continue
            for etiqueta in campo.etiquetas:
                for crudo, _ in candidatos_en_texto(lineas, etiqueta):
                    serie = serie_de(crudo)
                    if serie:
                        claves[campo.variable] = serie
                        break
                if claves.get(campo.variable):
                    break
        evidencias: list[Evidencia] = []
        for campo in campos:
            if campo.solo_clave or not admite(campo.variable, tipo_doc, spec):
                continue
            for etiqueta in campo.etiquetas:
                hallado = _primer_valor(campo, candidatos_en_texto(lineas, etiqueta), spec)
                if hallado is None:
                    continue
                valor, unidad, literal = hallado
                evidencias.append(
                    self._evidencia(
                        variable=campo.variable,
                        valor=valor,
                        doc=doc,
                        tipo_doc=tipo_doc,
                        pagina=pagina.numero,
                        texto_literal=literal,
                        metodo=METODO_OCR,
                        tipo_evidencia=campo.tipo_evidencia,
                        claves=claves,
                        unidad=unidad or unidad_declarada(campo.variable, spec),
                    )
                )
                break
        return evidencias

    # -- imagenes sueltas ----------------------------------------------------

    def _extraer_imagen(self, doc: Documento, spec: object) -> list[Evidencia]:
        """Foto suelta: las claves y el papel salen del EXIF; la placa, del OCR."""
        tipo_doc = doc.tipo or ""
        descripcion = doc.exif.get("descripcion", "")
        claves: dict[str, str | None] = {
            CLAVE_MOTOR: self._serie_tras(descripcion, "motor"),
            CLAVE_VARIADOR: self._serie_tras(descripcion, "variador"),
        }
        pagina = doc.paginas[0].numero if doc.paginas else 0
        evidencias: list[Evidencia] = []
        for variable, serie in ((CLAVE_MOTOR, claves[CLAVE_MOTOR]), (CLAVE_VARIADOR, claves[CLAVE_VARIADOR])):
            if serie and admite(variable, tipo_doc, spec):
                evidencias.append(
                    self._evidencia(
                        variable=variable,
                        valor=serie,
                        doc=doc,
                        tipo_doc=tipo_doc,
                        pagina=pagina,
                        texto_literal=descripcion,
                        metodo=METODO_EXIF,
                        tipo_evidencia=DEMOSTRADO,
                        claves=claves,
                    )
                )
        if doc.subtipo in (SUBTIPO_FOTO_ANTES, SUBTIPO_FOTO_DESPUES):
            variable = "foto.antes" if doc.subtipo == SUBTIPO_FOTO_ANTES else "foto.despues"
            evidencias.append(
                self._evidencia(
                    variable=variable,
                    valor=doc.nombre,
                    doc=doc,
                    tipo_doc=tipo_doc,
                    pagina=pagina,
                    texto_literal=descripcion,
                    metodo=METODO_EXIF,
                    tipo_evidencia=DEMOSTRADO,
                    claves=claves,
                )
            )
        for pag in doc.paginas:
            evidencias.extend(self._de_ocr(doc, pag, CAMPOS.get(tipo_doc, ()), spec, claves))
        return evidencias

    @staticmethod
    def _serie_tras(descripcion: str, palabra: str) -> str | None:
        encontrado = re.search(rf"(?i){palabra}\s+({SERIE})", descripcion or "")
        return encontrado.group(1).upper() if encontrado else None

    # -- hechos documentales -------------------------------------------------

    def _hechos(
        self, doc: Documento, pagina: Pagina, spec: object, claves: Mapping[str, str | None]
    ) -> list[Evidencia]:
        tipo_doc = doc.tipo or ""
        if tipo_doc == "factura":
            return self._hechos_factura(doc, pagina, spec, claves)
        if tipo_doc == "ficha_cumplimentada":
            return self._hechos_ficha(doc, pagina, claves)
        if tipo_doc == "convenio_cae":
            return self._hechos_convenio(doc, pagina, spec, claves)
        if tipo_doc == TIPO_INFORME_FOTOGRAFICO:
            return self._hechos_fotos(doc, pagina, claves)
        return []

    def _hechos_factura(
        self, doc: Documento, pagina: Pagina, spec: object, claves: Mapping[str, str | None]
    ) -> list[Evidencia]:
        evidencias: list[Evidencia] = []
        texto = pagina.texto or ""
        normalizado = normalizar(texto)
        lineas_factura: list[dict[str, str]] = []
        for tabla in pagina.tablas:
            if not es_tabla_de_lineas(tabla):
                continue
            cabecera = [normalizar(c or "") for c in tabla[0]]
            columna = next((i for i, c in enumerate(cabecera) if "descripcion" in c), None)
            if columna is None:
                continue
            for fila in tabla[1:]:
                if columna >= len(fila):
                    continue
                descripcion = " ".join((fila[columna] or "").split())
                if not descripcion:
                    continue
                lineas_factura.append(
                    {"descripcion": descripcion, "categoria": categoria_de_linea(descripcion)}
                )
                serie_variador = re.search(PATRON_SERIE_EN_TEXTO, descripcion)
                serie_motor = re.search(PATRON_MOTOR_EN_TEXTO, descripcion)
                claves_linea = {
                    CLAVE_MOTOR: serie_motor.group(1).upper() if serie_motor else claves.get(CLAVE_MOTOR),
                    CLAVE_VARIADOR: serie_variador.group(1).upper()
                    if serie_variador
                    else claves.get(CLAVE_VARIADOR),
                }
                if claves_linea[CLAVE_VARIADOR] and admite(CLAVE_VARIADOR, "factura", spec):
                    evidencias.append(
                        self._evidencia(
                            variable=CLAVE_VARIADOR,
                            valor=claves_linea[CLAVE_VARIADOR],
                            doc=doc,
                            tipo_doc="factura",
                            pagina=pagina.numero,
                            texto_literal=descripcion,
                            metodo=METODO_TABLA,
                            tipo_evidencia=DEMOSTRADO,
                            claves=claves_linea,
                        )
                    )
        if lineas_factura:
            evidencias.append(
                self._evidencia(
                    variable="factura.lineas",
                    valor=json.dumps(lineas_factura, ensure_ascii=False),
                    doc=doc,
                    tipo_doc="factura",
                    pagina=pagina.numero,
                    texto_literal="; ".join(linea["descripcion"] for linea in lineas_factura),
                    metodo=METODO_TABLA,
                    tipo_evidencia=DEMOSTRADO,
                    claves={},
                )
            )
        minimos = (
            "numero de factura",
            "fecha de factura",
            "nif del emisor",
            "nif del receptor",
            "base imponible",
            "iva",
            "total factura",
        )
        faltan = [m for m in minimos if m not in normalizado]
        if pagina.tablas or texto:
            evidencias.append(
                self._evidencia(
                    variable="factura.campos_minimos_presentes",
                    valor="true" if not faltan else "false",
                    doc=doc,
                    tipo_doc="factura",
                    pagina=pagina.numero,
                    texto_literal=(
                        "campos minimos AEAT hallados: " + ", ".join(m for m in minimos if m not in faltan)
                    ),
                    metodo=METODO_TABLA,
                    tipo_evidencia=DEMOSTRADO,
                    claves={},
                )
            )
        if "motor existente" in normalizado or "motor(es) existente" in normalizado:
            evidencias.append(
                self._evidencia(
                    variable="factura.menciona_motor_existente",
                    valor="true",
                    doc=doc,
                    tipo_doc="factura",
                    pagina=pagina.numero,
                    texto_literal=_linea_con(texto, "motor existente") or "motor existente",
                    metodo=METODO_REGEX,
                    tipo_evidencia=DEMOSTRADO,
                    claves={},
                )
            )
        return evidencias

    def _hechos_ficha(
        self, doc: Documento, pagina: Pagina, claves: Mapping[str, str | None]
    ) -> list[Evidencia]:
        normalizado = normalizar(pagina.texto or "")
        if "firmado electronicamente por" not in normalizado:
            return []
        return [
            self._evidencia(
                variable="ficha_cumplimentada.firmada",
                valor="true",
                doc=doc,
                tipo_doc="ficha_cumplimentada",
                pagina=pagina.numero,
                texto_literal=_linea_con(pagina.texto or "", "Firmado electr") or "Firmado electronicamente",
                metodo=METODO_REGEX,
                tipo_evidencia=DEMOSTRADO,
                claves={},
            )
        ]

    def _hechos_convenio(
        self, doc: Documento, pagina: Pagina, spec: object, claves: Mapping[str, str | None]
    ) -> list[Evidencia]:
        requisitos = _requisitos_de(spec, "convenio_cae")
        if not requisitos:
            return []
        normalizado = normalizar(pagina.texto or "")
        hallados = [r for r in requisitos if _requisito_presente(r, normalizado)]
        if not hallados:
            return []
        return [
            self._evidencia(
                variable="convenio.requisitos_presentes",
                valor=json.dumps(hallados, ensure_ascii=False),
                doc=doc,
                tipo_doc="convenio_cae",
                pagina=pagina.numero,
                texto_literal="; ".join(hallados),
                metodo=METODO_REGEX,
                tipo_evidencia=DEMOSTRADO,
                claves={},
            )
        ]

    def _hechos_fotos(
        self, doc: Documento, pagina: Pagina, claves: Mapping[str, str | None]
    ) -> list[Evidencia]:
        evidencias: list[Evidencia] = []
        for encontrado in re.finditer(PATRON_FOTO, pagina.texto or ""):
            momento = normalizar(encontrado.group(2))
            serie = encontrado.group(3).upper()
            variable = "foto.antes" if momento.startswith("antes") else "foto.despues"
            evidencias.append(
                self._evidencia(
                    variable=variable,
                    valor=encontrado.group(0).strip(),
                    doc=doc,
                    tipo_doc=TIPO_INFORME_FOTOGRAFICO,
                    pagina=pagina.numero,
                    texto_literal=encontrado.group(0).strip(),
                    metodo=METODO_REGEX,
                    tipo_evidencia=DEMOSTRADO,
                    claves={CLAVE_MOTOR: serie, CLAVE_VARIADOR: claves.get(CLAVE_VARIADOR)},
                )
            )
        return evidencias

    # -- registro xlsx -------------------------------------------------------

    def _extraer_registro(self, doc: Documento, spec: object) -> list[Evidencia]:
        registro = leer_registro(doc, spec)
        return evidencias_de_registro(registro, doc, spec, self)


def evidencias_de_registro(
    registro: RegistroFuncionamiento, doc: Documento, spec: object, extractor: ExtractorReglas
) -> list[Evidencia]:
    """Evidencias derivadas del registro (INT-03, INT-04, INT-05): pagina 0, metodo `xlsx`, `derivado`."""
    if not registro.legible:
        return []
    claves = {CLAVE_MOTOR: registro.num_serie_motor, CLAVE_VARIADOR: registro.num_serie_variador}
    tipo_doc = doc.tipo or ""
    evidencias: list[Evidencia] = []

    def anadir(
        variable: str, valor: str, literal: str, interpretacion: str | None = None, unidad: str | None = None
    ) -> None:
        evidencias.append(
            extractor._evidencia(
                variable=variable,
                valor=valor,
                doc=doc,
                tipo_doc=tipo_doc,
                pagina=0,
                texto_literal=literal,
                metodo=METODO_XLSX,
                tipo_evidencia=DERIVADO,
                claves=claves,
                unidad=unidad,
                interpretacion=interpretacion,
            )
        )

    lineas = registro.datos_canonicos.splitlines()
    cita = " … ".join(filter(None, (lineas[0] if lineas else "", lineas[-1] if len(lineas) > 1 else "")))
    for variable, valor in registro.derivados.items():
        anadir(
            variable,
            _texto_decimal(valor),
            f"{registro.n_marcha} de {registro.n_filas} filas en MARCHA; {cita}",
            registro.interpretaciones.get(variable),
            registro.unidades.get(variable),
        )
    if registro.dias is not None:
        anadir(
            f"{RAIZ_REGISTRO}.dias", _texto_decimal(registro.dias), f"periodo del registro: {cita}", None, "d"
        )
    if registro.inicio is not None:
        anadir(f"{RAIZ_REGISTRO}.inicio", registro.inicio.isoformat(), lineas[0] if lineas else "")
    if registro.fin is not None:
        anadir(f"{RAIZ_REGISTRO}.fin", registro.fin.isoformat(), lineas[-1] if lineas else "")
    if registro.datos_canonicos:
        anadir(
            f"{RAIZ_REGISTRO}.datos_canonicos",
            registro.datos_canonicos,
            f"{len(lineas)} lineas en formato canonico: {cita}",
            "INT-05",
        )
    return evidencias


def _texto_decimal(valor: Decimal) -> str:
    texto = format(valor.normalize(), "f")
    return texto


# ---------------------------------------------------------------------------
# Utilidades de hechos
# ---------------------------------------------------------------------------


def categoria_de_linea(descripcion: str) -> str:
    """Categoria de una linea de factura: **que se factura**, no que palabra aparece antes.

    Tres preguntas en orden (el orden es el criterio; ver el lexico y `docs/03` §8):

    1. **¿Se adquiere un equipo?** Un sustantivo de equipo con senal de compra (`suministro`, `sustitucion`,
       ...) en su mismo segmento, o con `nuevo`/`nueva` pegado, y **sin** marca de `existente`, da la
       categoria de ese equipo aunque la linea empiece por "Montaje" ("Montaje de bomba centrifuga nueva
       BCN-250" es `bomba`). Lo que va tras "no incluye" no cuenta: es una clausula que niega.
    2. **¿Es solo trabajo?** Una senal de mano de obra en la cabeza de la linea (hasta la primera coma o
       parentesis) da `instalacion`: "Instalacion de variador sobre motor existente" es `instalacion`, que es
       el caso de uso central del producto y **no** puede disparar `R-AMB-02`.
    3. **¿Cual es el sujeto?** El primer sustantivo de equipo de la cabeza, por **posicion** y no por
       precedencia de categoria ("Variador de frecuencia para bomba centrifuga" es `variador`), siempre que
       no venga marcado como existente. Si no hay ninguno, `otro`.
    """
    texto = normalizar(descripcion or "")
    if not texto:
        return "otro"
    util = _sin_clausulas_excluyentes(texto)
    adquiridos = _equipos_adquiridos(util)
    for categoria in ORDEN_EQUIPOS:
        if categoria in adquiridos:
            return categoria
    cabeza = re.split(SEPARADORES_SEGMENTO, util, maxsplit=1)[0]
    if re.search(PATRON_TRABAJO, cabeza):
        return "instalacion"
    return _equipo_sujeto(cabeza) or "otro"


def _sin_clausulas_excluyentes(texto: str) -> str:
    """Quita "no incluye suministro de motor ..." y demas clausulas que niegan, hasta el fin del segmento."""
    resultado = texto
    while (marca := re.search(PATRON_EXCLUSION, resultado)) is not None:
        inicio = marca.start()
        siguiente = re.search(SEPARADORES_SEGMENTO, resultado[inicio:])
        fin = inicio + siguiente.start() if siguiente else len(resultado)
        resultado = f"{resultado[:inicio]} {resultado[fin:]}"
    return resultado


def _segmentos(texto: str) -> list[tuple[int, int]]:
    """Tramos entre separadores (coma, punto y coma, parentesis): el alcance de una senal de compra."""
    tramos: list[tuple[int, int]] = []
    inicio = 0
    for separador in re.finditer(SEPARADORES_SEGMENTO, texto):
        tramos.append((inicio, separador.start()))
        inicio = separador.end()
    tramos.append((inicio, len(texto)))
    return tramos


def _ocurrencias(texto: str) -> list[tuple[int, int, str]]:
    """Sustantivos de equipo del texto, en orden de aparicion: `(inicio, fin, categoria)`."""
    encontradas: list[tuple[int, int, str]] = []
    for categoria, nombres in SENALES_EQUIPO.items():
        for nombre in nombres:
            for hallazgo in re.finditer(rf"\b{re.escape(nombre)}\b", texto):
                encontradas.append((*hallazgo.span(), categoria))
    return sorted(encontradas)


def _ventanas(texto: str, ocurrencias: Sequence[tuple[int, int, str]], indice: int) -> tuple[str, str]:
    """Lo pegado a un sustantivo, **cortado en el sustantivo vecino**.

    Sin el corte, "sustitucion de variador sobre motor existente" daria el `existente` del motor tambien al
    variador. Cada calificativo (`nuevo`, `existente`) es del equipo que tiene al lado, no del de mas alla.
    """
    inicio, fin, _ = ocurrencias[indice]
    anterior = max((f for _, f, _ in ocurrencias if f <= inicio), default=0)
    siguiente = min((i for i, _, _ in ocurrencias if i >= fin), default=len(texto))
    return texto[max(anterior, inicio - VENTANA_PRE) : inicio], texto[fin : min(siguiente, fin + VENTANA_POS)]


def _hay(patron: str, *ventanas: str) -> bool:
    return any(re.search(patron, ventana) for ventana in ventanas)


def _equipos_adquiridos(texto: str) -> set[str]:
    """Categorias de equipo que esta linea **compra** (EXC-01/EXC-02: tambien la sustitucion parcial)."""
    tramos = _segmentos(texto)
    ocurrencias = _ocurrencias(texto)
    adquiridos: set[str] = set()
    for indice, (inicio, fin, categoria) in enumerate(ocurrencias):
        if categoria in adquiridos:
            continue
        antes, despues = _ventanas(texto, ocurrencias, indice)
        if _hay(MARCA_EXISTENTE, antes, despues):
            # "motor existente": la linea nombra el equipo, no lo compra. Salvo que lo sustituya (EXC-02).
            if not _sustituido_por_uno_nuevo(texto, tramos, inicio, fin):
                continue
        if _hay(MARCA_NUEVO, antes, despues):
            adquiridos.add(categoria)
            continue
        gobierna = next((texto[i:inicio] for i, f in tramos if i <= inicio <= f), "")
        if re.search(PATRON_ADQUISICION, gobierna):
            adquiridos.add(categoria)
    return adquiridos


def _sustituido_por_uno_nuevo(texto: str, tramos: Sequence[tuple[int, int]], inicio: int, fin: int) -> bool:
    """Cuando "sustitucion de la soplante existente por una de nueva generacion" **si** es una compra.

    EXC-02 excluye la sustitucion "total o parcial" del equipo **existente**: ahi la palabra `existente` no
    dice que no se compre nada, dice cual se quita. Se exige que el mismo segmento traiga un `nuevo` detras,
    para no tratar como compra "Sustitucion de fusibles del motor existente".
    """
    desde, hasta = next(((i, f) for i, f in tramos if i <= inicio <= f), (0, len(texto)))
    if not re.search(PATRON_SUSTITUCION, texto[desde:inicio]):
        return False
    return bool(re.search(MARCA_NUEVO, texto[fin:hasta]))


def _equipo_sujeto(cabeza: str) -> str | None:
    """Categoria del **primer** sustantivo de equipo de la cabeza que no venga marcado como existente."""
    ocurrencias = _ocurrencias(cabeza)
    for indice, (_inicio, _fin, categoria) in enumerate(ocurrencias):
        if not _hay(MARCA_EXISTENTE, *_ventanas(cabeza, ocurrencias, indice)):
            return categoria
    return None


def _requisitos_de(spec: object, tipo_doc: str) -> list[str]:
    for declaracion in getattr(spec, "documentacion", None) or []:
        if not hasattr(declaracion, "get") or declaracion.get("tipo") != tipo_doc:
            continue
        requisitos = declaracion.get("requisitos")
        if isinstance(requisitos, Sequence) and not isinstance(requisitos, str):
            return [str(r) for r in requisitos]
    return []


def _requisito_presente(requisito: str, texto_normalizado: str) -> bool:
    objetivo = normalizar(requisito)
    if objetivo in texto_normalizado:
        return True
    palabras = [p for p in re.findall(r"[\wÀ-ſ]+", objetivo) if len(p) >= 4]
    return bool(palabras) and all(p in texto_normalizado for p in palabras)


def _linea_con(texto: str, fragmento: str) -> str | None:
    objetivo = normalizar(fragmento)
    for linea in (texto or "").splitlines():
        if objetivo in normalizar(linea):
            return linea.strip()
    return None


# ---------------------------------------------------------------------------
# Extraccion de la actuacion completa
# ---------------------------------------------------------------------------


def extraer_todos(
    documentos: Sequence[Documento], spec: object, extractor: Extractor | None = None
) -> list[Evidencia]:
    """Todas las evidencias de una actuacion: por documento y los recuentos que cruzan documentos.

    `n_motores` de un tipo que no trae campo explicito (registro de funcionamiento, fotos sueltas) es el
    numero de numeros de serie de motor distintos observados en documentos de ese tipo.
    """
    extractor = extractor or ExtractorReglas()
    evidencias: list[Evidencia] = []
    for doc in documentos:
        evidencias.extend(extractor.extraer(doc, spec))
    evidencias.extend(_recuentos_de_motores(documentos, evidencias, extractor))
    avisar_vinculo_por_huella(documentos, evidencias)
    return evidencias


def avisar_vinculo_por_huella(documentos: Sequence[Documento], evidencias: Sequence[Evidencia]) -> None:
    """Deja aviso cuando un documento se reconoce por su huella declarada y **no** por su nombre (caso G).

    Quien vincula es el consolidador (`evidencias.py`); aqui solo se hace visible que el nombre del fichero
    no es el que el certificado declara, para que el informe lo diga. Un fichero renombrado no cambia nada.
    """
    declarados: list[tuple[str, str | None]] = []
    for ev in evidencias:
        if ev.variable.endswith(".hash_declarado"):
            raiz = ev.variable.rsplit(".", 1)[0]
            nombre = next(
                (
                    otra.valor
                    for otra in evidencias
                    if otra.variable == f"{raiz}.nombre_declarado"
                    and otra.num_serie_motor == ev.num_serie_motor
                ),
                None,
            )
            declarados.append((ev.valor.lower(), nombre))
    if not declarados:
        return
    huellas_por_doc: dict[str, set[str]] = {}
    for doc in documentos:
        huellas = {doc.sha256.lower(), doc.doc_id.lower()}
        for ev in evidencias:
            if ev.doc_id == doc.doc_id:
                huellas.add(hashlib.sha256(ev.valor.encode("utf-8")).hexdigest())
        huellas_por_doc[doc.doc_id] = huellas
    for doc in documentos:
        for huella, nombre_declarado in declarados:
            if huella not in huellas_por_doc.get(doc.doc_id, set()):
                continue
            if nombre_declarado and normalizar(nombre_declarado) != normalizar(doc.nombre):
                doc.avisar(
                    f"registro_vinculado_por_hash: '{doc.nombre}' se identifica por su huella "
                    f"{huella[:12]}…; el documento que la declara la llama '{nombre_declarado}'"
                )


def _recuentos_de_motores(
    documentos: Sequence[Documento], evidencias: Sequence[Evidencia], extractor: Extractor
) -> list[Evidencia]:
    explicitos = {ev.tipo_doc for ev in evidencias if ev.variable == "n_motores"}
    series_por_tipo: dict[str, set[str]] = {}
    for ev in evidencias:
        if ev.num_serie_motor:
            series_por_tipo.setdefault(ev.tipo_doc, set()).add(ev.num_serie_motor)
    nuevas: list[Evidencia] = []
    for tipo_doc in FUENTES_N_MOTORES:
        if tipo_doc in explicitos:
            continue
        series = series_por_tipo.get(tipo_doc)
        if not series:
            continue
        for doc in documentos:
            if doc.tipo != tipo_doc or doc.es_combinado:
                continue
            pagina = doc.paginas[0].numero if doc.paginas else 0
            nuevas.append(
                Evidencia(
                    variable="n_motores",
                    valor=str(len(series)),
                    doc_id=doc.doc_id,
                    tipo_doc=tipo_doc,
                    pagina=pagina,
                    texto_literal=(
                        f"{len(series)} motor(es) con documentacion de tipo {tipo_doc}: "
                        + ", ".join(sorted(series))
                    ),
                    metodo=METODO_XLSX if doc.formato == "xlsx" else METODO_EXIF,
                    confianza=CONFIANZA_NATIVA,
                    extractor_version=getattr(extractor, "version", VERSION_EXTRACTOR),
                    tipo_evidencia=DEMOSTRADO,
                )
            )
    return nuevas
