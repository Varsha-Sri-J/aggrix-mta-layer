# AGGRIX MTA Layer — Technical Review & Architecture Guide

A comprehensive architectural and engineering review document explaining the design principles, implementation details, and reliability guarantees of the AGGRIX Multi-Tenant Analytics & Real-Time Aggregation Engine.

---

## 1. System Architecture

AGGRIX is designed as a **decoupled, event-driven analytical processing engine** engineered to provide near real-time operational reporting for multi-tenant e-commerce environments without imposing analytical query overhead on transactional order processing databases.

```
                          ┌────────────────────────────────────────────────────────┐
                          │                 DOMAIN TRANSACTIONS                    │
                          │  (E-Commerce Checkout, Fulfillment, Refund Engine)    │
                          └───────────────────────────┬────────────────────────────┘
                                                      │ Atomic DB Commit
                                                      ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       POSTGRESQL 16 DATABASE                                     │
│                                                                                                  │
│   ┌─────────────────────┐   ┌─────────────────────┐   ┌──────────────────────────────────────┐   │
│   │   Business Tables   │   │ Transactional Outbox│   │          Analytical Rollups          │   │
│   │ (tenants, customers,│   │   (outbox_events)   │   │       (daily_tenant_metrics,         │   │
│   │   products, orders) │   │                     │   │       daily_product_metrics)         │   │
│   └─────────────────────┘   └──────────┬──────────┘   └──────────────────▲───────────────────┘   │
└────────────────────────────────────────┼─────────────────────────────────┼───────────────────────┘
                                         │ FOR UPDATE SKIP LOCKED          │ Atomic Delta Upsert
                                         ▼                                 │
                          ┌───────────────────────────┐                    │
                          │     ANALYTICS WORKER      │────────────────────┘
                          │ (app.analytics.worker)    │
                          └─────────────┬─────────────┘
                                        │ NOTIFY aggrix_events
                                        ▼
                          ┌───────────────────────────┐
                          │   POSTGRES LISTEN LOOP    │
                          │ (app.analytics.broadcaster│
                          └─────────────┬─────────────┘
                                        │ Dispatch to Subscriptions
                                        ▼
                          ┌───────────────────────────┐
                          │    FASTAPI READ APIS      │
                          │ (/api/v1/analytics/stream)│
                          └─────────────┬─────────────┘
                                        │ Server-Sent Events (SSE)
                                        ▼
                          ┌───────────────────────────┐
                          │  LIVE ANALYTICS DASHBOARD │
                          │   (Vanilla JS / SVG UI)   │
                          └───────────────────────────┘
```

### Architectural Tenets
1. **Zero Analytical Overhead on Core OLTP**: Analytics summaries are never computed on the fly by scanning millions of historical orders. Instead, metrics are updated incrementally upon event ingestion.
2. **Crash-Resilient Domain Eventing**: Business domain mutations (order created, paid, fulfilled, cancelled) commit synchronously with an outbox record in the same database transaction.
3. **Decoupled Asynchronous Processing**: An autonomous background worker daemon polls, deduplicates, and aggregates events independently of the main API server.
4. **Push-Based Real-Time Propagation**: Metric updates and order events stream to user dashboards over Server-Sent Events (SSE) within milliseconds of worker completion.
5. **Strict Multi-Tenant Isolation**: Tenancy boundaries are enforced cryptographically via JWT, logically via API dependencies, and relationally via composite foreign keys.

---

## 2. Technology Stack

| Layer | Component | Version / Specification | Rationale & Trade-offs |
| :--- | :--- | :--- | :--- |
| **Language & Runtime** | Python | 3.9+ / CPython | Strong typing, async event loop support, extensive database ecosystem. |
| **Web Framework** | FastAPI | 0.110.0+ | High-performance ASGI framework with native OpenAPI schema generation and dependency injection. |
| **Database & ORM** | PostgreSQL & SQLAlchemy 2.0 | PostgreSQL 16 Alpine, SQLAlchemy 2.0.28+ | ACID reliability, native JSONB, `FOR UPDATE SKIP LOCKED`, advisory locking, and typed Mapped models. |
| **Database Migration**| Alembic | 1.13.0+ | Deterministic schema migrations with strict downgrade paths and constraint tracking. |
| **Real-Time Transport**| Server-Sent Events (SSE) | W3C EventSource Standard | Lightweight HTTP/2-friendly uni-directional streaming; bypasses WebSocket connection-state complexity while natively supporting `Last-Event-ID` reconnection. |
| **Cross-Container Bus**| PostgreSQL `LISTEN/NOTIFY` | Native IPC Channel | Zero additional infrastructure overhead (avoids deploying Redis/RabbitMQ/Kafka for inter-service signaling in single-cluster deployments). |
| **Security & Auth** | PyJWT & bcrypt | PyJWT 2.8+, bcrypt 4.0+ | HMAC-SHA256 cryptographically signed tokens with constant-time signature validation and 12-round bcrypt password hashing. |
| **Frontend UI** | Modern Vanilla CSS & JS | HTML5, CSS3, ES2022 | Dependency-free, zero-build-step glassmorphic UI with dynamic SVG area charts and CSS pulse animations. |
| **Containerization** | Docker & Docker Compose | Docker 20.10+, Compose v2 | Isolated, reproducible container network (`aggrix-postgres`, `aggrix-backend`, `aggrix-analytics-worker`). |

---

## 3. Database Design

### Strict Tenancy Keys & Schema Organization
All transactional and analytical tables incorporate `tenant_id: uuid.UUID` as part of their identity.

```
tenants (id PK, name, domain, timezone, created_at)
   ▲
   ├── customers (id PK, tenant_id FK, email, name, created_at)
   │     └── UNIQUE (tenant_id, id)
   │     └── UNIQUE (tenant_id, email)
   │
   ├── products (id PK, tenant_id FK, sku, name, price, currency, created_at)
   │     └── UNIQUE (tenant_id, id)
   │     └── UNIQUE (tenant_id, sku)
   │
   ├── orders (id PK, tenant_id FK, customer_id FK, external_order_id, status, currency, total_amount)
   │     └── UNIQUE (tenant_id, id)
   │     └── UNIQUE (tenant_id, external_order_id)
   │     └── FK (tenant_id, customer_id) REFERENCES customers (tenant_id, id)
   │
   ├── order_items (id PK, tenant_id FK, order_id FK, product_id FK, quantity, unit_price)
   │     └── FK (tenant_id, order_id) REFERENCES orders (tenant_id, id)
   │     └── FK (tenant_id, product_id) REFERENCES products (tenant_id, id)
   │
   ├── outbox_events (id PK, tenant_id FK, event_type, payload JSONB, created_at, processed_at)
   │
   ├── daily_tenant_metrics (id PK, tenant_id FK, metric_date, currency, orders_count, gross_sales, net_sales...)
   │     └── UNIQUE (tenant_id, metric_date, currency)
   │
   └── daily_product_metrics (id PK, tenant_id FK, product_id FK, metric_date, currency, gross_units, gross_sales...)
         └── UNIQUE (tenant_id, product_id, metric_date, currency)
```

### Composite Foreign Key Guarantees
Cross-tenant foreign key corruption is impossible at the relational level:
- An `order` cannot reference a `customer` belonging to a different tenant because the foreign key references `(tenant_id, customer_id)`.
- An `order_item` cannot reference an `order` or `product` from a different tenant because it enforces `(tenant_id, order_id)` and `(tenant_id, product_id)`.

### Partial Indexing for High-Throughput Polling
The outbox table contains a partial PostgreSQL index:
```sql
CREATE INDEX ix_outbox_events_unprocessed 
ON outbox_events (created_at) 
WHERE processed_at IS NULL;
```
This ensures that polling queries only index unprocessed rows, avoiding linear index bloat as millions of historical events accumulate.

---

## 4. Multi-Tenancy Architecture

### Row-Level vs Database-Level Isolation
AGGRIX adopts **shared-database, shared-schema tenancy with composite foreign keys**:
- **Why Not Database-per-Tenant?** Operational overhead of managing 500+ independent database connections, migrations, and connection pools makes database-per-tenant impractical at scale.
- **Why Not Schema-per-Tenant?** Schema-per-tenant creates hundreds of duplicate tables and exhausts PostgreSQL shared catalog cache (`pg_class`).
- **Shared Schema Defense-in-Depth**:
  1. **Relational Constraints**: Composite foreign keys prevent cross-tenant data insertion.
  2. **Model Uniqueness**: SKUs, order IDs, and emails are unique per tenant, allowing different tenants to share SKU names or customer emails without collision.
  3. **API Query Scoping**: Every query generated by `AnalyticsQueryService` filters on `tenant_id`.
  4. **RBAC Dependency**: `get_authorized_tenant` verifies that the caller's JWT role has explicit rights to inspect the requested `tenant_id`.

---

## 5. Transactional Outbox Pattern

### The Dual-Write Problem
When an order is created, writing to the database and sending an analytical message to an external message broker creates a dual-write vulnerability: if the message broker fails after the database commit (or vice versa), the system enters an inconsistent state.

### The AGGRIX Solution
1. **Atomic Outbox Commit**: The business transaction inserts into `orders`, `order_items`, and `outbox_events` in a single ACID commit.
2. **Worker Polling with Concurrency Control**:
   ```sql
   SELECT oe.id, oe.tenant_id, oe.event_type, oe.payload, oe.created_at
   FROM outbox_events oe
   WHERE oe.event_type IN ('order.created', 'order.paid', 'order.fulfilled', 'order.cancelled')
     AND NOT EXISTS (
         SELECT 1 FROM analytics_consumer_events ace
         WHERE ace.consumer_name = :consumer_name AND ace.event_id = oe.id
     )
   ORDER BY oe.created_at ASC, oe.id ASC
   LIMIT :limit
   FOR UPDATE OF oe SKIP LOCKED;
   ```
3. **Multi-Worker Scaling (`SKIP LOCKED`)**: Multiple worker processes can run concurrently without contention or row lock serialization.
4. **Advisory Locking**: PostgreSQL session-level advisory locks (`AGGRIX_ANALYTICS_LOCK_ID = 849204918239102`) prevent conflicts between historical backfills and live event stream workers.

---

## 6. Incremental Aggregation Engine

### State Transition Delta Calculation
Rather than executing slow `SUM(...) GROUP BY` queries across millions of order items, AGGRIX applies incremental state-machine deltas directly to `daily_tenant_metrics` and `daily_product_metrics`:

| Event Type | Orders Count | Gross Sales | Net Sales | Pending Sales | Cancelled Sales |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `order.created` | `+1` | `+amount` | `0` | `+amount` | `0` |
| `order.paid` | `0` | `0` | `+amount` | `-amount` | `0` |
| `order.fulfilled`| `0` | `0` | `0` | `0` | `0` |
| `order.cancelled` (from pending) | `0` | `0` | `0` | `-amount` | `+amount` |
| `order.cancelled` (from paid) | `0` | `0` | `-amount` | `0` | `+amount` |

### Out-of-Order & Causal Defensiveness
Network partitions and asynchronous commits can cause `order.paid` to arrive before `order.created`.
AGGRIX inspects prior events in `analytics_consumer_events`:
- If `order.paid` arrives first: Increments `orders_count += 1`, `gross_sales += amount`, `net_sales += amount`, and leaves `pending_sales = 0`.
- When `order.created` arrives later: Detects prior payment receipt and skips duplicate creation deltas.
- If duplicate events are retried: Handled idempotently via `analytics_consumer_events` unique constraint (`consumer_name`, `event_id`).

### Dead-Letter Queue (DLQ) Quarantine
If a poison-pill event contains corrupted JSON or invalid data:
1. The worker catches the exception and increments `attempts` in `analytics_dead_letter_events`.
2. After 3 failed attempts, the event is quarantined.
3. The worker commits the remaining valid events in the batch without halting.

---

## 7. Server-Sent Events (SSE) & Real-Time Updates

### Why SSE Over WebSockets?
- **HTTP/2 Multiplexing**: SSE operates over standard HTTP, leveraging existing proxies, TLS infrastructure, and load balancers.
- **Native Reconnection**: Browser `EventSource` automatically reconnects upon disconnection and transmits `Last-Event-ID`.
- **Uni-Directional Efficiency**: Dashboard analytics require server-to-client streaming without bidirectional socket overhead.

### Broadcaster Thread Safety & Disconnect Handling
- **Ring Buffer Replay**: Maintains a bounded in-memory buffer (`MAX_EVENT_BUFFER_SIZE = 500`) with deduplication (`_seen_ids`).
- **Threadsafe Async Queue Scheduling**: Dispatches from background OS threads (PostgreSQL LISTEN daemon) to client `asyncio.Queue` via `loop.call_soon_threadsafe`.
- **Bounded Client Queues**: Each connection has a bounded queue (`maxsize = 100`). If a slow client lags, the oldest unread event is dropped to prevent server memory bloat.
- **Automatic Resource Cleanup**: When a client socket closes, the `event_generator()` finally block unsubscribes the client ID, decrementing active subscriber counts.

---

## 8. Financial Reconciliation & Invariants

AGGRIX maintains mathematical and accounting integrity across all currencies and cohorts:

### 1. The Core Accounting Invariant
$$\text{Gross Sales} = \text{Net Sales} + \text{Pending Sales} + \text{Cancelled Sales}$$
Across 150,000 orders in Stage 2, this invariant holds with **$\Delta = \$0.00$**.

### 2. Multi-Currency Segregation
Currency totals are **strictly isolated** at both the database and API levels:
- `daily_tenant_metrics` enforces `UNIQUE(tenant_id, metric_date, currency)`.
- The summary API segregates totals per currency (e.g., USD, EUR, INR) and refuses to sum disparate currencies into a single meaningless number.

### 3. Check Constraints
Database constraints guarantee that no metric column can become negative:
```sql
CONSTRAINT gross_non_negative CHECK (gross_sales >= 0),
CONSTRAINT net_non_negative CHECK (net_sales >= 0),
CONSTRAINT orders_non_negative CHECK (orders_count >= 0)
```

---

## 9. Testing & Reliability Engineering

The test suite spans **211 automated tests** with 100% pass rate:

| Test Module | Coverage Scope | Test Count |
| :--- | :--- | :---: |
| `test_models.py` | Schema constraints, check constraints, cascade deletes | 7 |
| `test_tenancy.py` | Cross-tenant foreign key rejections, tenant isolation | 7 |
| `test_worker.py` | Outbox polling, causal state transitions, retry/DLQ, daemon polling | 17 |
| `test_incremental_generator.py` | Synthetic dataset expansion, collision avoidance, dry-run previews | 9 |
| `test_security_rbac.py` | JWT authentication, RBAC boundaries, provision security, CORS, timing attacks | 42 |
| `test_analytics_api.py` | Summary, daily metrics, product metrics, date range validation | 15 |
| `test_analytics_extended_api.py`| Tenant switcher, status distribution, recent orders feed, composite overview | 7 |
| `test_realtime_stream.py` | SSE stream authentication, tenant isolation, Last-Event-ID replay, concurrency | 10 |
| `test_realtime_e2e.py` | End-to-end pipeline: Order → Outbox → Worker → Rollup → API → SSE | 3 |
| `test_generator.py` & others | Deterministic seeding, metadata validation, live PostgreSQL checks | 94 |
| **Total** | **Comprehensive Multi-Layer Test Coverage** | **211 Passed** |
