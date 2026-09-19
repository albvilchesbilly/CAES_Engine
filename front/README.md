# `front/` — cuatro superficies por capacidades

Interfaz del CAE Engine (`ADR-050`). En **FR0 solo existía `compartido/`**: el sistema de diseño mínimo,
es decir, los tres rótulos que impiden que la interfaz mienta (`ADR-011` §5, contrato C16). **FR1 le añade
el cliente de `api/`** (`compartido/api/`, contrato C18 de `ADR-012` §3). Las cuatro superficies
(`workspace/`, `externo/`, `consola/`) llegan con las pantallas.

React con TypeScript (C1, aprobado por Billy el 19/09/2026). Node 22 y npm 10.

## Instalación y uso

```bash
cd front
npm install          # instala el workspace completo; no se commitea node_modules/
npm test             # vitest: los tests de compartido/
npm run test:watch   # los mismos, en observación
npm run typecheck    # tsc --build sobre src/ y tests/
```

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

**La capa HTTP todavía no existe.** `api/` es hoy un contrato en proceso de Python, y `transporteHttp`
describe el sobre que se espera (`POST /lecturas/{capacidad}`, `/comandos/{capacidad}`, `/documentos`) para
que el día que se escriba el servidor se lea de un sitio y no se invente otra vez.

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
```

Todos los textos de interfaz viven en `compartido/src/textos.ts`, en español y con sus tildes. Están
centralizados para que un test pueda recorrerlos y comprobar que no aparece ninguna fórmula prohibida
por `CLAUDE.md` §2 ("CAE garantizado", entre otras).
