# mapping/ — modelo canónico → destino

Mapeos **declarativos, por ficha y por destino**. Se crean en el Sprint 3 (`docs/06` S3.4). Vacío en la Fase 0.

| Fichero | Destino | Estado |
|---|---|---|
| `IND240.handoff.yaml` | Carpeta ordenada + manifiesto + informe para el tenant | S3.4 |
| `IND240.api.yaml` | Payload de detalle de la API oficial | Espera `TODO(API-08)` (diccionario) |
| `manifiesto.handoff.yaml` | Manifiesto interno en el handoff | S3.4 |
| `manifiesto.api.yaml` | Manifiesto oficial | Espera `TODO(API-02)` |

Regla: si un cambio en la API oficial exige tocar `engine/`, el diseño está mal. Lo desconocido se marca `TODO(API-xx)` con fila en `docs/HUECOS.md`; nunca se inventa un campo.
