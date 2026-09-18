---
description: Comprueba que documentación y código coinciden (marcas F0/NUEVO/EXISTE, estructura, huecos API, reglas, decisiones) y corrige las discrepancias documentales en la misma sesión.
---

Actúa como `orquestador-arquitectura` con `qa-evaluacion` y `revisor-normativo` como revisores. No cambies código: cambia documentación para que diga la verdad, o abre hallazgos para que el código se arregle.

## Comprobaciones (todas)

1. **Estructura**: árbol real vs. `docs/01` §1 y §3. Ficheros que existen y no están documentados, o al revés → corregir `docs/01`.
2. **Marcas de estado** en `docs/03` §3 (mapa de módulos), §13 (funcionalidades) y `docs/04` §9 (familias de reglas): `F0`/`NUEVO` que ya están implementados → `EXISTE`/`PARCIAL` con el fichero; `EXISTE` sin código → volver a `NUEVO` y avisar.
3. **Reglas**: cada regla de `spec/IND240_v1.1.yaml` tiene test que cumple y test que falla; la fase que aplica `engine/reglas.py` coincide con `docs/04` §5.
4. **Huecos**: `grep -rn "TODO(API-" .` ↔ `docs/HUECOS.md` §1. Sin huérfanos en ningún sentido. Ningún valor "provisional" de la API sin marca.
5. **Reglas de oro en código**: `eval(` en `engine/`; `float` en cálculo/reglas; imports de `agentes/` o `salida/` desde `engine/`; `if ficha ==`; "CAE garantizado" o "verificador" aplicado a A8 en textos de producto.
6. **Ground truth**: `git log -- expedientes/_resultados_esperados/` → cada cambio tiene ADR.
7. **Plan**: `docs/06` estados vs. commits reales; bitácora al día.
8. **Decisiones**: nada implementado que dependa de una línea de `ADR-001` §3 sin ADR que la cierre; `spec/propuestas/` no se carga (test de `spec_registry`).
9. **Vocabulario**: "expediente" usado para la unidad de trabajo en código o docs nuevos → corregir a "actuación" (`CLAUDE.md` §3). Excepción: `docs/historico/`.
10. **Normativo** (`revisor-normativo`): interpretaciones silenciosas nuevas en `engine/` o spec → `INT-xx` propuestos.

## Salida

Tabla de discrepancias (dónde, qué dice el doc, qué hace el código, acción: doc corregido / hallazgo abierto para código / decisión de Billy). Aplica las correcciones documentales en la sesión; un commit `contrastar: <fecha>`. Termina con lo que queda abierto y para quién.
