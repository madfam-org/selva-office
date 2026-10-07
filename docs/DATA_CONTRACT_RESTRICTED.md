# Contrato de datos — el nivel `restricted` de Selva

**Para quien consume Selva** (equipos de producto del ecosistema) y para
quien tiene que responderle a un cliente, al titular de los datos o a una
autoridad qué pasa exactamente con un dato sensible.

Escrito en español llano a propósito: si una frase de aquí no se puede
sostener frente a la persona cuyos datos se tratan, está mal escrita o el
sistema está mal hecho.

---

## 1. Los cuatro niveles

Selva no adivina qué tan sensible es lo que le mandas. **Tú lo declaras**
en el header `X-Sensitivity`, y ese header es **obligatorio**.

| Nivel | Qué significa | A dónde va |
|---|---|---|
| `public` | Puede publicarse. Marketing, texto de sitio. | Proveedor de nube más barato |
| `internal` | Interno de MADFAM. No confidencial de cliente. | Proveedor de nube |
| `confidential` | Confidencial de un cliente. | **Sólo modelo local** |
| `restricted` | Dato personal sensible o regulado: clínico, de menores, fiscal, laboral. | **Sólo modelo local** |

Si no mandas el header, o mandas un valor que no está en esta lista, la
llamada **se rechaza con 400**. No se adivina, no se degrada al nivel más
barato, no se procesa. Antes esto no era así: la ausencia del header
significaba `public`, y un valor mal escrito se ignoraba en silencio. Esa
era la peor falla posible, porque el modo de falla por defecto era «mandar
el dato a la nube más barata».

---

## 2. Qué garantiza `restricted` (y qué no)

### Lo que sí

1. **El dato no sale del perímetro.** Una llamada `restricted` sólo puede
   ser servida por el modelo local que corre dentro del cluster. No hay
   ningún camino de código por el que llegue a Anthropic, OpenAI,
   DeepInfra ni ningún otro tercero.

2. **Ningún atajo puede saltarse esa regla.** La sensibilidad se evalúa
   **antes** que cualquier otra decisión de ruteo. Ni el `task_type`, ni
   las listas de prioridad de la configuración de la organización, ni la
   cadena de reintentos pueden ampliar el conjunto de proveedores
   permitidos. Si alguien configura «los resúmenes van a DeepInfra», esa
   configuración es **rechazada** para datos `restricted` y queda un
   WARNING en la bitácora.

   *Esto no era así antes.* El ruteo por `task_type` se evaluaba primero
   y ganaba. Un consumidor `restricted` se salvaba de casualidad, porque
   los tipos de tarea que usaba no estaban en el catálogo interno. Estaba
   protegido por el nombre que eligió, no por una garantía. Ahora es una
   garantía.

3. **Si no hay modelo local, la llamada falla.** Devuelve **503** con el
   código `local_backend_unavailable`. Nunca se sirve desde la nube «para
   que al menos funcione». Falla cerrado.

4. **No se guarda ni el texto que mandas ni el que responde.** La bitácora
   de consumo registra: organización, quién llamó, proveedor, modelo,
   cuántos tokens y cuánto costó. **No hay ninguna columna donde quepa un
   prompt o una respuesta.** Las líneas de bitácora del gateway llevan
   metadatos de ruteo (organización, tipo de tarea, nivel de
   sensibilidad) y nunca contenido. Hay pruebas automáticas que fallan si
   alguna vez el contenido se filtra a una bitácora o a la base.

5. **Un piso por cliente, por si el header se pierde.** Una organización
   regulada puede declarar un `sensitivity_floor`. Con el piso en
   `restricted`, aunque una llamada llegue marcada como `public` —header
   perdido en un salto, proxy que lo borra, superficie nueva que se
   olvidó de ponerlo— se trata como `restricted`. El piso sube, nunca
   baja: quien pida más protección que su piso, la conserva. La única
   manera de quedar por debajo del piso es una **excepción por tarea**,
   explícita, autorizada y acotada (sección 6).

### Lo que no

1. **No es cifrado de extremo a extremo.** El texto se procesa en claro
   en la memoria del modelo local, dentro del cluster.

2. **No es una afirmación sobre los otros niveles.** `public` e
   `internal` sí van a proveedores de nube. Si tienes duda de qué nivel
   corresponde, sube de nivel: el costo de marcar de más es latencia; el
   de marcar de menos es un dato personal en un tercero.

3. **No sustituye la minimización.** Selva no puede saber que le mandaste
   un nombre completo cuando bastaban iniciales. **Manda lo mínimo.** La
   responsabilidad de no incluir lo que no hace falta es del llamador.

4. **No hay afirmación de «cero retención» (ZDR) con proveedores de
   nube.** No existe hoy, ni documentada ni aplicada. El sustituto
   arquitectónico es la localidad: por eso el dato regulado se sirve
   localmente en lugar de confiar en la promesa de un tercero. La
   excepción de la sección 6 sí depende de los términos de dos
   proveedores, y por eso lista qué hay que confirmar antes de
   encenderla.

---

## 3. Por qué esto importa legalmente

Cuando MADFAM trata datos personales de un cliente como **encargado**
bajo la LFPDPPP, que el encargado trate el dato no es una
*transferencia* sino una *remisión*.

Un aviso de privacidad que dice que **no se transfieren los datos a
terceros** es defendible **mientras la inferencia se sirva dentro de la
cadena de encargado** — es decir, dentro del perímetro, no en un
proveedor de nube externo.

Si `restricted` alguna vez se sirviera desde un tercero, esa frase
quedaría en falso frente a los titulares de los datos. De ahí que la
regla sea estructural en el código y no una convención, y que la falla
sea cerrada (503) en vez de abierta.

---

## 4. Cómo llamar bien (contrato del cliente)

```http
POST /v1/chat/completions
Authorization: Bearer <token>
X-Sensitivity: restricted          ← obligatorio, literal fijo en tu código
X-Selva-Tenant-Org: <org id>       ← tu organización
X-Task-Type: summarization         ← dado de alta para tu tenant
Content-Type: application/json
```

Reglas para el llamador:

1. **Fija el literal en el código.** Que ninguna superficie pueda bajar
   el nivel por descuido: una constante, no un parámetro (por ejemplo,
   `const SELVA_SENSITIVITY = 'restricted'`).
2. **Manda tu propio `AbortSignal`**, un poco por encima del deadline del
   servidor (p. ej., 45 s de cliente contra un deadline de servidor de
   40 s).
3. **Recorta la entrada** antes de mandarla. No dependas del tope del
   servidor.
4. **Degrada con gracia.** Si Selva no está configurado o responde 503,
   esconde la superficie de IA; el trabajo manual debe seguir intacto.
5. **No registres el prompt de tu lado tampoco.** El contrato se rompe
   igual si el dato queda en la bitácora del consumidor.

### Qué significa cada respuesta

| Código | Significa | Qué hacer |
|---|---|---|
| `200` | Listo. | Un humano revisa antes de enviar/guardar |
| `400 missing_sensitivity` | No mandaste el header | **Bug tuyo.** Alerta a ops; no lo trates como «la IA no pudo» |
| `400 invalid_sensitivity` | Valor fuera del enum | **Bug tuyo.** El log del gateway nombra el valor |
| `400 task_type_not_allowed` | Superficie no dada de alta | Alta previa en la política del tenant |
| `429 tenant_rate_limited` | Ráfaga | Respeta `Retry-After`. Revisa si hay un bucle |
| `504 inference_timeout` | Tardó más que el deadline | Reintento manual del usuario; entrada más corta |
| `503 local_backend_unavailable` | No hay modelo local | **IA no disponible.** Esconde la superficie. No es un error del usuario |

---

## 5. Si alguien pregunta

**«¿Mis datos van a ChatGPT / a una IA de Estados Unidos?»**
No, si están marcados como `restricted` o `confidential`. Esos se
procesan con un modelo que corre en la infraestructura de MADFAM, dentro
del mismo perímetro donde ya vive el dato. No se envían a ningún
proveedor externo, y si ese modelo local no está disponible la función
simplemente no funciona: no hay un plan B que mande el dato afuera.

**«¿Se guarda lo que escribo?»**
El texto que se manda al modelo y el que el modelo responde no se
guardan. Sólo se registra cuánto se usó (cuántos tokens, qué modelo,
cuánto costó) para poder facturar y vigilar el gasto. El resultado que la
persona usuaria decida conservar se guarda en el sistema que lo pidió
—no en Selva— y siempre después de que lo revise.

**«¿La IA decide algo?»**
No. Redacta un borrador. Siempre hay una persona que lo lee, lo corrige
y decide si se usa.

---

## 6. Excepción: una tarea seudonimizada

Hay **una** excepción al piso `restricted`, para **un** tenant y **una**
tarea. Existe porque el cliente, como responsable de los datos, autorizó
que los borradores de la tarea `family-feedback` los redacten Anthropic
(Claude) u OpenAI **sólo con texto seudonimizado**: sin nombres. El dueño
de MADFAM registró esa decisión el 2026-10-07. Nada más cambia: las
minutas (`summarization`), cualquier otra tarea y cualquier llamada que
no cumpla todo lo de abajo siguen siendo sólo modelo local.

### Cuándo aplica

Sólo si se cumple **todo** esto a la vez:

1. la llamada es del tenant que tiene la excepción en
   `infra/k8s/production/tenant-policies.yaml`;
2. `X-Task-Type` es la tarea exceptuada (`family-feedback`);
3. `X-Sensitivity` es exactamente `internal`. Ni `public` (no abre la
   excepción: se le aplica el piso), ni `restricted`/`confidential` (quien
   pide más protección la conserva);
4. lleva `X-Pseudonymized: true`, la constancia del cliente de que
   seudonimizó el texto.

Si falta cualquiera, se aplica el piso como si la excepción no existiera.
Y si una llamada manda `X-Pseudonymized` pero no encaja en una excepción
válida —otra tarea, otro tenant, configuración rota o ausente— se trata
como `restricted`: nunca como el `internal` que declaró.

```http
POST /v1/chat/completions
Authorization: Bearer <token>
X-Selva-Tenant-Org: <org id>
X-Task-Type: family-feedback
X-Sensitivity: internal            ← sólo en esta llamada
X-Pseudonymized: true              ← sólo si de verdad se seudonimizó
Content-Type: application/json
```

### Qué hace Selva dentro de la excepción

- **Sólo dos proveedores, en orden.** Anthropic (`claude-sonnet-4-6`)
  primero; OpenAI (`gpt-4o`) sólo si Anthropic falla por una causa
  transitoria (caída, saturación, 429, 5xx, saldo insuficiente). Un error
  de credenciales o de modelo inexistente no salta al otro: se
  reporta. Ningún otro proveedor —ni Groq, ni OpenRouter, ni DeepInfra, ni
  Gemini, ni Grok, ni otro— puede recibir la llamada: el conjunto es la
  lista de la excepción intersectada con el conjunto `internal` del
  ruteador, y ni la configuración de la organización ni las asignaciones
  por tarea pueden ampliarlo. El modelo lo fija la excepción; el campo
  `model` que mande el cliente se ignora. Si ninguno de los dos responde,
  la llamada falla con **503 `exception_providers_unavailable`**; no se
  busca a otro.
- **Una última revisión, burda a propósito.** Antes de enviar, Selva
  rechaza con **400 `direct_identifier_detected`** la llamada que traiga
  un correo, un teléfono, una CURP, un RFC o contenido que no sea texto
  (una imagen no se puede revisar). No envía nada a ningún proveedor y en
  la bitácora sólo queda el tipo de dato encontrado, nunca el dato. No
  detecta nombres: eso le toca al cliente.
- **Los mismos límites del tenant.** Tope de salida, plazo, límite de
  peticiones por minuto y presupuesto siguen igual.
- **Nada se guarda.** Igual que en `restricted`: ni el texto enviado ni
  la respuesta. La bitácora de consumo registra organización, servicio
  que llamó, tarea, proveedor, modelo, tokens, costo y latencia.
- **Si la configuración está mal, no aplica.** Una excepción inválida se
  descarta al arrancar con un ERROR en la bitácora y el piso sigue
  vigente. Al arrancar, el gateway escribe una línea `task exception in
  force` por cada excepción activa: así se confirma que está —o que ya no
  está—.

### Obligaciones del cliente

1. **Seudonimizar antes de llamar.** Quitar todo nombre (de la persona
   usuaria, de su familia, del personal) y todo identificador directo
   (correo, teléfono, CURP, RFC, domicilio, número de expediente) y
   sustituirlos por marcadores (`[PERSONA_1]`).
2. **Verificar antes de enviar.** Si queda un nombre conocido, **no se
   envía**. El cliente falla cerrado; no «manda casi todo».
3. **Atestiguar con verdad.** `X-Pseudonymized: true` va sólo en la
   llamada que pasó los pasos 1 y 2. Nunca como constante del cliente.
4. **Declarar `internal` sólo ahí.** Todo lo demás sigue con
   `X-Sensitivity: restricted` fijo.
5. **Sólo texto.** Nada de imágenes ni adjuntos.
6. **Reinsertar los nombres localmente.** La respuesta vuelve con
   marcadores; el cliente pone los nombres de vuelta en su lado, y la
   tabla marcador ↔ nombre vive sólo en la memoria de esa petición: no se
   envía, no se registra, no se guarda.
7. **Tratar las respuestas nuevas como lo que son.** `400
   direct_identifier_detected` es un defecto de la seudonimización del
   cliente: no se reintenta el mismo texto, se alerta. `503
   exception_providers_unavailable` es «IA no disponible»: se esconde la
   superficie.

### Términos de los proveedores que el dueño confirma antes de encender

Esto **no está en el código** y Selva no puede verificarlo. Lo confirma el
dueño de MADFAM con cada proveedor —Anthropic y OpenAI— antes de encender
la excepción y cada vez que cambien sus términos, y lo deja registrado en
el repositorio privado de operaciones:

- **Sin entrenamiento:** que los datos enviados por la API no se usan
  para entrenar modelos.
- **Retención:** cuánto tiempo conserva el proveedor entradas y salidas
  de la API y con qué excepciones (p. ej., revisión por abuso o por
  incumplimiento de sus políticas).
- **Cero retención (ZDR) donde exista:** si la cuenta de MADFAM tiene, o
  puede tener, retención cero para el endpoint que usa Selva (chat
  completions en OpenAI, Messages en Anthropic) y, si no, cuál es la
  retención estándar. Selva no pide almacenamiento: en OpenAI no envía el
  parámetro `store`.
- **Acuerdo de tratamiento de datos (DPA) y lugar de procesamiento:** que
  esté aceptado y en qué país se procesan los datos.

Que el texto vaya seudonimizado no lo vuelve anónimo: el responsable
conserva la correspondencia y puede re-identificarlo. Que su aviso de
privacidad y sus contratos reflejen este envío a proveedores externos le
corresponde al responsable y a su asesoría; el código no lo resuelve.

### Cómo se apaga

Se borra el bloque `task_exceptions` del tenant en
`infra/k8s/production/tenant-policies.yaml` y se reinician los pods del
inference-gateway. Desde ese momento todas las llamadas de esa tarea
vuelven al piso `restricted` (sólo modelo local) y ninguna llega a un
proveedor de nube. Para quitar sólo a un proveedor, se borra de
`allowed_providers` y de `models`.

---

## 7. Referencias

- Runbook de encendido de un tenant `restricted`: se conserva en el
  repositorio privado de operaciones.
- Ruteo y proveedores: [INFERENCE_PROVIDERS.md](INFERENCE_PROVIDERS.md)
- Residencia por tenant (borrador): [rfcs/0020-per-tenant-data-residency.md](rfcs/0020-per-tenant-data-residency.md)
- Código: `packages/inference/madfam_inference/router.py` (frontera de
  sensibilidad), `madfam_inference/tenant_policy.py` (pisos, topes y
  excepciones por tarea), `madfam_inference/identifier_guard.py` (la
  revisión de identificadores),
  `apps/nexus-api/nexus_api/routers/inference_proxy.py` (validación).
- Pruebas que sostienen cada afirmación de este documento:
  `packages/inference/tests/test_router_sensitivity_precedence.py`,
  `apps/nexus-api/tests/test_inference_proxy_sensitivity.py` y, para la
  sección 6, `packages/inference/tests/test_tenant_task_exception.py`,
  `packages/inference/tests/test_identifier_guard.py` y
  `apps/nexus-api/tests/test_inference_proxy_task_exception.py`.
