# CAES_Engine
Certificado de Ahorro Energetico

## Misión

Convertir la documentación desordenada de una actuación de ahorro energético en un expediente CAE trazable, calculado de forma determinista y prevalidado, listo para la
revisión de un profesional o verificador. La IA lee e interpreta; el motor calcula y decide, con evidencia documental detrás de cada dato y el BOE como referencia vinculante.

## Visión

Ser la infraestructura de prevalidación de referencia del Sistema CAE: un motor donde cada ficha del catálogo MITECO es configuración versionada, no código, capaz de cubrir de forma multisectorial todo el catálogo de actuaciones estandarizadas y de integrarse con la plataforma oficial, reduciendo el rechazo de expedientes y el tiempo de tramitación para instaladores, sujetos delegados y verificadores, sin prometer nunca un "CAE garantizado".

## Aporte de valor

Hoy, preparar una actuación CAE es un trabajo manual sobre documentación heterogénea:
fichas técnicas, placas, facturas, registros de horas, escaneos y fotos que hay que leer,
cruzar con la ficha del catálogo MITECO y convertir en un cálculo defendible ante un
verificador. Cada error de lectura o de interpretación se descubre tarde, como
requerimiento o rechazo, cuando corregirlo ya cuesta tiempo y dinero.

CAE Engine mueve ese control al principio del proceso. Entrega, para cada actuación:

- **Un veredicto antes de enviar.** `NO_ELEGIBLE`, `BLOQUEADO`, `SUBSANABLE` o
  `PREVALIDADO`, con la regla concreta que lo motiva y su severidad. Se sabe qué falta
  y qué hay que corregir antes de que lo diga el verificador.
- **Un ahorro calculado de forma determinista y reproducible.** La fórmula y las
  variables viven en la ficha como configuración versionada; el mismo expediente produce
  siempre el mismo resultado, sin intervención de la IA en el cálculo.
- **Evidencia detrás de cada dato.** Documento, página, texto literal, método de
  extracción y confianza. El expediente se defiende con citas, no con confianza en quien
  lo preparó. Ante dos fuentes fiables que discrepan, el motor se detiene y muestra ambas
  en lugar de elegir.
- **Separación entre lo declarado y lo demostrado.** Lo que solo está afirmado se marca
  y se trata distinto de lo que está acreditado por documento.
- **Interpretaciones explícitas.** Lo que la norma no cierra queda registrado como punto
  interpretativo (`INT-xx`) con criterio, alternativa e impacto, nunca resuelto en
  silencio dentro del código.

Para quien prepara actuaciones (instaladores, sujetos delegados), el valor es menos
subsanaciones y menos tiempo por expediente. Para quien las revisa (verificadores,
gestores), es un expediente ordenado, trazable y con el cálculo auditable. Para ambos,
es un criterio común y versionado sobre cómo se lee cada ficha.

### Lo que este proyecto no promete

No emite ni garantiza CAE. La certificación es un acto administrativo que depende de la
verificación acreditada, del gestor autonómico y del Coordinador Nacional. El Engine
prevalida contra su lectura de la ficha y del BOE, que manda sobre cualquier
interpretación propia. Su eficacia real se medirá con métricas de verificación
(actuaciones prevalidadas que superan verificación sin requerimiento, tiempo hasta
resolución, subsanaciones evitadas), aún no disponibles por no existir todavía envíos a
la plataforma oficial.
