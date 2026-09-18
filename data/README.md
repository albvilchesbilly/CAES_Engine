# data/ — Tablas de referencia

Toda tabla de esta carpeta es **dato normativo transcrito**, no dato calculado ni inventado. Cada una lleva aquí su fuente oficial, quién la transcribió, quién la verificó y su vigencia. Regla de oro 8 (el BOE manda) y 9 (todo cambio pasa por revisión humana): **Claude Code puede transcribir; solo Billy marca `verificado: si`.**

## Tablas

| Fichero | Contenido | Fuente oficial | Columnas | Vigencia | Estado |
|---|---|---|---|---|---|
| `reg_2019_1781_cuadro6.csv` | Pérdidas de referencia de variadores de velocidad en función de la potencia (Reglamento (UE) 2019/1781, anexo I, cuadro 6), en el punto de funcionamiento "90 % frecuencia estatórica nominal, 100 % corriente nominal generadora de par" | https://www.boe.es/buscar/doc.php?id=DOUE-L-2019-81609 | `kva_salida, kw_motor, perdidas_ref_kw, cos_phi, verificado` | `desde: 2019-10-25` (publicación DOUE) · `hasta: null` | **Por transcribir en F0.2** |

## Cómo se transcribe una tabla (F0.2 y siguientes)

1. Abrir la fuente oficial (DOUE/BOE), no el catálogo ni un resumen de fabricante.
2. Transcribir **todas** las filas con los valores exactos y las unidades del original. Sin redondear, sin interpolar, sin "completar".
3. Añadir la columna `verificado` con valor `pendiente` en cada fila.
4. Registrar aquí fecha de transcripción y quién la hizo.
5. Billy (o un revisor humano) contrasta fila a fila contra el original y cambia `pendiente` → `si`. Una fila `pendiente` **puede usarse en tests y en cálculo**, pero el informe de prevalidación la marca como "tabla pendiente de verificación humana" hasta que todas estén en `si`.

## Valores ya verificados (a reproducir exactamente)

| Tabla | Clave | Valor | Verificado por | Cuándo | Contra qué |
|---|---|---|---|---|---|
| cuadro 6 | `kw_motor = 110` | `perdidas_ref_kw = 5.55` | Billy / Sprint 1 del Engine 0.1 | 17/09/2026 | BOE/DOUE (según `docs/historico/cae-engine-estado-proyecto_2026-09-17.md` §4) |

Ese valor es el que sostiene el caso A del banco de pruebas: p = 5,55 / 110 = 5,0455 % → AEM = 305.829,6 kWh/año. `tests/test_tablas.py` lo comprueba.

## Lo que NO va aquí

- Coeficientes de corrección del art. 18 bis del proyecto de RD: no existen todavía. Cuando existan, `spec/coeficientes_*.yaml` con vigencia y ficha afectada (`docs/04` §14).
- Tablas de otras fichas (SEPR, Fd, Fc, horas por actividad de `docs/09`): se transcriben cuando entre la ficha, con el mismo procedimiento.
- Cualquier valor de la ficha técnica de un fabricante: eso es evidencia de un documento, no tabla de referencia (regla `R-CAL-04`: `p` nunca sale de la ficha del variador).

## Registro de transcripciones

| Fecha | Tabla | Filas | Quién | Verificación |
|---|---|---|---|---|
| — | — | — | — | — |
