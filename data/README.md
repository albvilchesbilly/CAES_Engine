# data/ — Tablas de referencia

Toda tabla de esta carpeta es **dato normativo transcrito**, no dato calculado ni inventado. Cada una lleva aquí su fuente oficial, quién la transcribió, quién la verificó y su vigencia. Regla de oro 8 (el BOE manda) y 9 (todo cambio pasa por revisión humana): **Claude Code puede transcribir; solo Billy marca `verificado: si`.**

## Tablas

| Fichero | Contenido | Fuente oficial | Columnas | Vigencia | Estado |
|---|---|---|---|---|---|
| `reg_2019_1781_cuadro6.csv` + `reg_2019_1781_cuadro6.meta.yaml` | Pérdidas de referencia de variadores de velocidad en función de la potencia (Reglamento (UE) 2019/1781, anexo I, cuadro 6), en el punto de funcionamiento "90 % frecuencia estatórica nominal, 100 % corriente nominal generadora de par" | https://www.boe.es/buscar/doc.php?id=DOUE-L-2019-81609 | `kva_salida, kw_motor, perdidas_ref_kw, cos_phi, verificado` | `desde: 2019-10-25` (publicación DOUE) · `hasta: null` | **Transcrita en F0.2 (18/09/2026) de memoria del agente, sin acceso al DOUE. 39 filas: 1 verificada (110 kW), 38 `pendiente`.** |

## Formato de cada tabla

Cada tabla son dos ficheros con el mismo nombre base, y `engine/tablas.py` los lee juntos:

- **`<nombre>.csv`**: separador coma, punto decimal, sin separador de miles, UTF-8, cabecera en la primera línea. Los valores se leen como `Decimal(texto)`; nunca pasan por `float`. Última columna siempre `verificado` ∈ {`si`, `pendiente`}; cualquier otro valor es error de carga.
- **`<nombre>.meta.yaml`**: `id` (el que usa la spec en `tablas.<ID>`), `fuente` (URL oficial), `fecha_transcripcion`, `transcrito_por`, `metodo_transcripcion` (`doue` | `boe` | `memoria_agente`), `verificacion` (responsable, filas verificadas, alcance), `vigencia: {desde, hasta}` (ISO; `hasta: null` si sigue vigente), `columnas`, `unidades` y `clave` (columna por la que se busca).

El motor busca por `clave` exacta. Si no hay fila exacta, aplica el criterio **INT-02** de la spec (interpolación lineal entre las dos filas adyacentes, `Decimal` sin redondeo) y devuelve la marca `INT-02` con aviso para el informe. Fuera del rango de la tabla **no extrapola**: devuelve `valor = null` y aviso. Si alguna fila usada está `pendiente`, el aviso lo dice ("tabla pendiente de verificación humana").

## Cómo se transcribe una tabla (F0.2 y siguientes)

1. Abrir la fuente oficial (DOUE/BOE), no el catálogo ni un resumen de fabricante.
2. Transcribir **todas** las filas con los valores exactos y las unidades del original. Sin redondear, sin interpolar, sin "completar".
3. Añadir la columna `verificado` con valor `pendiente` en cada fila.
4. Registrar aquí (y en el `.meta.yaml`) fecha de transcripción, quién la hizo y con qué método.
5. Billy (o un revisor humano) contrasta fila a fila contra el original y cambia `pendiente` → `si`. Una fila `pendiente` **puede usarse en tests y en cálculo**, pero el informe de prevalidación la marca como "tabla pendiente de verificación humana" hasta que todas estén en `si`.
6. Si en la sesión no hay acceso a la fuente oficial, la transcripción se hace de memoria del agente, se declara así en `metodo_transcripcion: memoria_agente` y en el registro de abajo, y **la verificación humana fila a fila es obligatoria** antes de fiarse de cualquier valor distinto de los ya verificados.

## Valores ya verificados (a reproducir exactamente)

| Tabla | Clave | Valor | Verificado por | Cuándo | Contra qué |
|---|---|---|---|---|---|
| cuadro 6 | `kw_motor = 110` | `perdidas_ref_kw = 5.55` | Billy / Sprint 1 del Engine 0.1 | 17/09/2026 | BOE/DOUE (según `docs/historico/cae-engine-estado-proyecto_2026-09-17.md` §4) |

Ese valor es el que sostiene el caso A del banco de pruebas: p = 5,55 / 110 = 5,0455 % → AEM = 305.829,6 kWh/año. `tests/test_tablas.py` lo comprueba.

**Alcance de esa verificación**: el par (`kw_motor = 110`, `perdidas_ref_kw = 5.55`). El `kva_salida = 135` de esa misma fila procede de la transcripción de memoria del 18/09/2026 y no está verificado, aunque la fila lleve `verificado: si` (la marca es por fila; Billy debe confirmar también el kVA al revisar).

## Sobre la columna `cos_phi`

El cuadro 6 del Reglamento, tal como lo recuerda el agente, **no contiene una columna de factor de potencia**: sus columnas son potencia aparente nominal de salida del variador (kVA), potencia nominal del motor (kW) y pérdidas de referencia (kW). La spec declara `cos_phi` entre las columnas de `REG1781_CUADRO6`, así que la columna existe en el CSV **vacía en todas las filas**. Si algún día hace falta, vendría de los datos del motor de referencia de la norma IEC 61800-9-2 (de la que el Reglamento toma el cuadro), no de este cuadro, y **no** se calcula como `kw_motor / kva_salida` (ese cociente incluye el rendimiento del motor, no solo el factor de potencia). Billy decide si se mantiene la columna en la spec o se retira en el diff v1.2.

## Lo que NO va aquí

- Coeficientes de corrección del art. 18 bis del proyecto de RD: no existen todavía. Cuando existan, `spec/coeficientes_*.yaml` con vigencia y ficha afectada (`docs/04` §14).
- Tablas de otras fichas (SEPR, Fd, Fc, horas por actividad de `docs/09`): se transcriben cuando entre la ficha, con el mismo procedimiento.
- Cualquier valor de la ficha técnica de un fabricante: eso es evidencia de un documento, no tabla de referencia (regla `R-CAL-04`: `p` nunca sale de la ficha del variador).

## Registro de transcripciones

| Fecha | Tabla | Filas | Quién | Método | Verificación |
|---|---|---|---|---|---|
| 18/09/2026 | `reg_2019_1781_cuadro6.csv` | 39 (0,12 kW … 1.000 kW) | Claude Code (agente spec-fichas, F0.2) | **Transcrita de memoria del agente, sin acceso al DOUE ni al BOE en la sesión** (el proxy de red denegó `www.boe.es` y `eur-lex.europa.eu`). | 1 fila `si` (110 kW, verificada por Billy el 17/09/2026); **38 filas `pendiente`; verificación humana obligatoria fila a fila** |

### Advertencias de la transcripción del 18/09/2026 (para la revisión de Billy)

1. **Ninguna fila salvo la de 110 kW ha sido contrastada con el texto oficial.** Los 38 valores restantes (kVA, kW y pérdidas) son la mejor reconstrucción de memoria del agente y pueden contener errores individuales o sistemáticos.
2. **La memoria del agente no coincide con el valor verificado en la fila 110 kW**: el agente recordaba `6,11 kW` de pérdidas de referencia para 110 kW (135 kVA), frente a los `5,55` verificados por Billy contra el BOE/DOUE. Se ha registrado el valor verificado (BOE > memoria, regla de oro 8), pero la discrepancia pone bajo sospecha toda la columna `perdidas_ref_kw` transcrita de memoria. Nótese además que 6,11 / 110 = 5,55 %: conviene que Billy confirme al revisar que el cuadro 6 expresa las pérdidas de referencia **en kW** (y no en % de la potencia del motor), porque de ello dependen INT-01 (`p = perdidas_ref_kw / PM`) y el valor de regresión 305.829,6 kWh/año. Esto no se decide aquí: se deja a Billy.
3. **Vigencia**: `desde: 2019-10-25` es la fecha de publicación en el DOUE (L 272), como fijó `docs/01` §3.2. El agente recuerda que el Reglamento **se aplica desde el 1 de julio de 2021** (art. 12); no se ha cambiado `desde` porque la ficha IND240 usa el cuadro como tabla de referencia con independencia de la aplicabilidad del Reglamento a los variadores. Si Billy prefiere la fecha de aplicación, se cambia en el `.meta.yaml` y aquí.
4. Rango transcrito: 0,12 kW a 1.000 kW (ámbito del Reglamento para variadores). Fuera de ese rango el motor no calcula `p`.
