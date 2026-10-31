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

## 4. Step 2: Access the Live Dashboard

1. Open your web browser and navigate to:
   **`http://localhost:8000/dashboard`**
2. Click **Authenticate / Connect**.
3. Select the **Sign In** tab:
   - **Email**: `admin@aggrix.com`
   - **Password**: `AggrixAdmin2026!Secure`
4. Click **Sign In & Connect**.

**Expected Results**:
- The modal closes and an authenticated session is established.
- The **Store Switcher** dropdown in the top header is populated with the 25 active tenant stores (e.g., *Apex Tech Lab*, *Aura Athletics*, *Haven Kitchenware*).
- The KPI cards display live totals:
  - **Gross Sales**
  - **Net Sales**
  - **Orders Count**
  - **Average Order Value (AOV)**
  - **Active Customers**
- The live revenue area chart renders historical trends.
- The order status distribution donut chart displays *Fulfilled*, *Paid*, *Pending*, and *Cancelled* ratios.
- The header displays a green glowing indicator: **LIVE**.

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

To execute the entire automated regression suite:
```bash
PYTHONPATH=backend ./.venv/bin/pytest
```
**Result**: **211 passed** across unit, integration, RBAC, and real-time streaming tests.
