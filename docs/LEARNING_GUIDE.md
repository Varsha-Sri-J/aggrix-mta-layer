# AGGRIX MTA Layer — Developer Learning Guide & Knowledge Handoff

A comprehensive, code-backed engineering guide designed to take you from foundational concepts to mastering the entire AGGRIX architecture. Every section is anchored directly to the actual files, classes, and algorithms in this repository.

---

## Learning Sequence Roadmap

1. **Module 1**: Multi-Tenant Relational Modeling & Composite Keys
2. **Module 2**: The Transactional Outbox Pattern
3. **Module 3**: The Incremental Aggregation Engine & Causal State Transitions
4. **Module 4**: Security, RBAC, and One-Time Administrative Bootstrap
5. **Module 5**: Analytical Query Services & Multi-Currency Segregation
6. **Module 6**: Real-Time Event Broadcasting (SSE & PostgreSQL LISTEN/NOTIFY)
7. **Module 7**: Dynamic Glassmorphic Frontend & Real-Time DOM Updates
8. **Module 8**: Hands-on Exercises (Build Core Pieces Yourself)

---

## Module 1: Multi-Tenant Relational Modeling & Composite Keys

### 1. What It Does
Provides the relational schema for tenants, customers, products, orders, and order line items. It ensures that data belonging to different stores is isolated at the database level so that tenant A can never access or reference tenant B's records.

### 2. Why It Exists
In multi-tenant SaaS, tenant leaks (e.g., an order line item pointing to another store's product or customer) can be catastrophic. Rather than relying solely on application-level filtering (`WHERE tenant_id = ...`), AGGRIX enforces tenant isolation directly inside the PostgreSQL database engine.

### 3. Which Files Implement It
- [`backend/app/models/tenant.py`](file:///Users/varshasri/aggrix-mta-layer/backend/app/models/tenant.py): Defines the `Tenant` model.
- [`backend/app/models/customer.py`](file:///Users/varshasri/aggrix-mta-layer/backend/app/models/customer.py): Defines the `Customer` model with `UniqueConstraint("tenant_id", "email")`.
- [`backend/app/models/product.py`](file:///Users/varshasri/aggrix-mta-layer/backend/app/models/product.py): Defines the `Product` model with `UniqueConstraint("tenant_id", "sku")`.
- [`backend/app/models/order.py`](file:///Users/varshasri/aggrix-mta-layer/backend/app/models/order.py): Defines the `Order` model with `UniqueConstraint("tenant_id", "external_order_id")`.
- [`backend/app/models/order_item.py`](file:///Users/varshasri/aggrix-mta-layer/backend/app/models/order_item.py): Defines the `OrderItem` model with composite foreign keys.

### 4. How Data Flows Through It
```
[ Tenant Created ] ──► [ Customer & Product Cataloged (tenant_id scoped) ]
                               │
                               ▼
[ Order Placed ] ──► Validates (tenant_id, customer_id)
       │
       ▼
[ OrderItem Added ] ──► Validates (tenant_id, order_id) AND (tenant_id, product_id)
```

### 5. Important Functions & Classes
- `OrderItem.__table_args__`: Declares the composite foreign keys:
  ```python
  ForeignKeyConstraint(
      ["tenant_id", "order_id"],
      ["orders.tenant_id", "orders.id"],
      ondelete="CASCADE",
      name="fk_order_items_order_tenant",
  ),
  ForeignKeyConstraint(
      ["tenant_id", "product_id"],
      ["products.tenant_id", "products.id"],
      ondelete="RESTRICT",
      name="fk_order_items_product_tenant",
  )
  ```

### 6. Key Concepts to Understand
- **Composite Foreign Key**: A foreign key consisting of two or more columns `(tenant_id, resource_id)`. This forces PostgreSQL to verify that both the parent and child belong to the exact same tenant ID.
- **Tenant-Scoped Uniqueness**: Allowing two different stores to both have a product with SKU `"TSHIRT-BLK-M"` without throwing a unique constraint violation.

---

## Module 2: The Transactional Outbox Pattern

### 1. What It Does
Captures domain events (e.g. `order.created`, `order.paid`, `order.fulfilled`, `order.cancelled`) at the exact instant an order transaction is committed to the database.

### 2. Why It Exists
Eliminates the "dual-write" distributed systems problem. If the application updates the order table and then tries to send a message to Kafka/RabbitMQ or an analytics service, a network drop between the two creates permanent data divergence. By writing the event directly into `outbox_events` within the same database transaction, atomicity is guaranteed by PostgreSQL ACID.

### 3. Which Files Implement It
- [`backend/app/models/outbox_event.py`](file:///Users/varshasri/aggrix-mta-layer/backend/app/models/outbox_event.py): The `OutboxEvent` SQLAlchemy model.
- [`backend/app/generator/incremental.py`](file:///Users/varshasri/aggrix-mta-layer/backend/app/generator/incremental.py): Creates outbox events synchronously alongside synthetic orders.
- [`database/schema.sql`](file:///Users/varshasri/aggrix-mta-layer/database/schema.sql): Defines the table and partial index.

### 4. How Data Flows Through It
```
BEGIN TRANSACTION;
  INSERT INTO orders (id, tenant_id, total_amount...) VALUES (...);
  INSERT INTO order_items (id, tenant_id, order_id, product_id...) VALUES (...);
  INSERT INTO outbox_events (id, tenant_id, event_type, payload...) VALUES (...);
COMMIT;
```

### 5. Important Functions & Classes
- `OutboxEvent`: Stores payload as native PostgreSQL `JSONB`.
- Partial index in `OutboxEvent.__table_args__`:
  ```python
  Index("ix_outbox_events_unprocessed", "created_at", postgresql_where=text("processed_at IS NULL"))
  ```

### 6. Key Concepts to Understand
- **Dual-Write Hazard**: Why calling an external API/message queue inside a database transaction is an anti-pattern.
- **Partial Indexing**: Indexing only the rows where `processed_at IS NULL` keeps the index tiny and fast even when there are millions of historical processed events.

---

## Module 3: Incremental Aggregation Engine & Causal State Machine

### 1. What It Does
Polls unprocessed outbox events, computes summary metric adjustments, updates `daily_tenant_metrics` and `daily_product_metrics` via upsert deltas, and records idempotent consumer receipts.

### 2. Why It Exists
Running queries like `SELECT SUM(total_amount) FROM orders WHERE tenant_id = ...` against a database with millions of records causes heavy disk I/O and freezes OLTP checkouts. AGGRIX precomputes daily rollups incrementally so that reporting queries return in <5ms.

### 3. Which Files Implement It
- [`backend/app/analytics/worker.py`](file:///Users/varshasri/aggrix-mta-layer/backend/app/analytics/worker.py): Core aggregation worker daemon (`AnalyticsAggregationWorker`).
- [`backend/app/analytics/coordination.py`](file:///Users/varshasri/aggrix-mta-layer/backend/app/analytics/coordination.py): Advisory locks and supported event whitelists.
- [`backend/app/models/analytics_consumer_event.py`](file:///Users/varshasri/aggrix-mta-layer/backend/app/models/analytics_consumer_event.py): Idempotent receipt tracking.
- [`backend/app/models/analytics_dead_letter_event.py`](file:///Users/varshasri/aggrix-mta-layer/backend/app/models/analytics_dead_letter_event.py): Poison pill DLQ quarantine.

### 4. How Data Flows Through It
```
[ poll_unprocessed_events() ] (FOR UPDATE SKIP LOCKED)
             │
             ▼
[ Deduplicate against analytics_consumer_events ]
             │
             ▼
[ _calculate_transition_deltas() ] ──► Computes (gross, net, pending, cancelled)
             │
             ▼
[ Upsert daily_tenant_metrics & daily_product_metrics ]
             │
             ▼
[ _write_consumer_receipt() ]
             │
             ▼
[ Emit NOTIFY aggrix_events ]
```

### 5. Important Functions & Classes
- `poll_unprocessed_events()`: Uses `FOR UPDATE OF oe SKIP LOCKED` to enable concurrent workers without lock contention.
- `_calculate_transition_deltas()`: Implements the state machine accounting rules:
  - If `order.paid` arrives before `order.created`, it treats the order as directly paid and prevents double-counting when `order.created` arrives later.
- `_apply_tenant_metric_delta()`: PostgreSQL `INSERT ... ON CONFLICT (tenant_id, metric_date, currency) DO UPDATE SET orders_count = daily_tenant_metrics.orders_count + :delta`.

### 6. Key Concepts to Understand
- **`SKIP LOCKED`**: How PostgreSQL allows multiple worker processes to poll different slices of the outbox table concurrently without blocking each other.
- **Idempotency**: Ensuring that re-processing an event 10 times produces the exact same metric result as processing it once.
- **Advisory Locks**: Application-defined 64-bit mutex locks in PostgreSQL memory (`pg_advisory_xact_lock`).

---

## Module 4: Security, RBAC, and One-Time Provisioning CLI

### 1. What It Does
Secures all API and SSE endpoints via JWT bearer tokens and implements Role-Based Access Control (RBAC) across three distinct roles:
1. `platform_admin`: Global access across all stores and administrative provisioning.
2. `store_manager`: Access restricted to an explicitly assigned subset of stores.
3. `tenant_user`: Access strictly limited to their own home store.

### 2. Why It Exists
Guarantees tenant isolation across user sessions and prevents unauthorized credential escalation or cross-tenant data leakage.

### 3. Which Files Implement It
- [`backend/app/core/security.py`](file:///Users/varshasri/aggrix-mta-layer/backend/app/core/security.py): Password hashing (bcrypt) and JWT encoding/decoding.
- [`backend/app/api/deps.py`](file:///Users/varshasri/aggrix-mta-layer/backend/app/api/deps.py): `get_current_user` and `get_authorized_tenant`.
- [`backend/app/cli/init_admin.py`](file:///Users/varshasri/aggrix-mta-layer/backend/app/cli/init_admin.py): One-time secure administrative bootstrap CLI.
- [`backend/app/api/routes/auth.py`](file:///Users/varshasri/aggrix-mta-layer/backend/app/api/routes/auth.py): Login and user provisioning endpoints.

### 4. How Data Flows Through It
```
Client Request ──► Bearer Token or ?token=
                         │
                         ▼
             [ get_current_user() ]
                         │  1. Cryptographically decode JWT (HMAC-SHA256)
                         │  2. Verify subject user exists and is_active
                         ▼
           [ get_authorized_tenant() ]
                         │  1. Check role
                         │  2. Platform Admin -> Allow
                         │  3. Store Manager -> Check manager_tenant_assignments
                         │  4. Tenant User -> Check user.tenant_id == path.tenant_id
                         ▼
                 Authorized Request
```

### 5. Important Functions & Classes
- `create_access_token(subject, role, tenant_id)`: Generates signed JWT tokens.
- `init_admin.py`: Refuses to bootstrap if any platform administrator already exists in the database.

---

## Module 5: Analytical Query Services & Multi-Currency Segregation

### 1. What It Does
Exposes fast, read-only analytics summaries and time-series data for tenant dashboards and manager overview reports.

### 2. Why It Exists
Provides the REST API boundary that serves pre-aggregated metrics to the frontend in milliseconds.

### 3. Which Files Implement It
- [`backend/app/analytics/service.py`](file:///Users/varshasri/aggrix-mta-layer/backend/app/analytics/service.py): `AnalyticsQueryService`.
- [`backend/app/api/routes/analytics.py`](file:///Users/varshasri/aggrix-mta-layer/backend/app/api/routes/analytics.py): HTTP endpoints.
- [`backend/app/schemas/analytics.py`](file:///Users/varshasri/aggrix-mta-layer/backend/app/schemas/analytics.py): Pydantic response models.

### 4. Important Functions & Classes
- `get_tenant_overview()`: Composite endpoint returning KPIs, status distribution, top products, and recent orders in a single roundtrip.
- `get_active_customers_count()`: Queries distinct customer counts within a date range.
- Dynamic Average Order Value (AOV): Calculated as `gross_sales / total_orders` if orders > 0.

### 5. Key Concepts to Understand
- **Multi-Currency Segregation**: Financial totals are never summed across different currency codes (e.g. adding 100 USD to 100 EUR to produce "200" is strictly forbidden).

---

## Module 6: Real-Time Event Broadcasting (SSE & PostgreSQL LISTEN/NOTIFY)

### 1. What It Does
Propagates new order events and metric changes to connected web dashboards with sub-second latency.

### 2. Why It Exists
Allows merchant dashboards to reflect live sales activity immediately as transactions happen without requiring full-page refreshes or polling.

### 3. Which Files Implement It
- [`backend/app/analytics/broadcaster.py`](file:///Users/varshasri/aggrix-mta-layer/backend/app/analytics/broadcaster.py): `EventBroadcaster`, `BroadcastEvent`, and `ClientSubscription`.
- [`backend/app/main.py`](file:///Users/varshasri/aggrix-mta-layer/backend/app/main.py): Application lifespan starting the PostgreSQL LISTEN background thread.
- [`backend/app/api/routes/analytics.py`](file:///Users/varshasri/aggrix-mta-layer/backend/app/api/routes/analytics.py): `stream_analytics_events()`.

### 4. How Data Flows Through It
```
Worker finishes batch ──► SELECT pg_notify('aggrix_events', '{"event_type": ...}')
                                   │
                                   ▼
PostgreSQL NOTIFY ──► Backend LISTEN thread (select() on psycopg2 connection)
                                   │
                                   ▼
EventBroadcaster.publish_event()
                                   │
                                   ▼
Filters by subscriber tenant authorization
                                   │
                                   ▼
sub.loop.call_soon_threadsafe(sub.queue.put_nowait, event)
                                   │
                                   ▼
StreamingResponse (Server-Sent Events) ──► Dashboard EventSource
```

### 5. Important Functions & Classes
- `EventBroadcaster.start_postgres_listener()`: Spawns the dedicated listener thread.
- `EventBroadcaster.get_events_since(last_event_id)`: Replays missed events upon client reconnection.
- `stream_analytics_events()`: FastAPI async generator yielding SSE messages and 15-second heartbeats (`: heartbeat\n\n`).

---

## Module 7: Dynamic Glassmorphic Frontend

### 1. What It Does
Provides an interface displaying live revenue trends, status distributions, order feeds, and KPI cards with CSS animations and live updates.

### 2. Which Files Implement It
- [`backend/app/static/index.html`](file:///Users/varshasri/aggrix-mta-layer/backend/app/static/index.html): HTML structure.
- [`backend/app/static/css/dashboard.css`](file:///Users/varshasri/aggrix-mta-layer/backend/app/static/css/dashboard.css): Glassmorphic styling, responsive grid, pulse animations.
- [`backend/app/static/js/charts.js`](file:///Users/varshasri/aggrix-mta-layer/backend/app/static/js/charts.js): Dynamic SVG area and donut chart renderers.
- [`backend/app/static/js/dashboard.js`](file:///Users/varshasri/aggrix-mta-layer/backend/app/static/js/dashboard.js): SSE client connection, state management, HTML escaping, and event listener logic.

---

## Module 8: Hands-On Exercises to Reproduce Core Functionality

Try these small coding exercises in scratch scripts to build intuition for AGGRIX's core mechanisms:

### Exercise 1: Simulate the Outbox & Worker Pattern
Write a standalone Python script that:
1. Connects to PostgreSQL using `psycopg2`.
2. Inserts an order and an `outbox_events` row in a single transaction.
3. Polls the event using `SELECT ... FOR UPDATE SKIP LOCKED`.
4. Updates a summary dictionary and marks the outbox event processed.

### Exercise 2: Test PostgreSQL LISTEN/NOTIFY
Write a script that:
1. Connects with `psycopg2` in autocommit mode and runs `LISTEN test_channel;`.
2. In a separate thread or terminal, runs `SELECT pg_notify('test_channel', '{"order_id": 123}');`.
3. Calls `conn.poll()` and prints the received JSON payload.

### Exercise 3: Build an Async SSE Generator
Write a minimal FastAPI app that:
1. Declares an `asyncio.Queue`.
2. Implements a route `@app.get("/stream")` returning `StreamingResponse(generator(), media_type="text/event-stream")`.
3. In a separate background task, puts messages into the queue every 2 seconds.
4. Verify using `curl -N http://localhost:8000/stream`.

---

## Module 9: React 18 + TypeScript Multi-Tenant Frontend Integration

### 1. What It Does
Implements a type-safe single-page application (SPA) with persona-specific operational views (Merchant, Store Manager, Platform Admin), dynamic SVG charts, multi-store comparison matrices, and real-time SSE stream ingestion.

### 2. Which Files Implement It
- [`frontend/src/types/api.ts`](file:///Users/varshasri/aggrix-mta-layer/frontend/src/types/api.ts): Strong TypeScript interface definitions for analytics, models, user profiles, and API query parameters.
- [`frontend/src/services/authService.ts`](file:///Users/varshasri/aggrix-mta-layer/frontend/src/services/authService.ts): Manages JWT bearer tokens, profile discovery, and bidirectional role mapping (`platform_admin` ↔ `admin`, `store_manager` ↔ `manager`, `tenant_user` ↔ `merchant`).
- [`frontend/src/services/analyticsService.ts`](file:///Users/varshasri/aggrix-mta-layer/frontend/src/services/analyticsService.ts): Client wrapper for tenant rollups, daily metrics, product rankings, and manager comparisons.
- [`frontend/src/hooks/useSSE.ts`](file:///Users/varshasri/aggrix-mta-layer/frontend/src/hooks/useSSE.ts): Reusable React hook for `EventSource` live updates with token query authentication and automatic reconnection.
- [`frontend/src/pages/dashboards/MerchantDashboardPage.tsx`](file:///Users/varshasri/aggrix-mta-layer/frontend/src/pages/dashboards/MerchantDashboardPage.tsx): Single-store operational cockpit with live SSE pulse.
- [`frontend/src/pages/dashboards/ManagerDashboardPage.tsx`](file:///Users/varshasri/aggrix-mta-layer/frontend/src/pages/dashboards/ManagerDashboardPage.tsx): Multi-store comparison workspace.
- [`frontend/src/pages/dashboards/AdminDashboardPage.tsx`](file:///Users/varshasri/aggrix-mta-layer/frontend/src/pages/dashboards/AdminDashboardPage.tsx): Platform-wide analytics across all 25 tenant stores.

### 3. Key Concepts to Understand
- **EventSource Token Authentication**: Standard browser `EventSource` cannot send custom headers. Token is passed securely via `?token=` query parameter and validated by backend FastAPI dependency.
- **Query Parameter Serialization**: FastAPI expects array parameters repeated (`?tenant_ids=A&tenant_ids=B`). `apiClient` serializes arrays into repeated query keys rather than comma-separated strings.
- **Client-Side Tenant Isolation**: In addition to backend 403 Forbidden enforcement, the UI isolates tenant views to prevent cross-tenant UI leakage.

