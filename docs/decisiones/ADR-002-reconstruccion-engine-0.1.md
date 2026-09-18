# ADR-002 — Reconstrucción del Engine 0.1 (Fase 0)

**Estado**: EN CURSO
**Fecha**: 2026-09-18
**Decide**: Claude (técnica, §3–§5) · Billy (§6: ground truth de E y F, INT-xx propuestos)
**Ámbito**: `engine/`, `generator/`, `expedientes/`, `tests/`, `data/`, `evaluar_casos.py`, `pyproject.toml`, `README.md`, marcas de `docs/03`/`docs/04`

## Contexto

El repositorio arranca sin código (`docs/06` §0). El Engine 0.1 (Sprints 1 y 2) se construyó en otro entorno; aquí se reconstruye
con la estructura de `docs/01`, las decisiones de diseño de `docs/03` §14 y `docs/04` §5–§6, y los criterios de aceptación de
`docs/05`. Este ADR es el plan de sesión y el registro de las decisiones técnicas que la reconstrucción obliga a tomar. Las
decisiones que son de Billy quedan en §6 como `PROPUESTA`.

Entorno de esta sesión: Python 3.11.15 (Linux, contenedor), dependencias de `pyproject.toml` instaladas, `tesseract 5.3.4`
con `spa` disponible (la suite OCR se ejecuta aquí; en Windows sin tesseract los tests `@pytest.mark.ocr` se saltan).

## 1. Plan de la sesión

Orden de `docs/06` §1 con las paralelizaciones que permite `.claude/commands/bootstrap.md` (sin dependencia y sin ficheros
compartidos). Cada paso es un commit `F0.n: …`. Tras cada oleada, `qa-evaluacion` revisa; no se avanza sin `APTO` o
`APTO CON RESERVAS` documentadas.

| Oleada | Paso | Agente | Ficheros | Hecho cuando (copiado de `docs/06` §1) |
|---|---|---|---|---|
| 0 | F0.0 | orquestador | esqueleto de `docs/01` §1, `pyproject.toml`, `.gitignore`, `README.md`, `tests/conftest.py` | `python -m pytest -q` arranca (0 tests) y `ruff check .` pasa; `docs/01` coincide con el árbol real |
| 1 | F0.1 | motor-nucleo | `engine/expresiones.py`, `tests/test_expresiones.py` | Evalúa todas las construcciones de las 26 reglas y la fórmula (`docs/04` §6); función desconocida lanza error de carga; no hay `eval` en el módulo (test lo comprueba leyendo el fuente); operadores lógicos trivaluados con `NO_EVALUABLE` |
| 1 | F0.2 | spec-fichas | `data/README.md`, `data/reg_2019_1781_cuadro6.csv`, `engine/tablas.py`, `tests/test_tablas.py` | 110 kW → 5,55 kW; fila inexistente devuelve `INT-02` en lugar de un valor; toda fila lleva marca `verificado` según `data/README.md` |
| 2 | F0.3 | motor-nucleo | `engine/calculo.py`, `tests/test_calculo.py` | Caso A en memoria da exactamente `305829.6` con `Decimal`; `AETOTAL_cae = 305829`; `h = min(h_antes, h_despues)`; FIS-01/FIS-02 retiran el resultado; traza con cada paso; `p` solo desde tabla |
| 2 | F0.4 | spec-fichas | `engine/spec_registry.py`, `tests/test_spec_registry.py` | Carga `spec/IND240_v1.1.yaml` y rechaza `spec/propuestas/`; valida campos y valores por defecto de `docs/04` §3; comprueba la garantía NO_EVALUABLE → SUBSANABLE; calcula `hash_reglas` |
| 3 | F0.5 | generador-casos | `generator/**`, `expedientes/EXP001-*/`, `expedientes/_resultados_esperados/`, `tests/test_generator.py` | 7 carpetas con los documentos de `docs/05` §4, marca sintética; ground truth del mismo modelo; E y F con parámetros fijados y AETOTAL recalculado con `engine/calculo.py` y registrado aquí (§4); G con PDF combinado, escaneo girado, fotos y xlsx renombrado |
| 3 | F0.8 | motor-nucleo | `engine/evidencias.py`, `tests/test_evidencias.py` | Tres capas por dato; normalización `exacto`/`normalizado`; tolerancias de la spec; conflicto entre fuentes fiables → `valor_consumido = null` y ambas evidencias; OCR discrepante no bloquea; declarado ≠ demostrado marcado |
| 4 | F0.6 + F0.7 | ingesta-extraccion | `engine/ingesta.py`, `engine/clasificacion.py`, `engine/extraccion.py`, `engine/registro_xlsx.py`, `tests/test_ingesta.py` | SHA-256 de todo antes de transformar; separación de PDF combinados conservando hash original y de partes; OCR con tesseract si está (tests marcados); clasificación léxica con confianza; vinculación por hash y nº de serie · Tablas antes que texto; evidencia con documento, página, texto literal, método, confianza; OCR 0,75; el xlsx produce N2, P_prom, h_despues según la spec (INT-03, INT-04) |
| 4 | F0.9 | motor-nucleo | `engine/reglas.py`, `tests/test_reglas.py` | 26 reglas desde su `logica`; fases de `docs/04` §5; tres resultados; veredicto por prioridad; por regla un test que cumple y uno que falla; caso B `SUBSANABLE` y no `BLOQUEADO` |
| 5 | F0.10 | motor-nucleo | `engine/motor.py`, `engine/informe.py`, `engine/cli.py` | `python -m engine.cli expedientes/EXP001-A_completo --md --json` produce informe con veredicto, ahorro, evidencias, reglas, interpretaciones y carencias; orden ámbito y consistencia → cálculo → resto |
| 6 | F0.11 | qa-evaluacion | `evaluar_casos.py`, `tests/test_engine_e2e.py`, `tests/test_metamorficas.py`, `tests/test_modo_degradado.py` | 7/7 veredictos; A, E, F, G con el AETOTAL del ground truth; las 6 metamórficas de `docs/05` §6; con `agentes/` y `salida/` ausentes el motor funciona |
| 6 | revisión | revisor-normativo | solo hallazgos | `engine/reglas.py`, `engine/calculo.py`, `data/` contrastados; interpretaciones silenciosas → `INT-xx` propuestos |
| 7 | F0.12 | orquestador | `docs/03`, `docs/04`, `docs/06`, `docs/01`, este ADR, `README.md` | Marcas `F0` → `EXISTE`/`PARCIAL`; ADR con E/F, ground truth, nº de tests y desviaciones; README Windows y Linux |

Cambio de orden respecto a `docs/06`: **F0.8 (Evidence Store) se construye antes que F0.6/F0.7** porque define el tipo
`Evidencia` que la extracción produce (§2.3). El número de paso se conserva en el commit.

## 2. Contratos entre módulos (decisión de diseño; obligatoria para todos los agentes)

Sin estos contratos dos agentes en paralelo inventarían dos modelos de datos. Los nombres son definitivos para la Fase 0; un
cambio pasa por este ADR. Todo en español sin tildes; `Decimal` para magnitudes; fechas como `datetime.date`.

### 2.1 Tipos base (`engine/evidencias.py`, dueño motor-nucleo)

```python
@dataclass(frozen=True)
class Evidencia:
    variable: str            # nombre de la spec ("PM") o hecho documental con punto ("factura.campos_minimos_presentes")
    valor: str               # valor crudo tal y como se leyó, normalizado a texto ("110", "1188", "true", "2026-03-02")
    doc_id: str              # sha256 del documento (o de la parte, si viene de un PDF separado)
    tipo_doc: str            # tipo de documento según la spec (ficha_tecnica_motor, certificado_instalador, …)
    pagina: int              # 1-based; 0 si no aplica (xlsx)
    texto_literal: str       # fragmento literal del documento del que sale el valor
    metodo: str              # "tabla" | "regex" | "ocr" | "xlsx" | "exif" | "llm"
    confianza: Decimal       # 1 para nativo; Decimal("0.75") para OCR
    extractor_version: str   # p. ej. "reglas-0.1.0"
    tipo_evidencia: str      # "demostrado" | "declarado" | "derivado"
    num_serie_motor: str | None = None      # claves de unión: las que aparezcan junto al valor
    num_serie_variador: str | None = None
    unidad: str | None = None               # "kW", "rpm", "h", "kWh" … si el documento la expresa
    interpretacion: str | None = None       # INT-xx si el valor se derivó con un criterio interpretativo
```

```python
@dataclass
class DatoConsolidado:                      # tres capas (docs/03 §5.3)
    variable: str
    evidencias: list[Evidencia]             # capa 1
    valor_normalizado: str | None           # capa 2 (texto canónico; Decimal como cadena)
    tipo_evidencia: str | None              # demostrado | declarado | derivado (el mejor disponible)
    fuente_primaria: str | None
    interpretacion: str | None
    valores_por_fuente: dict[str, str]      # tipo_doc → valor normalizado (para unique(...))
    valor_consumido: Decimal | date | str | bool | None   # capa 3; None si conflicto o ausente
    conflicto: bool
    posibles_errores_ocr: list[Evidencia]   # evidencias OCR que discrepan de una fuente fiable (no bloquean)
```

```python
@dataclass
class ActuacionConsolidada:
    documentos: list[Documento]                        # de ingesta (§2.2)
    unidades: dict[str, dict[str, DatoConsolidado]]    # clave: num_serie_motor → variable → dato (nivel motor)
    variables: dict[str, DatoConsolidado]              # nivel actuación (titular_nif, fechas, hechos documentales)
    conflictos: list[DatoConsolidado]
    avisos: list[str]                                  # avisos de ingesta/clasificación/consolidación (caso G)
```

Funciones: `consolidar(evidencias, documentos, spec) -> ActuacionConsolidada`.

### 2.2 Ingesta y clasificación (`engine/ingesta.py`, `engine/clasificacion.py`, dueño ingesta-extraccion)

```python
@dataclass
class Pagina:
    numero: int; texto: str; tablas: list[list[list[str]]]; metodo: str   # "pdf_nativo" | "ocr"

@dataclass
class Documento:
    doc_id: str              # = sha256 del fichero original, o de la parte (§F0.6) si procede de un PDF combinado
    sha256: str              # hash del contenido tal cual entró (antes de transformar)
    ruta: Path; nombre: str; bytes: int; formato: str         # "pdf" | "xlsx" | "imagen" | "otro"
    paginas: list[Pagina]
    exif: dict[str, str]
    origen: str | None       # None si es original; sha256 del PDF combinado del que se separó
    rango_paginas: tuple[int, int] | None
    tipo: str | None         # lo rellena clasificacion
    confianza_tipo: Decimal | None
    subtipo: str | None      # p. ej. "foto_antes" | "foto_despues" | "placa" para imágenes sueltas (EXIF)
```

`ingestar(carpeta: Path, ocr: bool = True) -> list[Documento]` · `clasificar(doc, spec) -> Documento`. El SHA-256 se calcula
sobre los bytes originales **antes** de abrir el fichero. `doc_id` de una parte separada = `sha256(sha256_original + ":" +
"p{ini}-{fin}")`, y la parte conserva `origen` y `rango_paginas`. Un fichero no clasificable produce un aviso y no una
excepción. Sin `tesseract` en el PATH, `ocr` se desactiva y las páginas sin texto quedan vacías con aviso.

### 2.3 Extracción (`engine/extraccion.py`, `engine/registro_xlsx.py`, dueño ingesta-extraccion)

```python
class Extractor(Protocol):
    version: str
    def extraer(self, doc: Documento, spec: Spec) -> list[Evidencia]: ...
class ExtractorReglas: ...                # tablas del PDF antes que texto; regex de respaldo
def leer_registro(doc: Documento) -> RegistroFuncionamiento   # N2, P_prom, h_despues, dias, inicio, fin, hash_canonico
```

**Variables y hechos que la extracción debe producir** (nombres de `variable` en `Evidencia`; los del bloque de spec son
exactamente los de `spec/IND240_v1.1.yaml`):

| Nivel | `variable` | Fuentes (spec) | `tipo_evidencia` |
|---|---|---|---|
| actuación | `titular_nif`, `titular_razon_social` | ficha_cumplimentada, factura, declaracion_responsable, convenio_cae | demostrado |
| actuación | `fecha_inicio_actuacion` | ficha_cumplimentada, factura (fecha de factura / pedido) | demostrado |
| actuación | `fecha_fin_actuacion` | ficha_cumplimentada, certificado_instalador | demostrado |
| actuación | `n_motores` | factura, certificado_instalador, ficha_cumplimentada, informe_fotografico, registro_funcionamiento | demostrado |
| actuación | `factura.lineas` | factura; valor: JSON `[{"descripcion": …, "categoria": …}]`, categoría ∈ {variador, instalacion, motor, bomba, ventilador, compresor, equipo_completo, otro} | demostrado |
| actuación | `factura.campos_minimos_presentes` | factura; `"true"`/`"false"` | demostrado |
| actuación | `ficha_cumplimentada.firmada` | ficha_cumplimentada | demostrado |
| actuación | `convenio.requisitos_presentes` | convenio_cae; valor: JSON con los textos de `documentacion[PRC-01].requisitos` hallados | demostrado |
| actuación | `convenio.ahorro_kwh`, `convenio.fecha_firma` | convenio_cae | declarado / demostrado |
| motor | `num_serie_motor`, `num_serie_variador` | según `fuentes` de la spec | demostrado |
| motor | `tipo_equipo_accionado` (enum de la spec), `regimen_previo` | ficha_tecnica_equipo_accionado, certificado_instalador / registro_horas_previo, certificado_instalador | demostrado |
| motor | `PM`, `N1` | ficha_tecnica_motor, placa_caracteristicas_foto (OCR), certificado_instalador, ficha_cumplimentada | demostrado |
| motor | `N2`, `P_prom` | certificado_instalador, ficha_cumplimentada → **declarado**; registro_funcionamiento → **derivado** (INT-03) | declarado / derivado |
| motor | `h_antes` | registro_horas_previo | demostrado |
| motor | `h_despues` | registro_funcionamiento → derivado (INT-04) | derivado |
| motor | `foto.antes`, `foto.despues` | informe_fotografico (pies de foto nativos) o imágenes sueltas (EXIF); una evidencia por foto, `valor` = identificador de la foto | demostrado |
| motor | `registro.dias`, `registro.inicio`, `registro.fin`, `registro.datos_canonicos` | registro_funcionamiento (xlsx) | derivado |
| motor | `registro.hash_declarado` | certificado_instalador (huella SHA-256 del registro declarada) | declarado |

`solicitud.fecha` **no** sale de ningún documento (no existe solicitud en prevalidación): la fija `engine/motor.py` como fecha de
evaluación y se marca `declarado` con interpretación propuesta `INT-10` (§6).

Los números se leen en formato español (`1.485 rpm`, `6.000 h`, `3,90 kW`) y se normalizan a texto canónico (`"1485"`,
`"6000"`, `"3.90"`). La ficha técnica del variador declara pérdidas (`3,90 kW`): la extracción puede registrarlo como
`perdidas_declaradas_variador` (informativo); **nunca** como `perdidas_ref_kw` ni `p`.

### 2.4 Contexto de evaluación (`engine/reglas.py`, dueño motor-nucleo)

El Rules Engine construye, a partir de `ActuacionConsolidada`, spec, tablas y el resultado de cálculo, el espacio de nombres
que resuelve cada identificador de `logica`. Nombres que deben resolverse (todos los que usan las 26 reglas):

`tipo_equipo_accionado`, `ambito.tipos_equipo_incluidos`, `factura.linea` (colección con `categoria`), `regimen_previo`,
`doc` (colección de `documentacion` con `obligatorio`, `tipo`), `presente(doc)`, `motor` (colección de unidades para
`for each`), `foto.antes`, `foto.despues`, `factura.campos_minimos_presentes`, `requisito` / `convenio_cae`,
`ficha_cumplimentada.firmada`, `registro.dias`, `registro.inicio`, `registro.hash_declarado`, `registro.datos_canonicos`,
`fecha_fin_actuacion`, `fecha_inicio_actuacion`, `N2.evidencia`, `N2.declarado`, `N2.derivado`, `PM.valores_por_fuente`,
`N1.valores_por_fuente`, `num_serie_variador`, `num_serie_motor`, `titular_nif`, `n_motores_por_fuente`,
`convenio.ahorro_kwh`, `AETOTAL_cae`, `convenio.fecha_firma`, `solicitud.fecha`, `N2`, `N1`, `PM`, `REG1781_CUADRO6.kw_motor`,
`FIS-01`, `FIS-02`, `p.fuente`, `tabla:REG1781_CUADRO6`. Un identificador ausente resuelve a `NO_EVALUABLE`, nunca a excepción.

Las reglas de nivel motor (`R-CON-01..04`, `R-CAL-*`, `R-EVD-*`, `R-DOC-02`, `R-AMB-01/03`) se evalúan una vez por unidad y la
regla `CUMPLE` solo si cumple en todas; `FALLA` si falla en alguna; si no, `NO_EVALUABLE`.

### 2.5 Cálculo (`engine/calculo.py`, dueño motor-nucleo)

```python
def calcular(spec, unidades: dict[str, dict[str, Decimal]], tablas) -> ResultadoCalculo
# ResultadoCalculo: por_unidad[{num_serie_motor, PM, N1, N2, h_antes, h_despues, h, perdidas_ref_kw, p, AEM, controles{FIS-01: bool, FIS-02: bool}}],
#                   total (Decimal), total_cae (int), traza[str], provisional: bool, motivo_no_calculo: str | None, interpretaciones[str]
```

### 2.6 Motor, informe y CLI

`procesar_actuacion(carpeta: Path, spec_id="IND240", fecha_evaluacion: date | None = None, ocr: bool = True) -> Actuacion`
donde `Actuacion` agrega consolidación, evaluación (`resultados[]`, `veredicto`, `hash_reglas`), cálculo, avisos e
`interpretaciones_aplicadas[]`. `informe.a_markdown(actuacion)`, `informe.a_json(actuacion)` (Decimal como cadena).

## 3. Decisiones de diseño tomadas durante la reconstrucción

Se rellena paso a paso. Formato: paso · decisión · por qué · alternativa descartada.

| Paso | Decisión | Por qué | Alternativa |
|---|---|---|---|
| plan | F0.8 antes que F0.6/F0.7 | `Evidencia` la define el Evidence Store y la consume la extracción | Definir `Evidencia` en `extraccion.py` (invertiría la dependencia) |
| plan | Contratos de §2 fijados antes de delegar | Permite oleadas paralelas sin colisión de modelos | Diseño emergente por agente (riesgo de retrabajo) |
| plan | `solicitud.fecha` = fecha de evaluación, `declarado`, INT-10 propuesto | No existe solicitud en prevalidación; dejarla ausente haría `R-TMP-02/03` `NO_EVALUABLE` en todos los casos | Fecha de firma de la ficha cumplimentada (no es la solicitud) |
| plan | Caso G sin OCR debe dar el mismo resultado que A: el escaneo girado es `ficha_tecnica_variador` (EVD-04, no obligatorio) y las fotos sueltas se clasifican por EXIF | `docs/05` §8.2 exige 7/7 en un clon sin tesseract | Escanear un documento obligatorio (rompería 7/7 sin OCR) |

## 4. Parámetros de los casos E y F y ground truth recalculado

Se rellena en F0.5 con la salida de `engine/calculo.py`.

## 5. Desviaciones respecto a `docs/05` y número de tests

Se rellena en F0.12.

## 6. Decisiones que quedan para Billy (PROPUESTA)

Se rellena al cierre. Candidatos ya identificados: INT-10 (fecha de solicitud en prevalidación).

## Verificación

`python -m pytest -q` · `python evaluar_casos.py` · `ruff check . && ruff format --check .` · `grep -rn "eval(" engine/` vacío ·
`grep -rn "from agentes\|from salida\|import agentes\|import salida" engine/` vacío · `docs/01` coincide con el árbol.
