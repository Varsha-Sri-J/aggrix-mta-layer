# AGGRIX Analytics Read API & Query Services Reference

## 1. Architectural Overview

The **AGGRIX Analytics Read API** exposes precomputed e-commerce metrics to client applications, storefront dashboards, and platform managers.

### Core Architecture Principles:
1. **Precomputed Summaries Only**: All read APIs query `daily_tenant_metrics` and `daily_product_metrics`. The read APIs **never** aggregate across raw `orders` or `order_items` tables, guaranteeing sub-5ms response times regardless of transactional volume.
2. **Strict Currency Segregation**: Financial totals are **never combined across different currencies**. If multiple currencies exist within an unbounded query, sales totals at the root level remain `null`, and accurate totals are provided per currency within the `currencies` breakdown list.
3. **Exact Decimal Preservation**: All monetary amounts are handled and transmitted using exact `Decimal` precision (serialized as high-precision JSON numeric strings, e.g. `"1066135.02"`), eliminating IEEE-754 floating point inaccuracies.
4. **N+1 Query Elimination**: Catalog metadata (`product_name`, `product_sku`) is retrieved via a single SQL `OUTER JOIN` on `products` within the aggregation query.
5. **Strict Tenant Scoping**: Query service methods require an explicit `tenant_id: uuid.UUID` scope and verify tenant existence before querying.

---

## 2. API Endpoints

### 2.1 GET `/api/v1/analytics/tenants/{tenant_id}/summary`

Retrieves tenant-level summary metrics across an optional date window and currency filter.

#### Path Parameters
* `tenant_id` (`UUID`, required): Target tenant identifier.

#### Query Parameters
* `start_date` (`date`, optional): Filter start date (`YYYY-MM-DD`, inclusive).
* `end_date` (`date`, optional): Filter end date (`YYYY-MM-DD`, inclusive).
* `currency` (`string`, optional): ISO 4217 3-letter currency code (e.g. `USD`, `EUR`, `INR`).

#### Example Request
```http
GET /api/v1/analytics/tenants/85056a62-e8fa-4587-8a50-c979bc73d7bf/summary?currency=USD HTTP/1.1
Host: localhost:8000
Accept: application/json
```

#### Example Response (Single Currency)
```json
{
  "tenant_id": "85056a62-e8fa-4587-8a50-c979bc73d7bf",
  "date_range": {
    "start_date": null,
    "end_date": null
  },
  "currency": "USD",
  "total_orders": 2000,
  "gross_sales": "1066135.02",
  "net_sales": "892047.17",
  "pending_orders_count": 215,
  "pending_sales": "124527.25",
  "cancelled_orders_count": 95,
  "cancelled_sales": "49560.60",
  "currencies": [
    {
      "currency": "USD",
      "total_orders": 2000,
      "gross_sales": "1066135.02",
      "net_sales": "892047.17",
      "pending_orders_count": 215,
      "pending_sales": "124527.25",
      "cancelled_orders_count": 95,
      "cancelled_sales": "49560.60"
    }
  ]
}
```

#### Example Response (Multi-Currency Segregated)
```json
{
  "tenant_id": "85056a62-e8fa-4587-8a50-c979bc73d7bf",
  "date_range": {
    "start_date": "2026-09-01",
    "end_date": "2026-09-30"
  },
  "currency": null,
  "total_orders": 2100,
  "gross_sales": null,
  "net_sales": null,
  "pending_orders_count": null,
  "pending_sales": null,
  "cancelled_orders_count": null,
  "cancelled_sales": null,
  "currencies": [
    {
      "currency": "EUR",
      "total_orders": 100,
      "gross_sales": "45000.00",
      "net_sales": "42000.00",
      "pending_orders_count": 5,
      "pending_sales": "2000.00",
      "cancelled_orders_count": 2,
      "cancelled_sales": "1000.00"
    },
    {
      "currency": "USD",
      "total_orders": 2000,
      "gross_sales": "1066135.02",
      "net_sales": "892047.17",
      "pending_orders_count": 215,
      "pending_sales": "124527.25",
      "cancelled_orders_count": 95,
      "cancelled_sales": "49560.60"
    }
  ]
}
```

---

### 2.2 GET `/api/v1/analytics/tenants/{tenant_id}/daily`

Retrieves chronological daily aggregated metric records for a tenant.

#### Path Parameters
* `tenant_id` (`UUID`, required): Target tenant identifier.

#### Query Parameters
* `start_date` (`date`, optional): Filter start date (`YYYY-MM-DD`, inclusive).
* `end_date` (`date`, optional): Filter end date (`YYYY-MM-DD`, inclusive).
* `currency` (`string`, optional): ISO 4217 3-letter currency code (e.g. `USD`).
* `page` (`integer`, optional, default=1): 1-indexed page number (`ge=1`).
* `page_size` (`integer`, optional, default=50): Records per page (`1 <= page_size <= 250`).

#### Example Request
```http
GET /api/v1/analytics/tenants/85056a62-e8fa-4587-8a50-c979bc73d7bf/daily?page=1&page_size=2 HTTP/1.1
Host: localhost:8000
Accept: application/json
```

#### Example Response
```json
{
  "tenant_id": "85056a62-e8fa-4587-8a50-c979bc73d7bf",
  "date_range": {
    "start_date": null,
    "end_date": null
  },
  "currency": null,
  "pagination": {
    "total_records": 61,
    "page": 1,
    "page_size": 2,
    "total_pages": 31
  },
  "data": [
    {
      "metric_date": "2026-09-01",
      "currency": "USD",
      "orders_count": 2,
      "gross_sales": "889.97",
      "net_sales": "889.97",
      "pending_orders_count": 0,
      "pending_sales": "0.00",
      "cancelled_orders_count": 0,
      "cancelled_sales": "0.00"
    },
    {
      "metric_date": "2026-09-02",
      "currency": "USD",
      "orders_count": 5,
      "gross_sales": "2757.32",
      "net_sales": "2148.30",
      "pending_orders_count": 1,
      "pending_sales": "609.02",
      "cancelled_orders_count": 0,
      "cancelled_sales": "0.00"
    }
  ]
}
```

---

### 2.3 GET `/api/v1/analytics/tenants/{tenant_id}/products`

Retrieves precomputed product-level rollups joined with catalog metadata, sorted by `gross_sales DESC`.

#### Path Parameters
* `tenant_id` (`UUID`, required): Target tenant identifier.

#### Query Parameters
* `start_date` (`date`, optional): Filter start date (`YYYY-MM-DD`, inclusive).
* `end_date` (`date`, optional): Filter end date (`YYYY-MM-DD`, inclusive).
* `currency` (`string`, optional): ISO 4217 3-letter currency code.
* `product_id` (`UUID`, optional): Filter for a specific product item.
* `page` (`integer`, optional, default=1): 1-indexed page number (`ge=1`).
* `page_size` (`integer`, optional, default=50): Records per page (`1 <= page_size <= 250`).

#### Example Request
```http
GET /api/v1/analytics/tenants/85056a62-e8fa-4587-8a50-c979bc73d7bf/products?page=1&page_size=1 HTTP/1.1
Host: localhost:8000
Accept: application/json
```

#### Example Response
```json
{
  "tenant_id": "85056a62-e8fa-4587-8a50-c979bc73d7bf",
  "date_range": {
    "start_date": null,
    "end_date": null
  },
  "currency": null,
  "pagination": {
    "total_records": 100,
    "page": 1,
    "page_size": 1,
    "total_pages": 100
  },
  "data": [
    {
      "product_id": "1e704549-88c4-4077-b59d-cbccd1d629f2",
      "product_name": "Active Noise Cancelling Wireless Headphones",
      "product_sku": "ELE-0024",
      "currency": "USD",
      "units_sold_gross": 153,
      "units_sold_net": 130,
      "pending_units": 17,
      "cancelled_units": 6,
      "gross_sales": "42927.21",
      "net_sales": "36474.10",
      "pending_sales": "4769.69",
      "cancelled_sales": "1683.42",
      "orders_count": 78
    }
  ]
}
```

### 2.4 GET `/api/v1/analytics/stream` and `/api/analytics/stream` (SSE Event Stream)

Establishes a persistent Server-Sent Events (SSE) stream for live analytics updates and event propagation.

#### Query Parameters
* `token` (`string`, optional): JWT bearer token (enables native browser `EventSource` connections).
* `tenant_id` (`UUID`, optional): Scopes event stream to a specific tenant (caller must be authorized for this tenant).
* `last_event_id` (`string`, optional): Fallback for `Last-Event-ID` header.
* `max_events` (`integer`, optional): Closes stream after receiving $N$ events (useful for probes and test validation).

#### Headers
* `Authorization` (`string`, optional): `Bearer <jwt_token>`.
* `Last-Event-ID` (`string`, optional): Reconnection identifier to replay missed events from the in-memory ring buffer.

#### Event Stream Protocol Format
```http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no

id: init
event: connected
data: {"status": "connected", "client_id": "client-...", "role": "tenant_user", "timestamp": "2026-11-01T00:00:00Z"}

id: evt-1730419200000-000001
event: order.created
data: {"id": "evt-...", "event_type": "order.created", "tenant_id": "85056a62-...", "order_id": "...", "status": "pending", "total_amount": 250.00, "currency": "USD", "created_at": "..."}

: heartbeat
```

---

### 2.5 GET `/api/v1/analytics/tenants` (Store Switcher)

Retrieves all tenant stores accessible to the authenticated user based on role:
* **Platform Admin**: Returns all 25 tenant stores.
* **Store Manager**: Returns only assigned tenant stores.
* **Tenant User**: Returns only home tenant store.

---

### 2.6 GET `/api/v1/analytics/tenants/{tenant_id}/status-distribution`

Returns order volume and revenue grouped by order lifecycle status (`pending`, `paid`, `fulfilled`, `cancelled`) with percentage calculations.

---

### 2.7 GET `/api/v1/analytics/tenants/{tenant_id}/recent-orders`

Returns a chronological feed of recent order transactions joined with customer display metadata and line item counts, supporting page-based pagination.

---

### 2.8 GET `/api/v1/analytics/tenants/{tenant_id}/overview`

Composite real-time dashboard endpoint returning KPI summary, order status distribution, recent activity feed, and top-performing products in a single round-trip.

---

## 3. Error Responses & Validation

| Status Code | Condition | Example Response |
| :--- | :--- | :--- |
| **`400 Bad Request`** | `start_date > end_date` | `{"detail": "Invalid date range: start_date (2026-09-10) must be before or equal to end_date (2026-09-01)."}` |
| **`401 Unauthorized`** | Missing or invalid JWT bearer token | `{"detail": "Missing authentication token."}` |
| **`403 Forbidden`** | Caller lacks role permissions or tenant assignment | `{"detail": "Access denied: tenant users can only access their own tenant data."}` |
| **`404 Not Found`** | `tenant_id` does not exist | `{"detail": "Tenant with ID '...' not found."}` |
| **`422 Unprocessable Entity`** | Malformed UUID or invalid date format | `{"detail": [{"loc": ["query", "start_date"], "msg": "invalid date", "type": "value_error"}]}` |

---

## 4. Multi-Tenant Security & Real-Time Isolation

* **Strict Tenancy Boundaries**: All stream subscriptions and read requests are cryptographically validated against `current_user`.
* **Zero Cross-Tenant Leakage**: Subscribers receive only events matching authorized tenant UUIDs.
* **Memory Bounded**: Fixed-size event ring buffer (500 events) and bounded per-client queues (100 events) prevent unbounded resource consumption.
* **Heartbeats**: Periodic heartbeat comments (`: heartbeat\n\n`) every 15 seconds maintain reverse proxy and gateway connection liveness.
