# `front/workspace/` — el workspace del tenant

Superficie de `T-RES`, `T-OPE` y `T-REV` (`ADR-050`). Escritorio, cuenta de usuario del tenant.

**Estado**: `FR1.c` entrega la primera pantalla, `T-REV-cola` (`docs/front/pantallas/T-REV-cola.md`).
La vista de revisión (`T-REV-revision`) entra como carpeta hermana de `cola/` y reutiliza este mismo
andamiaje: **no hay que rehacer nada de lo que hay aquí para añadirla**.

## Lo que hay que saber antes de tocar nada

1. **El transporte se inyecta y no existe capa HTTP** (`ADR-014` §4, decisión de Billy del 23/09/2026).
   `FR1` entrega pantallas verificadas contra el contrato con un transporte de pruebas, no una
   aplicación que se abra en un navegador. Aquí no se escribe un `fetch`, no se levanta un servidor y
   no se inventa una sesión: la pantalla recibe un `Cliente` ya construido.
2. **El front no contiene lógica de negocio** (`R-UI-11`). No calcula, no evalúa reglas, no decide
   transiciones y **no ordena**. Hay un test que recorre el árbol y falla si aparece un `sort`.
3. **Ninguna cifra de ahorro pasa por `Number`.** `api/` sirve `total_exacto` y
   `total_exacto_presentable` juntos: se pinta el presentable, tal cual llega. Reformatear obligaría a
   pasar por coma flotante (`CLAUDE.md` §2).
4. **Un error del servidor se muestra.** Ocultar un control no es autorización (`R-UI-01`): una
   denegación se pinta con su capacidad y su motivo literales.

## Estructura

```
front/workspace/
  src/
    index.ts          Lo que exporta el paquete: pantallas y andamiaje
    textos.ts         TODO texto de interfaz del workspace, en un solo sitio (CA-COLA-10)
    json.ts           Lectores defensivos de `Respuesta.datos`: objeto, lista, texto, campo…
    fallos.ts         `ErrorPermiso` / `ErrorApi` → `FalloServidor`, que siempre se enseña
    useLectura.ts     Hook con los tres estados de una lectura: cargando / listo / error + recargar
    fechas.ts         Fecha absoluta tal y como llegó, y "hace N días" con el reloj inyectado
    Pantalla.tsx      Marco común: título, rol de `Respuesta.rol`, `MarcaOrigen`, avisos
    AvisoServidor.tsx El motivo del servidor, literal, con "Reintentar" cuando tiene sentido
    estilos.css       Estilos del workspace; acompañan a `@cae/compartido/estilos.css`
    cola/             T-REV-cola
      datos.ts          Las cuatro lecturas y los tipos de fila. Aquí no se ordena
      motivos.ts        Identificador de motivo de `api/` → rótulo en castellano
      ColaRevision.tsx  La pantalla y sus cuatro estados
      FilaCola.tsx      Una fila: veredicto, motivos, ahorro, antigüedad, estado, enlace
  tests/
    apoyo.tsx         Servidor de pruebas sobre los datos reales + ayudas de render
    cola.test.tsx     Un test por criterio CA-COLA-* que se comprueba pintando
    arbol.test.ts     Los que se comprueban recorriendo el árbol (CA-COLA-05, CA-COLA-11, R-UI-11)
    textos.test.ts    CA-COLA-10: la misma lista de fórmulas prohibidas que `compartido/`
    datos/
      generar.py      Genera los tres JSON llamando a `api/` de verdad. Se ejecuta a mano
      cola.json       Respuesta real de `CAP-17` con sus filas **ya ordenadas** por el servidor
      detalle.json    Respuestas reales de `CAP-03`, `CAP-04` y `CAP-14` por actuación
      denegacion.json La denegación real de `CAP-17` a un perfil que no la tiene
```

## Cómo se añade la segunda pantalla

1. Carpeta nueva en `src/` (`revision/`), con su `datos.ts`, su componente y lo que necesite. **No se
   toca `cola/`.**
2. Sus textos, al final de `src/textos.ts`, y al catálogo `TEXTOS`: así entran solos en la
   comprobación de fórmulas prohibidas.
3. Se reutiliza el andamiaje: `Pantalla` para la cabecera (rol y marca de origen en todos los
   estados), `useLectura` para los tres estados de una lectura, `AvisoServidor` para lo que conteste
   el servidor, `json.ts` para leer los bloques y `fallos.ts` para no tragarse ningún error.
4. Sus tests, en `tests/`, con un fichero por pantalla. `tests/arbol.test.ts` y `tests/textos.test.ts`
   **ya cubren el árbol entero**: no hay que ampliarlos, empiezan a mirar la carpeta nueva solos.
5. Si necesita datos de `api/` que hoy no están en `datos/`, se añaden a `generar.py` y se regenera.
   Nunca se escribe un payload a mano: probaría la pantalla contra la idea que tenemos del contrato.

## Regenerar los datos de prueba

```bash
python front/workspace/tests/datos/generar.py     # desde la raíz del repositorio
```

Carga los siete casos sintéticos en un tenant, los procesa sin OCR y pide las cuatro lecturas a `api/`.
De los siete, el servidor deja cinco en la cola: `E` y `F` están `PREVALIDADO` y sin nada que esperar.

## Lo que esta superficie no hace

- **No dispara ningún comando desde la cola** (`T-REV-cola` §4): una lista es el peor sitio para
  ejercer una capacidad que escribe en el log.
- **No pinta el aviso de registro de actividad** (`R-UI-10`): depende de `O-EQU` (`CAP-36`), que no
  está implementado. Avisar de algo que no ocurre sería decir algo falso.
- **No declara el origen de los datos** porque `api/` todavía no lo sirve (`GAP-COLA-03`, `ADR-014`
  §7): se lee `ORIGEN DE DATOS SIN DECLARAR`, que es lo honesto mientras nadie lo haya decidido.
