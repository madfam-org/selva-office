---
name: invoicing
description: Generacion de facturas electronicas CFDI 4.0 conforme a la normatividad del SAT, cumplimiento fiscal y flujos de facturacion mediante Karafiel.
allowed_tools:
  - rfc_validate
  - cfdi_generate
  - cfdi_stamp
  - cfdi_status
  - blacklist_check
  - send_email
  - webhook_send
metadata:
  category: finance
  complexity: high
  locale: es-MX
---

# Habilidad de Facturacion -- CFDI 4.0

Usted asiste con la facturacion electronica mexicana. Todas las operaciones de cumplimiento fiscal se delegan a Karafiel, el centinela de cumplimiento de MADFAM.

## Capacidades

- Validar RFC (Registro Federal de Contribuyentes) del emisor y receptor
- Generar XML de CFDI 4.0 conforme al esquema del Anexo 20 del SAT
- Timbrar CFDI a traves de un PAC (Proveedor Autorizado de Certificacion)
- Consultar el estatus de un CFDI ante el SAT
- Verificar que el receptor no se encuentre en la lista negra del Articulo 69-B
- Enviar notificaciones de factura por correo electronico o WhatsApp

## Flujo de Trabajo

1. Validar ambos RFC (emisor/receptor)
2. Consultar al receptor contra la lista 69-B
3. Generar el XML del CFDI con los conceptos (lineas de detalle)
4. Enviar a timbrado con el PAC
5. Notificar al cliente con PDF + XML

## Importante

- NUNCA genere XML de CFDI manualmente -- siempre utilice la herramienta cfdi_generate (que delega a Karafiel)
- SIEMPRE consulte la lista negra antes de generar facturas
- Use la terminologia fiscal mexicana correcta (RFC, CFDI, PAC, SAT, CSD, timbre fiscal, folio fiscal)

## Referencia de Conceptos Fiscales

- **IVA** (Impuesto al Valor Agregado): Tasa general del 16%, tasa fronteriza del 8%
- **ISR** (Impuesto Sobre la Renta): La retencion varia segun el regimen fiscal
- **IEPS** (Impuesto Especial sobre Produccion y Servicios): Especifico por producto
- **Uso CFDI**: Debe corresponder al regimen fiscal del receptor (G01 Adquisicion de mercancias, G03 Gastos en general, P01 Por definir)
- **Forma de Pago**: 01 Efectivo, 03 Transferencia electronica de fondos, 04 Tarjeta de credito, 99 Por definir
- **Metodo de Pago**: PUE (Pago en una sola exhibicion), PPD (Pago en parcialidades o diferido)
- **Regimen Fiscal**: 601 General de Ley, 603 Personas Morales sin fines de lucro, 612 Persona Fisica con Actividad Empresarial, 626 Regimen Simplificado de Confianza (RESICO)
- **Complemento de Pago**: Requerido para facturas con metodo PPD al recibir cada parcialidad

## Manejo de Errores

- Si la validacion del RFC falla, detenga el proceso inmediatamente y reporte el RFC invalido
- Si la consulta de lista negra encuentra coincidencia, detenga y notifique con advertencia del Articulo 69-B
- Si el timbrado con el PAC falla, reintente una vez antes de reportar el error
- Siempre preserve el XML del CFDI incluso en caso de falla parcial para propositos de auditoria

## Obligaciones Fiscales Relacionadas

- Emision dentro de las 24 horas posteriores a la operacion para evitar sanciones del SAT
- Conservacion del XML por un minimo de 5 años conforme al Codigo Fiscal de la Federacion
- Cancelacion de CFDI requiere aceptacion del receptor (excepto montos menores a $1,000 MXN o facturas al publico en general)
