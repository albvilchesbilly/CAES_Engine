# ADR-015 — `FR-HTTP`: publicar `api/` por red, y de dónde sale el principal

**Estado: ACEPTADO en sus tres decisiones de Billy (24/09/2026). Los contratos C27–C30 son diseño de esta
sesión y se implementan en `FR-HTTP`.**

**Contexto**: desde `FR0` existe un contrato completo en `api/` y desde `FR1` dos pantallas que lo consumen,
pero **nada lo publica por red**. El sobre está descrito en un solo sitio —`front/compartido/api/transporte.ts`,
escrito precisamente «para que el día que se escriba el servidor se lea de aquí y no se invente otra vez»— y
ese día es hoy.

Es el entregable que convierte dos pantallas verificadas en algo que una persona abre.

---

## 1. Lo que ya está decidido y este ADR no reabre

El sobre no se rediseña: se implementa **tal y como está escrito** en `transporte.ts`.

- `POST {base}/lecturas/{capacidad}` · `POST {base}/comandos/{capacidad}` · `POST {base}/documentos`
- Cuerpo: `{ contexto, datos }`.
- Respuesta 200: `{ capacidad, rol, rol_nombre, eventos, datos, avisos }`.
- 403: `{ error: "permiso", motivo, codigo? }` · cualquier otra: `{ error: "api", motivo, codigo? }`.
- **Ni el usuario ni el tenant real viajan en el cuerpo.** El `tenant_id` del `contexto` es el que *declara
  la pantalla*, y el servidor lo compara con el del principal; si no coinciden, deniega.

Si al implementarlo algo del sobre resulta impracticable, se corrige **en `transporte.ts` y aquí**, nunca
divergiendo en silencio: hay un cliente y 208 tests de front que dependen de esa forma.

---

## 2. El riesgo que gobierna este entregable

Hasta hoy el CAE Engine es un motor que corre donde lo lanzas. Con `FR-HTTP` pasa a ser **un servicio con
superficie de ataque**, y conviene decirlo antes de escribir la primera línea:

> **Todo el aislamiento por tenant y toda la matriz de capacidades descansan en que el `Principal` sea
> verdadero.** `api.permisos.Principal(usuario_id, perfiles, tenant_id)` es hoy un objeto que construye
> quien llama. En proceso, quien llama somos nosotros. Por red, quien llama es cualquiera.

De ahí que la decisión 2 sea la importante de este ADR, y no la del framework. Un fallo en el stack se nota;
un principal mal construido no se nota: sirve datos de otro tenant con toda naturalidad, y el log registra
que fue una acción legítima de un usuario legítimo.

---

## 3. Decisión 1 — Starlette y uvicorn

**Billy, 24/09/2026.**

Descartado FastAPI: pydantic querría validar lo que `api/contrato.Peticion` ya valida, y su OpenAPI
autogenerado competiría con el contrato de tipos que `FR0` genera para el front. **Dos fuentes de verdad
sobre la misma forma es exactamente como acaban divergiendo.** Descartada también la biblioteca estándar:
escribir a mano concurrencia, cabeceras y errores para un servidor que verá datos de clientes es trabajo
propenso a fallos que nadie audita.

Starlette es ASGI estándar y mínimo, y si mañana se quiere FastAPI encaja encima sin tirar nada, porque
FastAPI es Starlette por dentro.

**Contrato C27 — el servidor es una capa de traducción, y nada más.**

Vive en `api/http/` y su única responsabilidad es: leer el sobre, construir `Peticion`, llamar a
`api.lecturas.leer` / `api.comandos.ejecutar` / `api.lecturas.documentos.leer_documento`, y traducir la
`Respuesta` o el error de vuelta al sobre.

Lo que **no** hace, y hay tests que lo comprueban sobre el árbol:

- No decide permisos: eso es `api.contrato.exigir`, que ya está probado.
- No proyecta ni filtra bloques: eso es `api.proyeccion`.
- No toca `engine/` directamente: ni un import.
- No añade validación propia de los datos del contrato. Si `Peticion` acepta algo, el servidor lo pasa; si
  lo rechaza, el servidor traduce el error. Una segunda validación aquí es una segunda verdad.

Las dependencias nuevas (`starlette`, `uvicorn`) van en un **extra** de `pyproject.toml`, no en las
obligatorias: el motor, el CLI y los 2.588 tests siguen corriendo sin ellas. `engine/` no las ve jamás.

---

## 4. Decisión 2 — La autenticación es un puerto, y el proveedor llega después

**Billy, 24/09/2026.** Misma disciplina que `Repositorio`: el contrato ahora, la implementación real cuando
haya cliente.

Se descartó integrar OIDC ya, no por pereza sino porque **sin cliente no se sabe contra qué proveedor ni,
sobre todo, cómo mapea sus grupos a nuestros ocho perfiles — y ese mapeo es la decisión de verdad**, no la
integración. Se descartó construir sesiones con usuario y contraseña: custodiar contraseñas añade una
responsabilidad que hoy no tenemos, y un sujeto delegado con empleados va a pedir su SSO corporativo.

**Contrato C28 — el puerto `Autenticador`.**

```python
class Autenticador(Protocol):
    def principal(self, peticion) -> Principal:
        """El principal de esta peticion, o levanta `ErrorAutenticacion` si no se puede establecer."""
```

- **Nunca devuelve `None` ni un principal anónimo.** O hay principal, o hay error: un principal «vacío» es
  la forma en que se cuelan las peticiones sin autenticar.
- El servidor **no sabe** cómo se autentica: recibe el puerto construido y lo usa.
- Los `perfiles` que devuelva se validan contra la matriz al usarse, como ya hace `api.permisos`.

**Contrato C29 — la implementación de desarrollo se niega a arrancar fuera de local.**

`AutenticadorDeDesarrollo` lee el principal de una cabecera, para poder abrir las pantallas contra datos de
prueba. Es exactamente la pieza que, olvidada en producción, regala el sistema entero. Por eso:

- **Falla al construirse** si no se le pasa una señal explícita de que esto es desarrollo, y esa señal no
  puede ser un valor por defecto.
- **Dice en cada respuesta** que la autenticación es de desarrollo, en `avisos`. Que se vea en la pantalla.
- Hay un test que comprueba que **no se puede instanciar sin la señal**, y otro que recorre el árbol para
  que ninguna ruta de arranque la elija por defecto.

Un `AutenticadorAusente` es el valor por defecto del servidor y **deniega todo** citando este ADR, con el
mismo patrón que `RepositorioAusente`: el sistema por defecto no autentica a nadie, en vez de autenticar a
cualquiera.

**Contrato C30 — el tenant se comprueba, no se cree.**

El sobre dice que el `tenant_id` del contexto lo declara la pantalla. El servidor lo compara con el del
principal y **deniega si no coinciden**, antes de llegar a `api/`. Es una segunda barrera, no la primera:
`api.contrato.comprobar_alcance` ya falla cerrado desde el 20/09. Que haya dos es deliberado.

---

## 5. Decisión 3 — Qué significa «FR-HTTP hecho»

**Billy, 24/09/2026.** Servidor y contrato, sin desplegar.

Con `FR1` aprendimos que «hecho» necesita definición explícita, así que aquí va sin ambigüedad:

**Entra**: el servidor publica `api/` entero; las pantallas de `FR1` se abren contra él **en local** y
funcionan; hay tests de extremo a extremo **por HTTP real**, no simulado.

**No entra, y se declara como entregable aparte** (`FR-DESPLIEGUE`): TLS, dominio, configuración de
producción y procedimiento de despliegue. Dependen de infra que no existe y de **dónde vive el sistema**,
que está ligado a `API-09` —si el certificado del perfil Modificación puede usarse desde infraestructura de
un tercero— y sigue esperando respuesta del gestor de la plataforma.

Dicho de otro modo: al terminar `FR-HTTP` una persona puede abrir la cola de revisión en su navegador contra
datos sintéticos. **No** puede haber un cliente real al otro lado.

---

## 6. Lo que queda para Billy

| Qué | Por qué llega aquí |
|---|---|
| **El proveedor de identidad y el mapeo de sus grupos a los ocho perfiles** | Es la decisión de verdad de la autenticación, y necesita un cliente delante. El puerto la espera |
| **`FR-DESPLIEGUE`**: dónde vive el sistema | Ligado a `API-09`. Sin esto no hay producción, por mucho servidor que haya |
| **Revisión jurídica de la monitorización de trabajadores** | Ya estaba abierta (`ADR-007`) y este entregable la acerca: un servicio en red con usuarios identificados es el momento en que deja de ser teórica |
| **Límites de tamaño y de frecuencia** | Un servidor que sirve documentos acepta subidas. Hoy no hay ni límite de tamaño ni límite de peticiones, y eso es una decisión de producto, no un detalle |

---

*`ADR-011` (contrato de `api/`) y `ADR-014` (FR1) siguen vigentes; este ADR los continúa. El sobre de
`front/compartido/api/transporte.ts` es la fuente de la forma: si este documento y aquel discrepan, se
arreglan los dos en la misma sesión.*
