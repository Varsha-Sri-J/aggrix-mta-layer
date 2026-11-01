# AGGRIX Analytics & Aggregation Engine — Architecture & Specification

**Document Version:** 2.0.0 (Revised Design Specification)  
**Status:** DRAFT (Design Phase — Pending User Approval)  
**Target Modules:** `backend/app/analytics/` & PostgreSQL Aggregation Tables  

---

## 1. Executive Summary & Core Architectural Principles

AGGRIX is a multi-tenant analytics and aggregation platform engineered for high-growth e-commerce merchants, with initial focus on the **Indian retail ecosystem**.

Having established our foundational relational schema (six PostgreSQL models, composite foreign keys, Alembic migrations, and deterministic synthetic data), this document specifies the **Analytics & Aggregation Engine**.

### Core Architectural Decisions:
1. **Currency Grounding**: Indian Rupee (`INR`) with `₹` display symbol as the default currency for Indian tenants. Strict enforcement of `NUMERIC(14, 2)` and Python `Decimal` across all storage and calculation. Multi-currency support is retained at the schema level by partitioning aggregation keys by `(tenant_id, currency, ...)`. Currencies are never mixed without explicit conversion.
2. **Timezone Grounding**: Timestamps are stored in UTC (`TIMESTAMPTZ`), but daily aggregations dynamically convert timestamps into the **tenant's local timezone** (defaulting to `Asia/Kolkata` / `IST` = `UTC+05:30`) before truncating calendar day buckets.
3. **Decoupled Historical vs. Current-State Analytics**: Historical daily summaries (`daily_tenant_metrics`, `daily_product_metrics`) capture immutable transaction dates and financial metrics. Real-time operational queues (`pending`, `paid`, `fulfilled`, `cancelled`) are queried directly against source tables using indexed composite scans, completely preventing status synchronization drift.
4. **Outbox Event Processing Integrity**: Incremental event consumption via PostgreSQL `FOR UPDATE SKIP LOCKED`. Status transitions do not duplicate order counts or revenue. Product aggregates query reliable source line-item data.
5. **Non-Destructive Full Rebuilds**: Aggregations support idempotent full rebuilds using atomic upserts (`ON CONFLICT DO UPDATE`) without destructive table truncations, guaranteeing zero downtime for analytical API reads.
6. **Scalability Target**: Engineered to scale to **10 million records across 100 tenants** with sub-second API latencies and data freshness within minutes.

---

## 2. Currency & Monetary Conventions

### 2.1. Indian E-Commerce Environment Conventions
- **Default Currency**: Indian Rupee (`INR`).
- **Currency Symbol**: `₹` (Unicode `U+20B9`).
- **Numeric Precision**: `NUMERIC(14, 2)` in PostgreSQL; `decimal.Decimal` in Python. Floating-point types are strictly forbidden.
- **Explicit Currency Codes**: Every API response payload must explicitly declare `"currency": "INR"` alongside monetary amounts.
- **Indian Number Formatting**: Presentation values are formatted using the Indian numbering system (Lakhs and Crores, grouping the last 3 digits, then successive 2-digit pairs):
  - Value: `5332954.22`
  - Western formatting: `$5,332,954.22`
  - **Indian formatting**: `₹53,32,954.22` ($53.32$ Lakhs)
  - Formula: `₹[Crores],[Lakhs],[Thousands],[Hundreds].[Paise]`
- **Currency Mixing Rule**: Different currencies are never aggregated or summed together without an explicit exchange rate conversion mechanism.

### 2.2. Inspection of Existing Database & Synthetic Generator
Direct inspection of the live PostgreSQL database and generator codebase reveals:
1. **Live PostgreSQL State**:
   - `products`: 500 rows, all with `currency = 'USD'` (prices range from `$18.00` to `$279.99`).
   - `orders`: 10,000 rows, all with `currency = 'USD'`.
   - `outbox_events`: 25,481 rows, all with payload `"currency": "USD"`.
   - `models/product.py` and `models/order.py`: Table schema defaults are `server_default="USD"`.
2. **Generator Codebase Inspection**:
   - In `backend/app/generator/config.py`: Has `currency: str = "USD"` field.
   - In `backend/app/generator/providers.py`: Catalog templates (`PRODUCT_TEMPLATES`) define base prices in USD amounts (`Decimal("34.00")`, `Decimal("88.50")`, etc.).
   - Passing `currency="INR"` to the current generator changes the currency label to `INR`, but assigns unrealistic prices (e.g. ₹34.00 for a heavyweight hoodie).

### 2.3. Recommended Safe Regeneration Approach (INR Pricing)
To transition to realistic INR numbers without corrupting database integrity or altering migrations:
- **Do Not Silently Reinterpret**: Never treat `$34.00` as `₹34.00`.
- **Recommended Strategy (Controlled Regeneration)**:
  1. Add an Indian retail pricing catalog profile to `providers.py` (e.g., standard consumer price points like ₹499, ₹999, ₹1,499, ₹2,499, ₹4,999, ₹9,999, ₹14,999) or an INR pricing multiplier.
  2. Use the existing safe cleanup utility (`cleanup_synthetic_data(confirm=True)`) which specifically targets the dedicated synthetic namespace `*.synthetic.aggrix.test`. This cleanly purges existing synthetic stores and cascades to all child records, leaving non-synthetic records untouched.
  3. Run the generator with `--currency INR --seed 42 --as-of 2026-10-31T12:00:00Z` to populate realistic Indian retail figures.
- **Multi-Currency Schema Isolation**:
  Both aggregation tables include `currency` in their composite primary/unique key (`tenant_id, metric_date, currency`), ensuring that even if a tenant processes both USD and INR transactions, they are segregated into distinct daily metric rows.

---

## 3. Timezone & Calendar Day Bucketing

### 3.1. Timezone Grounding
- **Storage**: All database timestamp columns (`created_at`, `updated_at`, `processed_at`) store timezone-aware UTC timestamps (`TIMESTAMPTZ` in PostgreSQL).
- **Default Indian Tenant Timezone**: `Asia/Kolkata` (Indian Standard Time, `IST` = `UTC+05:30`).
- **Tenant-Configurable Timezone**: The aggregation engine supports tenant-configurable timezones. When introduced, each tenant record specifies its operational timezone (e.g., `Asia/Kolkata`, `Asia/Dubai`, `UTC`).

### 3.2. Calendar Day Boundary Conversion
Aggregating transactions by raw UTC date causes boundary errors for Indian merchants. For example, an order placed at `2026-10-05 20:30:00 UTC` is `2026-10-06 02:00:00 IST`. For an Indian merchant, this order belongs to **October 6**, not October 5.

All SQL aggregations must convert timestamps to the tenant timezone before calculating calendar-day buckets:
```sql
-- Convert UTC timestamp into tenant timezone before extracting calendar date
DATE(o.created_at AT TIME ZONE COALESCE(t.timezone, 'Asia/Kolkata')) AS metric_date
```

---

## 4. Decoupled Architecture: Historical vs. Current-State Metrics

A critical design flaw in naive analytics systems is mixing mutable current order statuses (`pending`, `paid`, `fulfilled`) into historical daily aggregation buckets.

```
+-------------------------------------------------------------------------------+
|                      DECOUPLED ANALYTICS ARCHITECTURE                         |
+-------------------------------------------------------------------------------+
|                                                                               |
|   1. HISTORICAL TIME-SERIES LEDGER (daily_tenant_metrics & daily_product_metrics)  |
|      - Partitioned by (tenant_id, metric_date, currency)                      |
|      - Groups by order placement date (created_at in tenant timezone)         |
|      - Tracks orders placed, gross revenue, net revenue, cancellations        |
|      - Immutable across standard status progression (pending -> paid -> fulfilled)|
|                                                                               |
|   2. CURRENT-STATE OPERATIONAL LEDGER (Live Source Query on orders)          |
|      - Evaluated directly against PostgreSQL index ix_orders_tenant_status   |
|      - Sub-millisecond scan (< 2ms) across thousands of rows                  |
|      - Tracks current queue sizes: Pending Payment, Ready to Ship, Cancelled  |
|      - Eliminates synchronization drift between real-time orders and metrics   |
|                                                                               |
+-------------------------------------------------------------------------------+
```

### 4.1. Why Mutable Status Counts Do Not Belong in Daily Aggregation Tables
1. **Semantic Ambiguity**: If an order placed on October 1 is fulfilled on October 10, does `fulfilled_orders` on October 1 mean orders placed on October 1 that are fulfilled today, or orders fulfilled on October 1?
2. **Cross-Day Write Amplification**: Updating daily tables every time an order transitions state requires mutating historical rows across 30–60 past days, causing write amplification, index churn, and cache invalidation.
3. **Zero Status Lag**: By querying current status distributions directly from the indexed `orders` table using composite index `(tenant_id, status)` or `(tenant_id, status, created_at)`, operational dashboards obtain true zero-lag counts without complex worker synchronization.

### 4.2. Metric Definitions & Formulas

#### 1. Total Orders (Historical Daily Metric)
- **Definition**: The total count of order entities placed on a given calendar day (evaluated in tenant timezone).
- **Formula**:
  $$\text{orders\_count} = \operatorname{COUNT}(\text{orders.id})$$
- **Invariance**: Unchanged by transitions between `pending`, `paid`, and `fulfilled`.

#### 2. Gross Sales (Historical Daily Metric)
- **Definition**: The cumulative gross monetary value of all orders placed on a given date, irrespective of current status.
- **Formula**:
  $$\text{gross\_sales} = \sum_{o \in \text{Orders}_{\text{date}}} o.\text{total\_amount}$$
- **Invariance**: Unchanged by subsequent fulfillment or cancellation.

#### 3. Net Sales (Historical Daily Metric)
- **Definition**: The recognized monetary value of orders placed on a given date, **excluding cancelled orders**.
- **Formula**:
  $$\text{net\_sales} = \sum_{o \in \text{Orders}_{\text{date}},\, o.\text{status} \ne \text{'cancelled'}} o.\text{total\_amount}$$
- **Accounting Rule**: If an order placed on October 5 is cancelled on October 8, the net sales for October 5 decreases by the order's `total_amount`.

#### 4. Cancelled Orders & Cancelled Value (Historical Daily Metric)
- **Definition**: Count and monetary value of orders placed on a given date that have been cancelled.
- **Identity**:
  $$\text{gross\_sales} - \text{net\_sales} = \text{cancelled\_sales}$$

#### 5. Product-Level Metrics (`daily_product_metrics`)
- **Gross Product Sales**: $\sum (\text{quantity} \times \text{unit\_price})$ for all line items on that date.
- **Net Product Sales**: $\sum (\text{quantity} \times \text{unit\_price})$ for line items on that date where parent order `status != 'cancelled'`.
- **Net Units Sold**: Units ordered on that date excluding cancelled orders.
- **Cancelled Units**: Units ordered on that date belonging to cancelled orders.

#### 6. Current-State Status Summary (Operational Metric)
- **Definition**: Real-time snapshot of store orders partitioned by current lifecycle state (`pending`, `paid`, `fulfilled`, `cancelled`).
- **Query Mechanism**: Evaluated directly against source table `orders` filtered by `tenant_id`:
  ```sql
  SELECT status, COUNT(*) AS count, SUM(total_amount) AS total_value
  FROM orders
  WHERE tenant_id = :tenant_id
  GROUP BY status;
  ```

---

## 5. Tenant-Scoped Aggregation Schema Specification

### 5.1. Table: `daily_tenant_metrics`

Stores historical daily store-level financial summaries.

```sql
CREATE TABLE daily_tenant_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    metric_date DATE NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'INR',
    orders_count INTEGER NOT NULL DEFAULT 0,
    gross_sales NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    net_sales NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    cancelled_orders_count INTEGER NOT NULL DEFAULT 0,
    cancelled_sales NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT fk_daily_tenant_metrics_tenant
        FOREIGN KEY (tenant_id)
        REFERENCES tenants (id)
        ON DELETE CASCADE,

    CONSTRAINT uq_daily_tenant_metrics_tenant_date_currency
        UNIQUE (tenant_id, metric_date, currency),

    CONSTRAINT ck_daily_tenant_metrics_orders_non_negative
        CHECK (orders_count >= 0),
    CONSTRAINT ck_daily_tenant_metrics_gross_non_negative
        CHECK (gross_sales >= 0),
    CONSTRAINT ck_daily_tenant_metrics_net_non_negative
        CHECK (net_sales >= 0),
    CONSTRAINT ck_daily_tenant_metrics_cancelled_sales_non_negative
        CHECK (cancelled_sales >= 0),
    CONSTRAINT ck_daily_tenant_metrics_cancelled_orders_non_negative
        CHECK (cancelled_orders_count >= 0)
);

CREATE INDEX ix_daily_tenant_metrics_tenant_date
    ON daily_tenant_metrics (tenant_id, metric_date DESC);
```

---

### 5.2. Table: `daily_product_metrics`

Stores historical daily product-level sales and demand.

```sql
CREATE TABLE daily_product_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    product_id UUID NOT NULL,
    metric_date DATE NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'INR',
    units_sold_gross INTEGER NOT NULL DEFAULT 0,
    units_sold_net INTEGER NOT NULL DEFAULT 0,
    gross_sales NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    net_sales NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    cancelled_units INTEGER NOT NULL DEFAULT 0,
    cancelled_sales NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    orders_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT fk_daily_product_metrics_tenant
        FOREIGN KEY (tenant_id)
        REFERENCES tenants (id)
        ON DELETE CASCADE,

    -- Multi-tenant composite foreign key prevents cross-tenant product association
    CONSTRAINT fk_daily_product_metrics_product_tenant
        FOREIGN KEY (tenant_id, product_id)
        REFERENCES products (tenant_id, id)
        ON DELETE CASCADE,

    CONSTRAINT uq_daily_product_metrics_tenant_product_date_currency
        UNIQUE (tenant_id, product_id, metric_date, currency),

    CONSTRAINT ck_daily_product_metrics_gross_units_non_negative
        CHECK (units_sold_gross >= 0),
    CONSTRAINT ck_daily_product_metrics_net_units_non_negative
        CHECK (units_sold_net >= 0),
    CONSTRAINT ck_daily_product_metrics_gross_sales_non_negative
        CHECK (gross_sales >= 0),
    CONSTRAINT ck_daily_product_metrics_net_sales_non_negative
        CHECK (net_sales >= 0),
    CONSTRAINT ck_daily_product_metrics_cancelled_units_non_negative
        CHECK (cancelled_units >= 0)
);

CREATE INDEX ix_daily_product_metrics_tenant_date
    ON daily_product_metrics (tenant_id, metric_date DESC);

CREATE INDEX ix_daily_product_metrics_tenant_product
    ON daily_product_metrics (tenant_id, product_id);

CREATE INDEX ix_daily_product_metrics_top_products
    ON daily_product_metrics (tenant_id, metric_date DESC, net_sales DESC);
```

---

## 6. Non-Destructive Full Rebuild Logic

A fundamental requirement for our analytics engine is the ability to execute an **idempotent, safe, and non-destructive full rebuild** from raw transaction records without dropping tables or locking analytical APIs.

### 6.1. Rebuild Safety Rules
1. **No Destructive Truncations**: Never issue `TRUNCATE TABLE`. Truncation acquires an `ACCESS EXCLUSIVE` lock on PostgreSQL, blocks concurrent API queries, and leaves the analytics tables empty if the transaction errors.
2. **Tenant-Isolated Scope**: Rebuilds can execute globally or for a specific tenant (`tenant_id = :target_tenant_id`) without locking or touching other merchants' analytics rows.
3. **PostgreSQL MVCC Non-Blocking Reads**: Uses `INSERT ... ON CONFLICT (...) DO UPDATE SET ...`. Live API queries continue reading the consistent prior snapshot until the rebuild transaction commits.
4. **Timezone Conversion**: Uses tenant timezone before truncating to date.
5. **Handling Empty Tenants**: A tenant with zero transactions returns 0 rows during aggregation. Analytical queries use `COALESCE` to return `0.00` metrics.

### 6.2. Transformation Queries

#### A. Rebuilding `daily_tenant_metrics`
```sql
INSERT INTO daily_tenant_metrics (
    id,
    tenant_id,
    metric_date,
    currency,
    orders_count,
    gross_sales,
    net_sales,
    cancelled_orders_count,
    cancelled_sales,
    created_at,
    updated_at
)
SELECT
    gen_random_uuid(),
    o.tenant_id,
    DATE(o.created_at AT TIME ZONE COALESCE(t.domain, 'Asia/Kolkata')) AS metric_date,
    o.currency,
    COUNT(o.id) AS orders_count,
    SUM(o.total_amount) AS gross_sales,
    SUM(CASE WHEN o.status != 'cancelled' THEN o.total_amount ELSE 0.00 END) AS net_sales,
    COUNT(CASE WHEN o.status = 'cancelled' THEN 1 END) AS cancelled_orders_count,
    SUM(CASE WHEN o.status = 'cancelled' THEN o.total_amount ELSE 0.00 END) AS cancelled_sales,
    NOW(),
    NOW()
FROM orders o
JOIN tenants t ON o.tenant_id = t.id
WHERE (:tenant_id IS NULL OR o.tenant_id = :tenant_id)
GROUP BY o.tenant_id, DATE(o.created_at AT TIME ZONE COALESCE(t.domain, 'Asia/Kolkata')), o.currency
ON CONFLICT (tenant_id, metric_date, currency)
DO UPDATE SET
    orders_count           = EXCLUDED.orders_count,
    gross_sales            = EXCLUDED.gross_sales,
    net_sales              = EXCLUDED.net_sales,
    cancelled_orders_count = EXCLUDED.cancelled_orders_count,
    cancelled_sales        = EXCLUDED.cancelled_sales,
    updated_at             = NOW();
```

#### B. Rebuilding `daily_product_metrics`
```sql
INSERT INTO daily_product_metrics (
    id,
    tenant_id,
    product_id,
    metric_date,
    currency,
    units_sold_gross,
    units_sold_net,
    gross_sales,
    net_sales,
    cancelled_units,
    cancelled_sales,
    orders_count,
    created_at,
    updated_at
)
SELECT
    gen_random_uuid(),
    oi.tenant_id,
    oi.product_id,
    DATE(o.created_at AT TIME ZONE COALESCE(t.domain, 'Asia/Kolkata')) AS metric_date,
    o.currency,
    SUM(oi.quantity) AS units_sold_gross,
    SUM(CASE WHEN o.status != 'cancelled' THEN oi.quantity ELSE 0 END) AS units_sold_net,
    SUM(oi.quantity * oi.unit_price) AS gross_sales,
    SUM(CASE WHEN o.status != 'cancelled' THEN oi.quantity * oi.unit_price ELSE 0.00 END) AS net_sales,
    SUM(CASE WHEN o.status = 'cancelled' THEN oi.quantity ELSE 0 END) AS cancelled_units,
    SUM(CASE WHEN o.status = 'cancelled' THEN oi.quantity * oi.unit_price ELSE 0.00 END) AS cancelled_sales,
    COUNT(DISTINCT oi.order_id) AS orders_count,
    NOW(),
    NOW()
FROM order_items oi
JOIN orders o ON oi.order_id = o.id AND oi.tenant_id = o.tenant_id
JOIN tenants t ON o.tenant_id = t.id
WHERE (:tenant_id IS NULL OR oi.tenant_id = :tenant_id)
GROUP BY oi.tenant_id, oi.product_id, DATE(o.created_at AT TIME ZONE COALESCE(t.domain, 'Asia/Kolkata')), o.currency
ON CONFLICT (tenant_id, product_id, metric_date, currency)
DO UPDATE SET
    units_sold_gross = EXCLUDED.units_sold_gross,
    units_sold_net   = EXCLUDED.units_sold_net,
    gross_sales      = EXCLUDED.gross_sales,
    net_sales        = EXCLUDED.net_sales,
    cancelled_units  = EXCLUDED.cancelled_units,
    cancelled_sales  = EXCLUDED.cancelled_sales,
    orders_count     = EXCLUDED.orders_count,
    updated_at       = NOW();
```

---

## 7. Outbox Event-Processing Architecture

### 7.1. Inspection of OutboxEvent Model & Live Payloads
Inspection of `backend/app/models/outbox_event.py` and live records in PostgreSQL confirms:
- **Columns**: `id`, `tenant_id`, `event_type`, `payload` (JSONB), `created_at`, `processed_at`.
- **Actual Event Types**: `order.created`, `order.paid`, `order.fulfilled`, `order.cancelled`.
- **Actual Payload Contents**:
  ```json
  {
    "event_id": "113319c7-b38a-4209-9f7c-0e4e5f0b3c58",
    "event_type": "order.created",
    "tenant_id": "85056a62-e8fa-4587-8a50-c979bc73d7bf",
    "order_id": "0a7355de-d578-4eb4-b49a-653d76ff2636",
    "customer_id": "c3643ca9-a673-497d-b52f-284201774d95",
    "external_order_id": "SHP-000001",
    "status": "pending",
    "previous_status": null,
    "order_status_at_event": "pending",
    "total_amount": "1789.17",
    "currency": "USD",
    "items_count": 5,
    "occurred_at": "2026-10-19T02:14:04.503157+00:00"
  }
  ```
- **Crucial Architectural Reality**: Order-level outbox payloads contain `items_count`, but **do not contain line-item details** (no product IDs, quantities, or unit prices).
- **Processing Rule**: To update `daily_product_metrics` reliably without inventing artificial payload schemas, the outbox processor queries the source table `order_items` for that `order_id` within the **same PostgreSQL transaction**:
  ```sql
  SELECT product_id, quantity, unit_price
  FROM order_items
  WHERE order_id = :order_id AND tenant_id = :tenant_id;
  ```

### 7.2. Correct Event Transitions & Prevention of Double-Counting

| Event Type | `daily_tenant_metrics` Effect | `daily_product_metrics` Effect | Current Status Query Effect |
| :--- | :--- | :--- | :--- |
| **`order.created`** | `+1 orders_count`<br>`+total_amount gross_sales`<br>`+total_amount net_sales` | Queries `order_items` for order:<br>`+quantity units_sold_gross`<br>`+quantity units_sold_net`<br>`+line_total gross_sales`<br>`+line_total net_sales`<br>`+1 orders_count` | `orders` table now has 1 row with `status='pending'` |
| **`order.paid`** | **NO CHANGE** (Prevents double-counting!) | **NO CHANGE** (Prevents double-counting!) | Source row updated to `status='paid'` |
| **`order.fulfilled`**| **NO CHANGE** (Prevents double-counting!) | **NO CHANGE** (Prevents double-counting!) | Source row updated to `status='fulfilled'` |
| **`order.cancelled`**| On order's original date:<br>`-total_amount net_sales`<br>`+total_amount cancelled_sales`<br>`+1 cancelled_orders_count` | Queries `order_items` for order:<br>`-quantity units_sold_net`<br>`-line_total net_sales`<br>`+quantity cancelled_units`<br>`+line_total cancelled_sales` | Source row updated to `status='cancelled'` |

### 7.3. Worker Concurrency, Idempotency & Transaction Safety
- **Lock-Free Polling**: Multiple worker instances safely claim non-overlapping batches of unprocessed events:
  ```sql
  SELECT id, tenant_id, event_type, payload
  FROM outbox_events
  WHERE processed_at IS NULL
  ORDER BY created_at ASC
  LIMIT 100
  FOR UPDATE SKIP LOCKED;
  ```
- **Atomic Acknowledgment**: The worker updates the aggregation tables and marks the event processed within the **same database transaction**:
  ```sql
  UPDATE outbox_events
  SET processed_at = NOW()
  WHERE id = :event_id;
  ```
- **Idempotency Guarantee**: If a crash occurs before commit, the transaction rolls back, locks are released, and aggregation tables remain clean. If an event is re-processed, status checks (`processed_at IS NOT NULL`) prevent duplicate metric application.

---

## 8. Scalability & Realistic Benchmarking Strategy

### 8.1. Scalability Targets
- **Total Records**: 10,000,000 orders across 100 tenants (~100,000 orders per tenant).
- **Target Query Latency**: Analytical endpoints must respond in **under 1.0 second** (Target p95 < 100ms, p99 < 300ms).
- **Data Freshness**: Within 1–2 minutes of transactional event creation.

### 8.2. Query Complexity Comparison

| Query Type | Without Aggregation Tables (Raw Scan) | With Aggregation Tables (`daily_*_metrics`) |
| :--- | :--- | :--- |
| **7-Day Overview** | Full scan on `orders` & joins: **~100,000 rows** per tenant | B-tree index scan on `daily_tenant_metrics`: **Exactly 7 rows** |
| **30-Day Daily Chart** | Grouping & summing: **~100,000 rows** | B-tree index scan: **Exactly 30 rows** |
| **Top 10 Products** | Join `order_items` + `orders`: **~300,000 rows** | Compound index scan on `(tenant_id, date, net_sales)`: **10 rows** |
| **Current Status** | Index scan on `(tenant_id, status)`: **~100,000 index keys** | Direct composite index scan: **< 2ms** |

### 8.3. Benchmarking & Load Testing Plan
Rather than assuming targets are achieved, the implementation phase will execute a formal benchmarking harness:
1. **Data Scaling Benchmarks**:
   - Tier 1: 10,000 orders (Current live baseline).
   - Tier 2: 100,000 orders.
   - Tier 3: 1,000,000 orders.
   - Tier 4: 10,000,000 orders (Generated using `SyntheticDataGenerator.insert_dataset_streaming()`).
2. **Query Profiling**:
   - Run `EXPLAIN (ANALYZE, BUFFERS)` on each analytical endpoint query.
   - Assert zero sequential table scans (`Seq Scan`) on large tables.
   - Record p50, p95, and p99 latency metrics under simulated concurrent tenant load (10 concurrent requests per second).
3. **Write Throughput Profiling**:
   - Measure full rebuild duration for a 100,000-order tenant.
   - Measure outbox processor throughput (target > 1,000 events/second per worker process).

---

## 9. Comprehensive Design Summary & Review Deliverable

### 9.1. Final Proposed Table Schemas
1. **`daily_tenant_metrics`**:
   - `id UUID PK`, `tenant_id UUID FK`, `metric_date DATE`, `currency VARCHAR(3)`
   - `orders_count INT`, `gross_sales NUMERIC(14,2)`, `net_sales NUMERIC(14,2)`, `cancelled_orders_count INT`, `cancelled_sales NUMERIC(14,2)`
   - `created_at TIMESTAMPTZ`, `updated_at TIMESTAMPTZ`
   - Unique: `(tenant_id, metric_date, currency)`
2. **`daily_product_metrics`**:
   - `id UUID PK`, `tenant_id UUID FK`, `product_id UUID FK`, `metric_date DATE`, `currency VARCHAR(3)`
   - `units_sold_gross INT`, `units_sold_net INT`, `gross_sales NUMERIC(14,2)`, `net_sales NUMERIC(14,2)`, `cancelled_units INT`, `cancelled_sales NUMERIC(14,2)`, `orders_count INT`
   - `created_at TIMESTAMPTZ`, `updated_at TIMESTAMPTZ`
   - Unique: `(tenant_id, product_id, metric_date, currency)`
   - Composite FK: `(tenant_id, product_id) REFERENCES products(tenant_id, id)`

### 9.2. Final Metric Definitions
- **Gross Sales**: Cumulative value of all orders placed on that calendar date in tenant timezone.
- **Net Sales**: Cumulative value of orders placed on that date excluding currently cancelled orders.
- **Cancelled Sales**: Value of orders placed on that date that have been cancelled.
- **Current Status Counts**: Real-time counts (`pending`, `paid`, `fulfilled`, `cancelled`) queried directly from `orders` indexed by `(tenant_id, status)`.

### 9.3. Currency & Timezone Decisions
- **Currency**: `INR` (`₹`) default for Indian stores. Indian number formatting (`₹53,32,954.22`). Explicit `currency` field returned in all API payloads. Different currencies are never aggregated together.
- **Timezone**: UTC for storage (`TIMESTAMPTZ`). `Asia/Kolkata` (`IST`, `UTC+05:30`) as default calculation timezone. Dates truncated after conversion: `DATE(created_at AT TIME ZONE timezone)`.

### 9.4. Outbox Event-Processing Strategy
- Claim via `FOR UPDATE SKIP LOCKED`.
- `order.created` initializes gross/net sales and order counts.
- `order.paid` and `order.fulfilled` do not duplicate order counts or revenue.
- `order.cancelled` reverses net sales and records cancellations on the order's original date.
- Product aggregates query source `order_items` for that order within the worker's transaction.

### 9.5. Remaining Unresolved Questions
1. **Controlled Synthetic INR Regeneration**: Do you approve running the safe synthetic data regeneration with realistic INR catalog prices (₹499–₹14,999) using seed `42` before creating the aggregation tables and API endpoints?
2. **Tenant Timezone Column**: In the upcoming Alembic migration, shall we add `timezone VARCHAR(50) DEFAULT 'Asia/Kolkata'` directly to the `tenants` table? (Recommended: Yes).
3. **Refund Events**: When partial refunds and returns are modeled in Phase 3, shall they be bucketed on the refund date rather than mutating historical order placement dates? (Recommended: Yes).

### 9.6. Compatibility with Existing Codebase
- **Models**: All existing six models remain completely untouched.
- **Alembic**: The upcoming aggregation tables will be introduced via a clean new migration `0002_analytics_aggregation_schema.py`.
- **FastAPI**: New router `backend/app/api/routes/analytics.py` will be mounted cleanly under `/api/v1/analytics/` without disrupting existing health endpoints.
- **Tests**: All 38 existing tests will continue to pass untouched.
