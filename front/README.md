# `front/` — cuatro superficies por capacidades

Interfaz del CAE Engine (`ADR-050`). En **FR0 solo existía `compartido/`**: el sistema de diseño mínimo,
es decir, los tres rótulos que impiden que la interfaz mienta (`ADR-011` §5, contrato C16). **FR1 le añade
el cliente de `api/`** (`compartido/api/`, contrato C18 de `ADR-012` §3) y la primera superficie,
**`workspace/`**, con las dos pantallas de `T-REV` (`FR1.c`): la **cola de revisión** y la **vista de
revisión**, que es donde se mide el valor del producto. `externo/` y `consola/` llegan con sus pantallas.

**Las pantallas se abren en un navegador desde el 24/09/2026** (`GAP-HTTP-03`, cerrado; `ADR-015` §5).
`FR1` las entregó verificadas contra el contrato con un transporte de pruebas (`ADR-014` §4), `FR-HTTP`
publicó el contrato por red, y **`aplicacion/`** es la tercera pieza: el empaquetador (Vite) y la página
que monta el `workspace/` y navega entre la cola y la vista de revisión. No cambió ni una pantalla para
conseguirlo.

React con TypeScript (C1, aprobado por Billy el 19/09/2026). Node 22 y npm 10.

## Instalación y uso

```bash
cd front
npm install          # instala el workspace completo; no se commitea node_modules/
npm test             # vitest: los tests de compartido/, workspace/ y aplicacion/
npm run test:watch   # los mismos, en observación
npm run typecheck    # tsc --build sobre src/ y tests/
npm run e2e          # Playwright contra los dos servidores levantados. NO entra en la puerta
```

## Abrir la cola de revisión en un navegador

Dos procesos, dos terminales. El primero es el servidor (`FR-HTTP`); el segundo, esta página.

```bash
# 1 · el servidor, desde la raíz del repositorio: api/ sobre los siete casos sintéticos
python servidor_desarrollo.py --desarrollo

# 2 · el front, desde front/. El principal se escribe a mano: no hay valor por defecto
cd front
VITE_CAE_PRINCIPAL='{"usuario_id":"u-rev","perfiles":["T-REV"],"tenant_id":"T-001"}' npm run dev
```

Y se abre **<http://127.0.0.1:5173/>**. Lo que se ve:

- La **cola de revisión** con las actuaciones que el servidor pone en ella, en el orden que él decide.
  Cada fila enlaza a `#/revision/<actuacion_id>`; pulsando «Revisar» se abre la **vista de revisión**
  con el documento original incrustado, cada dato con su cita y el formulario de corrección. El lazo
  del caso C se cierra entero en el navegador: corregir `PM` con su justificación devuelve
  `PREVALIDADO` y **305.829,6 kWh/año**.
- Arriba del todo, en amarillo y en todos los estados, **el aviso de que la autenticación es de
  mentira**, con el principal que esta página declara. Y dentro de cada pantalla, el aviso que manda
  el propio servidor en `avisos` (`ADR-015` C29). Los dos se ven a la vez a propósito.
- Si `VITE_CAE_PRINCIPAL` falta o está mal escrita, la página **no pide nada** y lo dice: no se
  autentica sola.

`VITE_CAE_PRINCIPAL` no tiene valor por defecto, y no lo tiene a propósito: esa cabecera
(`x-cae-principal-desarrollo`) es la pieza que, olvidada, regala el sistema. El servidor la exige y esta
página obliga a escribirla, igual que `servidor_desarrollo.py` obliga a escribir `--desarrollo`.
`CAE_SERVIDOR` cambia a dónde se reenvía `/api` (por defecto `http://127.0.0.1:8000`); eso sí es una
dirección, no una credencial.

**No es un despliegue**: no hay TLS, ni sesión, ni límite de peticiones, y el principal lo declara quien
pregunta. Eso es `FR-DESPLIEGUE` (`ADR-015` §5). Y el repositorio del servidor es de memoria: las
correcciones que se hagan desde el navegador duran lo que dure el proceso.

`compartido/` se consume como código fuente (`main`/`exports` apuntan a `src/index.ts`): las superficies
viven en este mismo repositorio y las empaqueta su propio bundler, así que no hay paso de compilación
que mantener. Los estilos son un fichero aparte, `@cae/compartido/estilos.css`, que importa la
aplicación que los use.

## Las tres reglas que estos componentes garantizan

| Componente | Regla | Qué garantiza |
|---|---|---|
| `RotuloPrevalidado` | `R-UI-06` | Una cifra prevalidada nunca sale sin "no son CAE emitidos"; un estado de expediente sale marcado `NO OFICIAL`. No hay prop que quite el aviso |
| `ValorMetrica` | `R-UI-07` | `SIN DATO` se ve `SIN DATO` y nunca como cero, en blanco o `NaN`. Un cero de verdad se ve `0` |
| `MarcaOrigen` | `R-UI-08` | Todo panel declara si mira datos sintéticos o reales. Sin valor por defecto: un origen que falta se anuncia `ORIGEN DE DATOS SIN DECLARAR` |

```tsx
import { MarcaOrigen, RotuloPrevalidado, ValorMetrica } from "@cae/compartido";

<MarcaOrigen origen="SINTETICO" />
<RotuloPrevalidado tipo="AHORRO_PREVALIDADO">305.829,6 kWh/año</RotuloPrevalidado>
<ValorMetrica etiqueta="Minutos de revisión" metrica={{ estado: "SIN_DATO", desde: "S3.5" }} />
```

El valor llega **ya decidido y ya formateado** por el servidor: un `Decimal` viaja como cadena
(`"305.829,6"`) y se pinta tal cual. Reformatear aquí obligaría a pasar por `float`, prohibido en todo
lo que toca el ahorro (`CLAUDE.md` §2).

## El cliente de `api/` (`@cae/compartido/api`)

Va en un subcamino aparte, y no en el índice del paquete, para que los tres rótulos sigan siendo
componentes de presentación puros: quien importa `@cae/compartido` no se lleva un cliente HTTP de regalo.

```ts
import { crearCliente, transporteHttp, ErrorPermiso, bloque } from "@cae/compartido/api";

const cliente = crearCliente(transporteHttp("/api"));
const respuesta = await cliente.leer("CAP-03", { superficie: "vista_revision", tenant_id, actuacion_id });
const veredicto = bloque(respuesta, "veredicto");          // `undefined` si el ámbito no lo trae
const quien = respuesta.rol_nombre;                        // "Revisor tecnico", leído de la matriz
const papel = await cliente.leerDocumento("CAP-03", contexto, doc_id);   // los bytes de la ingesta
```

Cuatro reglas, las de `ADR-012` §3:

1. **No decide permisos.** No hay tabla de perfiles ni de capacidades: pide, y el servidor concede o
   niega. Ocultar un control no es autorización, y el front tampoco autoriza por su cuenta (`R-UI-01`).
2. **Un `ErrorPermiso` se muestra, no se traga.** Llega como excepción tipada, con el motivo del servidor
   y un `mensaje` en castellano listo para pintar.
3. **No reordena ni recalcula** (`R-UI-11`): `datos` sale con la misma referencia con la que llegó.
4. **Tipos derivados del contrato**: `Bloque`, `CapacidadLectura` y `CapacidadComando` viven en
   `api/contrato.generado.ts`, que **genera `api/tipos_front.py`** desde `api/proyeccion.py` y
   `engine/capacidades.yaml`. No se edita a mano. Para regenerarlo, desde la raíz del repositorio:

```bash
python -c "from pathlib import Path; from api.tipos_front import RUTA_GENERADA, typescript; \
Path(RUTA_GENERADA).write_text(typescript(), encoding='utf-8')"
```

`tests/test_api_tipos_front.py` lo regenera y compara: si `api/` cambia y el fichero no, el banco de
pruebas de Python se pone rojo; en cuanto se regenera, `npm run typecheck` señala cada sitio del front que
usaba un bloque que ya no existe.

**La capa HTTP ya existe** (`api/http/`, `ADR-015`), y se escribió leyendo el sobre de `transporte.ts`, que
sigue siendo la fuente de su forma: `POST /lecturas/{capacidad}`, `/comandos/{capacidad}` y `/documentos`.
Un test del banco de Python compara las rutas que sirve el servidor con las que este fichero declara, así
que añadir una en un sitio y no en el otro se ve enseguida. Dos cosas que el sobre no resuelve están
anotadas en `ADR-015` §7.1: `/documentos` no lleva la capacidad (el servidor la deriva de la matriz) y el
contenido de una subida (`CAP-02`) no cabe en JSON (`GAP-HTTP-02`).

Quien lo usa contra el servidor de desarrollo es `aplicacion/`: `transporteHttp("/api")` con un `fetch`
envuelto que añade la cabecera `x-cae-principal-desarrollo`. El sobre **no se toca** para eso (`ADR-015`
§1): la cabecera se añade fuera, en `aplicacion/src/transporte.ts`, porque quién pide es cosa de la
composición y no del contrato.

## Lo que este paquete no hace, por diseño

- **No contiene lógica de negocio** (`R-UI-11`): no calcula, no evalúa reglas, no decide transiciones.
- **Los rótulos no hablan con nadie**: sin `fetch` y sin imports fuera del paquete. Quien habla con `api/`
  es `compartido/api/`, y solo con `api/`: nunca con `engine/`.
- **Sin ejecución dinámica**: nada de `eval`, `new Function` ni `dangerouslySetInnerHTML`.
- **No autoriza nada**: ocultar un control no es autorización; eso se valida en el servidor (`R-UI-01`).

Las cuatro cosas están comprobadas por test (`compartido/tests/textos.test.ts` para los rótulos y
`compartido/tests/cliente.test.ts` para el cliente), no solo escritas aquí.

## Estructura

```
front/
  package.json          Workspace raíz: dependencias de desarrollo y scripts
  tsconfig.base.json    Opciones compartidas (strict, jsx react-jsx)
  vitest.config.ts      Entorno jsdom; recoge */tests/**/*.test.ts(x)
  compartido/
    src/                index · textos · valores · los tres rótulos · estilos.css
    api/                cliente de `api/` · transporte · contrato.generado.ts (no se edita)
    tests/              casos adversariales, los tres rótulos y el cliente
  workspace/            T-RES, T-OPE, T-REV — las dos pantallas de `T-REV` (FR1.c) y su andamiaje
    src/                marco de pantalla, lecturas, fallos, fechas, textos · cola/ · revision/
    tests/              un test por criterio CA-COLA-* y CA-REV-*, con datos generados desde `api/`
  aplicacion/           La página que monta las superficies contra el servidor (GAP-HTTP-03)
    index.html          Un único documento; el enrutado es por hash
    vite.config.ts      Vite, sin plugin de React; /api se reenvía al servidor de desarrollo
    src/                configuración del principal · transporte con cabecera · enrutador · marco
    tests/              humo (la aplicación entera montada) y el principal, que no tiene defecto
    e2e/                Playwright contra los dos servidores. `npm run e2e`, fuera de la puerta
```

Cada superficie es un paquete de los workspaces de npm y se consume como código fuente, igual que
`compartido/`. `front/workspace/README.md` explica cómo entra una pantalla nueva sin rehacer las que hay.

**`aplicacion/` no es una superficie**: es la composición, el equivalente de `servidor_desarrollo.py` en
el lado del navegador. Es el único sitio del front que conoce una URL, construye un `Cliente` y sabe de
dónde sale el principal. Las superficies siguen recibiendo el cliente ya hecho.

Todos los textos de interfaz viven en `compartido/src/textos.ts`, en español y con sus tildes. Están
centralizados para que un test pueda recorrerlos y comprobar que no aparece ninguna fórmula prohibida
por `CLAUDE.md` §2 ("CAE garantizado", entre otras).
