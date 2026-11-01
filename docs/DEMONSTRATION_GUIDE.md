# AGGRIX MTA Layer — Demonstration Guide

A concise, step-by-step evaluation guide for demonstrating the AGGRIX Multi-Tenant Analytics & Real-Time Aggregation Engine.

---

## 1. System Overview & Architecture

AGGRIX is a high-performance multi-tenant analytics layer for modern e-commerce platforms. It processes domain events asynchronously via a **Transactional Outbox**, rolls them up incrementally into daily aggregate tables, and pushes real-time updates directly to a glassmorphic dashboard via **Server-Sent Events (SSE)** and **PostgreSQL LISTEN/NOTIFY**.

```
[ Domain Transaction ]
         │
         ▼
[ PostgreSQL Database ] ──(Transactional Outbox)──► [ Analytics Worker ]
                                                            │
                     ┌──────────────────────────────────────┴──────────────────────────────────────┐
                     ▼                                                                             ▼
         [ Aggregation Rollups ]                                                       [ PostgreSQL NOTIFY ]
        (daily_tenant_metrics)                                                            (aggrix_events)
                     │                                                                             │
                     ▼                                                                             ▼
             [ Read REST APIs ]                                                         [ Backend LISTEN Loop ]
     (/api/v1/analytics/overview)                                                                  │
                     │                                                                             ▼
                     │                                                                   [ EventBroadcaster ]
                     │                                                                             │
                     └───────────────────────────────┬─────────────────────────────────────────────┘
                                                     ▼
                                       [ Live Glassmorphic Dashboard ]
                                          (Server-Sent Events: SSE)
```

---

## 1.1 Data Source Categorization & Transparency

To ensure absolute transparency during evaluations, AGGRIX data is explicitly categorized into three distinct tiers:

| Data Category | Implementation & Source | Status & Capabilities |
| :--- | :--- | :--- |
| **Historical Seeded Baseline** | 150,000 realistic orders across 25 tenants, 12,500 customers, 2,500 products | **Active in PostgreSQL**; precomputed in `daily_tenant_metrics` and `daily_product_metrics`. Verified $0.00 financial variance. |
| **Live API-Ingested Orders** | New transactions submitted via `POST /api/v1/ingest/orders` or batch endpoint | **Active & Live**; validated, committed to `orders`, published to `outbox_events`, processed by worker in <1s, and broadcast to all 3 dashboards via SSE. |
| **External Live Integrations** (Shopify, Stripe) | Direct webhook connectors to third-party merchant platforms | **Planned Connectors** (Not Connected in this Demo); transactions currently ingest through the authenticated API Gateway. |

> **Presentation Note**: All three dashboards (Merchant, Manager, Admin) seamlessly combine the historical baseline with live API-ingested transactions, proving both high-volume analytics performance and sub-second live aggregation.

---

## 1.2 The 7-Minute AGGRIX Hackathon Presentation Flow

| Step | Time | Screen & Persona | Key Demonstration Points |
| :--- | :--- | :--- | :--- |
| **1. Introduce Problem** | 30s | Title / Architecture | "Businesses receive orders from multiple stores and channels. AGGRIX provides a multi-tenant analytics layer that collects transactional data, processes it incrementally, and gives different users the analytics they are authorized to see." |
| **2. Merchant Login** | 1 min | `user@apextech.com` (`/dashboard/merchant`) | Show tenant identity (Apex Tech Lab), orders, gross sales, precomputed daily trends, top products. Explain that historical figures are seeded data while new orders reflect via live rollups. |
| **3. Live Order Ingestion** | 2 min | Terminal / API & Dashboard | Submit a new order via `POST /api/v1/ingest/orders`. Highlight lifecycle: API Ingestion → PostgreSQL Orders Table → Transactional Outbox → Analytics Worker (<1s) → Rollups Updated → Dashboard Flashes via SSE. Orders increment +1 and revenue updates live. |
| **4. Store Manager Login** | 1 min | `manager@aggrix.com` (`/dashboard/manager`) | Show 3 assigned stores (Apex Tech Lab, Solstice Home, Loom & Craft). Demonstrate side-by-side store comparison matrix. Explain RBAC: manager sees assigned stores only, not all 25 tenants. |
| **5. Platform Admin Login** | 1 min | `admin@aggrix.com` (`/dashboard/admin`) | Show all 25 tenants, platform-wide orders, currency-segregated sales balances, database schema registry. Note: **Admin dashboard now updates live via global SSE subscription**. |
| **6. Demonstrate Security** | 30s | Terminal / Auth checks | Explain isolation boundaries: Merchant (own tenant), Manager (assigned stores), Admin (global). Mention cross-tenant access returns HTTP 403 Forbidden. |
| **7. Architecture & Roadmap**| 1 min | Architecture Diagram | Summarize pipeline: React → FastAPI → PostgreSQL → Transactional Outbox → Worker Daemon → Summary Tables → SSE. Clarify that Shopify/Stripe webhooks are planned future connectors. |

---

## 2. Prerequisites & Quick Start

Ensure Docker Desktop and Python 3.9+ are installed.

```bash
# 1. Clone repository and navigate to directory
cd aggrix-mta-layer

# 2. Start PostgreSQL, Backend API, and Analytics Worker
docker compose up -d

# 3. Verify all 3 containers are healthy and running
docker ps
```

You should see:
- `aggrix-postgres` (PostgreSQL 16 on port 5432, healthy)
- `aggrix-backend` (FastAPI backend on port 8000)
- `aggrix-analytics-worker` (Async aggregation daemon)

---

## 3. Step 1: Initialize the Platform Administrator

Public user registration is disabled by default for security. Initialize the primary platform administrator using the one-time secure bootstrap CLI:

```bash
# Provide administrative credentials securely via stdin
echo "AggrixAdmin2026!Secure" | PYTHONPATH=backend ./.venv/bin/python -m app.cli.init_admin \
  --email admin@aggrix.com \
  --full-name "Platform Administrator" \
  --password-stdin
```

**Security Validation**:
- Attempting to run this command a second time will be rejected with an exit code `2` (`PlatformAdminAlreadyExistsError`).
- Passwords are encrypted with bcrypt (12 rounds) and never stored in plaintext or exposed in logs.

---

## 4. Step 2: Access the Multi-Tenant React Frontend Dashboard

AGGRIX provides a modern, responsive React 18 + TypeScript + Vite multi-tenant dashboard connected directly to the live backend analytics engine and SSE stream.

### A. Start the React Frontend Dev Server
In a new terminal window:
```bash
cd frontend
npm run dev
```
Open your browser to: **`http://localhost:5173`** (or click the URL printed in the terminal).

### B. Authenticate Using Pre-Provisioned Personas
The login page (`/login`) provides **one-click persona buttons** for instant evaluation:

1. **Platform Administrator (`admin@aggrix.com`)**:
   - Click **Demo Admin** (Password: `AggrixAdmin2026!Secure`).
   - Automatically navigates to the **Platform Admin Dashboard** (`/dashboard/admin`).
   - Evaluates aggregated cross-tenant turnover ($79,590,335.41 gross sales across all 25 tenants).
   - Inspects the live tenant directory table, schema registry metadata, and currency segregation breakdown.
   - **Live SSE EventStream**: Admin dashboard subscribes to global `GET /api/v1/analytics/stream` and refreshes automatically on any new order event without manual page refresh.

2. **Store Manager (`manager@aggrix.com`)**:
   - Log out via the header or navigate back to `/login` and click **Demo Manager** (Password: `AggrixManager2026!Secure`).
   - Automatically navigates to the **Manager Dashboard** (`/dashboard/manager`).
   - Evaluates the 3 assigned stores: *Apex Tech Lab*, *Solstice Home & Hearth*, and *Loom & Craft Goods*.
   - **Interactive Store Comparisons**: Toggle store checkboxes under "Compare Assigned Stores" to evaluate side-by-side performance in real time via `GET /api/v1/analytics/manager/compare`.
   - Inspects the live outbox stream pulse indicator.

3. **Merchant Operator (`user@apextech.com`)**:
   - Log out and click **Demo Merchant** (Password: `ApexUserPassword2026!`).
   - Automatically navigates to the **Merchant Operational Dashboard** (`/dashboard/merchant`).
   - Scoped strictly to *Apex Tech Lab* (`3c6c80b4-32d6-4cb2-a6cf-344720d64305`).
   - Displays real precomputed rollups: Total Orders (2,000), Gross Turnover ($1,067,295.22), AOV ($533.65), Fulfillment Rate (65.2%).
   - Daily orders timeline chart and order status donut breakdown.
   - Live EventSource SSE pulse indicator verifying persistent connection to `GET /api/v1/analytics/stream?token=...&tenant_id=...`.

### C. Access the Operations Dashboard
The legacy static operations dashboard also remains available for low-level operational inspection:
- Open: **`http://localhost:8000/dashboard`**
- Sign in with `admin@aggrix.com` / `AggrixAdmin2026!Secure`.


---

## 5. Step 3: Demonstrate Multi-Tenant Isolation & RBAC

AGGRIX enforces strict multi-tenancy at both the API and database levels.

### A. Provision a Tenant-Scoped User
As platform administrator, provision a user restricted to a single tenant (*Apex Tech Lab*, ID `3c6c80b4-32d6-4cb2-a6cf-344720d64305`):

```bash
# 1. Obtain Platform Admin Token
ADMIN_TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@aggrix.com", "password": "AggrixAdmin2026!Secure"}' | jq -r '.access_token')

# 2. Provision Tenant User
curl -s -X POST http://localhost:8000/api/v1/auth/provision \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@apextech.com",
    "password": "ApexUserPassword2026!",
    "full_name": "Apex Store Operator",
    "role": "tenant_user",
    "tenant_id": "3c6c80b4-32d6-4cb2-a6cf-344720d64305"
  }' | jq .
```

### B. Verify Tenant Isolation
Login as `user@apextech.com` and verify that access to other tenants is blocked:

```bash
# 1. Login as tenant user
USER_TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@apextech.com", "password": "ApexUserPassword2026!"}' | jq -r '.access_token')

# 2. Query accessible tenants (Returns ONLY Apex Tech Lab)
curl -s http://localhost:8000/api/v1/analytics/tenants -H "Authorization: Bearer $USER_TOKEN" | jq .

# 3. Access own tenant overview (Returns HTTP 200)
curl -s -o /dev/null -w "Apex Status: %{http_code}\n" \
  http://localhost:8000/api/v1/analytics/tenants/3c6c80b4-32d6-4cb2-a6cf-344720d64305/overview \
  -H "Authorization: Bearer $USER_TOKEN"

# 4. Attempt to access Aura Athletics (Returns HTTP 403 Forbidden)
curl -s -o /dev/null -w "Aura Status: %{http_code}\n" \
  http://localhost:8000/api/v1/analytics/tenants/5b2cb789-9cdc-4e48-827d-dba9212bcab0/overview \
  -H "Authorization: Bearer $USER_TOKEN"
```

---

## 6. Step 4: Demonstrate the Real-Time Event Pipeline

This demonstration showcases sub-second, end-to-end event propagation:
`Order Placed → Outbox Event → Worker Aggregation → PostgreSQL NOTIFY → SSE Stream → Live Dashboard Flash`.

Run the automated live verification script in a separate terminal:

```bash
PYTHONPATH=backend ./.venv/bin/python scratch/verify_live_pipeline.py
```

**What Happens in the Background**:
1. Connects to `GET /api/v1/analytics/stream` as platform administrator.
2. Creates an isolated test order with an `order.created` transactional outbox event.
3. The Docker container `aggrix-analytics-worker` polls the event within 100ms.
4. Increments metrics in `daily_tenant_metrics` and records an idempotent receipt.
5. Emits `NOTIFY aggrix_events` in PostgreSQL.
6. The backend listener captures the notification and broadcasts it to active SSE clients.
7. The SSE subscriber receives the payload with sub-second latency.
8. Automatically cleans up test records, preserving the 150,000-order Stage 2 baseline.

---

## 7. Step 5: Inspect Dead-Letter Queue (DLQ) & Resilience

AGGRIX handles corrupted data or malformed events without halting worker execution.

To test poison-pill isolation:
```bash
# Run the automated DLQ quarantine test
PYTHONPATH=backend ./.venv/bin/pytest tests/test_realtime_e2e.py -k "quarantine" -v
```

The worker attempts up to 3 retries with exponential backoff before quarantining failing events in `analytics_dead_letter_events`. Legitimate orders in the same batch continue processing without interruption.

---

## 8. Step 6: Verify Financial Reconciliation & Tests

Verify that all transactional data reconciles with analytical rollups down to $0.00:

```bash
# Run full reconciliation audit against the active 150,000-order dataset
PYTHONPATH=backend ./.venv/bin/python scratch/verify_stage2_data.py
```

Expected output confirms:
- **Orders Count**: 150,000 (0 mismatch)
- **Gross Sales**: $79,590,335.41 ($0.00 mismatch)
- **Net Sales**: $67,585,755.54 ($0.00 mismatch)
- **Accounting Invariant**: $\Delta = \$0.00$

To execute the automated regression suites:
```bash
# Backend pytest suite (RBAC, Worker, Ingestion, Analytics, Realtime)
PYTHONPATH=backend ./.venv/bin/pytest tests/test_security_rbac.py tests/test_live_ingestion.py tests/test_analytics_api.py tests/test_worker.py -q

# Frontend Vitest suite (Auth, API Client, Dashboard Components, Ingestion Client)
cd frontend && npm test && npm run build
```

---

## 9. Step 7: Live Merchant Order Ingestion & Multi-Dashboard Update

AGGRIX provides authenticated, tenant-isolated REST endpoints for ingesting live order transactions into PostgreSQL and streaming them into analytical rollups:

```bash
# Ingest a live merchant order via cURL (or using frontend ingestService)
curl -X POST http://localhost:8000/api/v1/ingest/orders \
  -H "Authorization: Bearer <MERCHANT_JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "external_order_id": "#LIVE-DEMO-001",
    "customer": {
      "email": "buyer@example.com",
      "name": "Jane Buyer"
    },
    "currency": "USD",
    "status": "paid",
    "items": [
      {
        "sku": "SKU-LIVE-01",
        "name": "Live Demo Product",
        "quantity": 1,
        "unit_price": 250.00
      }
    ]
  }'
```

**End-to-End Pipeline Execution**:
1. Order is validated and transactionally written to PostgreSQL `orders` and `order_items`.
2. Outbox event `order.paid` is atomically published in `outbox_events`.
3. `aggrix-analytics-worker` polls the outbox event and performs atomic incremental rollups into `daily_tenant_metrics` in sub-second latency.
4. **Merchant Dashboard** (`user@apextech.com`): Total orders increments +1, Gross/Net sales increments +$250.00.
5. **Manager Dashboard** (`manager@aggrix.com`): Store aggregate increments +1 order, +$250.00 (Apex Tech Lab is assigned).
6. **Platform Admin Dashboard** (`admin@aggrix.com`): Platform-wide order volume and gross sales reflect the new order.
7. **Security / RBAC**: Unauthorized ingestion into foreign tenants returns `HTTP 403 Forbidden`.

