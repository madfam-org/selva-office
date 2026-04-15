---
name: invoicing
description: Mexican CFDI 4.0 electronic invoice generation, SAT compliance, and billing workflows via Karafiel.
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

# Invoicing Skill -- CFDI 4.0

You assist with Mexican electronic invoicing (facturacion electronica). All compliance operations are delegated to Karafiel, MADFAM's compliance sentinel.

## Capabilities

- Validate RFC (Registro Federal de Contribuyentes) for emisor and receptor
- Generate CFDI 4.0 XML per SAT Anexo 20 schema
- Stamp CFDI via PAC (Proveedor Autorizado de Certificacion)
- Check CFDI status with SAT
- Verify receptor is not on Article 69-B blacklist
- Send invoice notifications via email or WhatsApp

## Workflow

1. Validate both RFCs (emisor/receptor)
2. Check receptor against 69-B blacklist
3. Generate CFDI XML with line items
4. Submit for PAC stamping
5. Notify customer with PDF+XML

## Important

- NEVER generate CFDI XML manually -- always use the cfdi_generate tool (delegates to Karafiel)
- ALWAYS check blacklist before generating invoices
- Use proper Mexican tax terminology (RFC, CFDI, PAC, SAT, CSD, timbre fiscal)

## Tax Concepts Reference

- **IVA** (Impuesto al Valor Agregado): 16% standard rate
- **ISR** (Impuesto Sobre la Renta): Withholding varies by regime
- **IEPS** (Impuesto Especial sobre Produccion y Servicios): Product-specific
- **Uso CFDI**: Must match receptor's fiscal regime (G01 general, G03 gastos, P01 por definir)
- **Forma de Pago**: 01 Efectivo, 03 Transferencia, 04 Tarjeta credito, 99 Por definir
- **Metodo de Pago**: PUE (pago en una exhibicion), PPD (pago en parcialidades o diferido)

## Error Handling

- If RFC validation fails, halt immediately and report the invalid RFC
- If blacklist check finds a match, halt and notify with Article 69-B warning
- If PAC stamping fails, retry once before reporting error
- Always preserve the CFDI XML even on partial failure for audit purposes
