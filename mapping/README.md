# mapping/ — modelo canónico → destino

Mapeos **declarativos, por ficha y por destino**. Los carga `salida/mapeo.py` (contrato C5 de `ADR-009` §3): un `origen` es una ruta punteada del modelo canónico ya serializado, **solo selección** — sin expresiones, sin funciones y sin `eval`. Una clave desconocida en el YAML es error **de carga**, no de entrega.

| Fichero | Destino | Estado |
|---|---|---|
| `IND240.handoff.yaml` | Carpeta ordenada + manifiesto + informe para el tenant | `EXISTE` (S3.4) |
| `IND240.api.yaml` | Payload de detalle de la API oficial | Espera `TODO(API-08)` (diccionario) |
| `manifiesto.handoff.yaml` | Manifiesto interno en el handoff (nombre de fichero, orden y etiquetas) | `EXISTE` (S3.4) |
| `manifiesto.api.yaml` | Manifiesto oficial | Espera `TODO(API-02)` |

Regla: si un cambio en la API oficial exige tocar `engine/`, el diseño está mal. Lo desconocido se marca `TODO(API-xx)` con fila en `docs/HUECOS.md`; nunca se inventa un campo.
