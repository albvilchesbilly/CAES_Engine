"""Salida (S5): lo que convierte una actuacion evaluada en algo entregable (`docs/03` §10, `docs/01` §3.8).

Aqui empieza el unico paquete que mira hacia fuera. Tres reglas lo gobiernan desde el primer modulo:

1. **Nada en `salida/` inventa un campo de la API oficial.** Lo que la plataforma (OMIE/MIBGAS) no ha
   publicado es un hueco enumerado, `TODO(API-xx)` con su fila en `docs/HUECOS.md`, nunca una suposicion.
2. **Dependencias hacia dentro.** `salida/` puede importar de `engine/`; `engine/` nunca importa de
   `salida/`. Con `salida/` entera borrada, el Engine sigue dando veredicto.
3. **La firma es un acto humano.** No existe `salida/firma/`: solo se registra el evento `FirmaRegistrada`
   de actor humano. Ningun componente nuestro firma actos administrativos ni custodia certificados de
   representante (`docs/02` §6.2, `docs/03` §10.3).

Lo que hay hoy (S3.3 y S3.4):

- `puerto.py` — el contrato: `Paquete`, `Acuse`, `EstadoPlataforma`, `TareaPendiente` y el `Protocol` con las
  cuatro operaciones. Tipos **nuestros**: el conector de S3.7 traducira, no heredara.
- `mapeo.py` — `mapping/<FICHA>.<destino>.yaml` como configuracion. Solo selecciona rutas del modelo
  canonico; dar de alta una ficha en la salida es anadir un YAML.
- `constructor/` — el manifiesto interno y su verificacion de integridad.
- `handoff/` — la carpeta ordenada que recibe el tenant, reverificada despues de escribirla.
- `simulador/` — la plataforma simulada, solo con lo publicado.
- `transporte/` — frontera declarada: firma peticiones con certificado de usuario, y hoy se niega.

Falta `api_oficial/`, que es S3.7 y espera el diccionario (`TODO(API-01)`: ver docs/HUECOS.md).

No hay fachada: cada pieza se importa de su modulo (`from salida.handoff import AdaptadorHandoff`). Un
reexport aqui obligaria a cargar el simulador para usar el handoff, y son adaptadores independientes.
"""

from __future__ import annotations

__all__: list[str] = []
