/**
 * Todos los textos del workspace del tenant, en un solo sitio.
 *
 * Estan centralizados por la misma razon de control que en `compartido/` y no por comodidad:
 * `tests/textos.test.ts` recorre este catalogo con **la misma lista de formulas prohibidas** que
 * `front/compartido/tests/textos.test.ts` (`CLAUDE.md` §2, `CA-COLA-10`). Si los textos estuvieran
 * repartidos por los `.tsx`, esa comprobacion seria una busqueda de cadenas por el arbol y dejaria de
 * ser fiable en cuanto alguien compusiera una frase sobre la marcha.
 *
 * Los identificadores van en espanol sin tildes (como en `engine/`); lo que lee una persona, con ellas.
 *
 * **Lo que NO entra aqui**: el descargo, el mensaje de un veredicto, el motivo de un error y el motivo
 * de un no-calculo. Los escribe el servidor (la spec activa o `api/`), se pintan literales y no son
 * texto de producto nuestro (`T-REV-revision.md` §11 bis).
 *
 * La segunda pantalla del workspace anade su seccion al final; no reescribe las de arriba.
 */

// -- Marco de pantalla ------------------------------------------------------------------------

/** La cabecera dice siempre con que rol se esta actuando (`ADR-050`, §"Inferencia del rol"). */
export const ACTUANDO_COMO = "Actuando como";

/** Fallo que no es del contrato: tampoco se calla, aunque no se sepa mas. */
export const ERROR_DESCONOCIDO = "el fallo no trae ningún detalle";

/** Un error del servidor se puede volver a intentar; no se sustituye por "no hay datos". */
export const REINTENTAR = "Reintentar";

// -- Cola de revision (`T-REV-cola`) ----------------------------------------------------------

export const TITULO_COLA = "Cola de revisión";

/** Resumen de la tabla para quien la recorre con lector de pantalla. */
export const LEYENDA_COLA =
  "Actuaciones del tenant que esperan revisión, en el orden de prioridad que fija el servidor.";

export const COLUMNA_ACTUACION = "Actuación";
export const COLUMNA_VEREDICTO = "Veredicto";
export const COLUMNA_MOTIVOS = "Por qué está aquí";
export const COLUMNA_AHORRO = "Ahorro prevalidado";
export const COLUMNA_ANTIGUEDAD = "Esperando desde";
export const COLUMNA_ESTADO = "Estado";
export const COLUMNA_ACCION = "Ir a la revisión";

/** El enlace de la fila. La cola reparte trabajo: lo que se decide se decide con el expediente delante. */
export const IR_A_REVISION = "Revisar";

export const CARGANDO = "Cargando la cola de revisión…";
export const CARGANDO_DESCRIPCION =
  "Hueco de carga: la lectura está en vuelo y todavía no hay ninguna cifra que pintar.";

export const VACIO = "No hay nada esperando revisión.";
export const VACIO_DESCRIPCION =
  "La lectura ha respondido y no trae ninguna actuación. No es un error y no es un cero.";

/** `R-UI-05` anticipado: entrar y descubrir que no se puede tocar nada es descubrirlo tarde. */
export const SOLO_LECTURA = "Solo lectura";
export const SOLO_LECTURA_DESCRIPCION =
  "En la plataforma y sin requerimiento abierto: desde aquí no se cambia nada.";

/** `calculo.provisional`: la cifra existe, pero se apoya en algo declarado y no demostrado. */
export const ESTIMACION_NO_ACREDITADA = "ESTIMACIÓN NO ACREDITADA";

export const ETIQUETA_CICLO = "Ciclo";
export const ETIQUETA_ULTIMO_MOVIMIENTO = "Último movimiento";
export const ETIQUETA_PLATAFORMA = "Plataforma";

/** Antiguedad: la fecha absoluta manda y esto es el texto secundario (`T-REV-cola` §5). */
export const ANTIGUEDAD_HOY = "hoy";
export const ANTIGUEDAD_UN_DIA = "hace 1 día";
export const ANTIGUEDAD_DIAS = "hace N días";

/** Rotulos de los cinco motivos de `T-REV-cola` §6. El identificador lo decide `api/`; esto lo nombra. */
export const MOTIVO_CONFLICTO = "Conflicto";
export const MOTIVO_ESCALADO = "Escalado";
export const MOTIVO_REQUERIMIENTO = "Requerimiento abierto";
export const MOTIVO_CORRECCION = "Corrección pendiente";
export const MOTIVO_TAREA = "Tarea de la plataforma";

/**
 * Una fila que llega sin motivo no se esconde: el servidor promete que no las hay
 * (`T-REV-cola` §6), y el dia que llegue una, se ve que ha llegado.
 */
export const MOTIVO_AUSENTE = "El servidor no ha declarado ningún motivo para esta fila.";

// -- Vista de revision (`T-REV-revision`) -----------------------------------------------------
//
// La pantalla donde se mide el valor del producto. Tres preguntas, y en este orden: si esto esta bien,
// si me lo creo y que hago ahora (`T-REV-revision` §1).
//
// Lo que **no** esta aqui, y no por olvido: el mensaje del veredicto, su descargo, el motivo de un
// no-calculo, el motivo de una denegacion y el aviso de un recalculo que no se hizo. Los escribe el
// servidor (la spec activa o `api/`), se pintan literales y no son texto de producto nuestro
// (`T-REV-revision` §11 bis). Tampoco esta ninguna unidad ni ningun nombre de variable: los declara la
// ficha y los sirve `api/` (`GAP-REV-05`, `GAP-REV-10`); escribirlos aqui seria cablear una tabla por
// ficha en la interfaz, y la segunda ficha la desmentiria (regla de oro 4).

export const TITULO_REVISION = "Revisión de la actuación";

export const CARGANDO_REVISION = "Cargando la revisión…";
export const CARGANDO_REVISION_DESCRIPCION =
  "Hueco de carga: las lecturas están en vuelo y todavía no hay ninguna cifra que pintar.";

/** La regla que da forma a la pantalla entera (`R-UI-02`). Se dice, no se deja adivinar. */
export const SIN_CONTROL_DE_VEREDICTO =
  "No hay ningún control para cambiar el veredicto: si está mal, es que un dato está mal. " +
  "Se corrige el dato y el motor vuelve a calcular.";

/** `R-UI-01`: la pantalla inhabilita para explicar, no para proteger. */
export const INHABILITAR_NO_AUTORIZA = "Inhabilitar no es autorizar: el servidor valida igualmente.";

// Veredicto

export const ETIQUETA_VEREDICTO = "Veredicto";
export const ETIQUETA_FICHA = "Ficha";
export const ETIQUETA_EVALUACION = "Evaluada el";

/** `CA-REV-09`: un veredicto que no refleja la última corrección no se presenta como si la reflejara. */
export const PENDIENTE_DE_RECALCULO = "PENDIENTE DE RECÁLCULO";
export const PENDIENTE_DE_RECALCULO_DESCRIPCION =
  "La corrección quedó registrada y el motor no ha podido rehacer el cálculo: lo que se lee aquí es " +
  "el resultado anterior, no el de después de corregir.";

// Lo que lo impide

export const TITULO_IMPIDE = "Lo que lo impide";
export const TITULO_CONFLICTO = "Conflicto en";
export const CONFLICTO_EXPLICACION =
  "El motor no elige entre fuentes fiables. Sin este dato no hay cálculo.";
export const QUE_ES_ESTE_DATO = "Qué es este dato";
export const ETIQUETA_REFERENCIA = "Referencia de la ficha";
export const ETIQUETA_POR_FUENTE = "Lo que aporta cada fuente";
export const ETIQUETA_FUENTE_PRIMARIA = "fuente primaria";
export const TITULO_CARENCIAS = "Carencias";
export const CARENCIA_DOCUMENTOS = "Se subsana con";

// Citas y evidencias

export const COLUMNA_VALOR = "Valor";
export const COLUMNA_DOCUMENTO = "Documento · pág.";
export const COLUMNA_TEXTO_LITERAL = "Texto literal";
export const COLUMNA_METODO = "Método";
export const COLUMNA_CONFIANZA = "Confianza";
export const COLUMNA_TIPO_EVIDENCIA = "Tipo";
export const VER_EN_EL_DOCUMENTO = "Ver en el documento";
export const USAR_ESTE_VALOR = "Usar este valor";

/** Una corrección humana no sale de un papel: su "cita" es lo que escribió quien corrigió. */
export const CITA_CORRECCION_HUMANA = "corrección humana";

/** `R-UI-09`: un dato sin cita es un defecto visible, no una celda más. */
export const SIN_CITA = "Este dato ha llegado sin ninguna cita.";

// Corrección (`CAP-05` y `CAP-06`)

export const TITULO_CORRECCION = "Corregir el dato";
export const CAMPO_VARIABLE = "Variable";
export const CAMPO_UNIDAD = "Unidad";
export const CAMPO_VALOR = "Valor";
export const CAMPO_JUSTIFICACION = "Justificación";

/** `R-UI-04`. El campo nace vacío en todos los caminos de entrada y la pantalla no lo rellena. */
export const JUSTIFICACION_OBLIGATORIA = "obligatoria";
export const JUSTIFICACION_AYUDA =
  "Escribe por qué vale este valor y no los otros. No se rellena sola ni se copia de la evidencia.";
export const FALTA_LA_JUSTIFICACION = "Inhabilitado: falta la justificación.";
export const SE_ELIGE = "Se envía";
export const SE_DESCARTAN = "Se descartan";
export const GUARDAR_CORRECCION = "Guardar corrección";
export const CANCELAR_CORRECCION = "Cancelar";
export const CORRECCION_REGISTRADA = "Corrección registrada.";
export const CORRECCION_RECALCULADA = "El motor ha vuelto a calcular con el valor corregido.";

/** `CAP-10` marca que una persona revisó: es la mitad de la guarda, no el envío. */
export const APROBACION_REGISTRADA = "Revisión aprobada: queda registrada como revisada por una persona.";

// Ahorro (`T-REV-revision` §7)

export const TITULO_AHORRO = "Ahorro prevalidado";
export const PARA_PRESENTAR = "Para presentar";
/** INT-06. Sin unidad: la declara la ficha y la sirve `api/`, no se escribe aquí. */
export const TRUNCADO_INT06 = "truncado a entero, criterio conservador (INT-06)";
export const TITULO_PROCEDENCIA = "De dónde sale";
export const ETIQUETA_ENTRADAS = "Entradas del cálculo";
export const ETIQUETA_DERIVADAS = "Derivadas por el motor";
export const ETIQUETA_CONTROLES = "Comprobaciones físicas";
export const ETIQUETA_PRECONDICIONES = "Precondiciones";
export const VER_FORMULA = "Ver la fórmula y la traza del motor";
export const TRAZA_NOTA =
  "La traza se muestra tal y como la escribe el motor. Esta pantalla no calcula nada.";

/** `CLAUDE.md` §3: un `INT-xx` es criterio propio sin validar, nunca "según la normativa". */
export const CRITERIO_PROPIO = "criterio propio sin validar contra la norma";
export const TITULO_INTERPRETACIONES = "Criterios propios aplicados";

// Datos y comprobaciones

export const TITULO_DATOS_CALCULO = "Datos que entran en el cálculo";
export const TITULO_RESTO_DATOS = "Resto de datos consolidados";
export const RESTO_DATOS_NOTA = "Están, y no estorban: no hacen falta para decidir.";
export const COLUMNA_DATO = "Dato";
export const TITULO_COMPROBACIONES = "Comprobaciones";
export const COMPROBACIONES_CONFORMES = "conformes";
export const COMPROBACIONES_FALLAN = "fallan";
export const COMPROBACIONES_NO_EVALUABLES = "no evaluables";
export const TITULO_HISTORIAL = "Historial";
export const ETIQUETA_JUSTIFICACION_REGISTRADA = "Justificación";

// Acciones (`T-REV-revision` §8)

export const APROBAR_REVISION = "Aprobar la revisión";
export const APROBAR_NOTA =
  "Al aprobar queda pendiente de que Operaciones prepare la entrega: aprobar no es enviar.";
export const APROBAR_IMPEDIDO = "Inhabilitado mientras haya bloqueantes abiertos:";
export const ENVIAR_SUBSANACION = "Enviar la subsanación";
export const CONFIRMAR_DESCARTE = "Confirmar el descarte";
export const REVISAR_OBSERVACION = "Dar por revisada la observación";
export const RESOLVER_DISCREPANCIA = "Decidir ante la discrepancia";
export const CONFIRMAR_INTERPRETACION = "Confirmar la interpretación del requerimiento";
export const SUBIR_DOCUMENTO = "Subir documentación";

/** `GAP-REV-04`: antes esto que confirmar a ciegas algo que no se ha podido leer. */
export const INACTIVO_INTERPRETACION =
  "Inactivo: `api/` no sirve todavía la interpretación propuesta del requerimiento (GAP-REV-04), y " +
  "confirmar a ciegas lo que no se ha podido leer sería peor que esperar.";

/** `GAP-HTTP-01`: el comando admite los bytes; lo que falta es el canal del navegador. */
export const INACTIVO_SUBIDA =
  "Inactivo: subir un fichero desde el navegador necesita la capa HTTP, que todavía no existe " +
  "(GAP-HTTP-01). Mientras tanto, lo que falta se pide por subsanación.";

/**
 * `GAP-REV-13`: el comando exige un texto que no tenemos.
 *
 * La subsanación la redacta A5, que no existe; el descarte y la discrepancia los motiva una persona y
 * ese formulario no es de esta pantalla. Enviarlos vacíos es un comando que el servidor rechaza, y
 * escribir el texto aquí sería ponerle palabras a quien no las ha dicho.
 */
export const INACTIVO_SIN_TEXTO =
  "Inactivo: este comando exige un texto que todavía no tenemos, y enviarlo vacío lo rechaza el " +
  "servidor. Escribirlo aquí sería ponerle palabras a quien no las ha dicho (GAP-REV-13).";

/** `R-UI-05`. La lectura sigue entera; lo que se cierra es la escritura. */
export const SOLO_LECTURA_FIRMADA =
  "Solo lectura: la actuación está firmada y entregada a la plataforma. La información revisada y " +
  "firmada solo se modifica por requerimiento oficial.";
/**
 * `CAP-14` no ha contestado: no se sabe si se puede escribir, y no saberlo no es poder.
 *
 * Se dice esto y no "está firmada", que sería afirmar algo que no consta. Los controles quedan inactivos
 * igual, y el servidor valida igualmente (`R-UI-01`).
 */
export const ESCRITURA_SIN_ESTADO =
  "No se ha podido leer el estado de la actuación, así que no se puede saber si admite cambios: los " +
  "controles de escritura quedan inactivos hasta que esa lectura conteste.";

export const SOLO_LECTURA_REQUERIMIENTO =
  "Requerimiento oficial abierto: se activan únicamente los controles de su flujo; el resto sigue " +
  "cerrado.";
export const ETIQUETA_REQUERIMIENTO = "Requerimiento abierto";
export const CONTAGIADA =
  "Afectada por un requerimiento de su expediente, no por un defecto propio.";
export const TITULO_RECHAZOS = "Correcciones rechazadas tras la firma";

// Panel del documento (`T-REV-revision` §3, contrato C17)

export const TITULO_DOCUMENTO = "Documento";
export const CARGANDO_DOCUMENTO = "Cargando el documento…";
export const SIN_DOCUMENTO_ELEGIDO =
  "Ningún documento abierto. Pulsa una cita y aquí se abre el papel en el que se leyó el dato.";
export const ETIQUETA_PAGINA = "Página";
export const ETIQUETA_PAGINA_DE = "de";
export const DOCUMENTO_INTACTO =
  "Servido por su huella y sin transformar: el servidor recalcula el sha256 antes de servirlo.";
export const DOCUMENTO_ES_PARTE =
  "Es una parte de un PDF combinado: se sirve el combinado entero, sin recortar.";
export const ETIQUETA_RANGO_PAGINAS = "Páginas de la parte";
export const SIN_VISOR =
  "Este navegador no puede abrir el documento incrustado. Los bytes han llegado igualmente y su " +
  "huella es la de la ingesta.";
export const ETIQUETA_BYTES = "Bytes servidos";

/** Catalogo completo, para la comprobacion de `tests/textos.test.ts`. */
export const TEXTOS = {
  ACTUANDO_COMO,
  ERROR_DESCONOCIDO,
  REINTENTAR,
  TITULO_COLA,
  LEYENDA_COLA,
  COLUMNA_ACTUACION,
  COLUMNA_VEREDICTO,
  COLUMNA_MOTIVOS,
  COLUMNA_AHORRO,
  COLUMNA_ANTIGUEDAD,
  COLUMNA_ESTADO,
  COLUMNA_ACCION,
  IR_A_REVISION,
  CARGANDO,
  CARGANDO_DESCRIPCION,
  VACIO,
  VACIO_DESCRIPCION,
  SOLO_LECTURA,
  SOLO_LECTURA_DESCRIPCION,
  ESTIMACION_NO_ACREDITADA,
  ETIQUETA_CICLO,
  ETIQUETA_ULTIMO_MOVIMIENTO,
  ETIQUETA_PLATAFORMA,
  ANTIGUEDAD_HOY,
  ANTIGUEDAD_UN_DIA,
  ANTIGUEDAD_DIAS,
  MOTIVO_CONFLICTO,
  MOTIVO_ESCALADO,
  MOTIVO_REQUERIMIENTO,
  MOTIVO_CORRECCION,
  MOTIVO_TAREA,
  MOTIVO_AUSENTE,
  TITULO_REVISION,
  CARGANDO_REVISION,
  CARGANDO_REVISION_DESCRIPCION,
  SIN_CONTROL_DE_VEREDICTO,
  INHABILITAR_NO_AUTORIZA,
  ETIQUETA_VEREDICTO,
  ETIQUETA_FICHA,
  ETIQUETA_EVALUACION,
  PENDIENTE_DE_RECALCULO,
  PENDIENTE_DE_RECALCULO_DESCRIPCION,
  TITULO_IMPIDE,
  TITULO_CONFLICTO,
  CONFLICTO_EXPLICACION,
  QUE_ES_ESTE_DATO,
  ETIQUETA_REFERENCIA,
  ETIQUETA_POR_FUENTE,
  ETIQUETA_FUENTE_PRIMARIA,
  TITULO_CARENCIAS,
  CARENCIA_DOCUMENTOS,
  COLUMNA_VALOR,
  COLUMNA_DOCUMENTO,
  COLUMNA_TEXTO_LITERAL,
  COLUMNA_METODO,
  COLUMNA_CONFIANZA,
  COLUMNA_TIPO_EVIDENCIA,
  VER_EN_EL_DOCUMENTO,
  USAR_ESTE_VALOR,
  CITA_CORRECCION_HUMANA,
  SIN_CITA,
  TITULO_CORRECCION,
  CAMPO_VARIABLE,
  CAMPO_UNIDAD,
  CAMPO_VALOR,
  CAMPO_JUSTIFICACION,
  JUSTIFICACION_OBLIGATORIA,
  JUSTIFICACION_AYUDA,
  FALTA_LA_JUSTIFICACION,
  SE_ELIGE,
  SE_DESCARTAN,
  GUARDAR_CORRECCION,
  CANCELAR_CORRECCION,
  CORRECCION_REGISTRADA,
  CORRECCION_RECALCULADA,
  APROBACION_REGISTRADA,
  TITULO_AHORRO,
  PARA_PRESENTAR,
  TRUNCADO_INT06,
  TITULO_PROCEDENCIA,
  ETIQUETA_ENTRADAS,
  ETIQUETA_DERIVADAS,
  ETIQUETA_CONTROLES,
  ETIQUETA_PRECONDICIONES,
  VER_FORMULA,
  TRAZA_NOTA,
  CRITERIO_PROPIO,
  TITULO_INTERPRETACIONES,
  TITULO_DATOS_CALCULO,
  TITULO_RESTO_DATOS,
  RESTO_DATOS_NOTA,
  COLUMNA_DATO,
  TITULO_COMPROBACIONES,
  COMPROBACIONES_CONFORMES,
  COMPROBACIONES_FALLAN,
  COMPROBACIONES_NO_EVALUABLES,
  TITULO_HISTORIAL,
  ETIQUETA_JUSTIFICACION_REGISTRADA,
  APROBAR_REVISION,
  APROBAR_NOTA,
  APROBAR_IMPEDIDO,
  ENVIAR_SUBSANACION,
  CONFIRMAR_DESCARTE,
  REVISAR_OBSERVACION,
  RESOLVER_DISCREPANCIA,
  CONFIRMAR_INTERPRETACION,
  SUBIR_DOCUMENTO,
  INACTIVO_INTERPRETACION,
  INACTIVO_SUBIDA,
  INACTIVO_SIN_TEXTO,
  SOLO_LECTURA_FIRMADA,
  ESCRITURA_SIN_ESTADO,
  SOLO_LECTURA_REQUERIMIENTO,
  ETIQUETA_REQUERIMIENTO,
  CONTAGIADA,
  TITULO_RECHAZOS,
  TITULO_DOCUMENTO,
  CARGANDO_DOCUMENTO,
  SIN_DOCUMENTO_ELEGIDO,
  ETIQUETA_PAGINA,
  ETIQUETA_PAGINA_DE,
  DOCUMENTO_INTACTO,
  DOCUMENTO_ES_PARTE,
  ETIQUETA_RANGO_PAGINAS,
  SIN_VISOR,
  ETIQUETA_BYTES,
} as const;
