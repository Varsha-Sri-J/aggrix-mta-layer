# AGGRIX — Multi-Tenant Analytics & Aggregation Engine

AGGRIX is a high-performance backend analytics and aggregation engine designed for Shopify-inspired multi-tenant e-commerce platforms. It handles event stream ingestion, metric rollups, and multi-tenant reporting with strong data isolation.

---

## Tech Stack

* **Language**: Python 3.11+
* **Framework**: FastAPI
* **ORM & Database Toolkit**: SQLAlchemy 2.0
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
│   │   │   └── connection.py        # SQLAlchemy 2.0 engine, pool & session handling
│   │   └── api/
│   │       ├── __init__.py
│   │       └── routes/
│   │           ├── __init__.py
│   │           └── health.py        # Health check endpoint executing SELECT 1
│   ├── requirements.txt             # Python backend dependencies
│   └── Dockerfile                   # Container build definition
├── database/
│   └── schema.sql                   # Reserved for database teammate schema designs
├── tests/
│   ├── __init__.py
│   └── test_health.py               # Unit and integration tests for health & root routes
├── .env.example                     # Environment configuration template
├── .gitignore                       # Git ignore rules
├── docker-compose.yml               # PostgreSQL & Backend orchestration
├── pytest.ini                       # Test discovery and configuration
└── README.md                        # Documentation
```

---

## Architecture Decisions

1. **SQLAlchemy 2.0 Engine & Connection Pooling**:
   * Uses `create_engine` with PostgreSQL `QueuePool`.
   * Enforces `pool_pre_ping=True` to eliminate stale connections by validating liveness prior to checkout.
   * Parameterizes `pool_size`, `max_overflow`, `pool_recycle`, and `pool_timeout` via environment variables.
   * Provides a scoped `get_db` FastAPI dependency with deterministic cleanup.
   * Provides `Base = DeclarativeBase` ready for future schema models.

2. **Database Health Check (`SELECT 1`)**:
   * Implements a live connectivity test executing `SELECT 1` against PostgreSQL via `check_db_connection(db)`.
   * Returns **HTTP 200 OK** (`{"status": "healthy", "database": "connected"}`) when the database responds.
   * Returns **HTTP 503 Service Unavailable** (`{"status": "unhealthy", "database": "disconnected", "error": "..."}`) when PostgreSQL is unreachable or fails.

3. **Orchestration & Startup Order**:
   * `docker-compose.yml` runs PostgreSQL with an alpine image, persistent named volume (`postgres_data`), and native `pg_isready` health check.
   * The `backend` service is configured with `depends_on: db: condition: service_healthy` to guarantee PostgreSQL is accepting connections before FastAPI starts.

4. **Modular & Decoupled Design**:
   * Business models and database tables are decoupled and deferred, as database schema design is handled separately.
   * All credentials and environment overrides flow through `Settings` without hardcoded secrets.

---

## Configuration & Environment Variables

Copy the template file to `.env`:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `PROJECT_NAME` | `AGGRIX MTA Layer` | Application display name |
| `ENVIRONMENT` | `development` | Deployment environment (`development`, `staging`, `production`) |
| `DEBUG` | `false` | Enable/disable debug mode |
| `BACKEND_PORT` | `8000` | Port for the backend service |
| `POSTGRES_SERVER` | `localhost` (or `db` in Docker) | PostgreSQL host |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_USER` | `aggrix_user` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `aggrix_password` | PostgreSQL password |
| `POSTGRES_DB` | `aggrix_db` | PostgreSQL database name |
| `DATABASE_URL` | *(Optional)* | Complete connection string overriding discrete credentials |
| `DB_POOL_SIZE` | `10` | SQLAlchemy connection pool size |
| `DB_MAX_OVERFLOW` | `20` | Max overflow connections |
| `DB_POOL_TIMEOUT` | `30` | Connection pool timeout in seconds |
| `DB_POOL_RECYCLE` | `1800` | Connection recycle period in seconds |

---

## Running the Application

### Option A: Using Docker Compose (Recommended for Full Stack)

```bash
# 1. Start PostgreSQL and Backend services
docker compose up --build

# 2. Run in detached mode (background)
docker compose up -d --build

# 3. View logs
docker compose logs -f backend

# 4. Stop all services
docker compose down
```

### Option B: Local Python Development

#### 1. Setup Virtual Environment & Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

#### 2. Start PostgreSQL (e.g. via Docker Compose standalone db service)

```bash
docker compose up -d db
```

#### 3. Run FastAPI Application

```bash
PYTHONPATH=backend uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Application metadata and status |
| `GET` | `/health` | Service and database health check (`SELECT 1`) |
| `GET` | `/api/v1/health` | Versioned alias for health check |
| `GET` | `/docs` | Swagger UI Interactive API documentation |
| `GET` | `/redoc` | ReDoc API documentation |

### Example Responses

#### `GET /`
```json
{
  "name": "AGGRIX MTA Layer",
  "version": "0.1.0",
  "description": "Multi-Tenant Analytics & Aggregation Engine for Shopify-inspired e-commerce platforms",
  "environment": "development",
  "status": "running",
  "docs_url": "/docs"
}
```

#### `GET /health` (Healthy)
```json
{
  "status": "healthy",
  "database": "connected",
  "environment": "development",
  "error": null
}
```

#### `GET /health` (Unhealthy — 503 Service Unavailable)
```json
{
  "status": "unhealthy",
  "database": "disconnected",
  "environment": "development",
  "error": "(psycopg2.OperationalError) connection to server at \"localhost\" failed: Connection refused"
}
```

---

## Running Tests

Execute the test suite using `pytest`:

```bash
source .venv/bin/activate
pytest
```

To run with verbose output:

```bash
pytest -v
```
