> **HISTÓRICO.** Estado del proyecto a 17/09/2026 (tras Sprint 2). La evolución de la tesis y las correcciones sobre la conversación original se conservan aquí; el estado vivo está en `docs/00-instrucciones-de-entrada.md` §9 y las decisiones en `docs/decisiones/`.

# CAE Engine — Estado del proyecto

Última actualización: 17/09/2026 (tras Sprint 2). Origen: conversación de brainstorming con otra IA (PDF "Experto en CAE España"), analizada y contrastada en Cowork.

## 1. Evolución de la tesis (cómo llegamos aquí)

1. Brainstorming CAE → cálculo de ahorros (fichas estandarizadas vs. actuaciones singulares) y monetización (convenio CAE con sujeto delegado/obligado).
2. Benchmark España/Francia: CAE Market, CAE Claro, CertificAhorro, Greenescae, CAEConecta, Novawatt, Smart Light, caes.es, Aislame, AlfaCAE, Mitsubishi+Novawatt, Hisense, Santander; CEE Market y France CEE (Francia).
3. Concepto 1: marketplace de renovación energética financiada. Conclusión: ninguna pieza es nueva por separado; caes.es cubre gran parte.
4. Ampliación a movilidad (flotas, EV, recarga, renting). Benchmark Arval, Wallbox, Zeplug.
5. Pre-mortem: 3 esfuerzos muy altos → capa CAE/regulación, financiación, marketplace.
6. **Decisiones tomadas: 1A · 2A · 3D** — sujeto delegado como partner; financiación de partner sin riesgo CAE; entrada B2B2C vía instaladores.
7. **Pivote final (Billy):** el activo es el **motor de cálculo y validación CAE**.
8. **17/09/2026:** Sprint 1 (spec + paquete sintético) y Sprint 2 (Engine 0.1) completados.

## 2. Tesis vigente

"Infraestructura inteligente que convierte documentación desordenada de una actuación en un expediente CAE trazable, calculado de forma determinista, prevalidado y listo para revisión profesional/verificador."

Principios de diseño (ya implementados):
- IA ≠ cálculo. La IA extrae/interpreta; cálculo y reglas deterministas y versionados.
- Evidence Graph: cada variable con documento, página, método y confianza.
- Fichas MITECO como configuración (YAML), no como código.
- Estados: 🔴 NO_ELEGIBLE (ámbito) · 🔴 BLOQUEADO (inconsistencia crítica, no calcula) · 🟡 SUBSANABLE (cálculo provisional) · 🟢 PREVALIDADO. Nunca "CAE garantizado".
- Referencia vinculante = BOE.

## 3. Roadmap del Engine

- 0.1 ✅ IND240 V1.1 end-to-end. 0.2: + TRA050 y RES060 + identificación automática de ficha. 0.3: diez fichas. 0.4: sector industrial. 1.0: multisectorial.

## 4. Sprint 1 — COMPLETADO

Spec IND240 V1.1 en YAML (ámbito, exclusiones, variables con fuentes y tipo de evidencia, fórmula, 26 reglas, documentación, estados, 7 puntos interpretativos); tabla cuadro 6 del Reg. (UE) 2019/1781 en CSV (110 kW → 5,55 kW, verificada en BOE/DOUE); Calculation Engine determinista + lector xlsx con huella SHA-256; paquete sintético Industrias Delta (11 documentos por caso) con 7 variantes y ground truth.

## 5. Sprint 2 — COMPLETADO (Engine 0.1)

Cuatro capas: ingesta y clasificación (PDF nativo, OCR de escaneos con tesseract spa, xlsx, fotos con EXIF, separación de PDF combinados) → extracción y grafo de evidencias (interfaz `Extractor`; hoy implementación por reglas) → Rules Engine que ejecuta las 26 reglas del YAML → informe de prevalidación (markdown + JSON) y CLI.

Resultado sobre los 7 casos: **7/7 estados correctos**, 58/58 variables de cálculo extraídas con evidencia, 2,5 s de media por expediente (11,9 s el caso G por OCR). 61 tests en verde.

Decisiones de diseño relevantes:
- Tablas del PDF (pdfplumber) antes que texto plano: la marca de agua y los saltos de página separan etiqueta y valor.
- Vinculación por nº de serie y del registro por SHA-256, no por nombre de fichero.
- Datos de OCR con confianza 0,75: discrepancias se marcan como posible error de OCR, no bloquean.
- Ante conflicto de PM (caso C) el Engine no elige valor ni calcula.
- Orden: ámbito y consistencia → cálculo → resto de reglas.

**Cómo leer el 100 %:** el extractor por reglas se ajustó con estos documentos. Demuestra que la cadena completa funciona, no que acierte en un expediente real no visto.

## 6. Correcciones detectadas sobre la conversación original

1. Error de cálculo IND240: la otra IA dio ≈1.015.260 kWh/año (imposible: supera PM·h = 660.000). Resultado correcto del caso A: **305.829,6 kWh/año** (p = 5,55/110 = 5,0455 %).
2. p = pérdidas de referencia del cuadro 6, no las del fabricante del variador ni un supuesto.
3. h = menor de h_antes y h_despues.
4. "factura_motor" en la carpeta propuesta sería señal de sustitución (EXC-02): se sustituyó por ficha técnica + placa.
5. Precio CAE: 115–140 €/MWh a propietarios iniciales en 2025; 100–140 €/MWh orientativo 2026 (no 0,03 €/kWh). Caso A ≈ 30,6–42,8 k€ brutos.
6. Datos de mercado 2026 de la otra IA (Santander, Mitsubishi, Auto+, 9.400 solicitudes / 7.700 GWh, subastas) → pendientes de verificar.
7. CAE = ahorro anual (Orden TED/815/2023); validez 3 años desde fin de actuación (art. 17.1); convenio antes de la solicitud (art. 11.3).

## 7. Riesgos y consideraciones abiertas

- INT-01 (base de p), INT-03 (N2 anual con 30 días), INT-04 (extrapolación de h_despues), INT-05 ("registro inalterable"): criterios propios sin validar. Si uno es erróneo, cambia el ahorro calculado.
- Extracción por reglas: sin probar en documentos reales no vistos.
- Dependencia de un único sujeto delegado.
- Competidores con software CAE (CAE Claro, CertificAhorro): el diferencial debe demostrarse con métricas de prevalidación y trazabilidad.
- Moeve (empleador de Billy) es previsiblemente sujeto obligado → posible aliado o conflicto de interés; aclarar.
- Texto oficial del Anexo I no disponible: el paquete usa un modelo sintético.

## 8. Siguiente paso propuesto — Sprint 3 (superado por `docs/06-plan-de-construccion.md`)

1. Extractor con LLM tras la misma interfaz `Extractor`, comparado con el de reglas sobre los mismos 7 casos.
2. Expediente real anonimizado para medir precisión fuera del laboratorio (opción B del plan original).
3. Sesión con verificador/experto CAE para cerrar INT-01/03/04/05 y actualizar el YAML.
4. Segunda ficha (TRA050, movilidad) para comprobar que el marco aguanta en otro sector.

Alternativa de negocio, si el objetivo es enseñar el producto antes de seguir construyendo: demo visual del informe de prevalidación para un sujeto delegado o instalador.

Fuentes: ficha IND240 V1.1 (MITECO); Reglamento (UE) 2019/1781 (BOE/DOUE); Orden TED/815/2023 (BOE); DEKRA "Mercado CAE 2025"; Nertio "Precio del CAE en 2026".
