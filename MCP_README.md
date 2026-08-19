# Decklar Supply Chain MCP Server

The Decklar Supply Chain MCP Server exposes Decklar's shipment, tracking device ("bee"), location, asset, and webhook APIs as [MCP](https://modelcontextprotocol.io) tools, so LLM agents and MCP-compatible clients (Claude, autogen, custom agents, etc.) can query supply-chain data conversationally.

## Endpoints

| Transport | URL | Notes |
|---|---|---|
| Streaming HTTP (recommended) | `https://mcp-server.decklar.com/mcp` | `POST /mcp` handles JSON-RPC (`initialize`, `tools/list`, `tools/call`). `GET /mcp` is a long-lived SSE stream for server-to-client notifications. |
| SSE (legacy) | `https://mcp-server.decklar.com/sse` | `GET /sse` opens the stream, `POST /messages` sends requests. |

Both transports share the same tools and authentication.

## Authenticating

Every request is checked by an API-key/OAuth middleware before it reaches either transport. Supported credentials, in order of precedence:

1. **`OAuth 2.0 (recommended)`** — sign in via the server's Keycloak-backed OAuth flow and send the issued token as `Authorization: Bearer <token>`. The server publishes standard discovery documents at `/.well-known/oauth-protected-resource` and `/.well-known/oauth-authorization-server`, and 401 responses include a `WWW-Authenticate` header pointing MCP clients (like Claude) to the right auth flow, so most MCP clients can complete this automatically. Required scopes: `openid profile email offline_access`. Once authenticated, reuse the `Mcp-Session-Id` header returned by the server to skip re-validation for up to 1 hour (Streaming HTTP only).
2. **`Authorization: Bearer <token>`** — a legacy Roambee API key passed as a bearer token.
3. **`roambee-apikey` header** — your Roambee API key. This is the simplest and recommended method.
4. **`roambee-apikey` query parameter** — same as above, passed in the URL. Prefer the header form when possible.
5. **`Session cookie`** — if you're already authenticated to the Decklar portal in-browser, the cookie is validated and exchanged for an API key automatically.

## Available tools

All tools are read-only. Every tool accepts an optional `api_key` parameter — if you've already authenticated the connection (via header, Bearer token, or cookie), you can omit it and the server uses your session's key automatically.

**Discovery helpers**
- `list_custom_fields` — Lists the active custom field definitions configured on the account — each field's display name, its underlying es_identifier (used in filter queries), and its data type (string, number, date, etc). This is a discovery tool: it doesn't return shipment data itself, but tells the agent what account-specific fields it can filter fetch_shipments on, since every Decklar account defines its own custom fields.
Example questions: "What custom fields do we have on shipments?" / "Can I filter shipments by 'PO Number'? What's that field called internally?" / "Show me shipments where the custom field 'Customer Priority' is High" (agent calls this first to resolve the field name before calling fetch_shipments).
- `list_device_types` — Lists device type aliases — the mapping between user-friendly names (e.g. "temperature logger", "GPS tracker") and the system's internal device type text. Used so the agent can translate a user's casual terminology into a valid filter value for search_bees.
Example questions: "What types of bees do we have?" / "Show me all temperature sensors" (agent resolves "temperature sensors" to the correct device_type value first) / "What device categories exist on my account?"

**Shipments**
- `fetch_shipments(filter_query, size=20, offset=0, fields, order_by)` — Searches shipments with flexible filtering (by name, account, bee name/IMEI, origin/destination location, creation date, beacon-enabled flag, multimodal flag, shipment type, or any custom field), pagination, field selection, and sorting. This is the main entry point for shipment-related questions.
Example questions: "Show me all shipments created in the last 7 days" / "Find shipments going to our Chicago warehouse" / "List shipments using bee IMEI 123456789012345" / "Which shipments have beacon tracking enabled?" / "Show shipments where Customer Priority is High, sorted by creation date."
- `fetch_shipment_details(shipment_id)` — Retrieves full details and current status for a single shipment, given its shipment ID. Used once a specific shipment has been identified (often after fetch_shipments).
Example questions: "What's the status of shipment SHP-2024-001?" / "Give me the full details on that shipment we just found"
- `fetch_shipment_alerts(shipment_id)` — Retrieves alerts (temperature excursions, delays, tampering, geofence violations, etc.) raised against a specific shipment.
Example questions: "Were there any temperature alerts on this shipment?" / "Show me all alerts for shipment SHP-2024-001"
- `fetch_mkt_shipments(shipment_id)` — Retrieves Mean Kinetic Temperature (MKT) values for a shipment — a single computed metric summarizing cumulative thermal exposure, commonly required for cold-chain/pharma compliance reporting.
Example questions: "What was the MKT for this shipment?" / "Did this shipment stay within acceptable kinetic temperature limits?"
- `fetch_shipment_template` — Lists the shipment templates configured on the account (predefined shipment configurations/profiles used when creating new shipments).
Example questions: "What shipment templates do we have set up?" / "Show me our standard shipment configurations."

**Bees (tracking devices)**
- `fetch_bee_messages(bee_id, start, end, days, active)` — Retrieves raw telemetry messages (location, temperature, humidity, battery, etc.) sent by a specific tracking device (identified by IMEI), optionally filtered by a time window (start/end epoch seconds, or a rolling number of days) and active status.
Example questions: "Show me the last 3 days of readings from bee 123456789012345" / "What temperature data did this device report between June 1 and June 5?"
- `fetch_bees(active=1, offset=0, limit=10)` — Returns a paginated list of tracking devices (bees) on the account, filterable by active/inactive status.
Example questions: "List all our active bees" / "How many tracking devices do we have?" / "Show me the next page of devices."
- `search_bees(filter_query, size, offset, fields)` — A more targeted search over bees — filter by device type, bee number, bee name, IMEI, active status, communication status (online/offline), account, or creation date. Useful when the user wants a specific subset rather than a full listing.
Example questions: "Find all bees that haven't communicated in the last week" / "Show me devices of type 'GPS tracker' created this year" / "Search for bee number BEE-0021."

**Locations**
- `fetch_locations(limit, offset, account_id)` — Returns a paginated list of locations configured on the account (e.g. warehouses, distribution centers, customer sites) used as shipment origins/destinations or geofences.
Example questions: "What locations do we have set up?" / "List all our warehouse locations" / "Show me location details for account 12345."

**Assets**
- `fetch_assets(filter_query, size, offset, fields)` — Searches reusable/trackable assets (e.g. containers, pallets, reusable packaging) — filterable by asset number, name, associated bee name, or creation date.
Example questions: "Show me all our tracked containers" / "Find the asset with number A-9081" / "List assets created in the last month."
- `fetch_asset_details(uuid)` — Retrieves full details for a single asset by its UUID, once a specific asset has been identified.
Example questions: "Give me the details on that container we just found" / "What's the current status of asset UUID xyz?"

**Webhooks & audit**
- `fetch_webhook_audit_summary(alert_type, entity_id, start_date, end_date, webhook_category)` — Retrieves a summary of webhook deliveries/events — filterable by alert type, entity ID, date range, or webhook category. Useful for debugging whether notifications/integrations fired as expected.
Example questions: "Did our temperature-alert webhook fire yesterday?" / "Show me webhook activity for shipment SHP-2024-001 last week" / "Summarize webhook events by category for July."
- `fetch_communication_audit(fields, size, offset, order_by, filter_query)` — Retrieves a communication/device audit log — records of device check-ins, communication events, and connectivity history, with filtering, sorting, and pagination.
Example questions: "Show me the communication history for our devices this week" / "Which devices went silent recently?" / "Give me the audit log of device communications, sorted by most recent."

Date filters accept ISO date strings; the server resolves relative language and epoch conversions for you. Required parameters are noted inline above; everything else is optional.
