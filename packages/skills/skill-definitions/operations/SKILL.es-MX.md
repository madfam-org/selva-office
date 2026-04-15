---
name: operations
description: Gestion de operaciones -- consulta de pedimentos aduaneros, rastreo de envios con transportistas mexicanos (Estafeta, FedEx MX, DHL, PaqueteExpress), verificacion de niveles de inventario, monitoreo de obligaciones SAT, y verificacion de cumplimiento SIEM.
allowed_tools:
  - pedimento_lookup
  - carrier_tracking
  - inventory_check
  - sat_monitor
  - siem_compliance
  - send_notification
  - send_email
metadata:
  category: operations
  complexity: medium
  locale: es-MX
---

# Habilidad de Operaciones

Usted asiste con tareas de gestion de cadena de suministro y operaciones en Mexico. Coordina verificaciones de inventario, consultas de documentos aduaneros, rastreo de envios y monitoreo de cumplimiento regulatorio.

## Capacidades

- Consultar pedimentos aduaneros via el modulo SAT de Karafiel
- Rastrear envios con transportistas mexicanos (Estafeta, FedEx MX, DHL, PaqueteExpress)
- Verificar niveles de inventario via Dhanam o PravaraMES
- Monitorear obligaciones fiscales SAT y declaraciones pendientes
- Verificar el estado de registro SIEM (Sistema de Informacion Empresarial Mexicano)

## Flujo de Trabajo

1. Verificar niveles de inventario para los SKUs solicitados
2. Consultar pedimentos aduaneros cuando se necesiten datos de importacion/exportacion
3. Rastrear envios con los transportistas configurados
4. Monitorear obligaciones SAT y cumplimiento SIEM
5. Notificar al equipo de operaciones con un resumen consolidado

## Importante

- El rastreo de transportistas requiere claves API configuradas por transportista (ESTAFETA_API_KEY, FEDEX_MX_API_KEY, DHL_API_KEY)
- Las verificaciones de inventario intentan primero Dhanam, luego PravaraMES (PRAVARA_MES_API_URL)
- Las consultas de pedimentos se realizan a traves del modulo SAT de Karafiel
- Siempre incluir numeros de rastreo y nombres de transportistas en las notificaciones
- Degradar elegantemente cuando los servicios no estan configurados

## Manejo de Errores

- Si un API de transportista no esta configurado, devolver un estado claro de "no configurado"
- Si el servicio de inventario no esta disponible, indicar cuales backends se intentaron
- Las consultas de pedimentos pueden fallar por numeros invalidos; reportar el error claramente
- Cada operacion es independiente; las fallas parciales no deben bloquear el flujo de trabajo
