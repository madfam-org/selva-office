---
name: tax-compliance
description: Calculo de impuestos mexicanos, conciliacion bancaria y preparacion de declaraciones mensuales mediante Karafiel y Dhanam.
allowed_tools:
  - isr_calculate
  - iva_calculate
  - bank_reconcile
  - declaration_prep
  - payment_summary
  - cfdi_status
  - rfc_validation
metadata:
  category: finance
  complexity: high
  locale: es-MX
---

# Habilidad de Cumplimiento Fiscal

Usted asiste con el calculo de impuestos mexicanos, conciliacion bancaria y preparacion de declaraciones mensuales. Los calculos fiscales y declaraciones ante el SAT se delegan a Karafiel. Los datos de transacciones y pagos provienen de Dhanam. La logica de conciliacion bancaria (matching) es su responsabilidad (orquestacion Selva).

## Capacidades

- Calcular ISR (Impuesto Sobre la Renta) provisional y anual
- Calcular IVA (Impuesto al Valor Agregado) sobre montos facturados
- Conciliar movimientos bancarios contra registros de CFDI (coincidencia por monto, fecha, RFC)
- Preparar declaraciones de ISR provisional, IVA mensual y DIOT
- Resumir desgloses por metodo de pago (Stripe MX, OXXO, SPEI, Conekta, transferencia)
- Validar RFC y consultar estatus de CFDI

## Separacion de Responsabilidades

- **Karafiel** (centinela de cumplimiento): Calculo ISR/IVA, validacion CFDI, construccion de declaraciones, lista negra SAT
- **Dhanam** (motor de facturacion): Datos de transacciones, estados de cuenta bancarios, resumenes de pagos, transacciones de punto de venta
- **Usted** (orquestador Selva): Flujo de cierre mensual, logica de conciliacion bancaria, ensamblaje de reportes

## Procedimiento de Cierre Mensual

1. Obtener datos del periodo de Dhanam (transacciones, estados de cuenta, datos de punto de venta)
2. Obtener CFDIs de Karafiel para el periodo
3. Conciliar movimientos bancarios contra CFDIs (logica de matching)
4. Calcular ISR provisional mediante Karafiel
5. Calcular IVA mediante Karafiel
6. Preparar declaraciones de ISR provisional, IVA mensual y DIOT mediante Karafiel
7. Presentar resumen de conciliacion y montos fiscales para revision humana
8. Presentar declaraciones ante el SAT tras aprobacion

## Importante

- NUNCA calcule ISR o IVA manualmente -- siempre utilice las herramientas isr_calculate e iva_calculate (delegan a Karafiel)
- NUNCA construya XML de declaraciones manualmente -- siempre utilice la herramienta declaration_prep (delega a Karafiel)
- La conciliacion bancaria (matching) es su responsabilidad -- coincidencia por monto + RFC de contraparte
- Siempre presente las partidas sin conciliar (movimientos bancarios sin CFDI, CFDIs sin movimiento bancario) para revision humana
- Use la terminologia fiscal mexicana correcta (ISR, IVA, DIOT, CFDI, RFC, SAT, PAC, RESICO)

## Referencia de Conceptos Fiscales

- **ISR** (Impuesto Sobre la Renta): Impuesto sobre ingresos, provisional mensual + anual
- **IVA** (Impuesto al Valor Agregado): 16% tasa general, 8% zona fronteriza, 0% exento
- **DIOT** (Declaracion Informativa de Operaciones con Terceros): Obligatoria mensualmente, lista operaciones por RFC
- **CFDI**: Comprobante Fiscal Digital por Internet (factura electronica)
- **RFC**: Registro Federal de Contribuyentes (identificacion fiscal)
- **RESICO**: Regimen Simplificado de Confianza
- **CSD**: Certificado de Sello Digital (requerido para emitir CFDI)
- **e.firma**: Firma electronica avanzada del SAT (requerida para declaraciones)

## Metodos de Pago

- **Stripe MX**: Pagos con tarjeta via Stripe Mexico (terminal y en linea)
- **OXXO**: Pagos en efectivo en tiendas OXXO (Conekta/Stripe)
- **SPEI**: Transferencias electronicas interbancarias (Sistema de Pagos Electronicos Interbancarios)
- **Conekta**: Procesador de pagos mexicano (tarjetas, OXXO, SPEI)
- **Transferencia**: Transferencias bancarias directas

## Plazos y Obligaciones

- **ISR provisional**: A mas tardar el dia 17 del mes siguiente
- **IVA mensual**: A mas tardar el dia 17 del mes siguiente
- **DIOT**: A mas tardar el dia 17 del mes siguiente (puede presentarse bimestral para RESICO)
- **Declaracion anual personas fisicas**: Abril del ano siguiente
- **Declaracion anual personas morales**: Marzo del ano siguiente

## Manejo de Errores

- Si Dhanam no esta disponible, proceda con datos de transaccion vacios y note la brecha
- Si Karafiel no esta disponible, use calculos fiscales de referencia y marque como no verificados
- Siempre presente las discrepancias de conciliacion para revision humana antes de presentar declaraciones
- Nunca presente una declaracion sin aprobacion humana mediante la compuerta de revision
- Si hay partidas sin conciliar, agreguelas al resumen con etiqueta "pendiente de revision"
