# AGGRIX — Multi-Tenant Analytics & Aggregation Engine

AGGRIX is a high-performance backend analytics and aggregation engine designed for Shopify-inspired multi-tenant e-commerce platforms. It provides strict tenant isolation at the database engine level, event stream ingestion via Transactional Outbox, and high-performance metrics aggregation.

---

## Tech Stack

* **Language**: Python 3.11+
* **Framework**: FastAPI
* **ORM & Database Toolkit**: SQLAlchemy 2.0 & Alembic
* **Data Validation & Settings**: Pydantic v2 & Pydantic Settings
* **Database Driver**: `psycopg2-binary`
* **Containerization**: Docker & Docker Compose
* **Testing**: pytest & HTTPX

---

## Project Structure

```text
aggrix-mta-layer/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                  # FastAPI application entrypoint & routing
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   └── config.py            # Pydantic Settings & environment configuration
│   │   ├── database/
│   │   │   ├── __init__.py
│   │   │   ├── base.py              # DeclarativeBase with POSTGRES_NAMING_CONVENTION
│   │   │   └── connection.py        # SQLAlchemy 2.0 engine, pool & session management
│   │   ├── models/                  # Multi-tenant domain entities
│   │   │   ├── __init__.py          # Entity registration
│   │   │   ├── tenant.py            # Tenant store/organization model
│   │   │   ├── customer.py          # Tenant-scoped customer profile
│   │   │   ├── product.py           # Tenant-scoped catalog product
│   │   │   ├── order.py             # Tenant-scoped order with composite FK
│   │   │   ├── order_item.py        # Tenant-scoped order line items
│   │   │   └── outbox_event.py      # Transactional outbox event stream
│   │   └── api/
│   │       ├── __init__.py
│   │       └── routes/
│   │           ├── __init__.py
│   │           └── health.py        # Health check endpoint executing SELECT 1
│   ├── requirements.txt             # Python backend dependencies
│   └── Dockerfile                   # Container build definition
├── alembic/                         # Database migrations
│   ├── env.py                       # Migration runtime environment
│   ├── script.py.mako
│   └── versions/
│       └── 0001_initial_schema.py   # Multi-tenant schema DDL migration
├── alembic.ini                      # Alembic CLI configuration (prepend_sys_path = backend)
├── docker/
│   └── init-db.sql                  # Automated aggrix_test database initialization
├── docs/
│   └── database-schema.md           # Entity-Relationship diagram & schema spec
├── tests/                           # Unified test suite
│   ├── __init__.py
│   ├── conftest.py                  # Pytest fixtures for in-memory SQLite and PostgreSQL
│   ├── test_health.py               # Root and health endpoint tests
│   ├── test_alembic.py              # Migration validation tests
│   ├── test_metadata.py             # Constraint and naming convention tests
│   ├── test_models.py               # Model CRUD tests
│   ├── test_tenancy.py              # Strict multi-tenant isolation tests
│   └── test_postgres_live.py        # Live database roundtrip tests
├── .env.example                     # Environment configuration template
├── .gitignore                       # Git ignore rules
├── docker-compose.yml               # PostgreSQL & Backend orchestration
├── pytest.ini                       # Test discovery and configuration
└── README.md                        # Documentation
```

---

## Architecture & Multi-Tenancy Design

1. **Guaranteed Tenant Isolation at the Engine Level**:
   * Multi-tenancy is enforced physically by PostgreSQL foreign key constraints rather than application-level filtering alone.
   * `orders` reference `(tenant_id, customer_id) -> (customers.tenant_id, customers.id)` using composite foreign keys. Cross-tenant customer references are rejected at the database level.
2. **Standardized Naming Conventions**:
   * Uses `POSTGRES_NAMING_CONVENTION` (`ix_*`, `uq_*`, `ck_*`, `fk_*`, `pk_*`) to ensure seamless Alembic migrations without orphaned anonymous constraints.
3. **Database Health Check (`SELECT 1`)**:
   * Live connectivity test executing `SELECT 1` against PostgreSQL via `check_db_connection(db)`.
   * Returns **HTTP 200 OK** (`{"status": "healthy", "database": "connected"}`) when healthy.
   * Returns **HTTP 503 Service Unavailable** (`{"status": "unhealthy", "database": "disconnected"}`) when unreachable.
4. **Transactional Outbox Event Streaming**:
   * Changes emit structured events to `outbox_events` with partial indexes (`ix_outbox_events_unprocessed`) for high-throughput polling and reliable stream publication.

---

## Running the Application

### Option A: Using Docker Compose

```bash
# Start PostgreSQL and Backend services
docker compose up -d --build

# View container logs
docker compose logs -f backend

# Stop services
docker compose down
```

### Option B: Local Python Development

```bash
# 1. Setup Virtual Environment & Install Dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# 2. Copy environment configuration
cp .env.example .env

# 3. Run database migrations
alembic upgrade head

# 4. Provision Initial Platform Administrator (One-Time Bootstrap)
PYTHONPATH=backend python -m app.cli init-admin

# 5. Start FastAPI Application
PYTHONPATH=backend uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 6. Start Analytics Worker Daemon
PYTHONPATH=backend python -m app.analytics.worker
```

---

## Initial Platform Administrator CLI

Because public registration is disabled and account provisioning requires an authenticated platform administrator, AGGRIX provides an offline one-time bootstrap CLI:

```bash
# Interactive mode (hidden password entry via getpass)
PYTHONPATH=backend python -m app.cli init-admin

# Or directly:
PYTHONPATH=backend python -m app.cli.init_admin --email admin@example.com
```

Key features:
* **One-time bootstrap**: Automatically refuses execution if an administrator already exists.
* **Hidden password prompt**: Input masked using `getpass`.
* **Bcrypt hashing**: Salted hash (12 rounds) stored in database; never stores plaintext passwords.
* **Validation**: Validates email format and password constraints (>= 8 chars, <= 72 bytes).

---

## Analytics Worker & Dead Letter Queue (DLQ) Management

AGGRIX runs an incremental aggregation worker that continuously polls the transactional outbox (`outbox_events`), updates tenant-level and product-level rollups, and records idempotent receipts in `analytics_consumer_events`. Events failing 3 times are quarantined in `analytics_dead_letter_events`.

### Running the Worker

* **Via Docker Compose**:
  ```bash
  docker compose up -d analytics-worker
  docker compose logs -f analytics-worker
  ```
* **Locally**:
  ```bash
  PYTHONPATH=backend python -m app.analytics.worker
  ```

### Dead Letter Queue (DLQ) CLI

The DLQ CLI provides operations to inspect quarantined events, replay them after underlying data fixes, or reset retry attempt counters:

```bash
# 1. Inspect all quarantined events
PYTHONPATH=backend python -m app.cli dlq inspect

# Filter by tenant
PYTHONPATH=backend python -m app.cli dlq inspect --tenant-id <tenant-uuid>

# Inspect a specific event
PYTHONPATH=backend python -m app.cli dlq inspect --event-id <event-uuid>

# 2. Replay a specific quarantined event
PYTHONPATH=backend python -m app.cli dlq replay --event-id <event-uuid>

# Replay all quarantined events for a tenant (up to batch limit)
PYTHONPATH=backend python -m app.cli dlq replay --tenant-id <tenant-uuid> --limit 100

# 3. Reset retry counters to allow standard worker polling
PYTHONPATH=backend python -m app.cli dlq reset --event-id <event-uuid>
```

---

## Synthetic Data Generator & Incremental Dataset Expansion

AGGRIX provides a high-throughput, deterministic synthetic data generator supporting initial seeding, streaming multi-tenant generation, and safe incremental dataset expansion.

### CLI Usage

```bash
# 1. Incremental Dry Run (shows current DB counts vs planned additions with 0 writes)
PYTHONPATH=backend python -m app.generator.cli --incremental --dry-run --tenants 5 --orders-per-tenant 2000

# 2. Live Incremental Expansion (adds new tenants starting at auto-detected offset)
PYTHONPATH=backend python -m app.generator.cli --incremental --tenants 5 --customers-per-tenant 500 --products-per-tenant 100 --orders-per-tenant 2000 --all-unprocessed

# 3. High-Scale Streaming (commits per tenant partition to maintain O(1) memory)
PYTHONPATH=backend python -m app.generator.cli --incremental --tenants 45 --commit-per-tenant --batch-size 1000

# 4. Append Records to a Specific Existing Tenant
PYTHONPATH=backend python -m app.generator.cli --target-tenant-id <tenant-uuid> --orders-per-tenant 100 --all-unprocessed

# 5. Safe Synthetic Data Cleanup (preview impact with explicit confirmation guardrail)
PYTHONPATH=backend python -m app.generator.cli --cleanup
```

### Key Safety Invariants & Guardrails
* **Duplicate Prevention**: Before insertion, validates candidate domains and sequence IDs against active records, rejecting colliding runs.
* **Preservation of Existing Records**: Offsets start after existing records without modifying or regenerating historical data.
* **Deterministic Sequences**: Sequential `order_seq` (`SHP-XXXXXX`), customer emails (`first.last.XXXX@domain`), and SKUs (`CAT-XXXX`).
* **Live Worker Integration**: `--all-unprocessed` marks outbox events as pending (`processed_at = NULL`) for automatic incremental aggregation by the analytics worker.

---

## Running Tests

Execute the complete test suite using `pytest`:

```bash
source .venv/bin/activate
pytest -v
```


