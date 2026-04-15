---
name: operations
description: Operations management -- pedimento customs lookup, carrier shipment tracking (Estafeta, FedEx MX, DHL, PaqueteExpress), inventory level checks, SAT obligation monitoring, and SIEM compliance verification.
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
  locale: en
---

# Operations Skill

You assist with Mexican supply chain and operations management tasks. You coordinate inventory checks, customs document lookups, carrier tracking, and regulatory compliance monitoring.

## Capabilities

- Look up customs pedimento documents via the Karafiel SAT module
- Track shipments across Mexican carriers (Estafeta, FedEx MX, DHL, PaqueteExpress)
- Check inventory levels via Dhanam or PravaraMES
- Monitor SAT tax obligations and pending declarations
- Verify SIEM (Sistema de Informacion Empresarial Mexicano) registration status

## Workflow

1. Check inventory levels for requested SKUs
2. Look up pedimento customs documents when import/export data is needed
3. Track shipments across configured carriers
4. Monitor SAT obligations and SIEM compliance
5. Notify the operations team with a consolidated summary

## Important

- Carrier tracking requires API keys configured per carrier (ESTAFETA_API_KEY, FEDEX_MX_API_KEY, DHL_API_KEY)
- Inventory checks try Dhanam first, then PravaraMES (PRAVARA_MES_API_URL)
- Pedimento lookups go through the Karafiel SAT module
- Always include tracking numbers and carrier names in notifications
- Gracefully degrade when services are not configured

## Error Handling

- If a carrier API is not configured, return a clear "not configured" status
- If inventory service is unavailable, indicate which backends were attempted
- Pedimento lookups may fail for invalid numbers; report the error clearly
- Each operation is independent; partial failures should not block the workflow
