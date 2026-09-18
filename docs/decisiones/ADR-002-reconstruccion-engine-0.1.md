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

Tipado del contexto (decisión tras la revisión QA de la oleada 1): el contexto entrega **valores tipados** (`Decimal`, `date`,
`bool`, `str` solo para enumerados e identificadores, listas para colecciones); el parser **no coerciona texto** a número ni a
fecha (solo `int` → `Decimal`), y una igualdad entre familias distintas (`"true" == true`, `"2026-01-01" == date`) es
`ErrorEvaluacionExpresion`, nunca `False` silencioso. `valores_por_fuente` (para `unique`) son cadenas canónicas: `unique`
compara cadenas. `motor` es la **lista** de unidades (no el `dict` de `ActuacionConsolidada.unidades`). Los enumerados de la
spec (`variables.*.valores`, `ambito.tipos_equipo_*`, `{demostrado, declarado, derivado}`, categorías de línea) se pasan a
`compilar(..., enumerados=…)` desde el Spec Registry: un nombre del conjunto es siempre literal simbólico y no entra en
`Expresion.identificadores`; sin el conjunto se aplica la heurística de F0.1 (lado derecho de `==`/`!=` con izquierdo `str`).

Las reglas de nivel motor (`R-CON-01..04`, `R-CAL-*`, `R-EVD-*`, `R-DOC-02`, `R-AMB-01/03`) se evalúan una vez por unidad y la
regla `CUMPLE` solo si cumple en todas; `FALLA` si falla en alguna; si no, `NO_EVALUABLE`.

### 2.5 Cálculo (`engine/calculo.py`, dueño motor-nucleo)

```python
def planificar(spec_datos: Mapping, tablas: Mapping[str, Tabla]) -> Plan      # valida el bloque calculo y las derivaciones; ErrorCalculo si la spec no es calculable
def calcular(spec_datos, unidades: Mapping[str, Mapping[str, Decimal]], tablas, *, provisional=False, fecha=None, plan=None) -> ResultadoCalculo
# Plan: derivadas (orden topológico), entradas_requeridas, precondiciones, precondiciones_delegadas (solo prosa), controles, fórmulas, criterio_redondeo,
#       interpretaciones_estaticas, interpretaciones_por_entrada
# ResultadoUnidad (genérico, sin nombres de la ficha): num_serie_motor, entradas{}, derivadas{}, salida, controles{id: bool|NO_EVALUABLE},
#       precondiciones{}, fuentes{variable: "tabla:<ID>" | "derivado"}, interpretaciones[], avisos[], motivo_no_calculo
# ResultadoCalculo: por_unidad[], total, total_cae, traza[], provisional, motivo_no_calculo, interpretaciones[], avisos[], controles_ok, precondiciones_ok,
#       precondiciones_delegadas[]
```
El Spec Registry llama a `planificar` al cargar (dependencia `spec_registry → calculo → expresiones/tablas`, hacia dentro):
una spec que el registro activa es, por construcción, calculable. `reglas.py` construye `<variable>.fuente` (p. ej. `p.fuente`)
desde `ResultadoUnidad.fuentes`; `FIS-xx` desde `controles`; `AETOTAL_cae` desde `total_cae`.

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
| F0.1 | Tokenizador propio + parser de descenso recursivo + AST de dataclasses; sin `ast`, `eval`, `exec` ni `compile` (ni `re.compile`: el fuente no contiene `compile(`) | Regla de implementación de `CLAUDE.md` §2; un test lee el fuente | `ast.parse` con visitante de lista blanca (deja `compile(` en el fuente y amplía la superficie) |
| F0.1 | Ninguna de las 26 reglas queda registrada en Python por `id`: todo el vocabulario de `docs/04` §6 se evalúa con el parser | No hizo falta el registro `id → callable` de `docs/04` §6.1; queda disponible para `reglas.py` | Registrar en código las reglas con `where`/`->`/`for each` |
| F0.1 | Guion como identificador: `MAYUSCULAS(-MAYUSCULAS)*-DIGITOS` sin espacios (`FIS-01`, `R-CON-01`) es un nombre; la resta se escribe con espacios | La spec usa `FIS-01 and FIS-02`; decidirlo por datos en evaluación haría depender el léxico del contexto | Resolver en evaluación |
| F0.1 | Literal simbólico (enumerado sin comillas): un nombre sin punto que el contexto no resuelve se compara como cadena **solo** a la derecha de `==`/`!=` y **solo si el lado izquierdo es `str`**; dentro de `[...]` los nombres son siempre simbólicos y no entran en `identificadores` | Sin la segunda condición `exists(REG1781_CUADRO6.kw_motor == PM)` con `PM` ausente daba `False` en vez de `NO_EVALUABLE`; `motor` es a la vez colección y categoría de factura | Exigir comillas en la spec (cambio de spec, v1.2) o `compilar(variables_conocidas=…)` |
| F0.1 | Ligadura en `all/exists/count`: el primer nombre (con puntos, luego su raíz) que el contexto entrega como lista/tupla/conjunto; los `dict` no ligan | Cubre `all(doc.obligatorio == true -> presente(doc))`, `all(requisito in convenio_cae)`, `exists(REG1781_CUADRO6.kw_motor == PM)` | Sintaxis explícita `all(doc in docs: …)` (cambio de spec) |
| F0.1 | Agregaciones trivaluadas: `exists` vacío → `False`; `all` vacío → `True`; `for each` sobre colección vacía → `NO_EVALUABLE`; `count` con elemento `NO_EVALUABLE` → `NO_EVALUABLE` | Sin unidad no hay nada evaluado; coherente con `ADR-002` §2.4 | `for each` vacío → `True` (ocultaría la ausencia de motores) |
| F0.1 | `ErrorEvaluacionExpresion` (no `NO_EVALUABLE`) ante contexto mal construido: `float`, tipos incomparables, `where` sobre no-colección, división por cero. La ausencia nunca lanza | Silenciarlo como `NO_EVALUABLE` escondería defectos del consolidador; `reglas.py` lo captura y marca la regla con mensaje | Todo a `NO_EVALUABLE` |
| F0.1 | Coerción mínima: `int` → `Decimal`; `str` numérica frente a `Decimal` → `Decimal`. `unique` compara igualdad tras coerción, sin normalizar ni tolerar (eso es del consolidador) | `valores_por_fuente` son texto canónico | Tolerancias en el parser (duplicaría la consolidación) |
| F0.1 | Precisión: contexto `Decimal` por defecto (28 dígitos); con él el caso A da `305829.6000000000000000000000 == Decimal("305829.6")` | Suficiente y reproducible; `calculo.py` decide si fija `localcontext` | Precisión fija en el parser |
| QA-1 | Contexto tipado y sin coerción de texto (§2.4); `enumerados` explícitos desde la spec; `True/False/None/null` rechazados como identificadores; valores no finitos → error de contexto; profundidad de anidamiento acotada → error de carga | Hallazgos H3, H5, H6, H7, H8 de la revisión QA de la oleada 1: la corrección del literal simbólico dependía del tipo en runtime y `"true" == true` fallaba en silencio | Mantener coerción heurística (esconde defectos del consolidador) |
| QA-1 | `engine/tablas.py` genérico: filas como mapa columna → valor según `meta.columnas`; `clave` y `valor` (columna que devuelve `buscar`) declarados en el `.meta.yaml`; sanidad en carga (finito, > 0, monótono en clave con aviso) | Hallazgo H1 (regla de oro 4: el esquema del cuadro 6 estaba cableado) y H4 | Una clase por tabla (un `if ficha ==` encubierto) |
| QA-1 | Parser: con `enumerados`, la posición de ligadura gana al enumerado (`for each motor:` y `motor where` son colecciones aunque `motor` sea categoría de factura; se exponen en `Expresion.colecciones_ligadas`); un nombre en `[...]` que no esté en `enumerados` es error de carga; el orden `<` entre cadenas queda fuera del vocabulario; `datetime` prohibido en todo el lenguaje; sin cortocircuito en `in`/`unique`; `PROFUNDIDAD_MAXIMA = 64` | Errata de spec detectada al cargar, no en runtime; el contrato fija `date`; determinismo del error independiente del orden | Cortocircuito (error dependiente del orden) |
| QA-1 | `obligatorio: condicional` (DOC-05B) no llega al contexto como cadena: `reglas.py` (F0.9) resuelve `obligatorio` a `bool` evaluando la `condicion` de la spec antes de construir la colección `doc`; dato ausente → `NO_EVALUABLE` | `"condicional" == true` sería error de tipos | Tratar `condicional` como `false` en silencio |
| QA-1 | Tablas: el motor no reordena (clave estrictamente creciente en el orden del CSV o error); `restricciones` en el meta (solo `positivo`; restricción o columna desconocida = error); `clave ≠ valor`; celdas por regex cerrada (sin exponentes, `_`, coma); acceso a filas por `fila["col"]` | Un desorden es transcripción defectuosa y no se corrige en silencio; el esquema es dato | `sorted()` en carga; `__getattr__` mágico |
| F0.2 | Cada tabla = `<nombre>.csv` + `<nombre>.meta.yaml`; `cargar_tabla(id)` localiza el CSV por el `id` del meta, sin leer la spec | `tablas.py` no puede depender de `spec_registry`; vigencia y fuente viven junto al dato | Mapa id → fichero en código (un `if ficha ==` encubierto) |
| F0.2 | `cargar_tablas(bloque tablas de la spec)` comprueba fichero y columnas declaradas (garantía 4 de `docs/04` §2.5); la spec declara 4 columnas y el CSV tiene 5 (`verificado`): se exige que las declaradas existan, no que sean todas | El Spec Registry delega aquí la garantía 4 | Validar el CSV desde el registro |
| F0.2 | Columna `verificado` obligatoria con valores cerrados {`si`, `pendiente`}; otro valor = error de carga | Es la traza de la revisión humana (regla de oro 9) | Booleano libre |
| F0.2 | `buscar()`: sin fila exacta y dentro de rango → interpolación lineal `Decimal` (INT-02) con aviso; **fuera de rango → sin valor** y aviso "no se extrapola" | INT-02 solo cubre interpolación; extrapolar sería resolver en silencio | Tomar la fila extrema o etiquetar como INT-02 |
| F0.2 | Aviso "tabla pendiente de verificación humana" solo si alguna **fila usada** está `pendiente` | El informe señala exactamente qué valor no está verificado; 110 kW no arrastra avisos | Aviso global |
| F0.2 | Transcripción del cuadro 6 **de memoria del agente** (proxy bloquea BOE y EUR-Lex), 39 filas, `metodo_transcripcion: memoria_agente`; fila 110 kW fijada al valor verificado por Billy (5,55) aunque la memoria del agente decía 6,11 | Regla de oro 8: el valor verificado contra el BOE gana; lo demás se declara `pendiente` | Bloquear F0.2 hasta tener el DOUE (bloquearía toda la fase) |
| F0.3 | Precisión `Decimal` fija (34) en `localcontext` dentro de `calcular`, independiente del contexto global | H9 de QA: con prec 6 el caso A daba 305830 | Depender del contexto global |
| F0.3 | Derivaciones genéricas desde `variables`: una variable `derivado` se deriva en `calculo.py` si `derivacion.fuente` es `tabla:<ID>` o si su `metodo` compila como fórmula con identificadores de la spec; orden topológico; los `metodo` en prosa (N2, P_prom, h_despues) son entradas del consolidador | Sin nombres de la ficha en código (test lo comprueba); `h`, `p` y `perdidas_ref_kw` se derivan siempre aquí | Cablear `h = min(...)` y `p = .../PM` |
| F0.3 | Toda variable derivable que llegue en `unidades` se ignora con aviso (generaliza la trampa de la ficha del variador a `p`, `perdidas_ref_kw`, `h`); `fuentes` por propagación (`p` → `tabla:REG1781_CUADRO6`) alimenta `R-CAL-04` | `p` nunca sale de otra parte que la tabla | Aceptar valores externos |
| F0.3 | Redondeo: se lee `calculo.redondeo_salida.<salida>_cae` y su `interpretacion` (INT-06); el código solo implementa "truncar" hacia cero y exige que el criterio contenga esa palabra; truncado sobre el total, no por unidad; `calculo.aritmetica` ≠ `decimal_exacta` → error de carga | El texto del criterio no es parseable; el INT se cita desde la spec | Redondear por unidad |
| F0.3 | Precondición `0 < h <= 8760` (comparación encadenada) reescrita textualmente en `calculo.py` como `(0 < h) and (h <= 8760)` hasta que el parser la soporte; la precondición en prosa ("ninguna regla bloqueante fallida") queda en `precondiciones_delegadas` y la aplica `reglas.py` | El parser de F0.1 no admite encadenado; silenciarla habría dejado `h = 0` sin bloquear | **Pendiente F0.9**: soporte nativo en `expresiones.py` y retirada de la reescritura |
| F0.3 | Control físico `FALLA` retira el resultado (`total=None`, traza conservada); `NO_EVALUABLE` (falta `P_prom`) no retira; tabla no vigente → aviso, no bloqueo (criterio de vigencia abierto, `docs/04` §2.4) | `docs/04` §7 | Bloquear por vigencia (decisión de Billy) |
| F0.4 | `fase` y `nivel` por defecto **derivados** (sin lista de ids en código) y verificados contra la tabla de `docs/04` §5.2 (26/26; 3/10/2/11) y contra §2.4 (15 reglas de unidad) | `docs/03` §14.c y regla de oro 4 | Tabla `id → fase` en código |
| F0.4 | Garantía NO_EVALUABLE → SUBSANABLE estática: raíz de cada identificador de una regla bloqueante cubierta si (a) una SUBSANABLE la referencia, (b) es variable con alguna fuente obligatoria y existe regla de presencia (`presente`), (c) es prefijo de documento obligatorio, (d) derivada de tabla o por `metodo` con entradas cubiertas, (e) salida de cálculo o control físico con entradas cubiertas, (f) constante de la spec; no cubierta → error de carga; no mapeable → aviso (`n_motores` de R-CON-07, `categoria` de R-AMB-02) | `docs/04` §2.5.3 pedía fijar la forma en este ADR | Declaración explícita en la spec (cambio de spec) |
| F0.4 | `derivacion.metodo` se compila solo si la derivación no declara `fuente`; precondición que no compila → `Spec.precondiciones_texto` + aviso (no error); `hash_reglas` sobre el bloque `reglas` crudo (JSON canónico); toda cadena `INT-nn` debe existir en `interpretaciones`; versiones: con varias y solo fecha, se aplica `spec.vigencia` si todas la declaran, si no la más alta con aviso | Criterios deterministas; no inventar el criterio de vigencia (`docs/04` §2.4) | Error de carga por precondición en prosa (bloquearía la fase) |
| QA-2 | Criterio único de planificación: `calculo.planificar` valida derivaciones (fuente documental → prosa, nunca se compila; `tabla:<ID>` → tabla declarada y `clave` obligatoria; sin fuente → fórmula que compila sobre variables de la spec, sin ciclos), bloque `calculo`, redondeo (criterio exacto) y precondiciones (función desconocida = error de carga; solo la prosa sin operadores se delega); el registro lo invoca al cargar | Hallazgos H-F03-1/2/3/5 y H-F04-1/2/3: el registro activaba specs que el cálculo rechazaba y una errata en una precondición pasaba en silencio | Dos validaciones paralelas (divergen) |
| QA-2 | Comparación encadenada (`0 < h <= 8760`) soportada de forma nativa en el parser; retirada la reescritura de `calculo.py` | La reescritura ignoraba `not`/`or`/`->` | Mantener la reescritura acotada |
| QA-2 | `p_fuente` eliminado del núcleo (regla de oro 4): `fuentes[<variable>]` es la API y `reglas.py` expone `<var>.fuente` | Vocabulario de la ficha en `engine/` | Campo específico por ficha |
| QA-2 | Errores de una unidad (entrada `None` por conflicto, división por cero) → `motivo_no_calculo` por unidad, nunca excepción global; `float` sigue siendo error de contexto | Regla de oro 6: el conflicto detiene el cálculo, no el motor | Excepción global |
| QA-2 | Límite documentado de la garantía estática NO_EVALUABLE → SUBSANABLE: es por **raíz** de variable, necesaria pero no suficiente (p. ej. `N2.declarado` ausente con certificado presente no lo recoge ninguna SUBSANABLE de v1.1); cerrarlo exige spec nueva (Billy) | Hallazgo QA-2 | Garantía por sufijo (exigiría declarar coberturas en la spec) |
| F0.8 | Conflicto por tipo de evidencia solo con `cruce_con`: dentro de cada tipo (dos derivados distintos = conflicto); declarado ↔ derivado no es conflicto, se exponen ambos y la tolerancia la aplica la regla (`R-CON-03`). Sin `cruce_con`, cualquier diferencia entre fiables es conflicto | `docs/04` §4.2; no duplicar la regla en el consolidador | Tolerancias en el consolidador |
| F0.8 | `fiable = confianza >= 1 or metodo != "ocr"`; OCR discrepante → `posibles_errores_ocr`; solo OCR → se consume con aviso; `normalizado` = mayúsculas, sin tildes, alfanumérico sin espacios; `valor_consumido` de `string` es el texto crudo de la fuente primaria | `docs/03` §8 | — |
| F0.8 | Unidades por claves `clave_union` que sean atributos de `Evidencia`; índice `num_serie_motor` (nombre del contrato); variador huérfano o ambiguo → aviso, no se asigna (el motor no adivina); vinculación por huella con `<raiz>.hash_declarado` contra `sha256` del fichero, `doc_id` o SHA-256 de un valor extraído (datos canónicos); nombre distinto → aviso informativo (G) | Regla de implementación: nunca por nombre | Defecto a "la única unidad" |
| F0.8 | Colecciones (`foto.antes`, `factura.linea`, `motor`) detectadas desde `count(x)`/`sum(x)` y `colecciones_ligadas`; tipado cerrado de hechos (bool, lista JSON sin float, fecha ISO, Decimal, texto); `n_motores` es un dato normal y `valores_por_fuente_de("n_motores")` da `n_motores_por_fuente` | Sin nombres de la ficha en `evidencias.py` (test) | Lista de colecciones en código |
| F0.8 → F0.9 | Contrato para el contexto: `motor` = lista de unidades; `X` → `valor_consumido`; `X.valores_por_fuente`; `X.declarado/derivado/demostrado` → valores tipados por tipo; `X.evidencia`; `unique(nombre)` sin sufijo (`R-CON-04/05`) se resuelve sobre `valores_por_fuente`, nunca sobre el escalar; y **un conflicto consolidado bloquea** (`motor.py`: `conflictos` no vacío → `BLOQUEADO`, `docs/04` §4.2 "quien bloquea es el conflicto") aunque la regla quede `NO_EVALUABLE` | Sin esto `unique(titular_nif)` sería siempre `True` | Solo la regla |
| F0.5 | Un solo modelo de datos (`generator/modelo_caso.py`) produce documentos y ground truth; los casos B–G son variaciones declaradas del caso base A, no juegos de documentos escritos a mano | `docs/05` §2.2: documentos y ground truth no pueden discrepar | Editar documentos generados |
| F0.5 | Generación determinista: `Canvas(invariant=1)`, semilla fija, xlsx con fechas de propiedades fijas; dos ejecuciones dan los mismos bytes y un test lo comprueba contra lo commiteado | Regenerar no puede cambiar el ground truth en silencio | Aceptar diferencias de bytes |
| F0.5 | Datos canónicos del registro (para `sha256(registro.datos_canonicos)` de `R-EVD-03`): líneas `fecha_hora ISO;estado;velocidad_rpm;potencia_kw` en el orden de la hoja, UTF-8, sin cabecera; el certificado declara esa huella | INT-05 exige una prueba de inalterabilidad reproducible | Hash del fichero xlsx (cambia al reabrirlo) |
| F0.5 | El escaneo girado del caso G es la ficha técnica del variador (EVD-04, **no** obligatorio) y las fotos sueltas se clasifican por EXIF: sin OCR, G sigue dando el mismo veredicto y ahorro que A | `docs/05` §8.2 exige 7/7 en un clon sin tesseract | Escanear un documento obligatorio |
| F0.9 | La fase `resto` se evalúa antes del cálculo y se informa en orden de fase: ninguna regla de `resto` puede referenciar salidas del cálculo (por derivación irían a `post_calculo`), y así se sabe si el veredicto será `SUBSANABLE` antes de decidir un cálculo provisional | `docs/04` §5.1 sin recalcular ni retirar resultados | Calcular y retirar después |
| F0.9 | Cálculo provisional genérico (caso B): con veredicto `SUBSANABLE`, si a una unidad le falta una sola entrada del `Plan` que aparece en una derivada junto a otra presente, se sustituye por ella (`min(h_antes, h_despues)` → `h = h_antes`) con aviso y `provisional`. **Nunca** con `PREVALIDADO`: sin `h_despues` y sin fallos, el veredicto es `PREVALIDADO` y **no se publica ahorro** | `docs/05` §2.1 exige 305.829 provisional en B, sin cablear nombres de la ficha | Cablear `h`/`h_despues` |
| F0.9 | `<variable>.fuente` de una derivada sale del `Plan` (`Derivada.origen`), no del resultado del cálculo, para que `R-CAL-04` se evalúe en consistencia (`docs/04` §5.2); si además llega un dato consolidado homónimo (alguien extrajo `p` de la ficha del variador), gana la `fuente_primaria` del documento y la regla **falla** | Sin esto `R-CAL-04` sería estructuralmente incapaz de fallar | Leerlo solo del cálculo |
| F0.9 | Solo las reglas `BLOQUEANTE_*` detienen una fase (un `AVISO` fallido como `R-CAL-02` no impide calcular); una bloqueante de `cabecera` para igual que una de consistencia; una regla fuera de vigencia es `NO_EVALUABLE` con motivo, no se omite | `docs/04` §5.2; queda fijado para las futuras `R-CAB-*` | "Falla alguna" como criterio de parada |
| F0.9 | `obligatorio: condicional` cuya condición no se puede evaluar → el documento **no** es obligatorio, con aviso (matiza la fila QA-1). Motivo: `instalacion_personal_propio` no lo produce ningún extractor, y dejarlo `NO_EVALUABLE` haría que `R-DOC-01` fuese `NO_EVALUABLE` siempre y no detectase ninguna carencia | Mantener `R-DOC-01` operativa; el aviso lo dice en el informe | Dejarlo `NO_EVALUABLE` (R-DOC-01 inútil) o declarar el dato en la spec v1.2 (**decisión de Billy**) |
| F0.9 | `carencias[].documentos` se deriva cuando la spec no declara `subsanacion` (v1.1 no lo hace): tipos de las `fuentes` de las variables de la regla, documentos con esa raíz y, si usa `presente`, los obligatorios ausentes | Una petición de subsanación sin documentos concretos no sirve | Lista vacía |
| F0.9 | Alias de contexto reducidos a **uno** (`solicitud.fecha` → fecha de evaluación, INT-10) con test que impide que la tabla crezca; `factura.linea` y `requisito … in convenio_cae` se resuelven por reglas genéricas (singular de una colección; requisitos declarados en la spec frente a hallados) | Regla de oro 4: nada de la ficha en `engine/` | Tabla de alias por ficha |
| plan | Caso G sin OCR debe dar el mismo resultado que A: el escaneo girado es `ficha_tecnica_variador` (EVD-04, no obligatorio) y las fotos sueltas se clasifican por EXIF | `docs/05` §8.2 exige 7/7 en un clon sin tesseract | Escanear un documento obligatorio (rompería 7/7 sin OCR) |

## 3 bis. Estado al cierre de la sesión del 18/09/2026

Hecho y verificado: F0.0–F0.4 (commits 8ebb723, 4f26284/4d715d5, 79956a0/62df530, 0c97217, 7700ba2); 321 tests en verde;
`ruff` limpio; sin `eval`/`compile` ni importaciones prohibidas en `engine/`; caso A = 305.829,6 en memoria. QA de la oleada 1
ejecutada y sus hallazgos cerrados. **Pendiente**: QA de F0.3/F0.4, F0.5 y F0.8 (oleada 3, lanzada y abortada por límite de
sesión de la API), F0.6–F0.7, F0.9–F0.12. Al reanudar: relanzar la oleada 3 tal como la define §1 (los tres briefs no dependen
de nada nuevo). Pendiente técnico para F0.9: soporte nativo de comparación encadenada en `expresiones.py` y retirada de la
reescritura de `calculo.py`.

## 4. Parámetros de los casos E y F y ground truth recalculado

Fijados por el generator en F0.5 (18/09/2026, commit `cff6411`) y calculados con `engine.calculo.calcular`, no a
mano. Las tres potencias tienen **fila exacta** en el cuadro 6, así que `R-CAL-02` da `CUMPLE` en A–G y ningún
caso arrastra el aviso INT-02. Los valores de M2 y M3 son nuevos: los del Engine 0.1 (461.433 y 777.128) no son
reproducibles porque sus parámetros no están documentados fuera de aquel código (`docs/05` §2.3).

| Caso | Motor | Equipo | PM (kW) | N1 (rpm) | N2 (rpm) | h_antes | h_despues | h | pérdidas ref. (kW) | AEM (kWh/año) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A, B, C, D, G | MTR-SYN-0001 | bomba dinámica | 110 | 1.485 | 1.188 | 6.000 | 6.570 | 6.000 | 5,55 | 305.829,6 |
| E, F | MTR-SYN-0002 | ventilador radial | 55 | 1.480 | 1.110 | 5.500 | 5.840 | 5.500 | 3,12 | 164.962,1875 |
| F | MTR-SYN-0003 | compresor centrífugo | 160 | 2.960 | 2.516 | 7.000 | 6.205 | **6.205** | 8,82 | 361.978,4944125 |

En M3 `h_despues < h_antes`, así que `h = min(h_antes, h_despues)` toma `h_despues`: es la trampa de la regla
del menor `h` que exige `docs/05` §4.3, y un test comprueba que invertir cuál es el menor cambia el resultado.

**Ground truth de la Fase 0** (sustituye a los números del Engine 0.1; solo cambia con un ADR nuevo aprobado por
Billy):

| Caso | Veredicto | AETOTAL exacto (kWh/año) | AETOTAL CAE (kWh) | Provisional |
|---|---|---:|---:|---|
| A | `PREVALIDADO` | 305.829,6 | 305.829 | no |
| B | `SUBSANABLE` | 305.829,6 | 305.829 | **sí** (N2 declarado, `h = h_antes`) |
| C | `BLOQUEADO` | — | — | no calcula |
| D | `NO_ELEGIBLE` | — | — | no calcula |
| E | `PREVALIDADO` | 470.791,7875 | 470.791 | no |
| F | `PREVALIDADO` | 832.770,2819125 | 832.770 | no |
| G | `PREVALIDADO` | 305.829,6 | 305.829 | no |

Ficheros por caso: A, C, D 11 · B 10 (sin registro) · E 16 · F 21 · G 13. El caso A conserva exactamente los
parámetros de `docs/05` §2.3 y su 305.829,6 sigue siendo el criterio de aceptación de la fase.

## 5. Desviaciones respecto a `docs/05` y número de tests

Se rellena en F0.12.

## 6. Decisiones que quedan para Billy (PROPUESTA)

Se rellena al cierre. Candidatos ya identificados:

1. **Fila 110 kW del cuadro 6 (5,55 kW) frente a 6,11 kW.** Dos recuerdos independientes del cuadro (agente `spec-fichas` y
   orquestador) discrepan; la revisión QA observa que en la transcripción actual pérdidas/PM vale 5,6–5,8 % en las filas
   vecinas (45–160 kW) y **5,05 % solo en 110 kW**, mientras que 6,11 kW daría 5,55 %, coherente con la serie. `data/README.md`
   afirma que Billy verificó 5,55 contra el BOE el 17/09/2026, pero `docs/historico/cae-engine-estado-proyecto_2026-09-17.md`
   solo registra el valor, no el acto de contraste. **Decisión de Billy**: confirmar 5,55 kW contra el DOUE (entonces la fila
   queda `si` y nada cambia) o corregir a 6,11 kW (entonces cambian INT-01, el caso A y el criterio de aceptación 305.829,6:
   ADR nuevo, no parche). Hasta entonces la fila se mantiene `si` por precedencia de `data/README.md` y `CLAUDE.md` §5.
2. Verificación fila a fila de las 38 filas `pendiente` (en especial 55 kW y 160 kW, que sostienen E y F).
3. INT-10 (fecha de solicitud en prevalidación = fecha de evaluación).
4. **`instalacion_personal_propio`** (condición de DOC-05B): ningún documento lo declara. Hoy, si no se puede
   evaluar, el certificado de técnico competente se trata como **no obligatorio** con aviso (F0.9). Alternativa:
   declararlo en la spec v1.2 como variable de cabecera. Decide Billy.
5. **Interpretaciones citadas frente a aplicadas**: hoy `interpretaciones_aplicadas` incluye las de toda regla
   evaluada, así que en el caso A aparece INT-02 aunque haya fila exacta y la interpolación no se haya usado.
   Distinguir "regla que cita un INT" de "INT que influyó en el resultado" exige un campo nuevo en la spec.
   Mientras tanto, `evaluar_casos.py` compara la lista del ground truth como **subconjunto**, no por igualdad.

## Verificación

`python -m pytest -q` · `python evaluar_casos.py` · `ruff check . && ruff format --check .` · `grep -rn "eval(" engine/` vacío ·
`grep -rn "from agentes\|from salida\|import agentes\|import salida" engine/` vacío · `docs/01` coincide con el árbol.
