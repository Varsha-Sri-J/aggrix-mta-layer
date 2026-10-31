# AGGRIX Database Architecture & Schema Specification

## 1. Overview & Architectural Principles

AGGRIX is a high-performance multi-tenant analytics and aggregation engine tailored for Shopify-inspired e-commerce stores. The database layer is engineered from the ground up on **PostgreSQL** using **SQLAlchemy 2.0** and **Alembic**, prioritizing:

1. **Guaranteed Tenant Isolation at the Engine Level**: No tenant may ever reference or access records belonging to another tenant, enforced physically by PostgreSQL foreign key constraints rather than relying solely on application-level filtering.
2. **Deterministic Constraint Naming**: Predictable naming conventions across all constraints and indexes (`pk_*`, `fk_*`, `uq_*`, `ck_*`, `ix_*`) to ensure seamless Alembic migrations without orphaned anonymous constraints.
3. **Data Integrity & Immutability**: Timezone-aware timestamps (`TIMESTAMPTZ`), strict numeric precision for monetary values (`NUMERIC(12, 2)`), client-side UUID generation (`UUIDv4`), and check constraints preventing invalid data states (such as negative prices or zero quantities).
4. **Optimized Analytics & Event Streaming**: Dedicated compound indexes for chronological and status queries, coupled with PostgreSQL partial indexing for high-throughput Transactional Outbox polling.

---

## 2. Entity-Relationship & Schema Diagram

```mermaid
erDiagram
    TENANTS ||--o{ CUSTOMERS : "owns (1:N)"
    TENANTS ||--o{ PRODUCTS : "owns (1:N)"
    TENANTS ||--o{ ORDERS : "owns (1:N)"
    TENANTS ||--o{ ORDER_ITEMS : "owns (1:N)"
    TENANTS ||--o{ OUTBOX_EVENTS : "owns (1:N)"

    CUSTOMERS ||--o{ ORDERS : "places (1:N, scoped by tenant_id)"
    ORDERS ||--|{ ORDER_ITEMS : "contains (1:N, scoped by tenant_id)"
    PRODUCTS ||--o{ ORDER_ITEMS : "referenced by (1:N, scoped by tenant_id)"

    TENANTS {
        uuid id PK
        varchar name
        varchar domain UK
        timestamptz created_at
        timestamptz updated_at
    }

    CUSTOMERS {
        uuid id PK
        uuid tenant_id FK
        varchar email
        varchar name
        timestamptz created_at
        timestamptz updated_at
    }

    PRODUCTS {
        uuid id PK
        uuid tenant_id FK
        varchar name
        varchar sku
        numeric price
        varchar currency
        timestamptz created_at
        timestamptz updated_at
    }

    ORDERS {
        uuid id PK
        uuid tenant_id FK
        uuid customer_id FK
        varchar external_order_id
        numeric total_amount
        varchar currency
        varchar status
        timestamptz created_at
        timestamptz updated_at
    }

    ORDER_ITEMS {
        uuid id PK
        uuid tenant_id FK
        uuid order_id FK
        uuid product_id FK
        int quantity
        numeric unit_price
        timestamptz created_at
    }

    OUTBOX_EVENTS {
        uuid id PK
        uuid tenant_id FK
        varchar event_type
        jsonb payload
        timestamptz created_at
        timestamptz processed_at
    }
```

---

## 3. Table Specifications

### 3.1. `tenants`
The root organizational entity. All store data is partitioned by `tenant_id`.

| Column | PostgreSQL Type | Nullable | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | No | `uuid_generate_v4()` | Primary key. |
| `name` | `VARCHAR(255)` | No | — | Store/brand business name. |
| `domain` | `VARCHAR(255)` | No | — | Unique store domain (e.g., `store.myshopify.com`). |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Record creation timestamp. |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` | Record update timestamp. |

- **Constraints**:
  - `pk_tenants`: `PRIMARY KEY (id)`
  - `uq_tenants_domain`: `UNIQUE (domain)`
- **Indexes**:
  - `ix_tenants_domain` on `(domain)` (unique)

---

### 3.2. `customers`
Customer profiles scoped to an individual tenant.

| Column | PostgreSQL Type | Nullable | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | No | `uuid_generate_v4()` | Primary key. |
| `tenant_id` | `UUID` | No | — | Owning tenant identifier. |
| `email` | `VARCHAR(255)` | No | — | Customer email address. |
| `name` | `VARCHAR(255)` | Yes | `NULL` | Full customer display name. |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Record creation timestamp. |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` | Record update timestamp. |

- **Constraints**:
  - `pk_customers`: `PRIMARY KEY (id)`
  - `fk_customers_tenant_id`: `FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE`
  - `uq_customers_tenant_id_id`: `UNIQUE (tenant_id, id)` *(enables composite foreign key reference from `orders`)*
  - `uq_customers_tenant_id_email`: `UNIQUE (tenant_id, email)` *(tenant-scoped email uniqueness)*
- **Indexes**:
  - `ix_customers_tenant_id` on `(tenant_id)`
  - `ix_customers_email` on `(email)`

---

### 3.3. `products`
Store catalog items scoped to a tenant.

| Column | PostgreSQL Type | Nullable | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | No | `uuid_generate_v4()` | Primary key. |
| `tenant_id` | `UUID` | No | — | Owning tenant identifier. |
| `name` | `VARCHAR(255)` | No | — | Product title. |
| `sku` | `VARCHAR(100)` | No | — | Stock keeping unit. |
| `price` | `NUMERIC(12, 2)` | No | — | Selling price (must be $\ge 0$). |
| `currency` | `VARCHAR(3)` | No | `'USD'` | ISO 4217 three-letter currency code. |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Record creation timestamp. |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` | Record update timestamp. |

- **Constraints**:
  - `pk_products`: `PRIMARY KEY (id)`
  - `ck_products_price_non_negative`: `CHECK (price >= 0)`
  - `fk_products_tenant_id`: `FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE`
  - `uq_products_tenant_id_id`: `UNIQUE (tenant_id, id)` *(enables composite foreign key reference from `order_items`)*
  - `uq_products_tenant_id_sku`: `UNIQUE (tenant_id, sku)` *(tenant-scoped SKU uniqueness)*
- **Indexes**:
  - `ix_products_tenant_id` on `(tenant_id)`
  - `ix_products_sku` on `(sku)`

---

### 3.4. `orders`
E-commerce orders placed by customers within a tenant.

| Column | PostgreSQL Type | Nullable | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | No | `uuid_generate_v4()` | Primary key. |
| `tenant_id` | `UUID` | No | — | Owning tenant identifier. |
| `customer_id` | `UUID` | No | — | Customer identifier (co-verified with `tenant_id`). |
| `external_order_id` | `VARCHAR(255)` | No | — | Source platform order ID (e.g., Shopify `#1001`). |
| `total_amount` | `NUMERIC(12, 2)` | No | — | Total monetary value of order (must be $\ge 0$). |
| `currency` | `VARCHAR(3)` | No | `'USD'` | ISO 4217 currency code. |
| `status` | `VARCHAR(50)` | No | `'pending'` | Current status (`pending`, `paid`, `fulfilled`, etc.). |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Order placement timestamp. |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` | Order update timestamp. |

- **Constraints**:
  - `pk_orders`: `PRIMARY KEY (id)`
  - `ck_orders_total_amount_non_negative`: `CHECK (total_amount >= 0)`
  - `fk_orders_tenant_id`: `FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE`
  - `fk_orders_customer_tenant`: `FOREIGN KEY (tenant_id, customer_id) REFERENCES customers(tenant_id, id) ON DELETE RESTRICT` *(strict composite isolation)*
  - `uq_orders_tenant_id_id`: `UNIQUE (tenant_id, id)` *(enables composite reference from `order_items`)*
  - `uq_orders_tenant_id_external_order_id`: `UNIQUE (tenant_id, external_order_id)` *(tenant-scoped external order ID)*
- **Indexes**:
  - `ix_orders_tenant_id` on `(tenant_id)`
  - `ix_orders_tenant_status` on `(tenant_id, status)`
  - `ix_orders_tenant_created_at` on `(tenant_id, created_at)`
  - `ix_orders_tenant_status_created_at` on `(tenant_id, status, created_at)`
  - `ix_orders_tenant_customer_id` on `(tenant_id, customer_id)`

---

### 3.5. `order_items`
Line items belonging to an order, connecting orders and catalog products.

| Column | PostgreSQL Type | Nullable | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | No | `uuid_generate_v4()` | Primary key. |
| `tenant_id` | `UUID` | No | — | Owning tenant identifier. |
| `order_id` | `UUID` | No | — | Parent order identifier. |
| `product_id` | `UUID` | No | — | Purchased product identifier. |
| `quantity` | `INTEGER` | No | — | Quantity purchased (must be $> 0$). |
| `unit_price` | `NUMERIC(12, 2)` | No | — | Agreed unit price at purchase time (must be $\ge 0$). |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Record creation timestamp. |

- **Constraints**:
  - `pk_order_items`: `PRIMARY KEY (id)`
  - `ck_order_items_quantity_positive`: `CHECK (quantity > 0)`
  - `ck_order_items_unit_price_non_negative`: `CHECK (unit_price >= 0)`
  - `fk_order_items_tenant_id`: `FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE`
  - `fk_order_items_order_tenant`: `FOREIGN KEY (tenant_id, order_id) REFERENCES orders(tenant_id, id) ON DELETE CASCADE`
  - `fk_order_items_product_tenant`: `FOREIGN KEY (tenant_id, product_id) REFERENCES products(tenant_id, id) ON DELETE RESTRICT`
- **Indexes**:
  - `ix_order_items_tenant_id` on `(tenant_id)`
  - `ix_order_items_tenant_order_id` on `(tenant_id, order_id)`
  - `ix_order_items_tenant_product_id` on `(tenant_id, product_id)`

---

### 3.6. `outbox_events`
Transactional Outbox table for atomic event publication.

| Column | PostgreSQL Type | Nullable | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | No | `uuid_generate_v4()` | Primary key. |
| `tenant_id` | `UUID` | No | — | Owning tenant identifier. |
| `event_type` | `VARCHAR(100)` | No | — | Event classification (e.g. `order.created`, `order.paid`). |
| `payload` | `JSONB` | No | — | Structured JSON event data. |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Outbox insertion timestamp. |
| `processed_at` | `TIMESTAMPTZ` | Yes | `NULL` | Timestamp when published (`NULL` while pending). |

- **Constraints**:
  - `pk_outbox_events`: `PRIMARY KEY (id)`
  - `fk_outbox_events_tenant_id`: `FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE`
- **Indexes**:
  - `ix_outbox_events_tenant_id` on `(tenant_id)`
  - `ix_outbox_events_unprocessed`: `INDEX (created_at) WHERE processed_at IS NULL` *(PostgreSQL partial index)*
  - `ix_outbox_events_processed_at` on `(processed_at)`
  - `ix_outbox_events_tenant_created` on `(tenant_id, created_at)`

---

## 4. Multi-Tenant Isolation Strategy

### 4.1. The Cross-Tenant Reference Vulnerability
In standard single-column foreign key designs:
```sql
-- DANGEROUS: Allows cross-tenant data corruption!
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id),
    customer_id UUID REFERENCES customers(id) -- DOES NOT verify that customer belongs to tenant_id!
);
```
If an API bug occurs, Tenant B could pass `customer_id` belonging to Tenant A. Because the foreign key only checks if `customer_id` exists in `customers`, the row is written, causing critical data leakage.

### 4.2. Composite Foreign Keys as the Solution
AGGRIX eliminates this vulnerability entirely at the PostgreSQL engine level by enforcing **Composite Foreign Keys**:
```sql
CONSTRAINT fk_orders_customer_tenant
    FOREIGN KEY (tenant_id, customer_id)
    REFERENCES customers (tenant_id, id)
    ON DELETE RESTRICT;
```
For this constraint to exist, `customers` defines a composite unique constraint on `(tenant_id, id)`. Because both columns must match simultaneously, **it is mathematically impossible to assign Tenant A's customer to Tenant B's order**.

Similarly:
- `order_items(tenant_id, order_id) -> orders(tenant_id, id)` guarantees line items cannot reference an order from a different tenant.
- `order_items(tenant_id, product_id) -> products(tenant_id, id)` guarantees line items cannot reference a product catalog from a different tenant.

### 4.3. Tenant-Scoped Natural Uniqueness
In a multi-tenant SaaS, natural keys must not conflict across different tenants:
- Two distinct stores can have a customer with `john@example.com`.
- Two distinct stores can have a product with SKU `TSHIRT-BLK-S`.
- Two distinct stores can both issue order `#1001`.

AGGRIX enforces tenant-scoped composite unique constraints:
- `UNIQUE (tenant_id, email)` on `customers`
- `UNIQUE (tenant_id, sku)` on `products`
- `UNIQUE (tenant_id, external_order_id)` on `orders`

### 4.4. Deletion Cascades & Referential Integrity
- Deleting a `tenant` cascades down to all associated `customers`, `products`, `orders`, `order_items`, and `outbox_events` (`ON DELETE CASCADE`).
- Deleting an `order` cascades down to its `order_items` (`ON DELETE CASCADE`).
- Deleting a `customer` or `product` with existing historical orders is strictly forbidden (`ON DELETE RESTRICT`) to protect ledger integrity.

---

## 5. Indexing & Query Optimization Strategy

1. **Composite Foreign Key Indexes**:
   Every foreign key column pair is indexed (`(tenant_id, order_id)`, `(tenant_id, product_id)`, `(tenant_id, customer_id)`), preventing full table scans on joins and deletes.
2. **Order Chronological & Status Analytics**:
   - `ix_orders_tenant_status_created_at` on `(tenant_id, status, created_at)`: Optimizes dashboard filtering by order status within specific date intervals.
   - `ix_orders_tenant_created_at` on `(tenant_id, created_at)`: Optimizes time-series analytics and revenue aggregation queries.
3. **High-Performance Transactional Outbox**:
   - `ix_outbox_events_unprocessed` on `(created_at) WHERE processed_at IS NULL`: In an active system with millions of events, 99.9% of rows will have `processed_at IS NOT NULL`. A standard B-tree index on `processed_at` would be enormous and heavily fragmented. The PostgreSQL partial index only tracks pending events, keeping index size negligible (<1MB) and polling latency sub-millisecond.

---

## 6. Database Connection & Pooling

The connection module (`app/database/connection.py`) provides production-grade pooling and lifecycle management:

- **Pydantic Settings**: Strongly typed configuration loaded from `.env` or system environment variables with automatic URL normalization (e.g. converting `postgres://` to `postgresql+psycopg2://`).
- **Connection Health Checks**: `pool_pre_ping=True` proactively validates socket health before handing connections to workers, eliminating dropped-connection errors during idle periods.
- **FastAPI Session Dependency**:
  ```python
  from fastapi import Depends
  from sqlalchemy.orm import Session
  from app.database import get_db

  @router.get("/orders")
  def list_orders(db: Session = Depends(get_db)):
      ...
  ```
- **Context Manager for Background Jobs/Scripts**:
  ```python
  from app.database import get_db_session

  with get_db_session() as session:
      # Automatically commits on success, rolls back on exception
      ...
  ```

---

## 7. Migration Commands (Alembic)

Alembic is pre-configured to detect SQLAlchemy metadata in `app.database.base.Base.metadata`.

### Execute Online Migrations
Apply migrations against the configured database:
```bash
alembic upgrade head
```

### Inspect Generated SQL Offline (Dry Run)
Inspect the generated raw PostgreSQL DDL without connecting to a live database:
```bash
alembic upgrade head --sql
```

### Revert Migrations
Roll back the latest migration:
```bash
alembic downgrade -1
```

### Generate New Migrations
When adding new models or modifying existing columns:
```bash
alembic revision --autogenerate -m "describe_change"
```

---

## 8. Environment Variable Requirements

Create a `.env` file in the project root based on `.env.example`:

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `DATABASE_URL` | `postgresql+psycopg2://postgres:postgres@localhost:5432/aggrix` | Application PostgreSQL connection string. |
| `TEST_DATABASE_URL` | `postgresql+psycopg2://postgres:postgres@localhost:5432/aggrix_test` | PostgreSQL connection string for integration tests. |
| `DB_POOL_SIZE` | `10` | Number of persistent connections in pool. |
| `DB_MAX_OVERFLOW` | `20` | Maximum temporary connections above pool size. |
| `DB_POOL_TIMEOUT` | `30` | Seconds to wait before timing out on connection checkout. |
| `DB_POOL_RECYCLE` | `1800` | Seconds before recycling connections (30 min). |
| `DB_POOL_PRE_PING` | `true` | Ping connection on checkout to verify liveness. |
| `DB_ECHO` | `false` | Set to `true` to echo all SQL statements to stdout. |

---

## 9. Running Database Tests

The test suite is built on **pytest** and includes both offline schema validation and live PostgreSQL integration tests.

### Run All Tests
```bash
pytest -v
```

### Run with Live PostgreSQL (Docker Compose)
1. Start the PostgreSQL container:
   ```bash
   docker compose up -d
   ```
2. Run pytest:
   ```bash
   pytest -v
   ```
If PostgreSQL is offline, `test_postgres_live.py` will skip automatically with clear instructions, while all metadata, Alembic DDL generation, and multi-tenant constraint verification tests pass in-memory.

---

## 10. Teammate Integration Guide (FastAPI)

When integrating into the FastAPI application:

1. **Import Database Models**:
   ```python
   from app.models import Tenant, Customer, Product, Order, OrderItem, OutboxEvent
   ```

2. **Inject Database Sessions into Endpoints**:
   ```python
   from fastapi import APIRouter, Depends, HTTPException, status
   from sqlalchemy.orm import Session
   from app.database import get_db

   router = APIRouter(prefix="/tenants", tags=["tenants"])

   @router.post("/", status_code=status.HTTP_201_CREATED)
   def create_tenant(name: str, domain: str, db: Session = Depends(get_db)):
       tenant = Tenant(name=name, domain=domain)
       db.add(tenant)
       db.commit()
       db.refresh(tenant)
       return tenant
   ```

3. **Multi-Tenant Filter Pattern**:
   Always filter queries by `tenant_id` at the route/service layer:
   ```python
   @router.get("/{tenant_id}/products")
   def list_products(tenant_id: uuid.UUID, db: Session = Depends(get_db)):
       return db.query(Product).filter(Product.tenant_id == tenant_id).all()
   ```
   Even if an application developer forgets or introduces a bug in cross-referencing child tables, the composite foreign keys in the PostgreSQL database will reject invalid cross-tenant foreign key assignments with an `IntegrityError`.

