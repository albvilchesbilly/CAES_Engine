# `front/` — cuatro superficies por capacidades

Interfaz del CAE Engine (`ADR-050`). En **FR0 solo existe `compartido/`**: el sistema de diseño mínimo,
es decir, los tres rótulos que impiden que la interfaz mienta (`ADR-011` §5, contrato C16). Las cuatro
superficies (`workspace/`, `externo/`, `consola/`) llegan a partir de FR1.

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

## Lo que este paquete no hace, por diseño

- **No contiene lógica de negocio** (`R-UI-11`): no calcula, no evalúa reglas, no decide transiciones.
- **No habla con nadie**: sin `fetch`, sin imports fuera del paquete. El contrato con `api/` llega en FR1.
- **Sin ejecución dinámica**: nada de `eval`, `new Function` ni `dangerouslySetInnerHTML`.
- **No autoriza nada**: ocultar un control no es autorización; eso se valida en el servidor (`R-UI-01`).

Las cuatro cosas están comprobadas por test (`compartido/tests/textos.test.ts`), no solo escritas aquí.

## Estructura

```
front/
  package.json          Workspace raíz: dependencias de desarrollo y scripts
  tsconfig.base.json    Opciones compartidas (strict, jsx react-jsx)
  vitest.config.ts      Entorno jsdom; recoge */tests/**/*.test.ts(x)
  compartido/
    src/                index · textos · valores · los tres rótulos · estilos.css
    tests/              casos adversariales y tests de los tres rótulos
```

Todos los textos de interfaz viven en `compartido/src/textos.ts`, en español y con sus tildes. Están
centralizados para que un test pueda recorrerlos y comprobar que no aparece ninguna fórmula prohibida
por `CLAUDE.md` §2 ("CAE garantizado", entre otras).
