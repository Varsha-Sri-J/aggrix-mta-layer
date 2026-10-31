# AGGRIX MTA Layer — Hackathon Demo Guide & Mentor Presentation

A structured 5-minute presentation guide, walkthrough script, and technical Q&A reference for demonstrating the AGGRIX frontend and engine architecture to hackathon mentors and judges.

---

## 1. Executive Presentation Strategy (30 Seconds)

* **The Problem**: Multi-tenant e-commerce platforms (like Shopify) require high-velocity operational analytics, tenant data isolation, and low-latency metrics without cross-tenant data contamination.
* **The AGGRIX MTA Solution**:
  - **Shared Database / Shared Process Schema**: Enforces physical tenant isolation via composite primary and foreign keys `(tenant_id, id)` across all 6 core tables.
  - **Transactional Outbox Event Streaming**: Reliable event capture into `outbox_events` for asynchronous rollup processing.
  - **Specialized Multi-Role Frontend**: Responsive interfaces tailored to Merchants, Multi-Store Managers, and Platform Administrators.
  - **Absolute Accuracy Mandate**: Zero fake mock JWTs, zero hidden simulated routes, and honest labeling of live diagnostics vs. preview data.

---

## 2. Recommended 5-Minute Page Walkthrough

```text
[0:00 - 0:45] Overview Ledger (/)
     ↓
[0:45 - 1:45] Platform Admin & Live Diagnostics (/dashboard/admin & /health)
     ↓
[1:45 - 3:00] Merchant Operational Portal (/dashboard/merchant)
     ↓
[3:00 - 4:00] Store Manager Multi-Tenant Portal (/dashboard/manager)
     ↓
[4:00 - 5:00] Authentication Readiness & RBAC Architecture (/login & Q&A)
```

### Stop 1: Overview Ledger (`/`) — 45 Seconds
* **Action**: Open `http://localhost:5173/` (or preview `http://localhost:4173/`).
* **Highlight**:
  - Point out the **API Endpoint Availability Ledger**: 3 endpoints verified available (`/`, `/health`, `/api/v1/health`) and 9 endpoints clearly classified as planned Stage 4 deliverables.
  - Emphasize the architectural notice: the platform never pretends unimplemented backend features exist.
  - Use the top **Role Switcher** to demonstrate immediate accessibility to all three personas.

### Stop 2: Platform Admin & Live Engine Diagnostics (`/dashboard/admin`) — 60 Seconds
* **Action**: Click `3. Platform Admin` on the role switcher.
* **Highlight**:
  - **Live Backend Connection**: Click the **"Probe Engine"** button to execute a real-time probe against FastAPI.
  - **Honest Database Status**: If PostgreSQL is offline, explain that the dashboard shows `POSTGRESQL: DISCONNECTED (SELECT 1 failed)` honestly rather than faking an operational database.
  - **Schema Registry**: Walk through the 6 verified SQLAlchemy models from migration `0001_initial_schema.py` (`tenants`, `customers`, `products`, `orders`, `order_items`, `outbox_events`), showing composite keys that enforce physical isolation.

### Stop 3: Merchant Operational Portal (`/dashboard/merchant`) — 75 Seconds
* **Action**: Click `1. Merchant / Tenant` on the role switcher.
* **Highlight**:
  - **Active Tenant Context**: Notice the store header binding to `Apex Athletics (UUID: 550e8400...)`.
  - **Metric 1 (7-Day Orders) & Metric 2 (7-Day Gross Sales)**: Explain the business rule excluding `cancelled`/`pending` orders and enforcing currency segregation.
  - **Metric 3 (30-Day Daily Orders Chart)**: Hover over the SVG bars. Show how the chart represents the SQL `generate_series()` contract with guaranteed 30 calendar dates and zero-count fill.
  - **Metric 4 (Top 10 Products under Contract A)**: Show the product ranking table. Explain the historical price preservation invariant: revenue references `order_items.unit_price`, not mutable `products.price`.
  - **Transparency**: Note the prominent `DEMO DATA — NOT LIVE` badges and the explanatory banner detailing that analytics routes are awaiting Stage 4 backend deployment.

### Stop 4: Store Manager Multi-Tenant Portal (`/dashboard/manager`) — 60 Seconds
* **Action**: Click `2. Store Manager` on the role switcher.
* **Highlight**:
  - **Multi-Store Portfolio**: Show oversight across 4 assigned tenant stores (Apex Athletics, Lumina Home, Zenith Tech, Orbit Coffee).
  - **Cross-Tenant Comparison Matrix**: Contrast store turnover, order velocity, and stream sync status.
  - **RBAC Security Boundaries**: Explain that managers only query stores within their assigned UUID array; unauthorized tenant requests return HTTP 403 Forbidden.

### Stop 5: Authentication Readiness & Security Probe (`/login`) — 60 Seconds
* **Action**: Click `Auth & RBAC (Stage 4)` in the sidebar.
* **Highlight**:
  - **Architectural Banner**: Review the Stage 3 (schema/SQL) vs Stage 4 (FastAPI auth/JWT) transition status.
  - **Real Endpoint Probe**: Enter a test email and password, click **"Probe /api/v1/auth/login"**.
  - Show the live response: the application executes a real network request, catches the HTTP 404 response, and displays a clear explanation without storing dummy tokens or faking a session.

---

## 3. Explanation of "DEMO DATA — NOT LIVE" Badges

If mentors ask about the `DEMO DATA` tags:
> *"In accordance with senior engineering best practices, we separate user interface readiness from backend implementation. Our database schema and five analytics SQL queries are fully designed and verified in `docs/analytics-sql-design.md`. Because the FastAPI backend does not yet mount the analytics endpoints, we populated the merchant and manager views with representative preview datasets and visibly watermarked them with 'DEMO DATA — NOT LIVE'. We never present sample data as live telemetry."*

---

## 4. Live Health Check Demonstration

To prove the frontend communicates with the real backend:
1. Ensure the FastAPI backend is running on `http://localhost:8000`:
   ```bash
   .venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --port 8000
   ```
2. In the frontend header and on `/dashboard/admin`, observe the live green badge:
   `FastAPI Connected (v0.1.0)`.
3. Stop the backend process:
   Observe the badge automatically update on the next probe interval or refresh:
   `FastAPI Offline (Port 8000)`.

---

## 5. Likely Mentor Questions & Recommended Answers

### Q1: "How do you guarantee that Tenant A cannot see Tenant B's data?"
* **Answer**:
  1. **Database Engine Level**: Composite foreign keys like `fk_orders_customer_tenant` require `(tenant_id, customer_id) REFERENCES customers(tenant_id, id)`. A database transaction attempting to reference a customer from another tenant is rejected by PostgreSQL with an `IntegrityError`.
  2. **Query Level**: Every analytics query binds `:tenant_id` as a mandatory parameter in the `WHERE` clause.
  3. **Application Level**: Once Stage 4 JWT auth is deployed, the tenant ID is extracted directly from the verified cryptographic JWT claims, never from client-controlled request parameters.

### Q2: "Why isn't authentication returning a live JWT right now?"
* **Answer**:
  *"Stage 3 focused on the relational database foundation, Alembic migrations, and analytics SQL query design. User authentication and JWT issuance (`POST /api/v1/auth/login`) are Stage 4 deliverables. Rather than writing a temporary mock server or storing fake tokens in localStorage, our frontend client is fully wired to the real endpoints and honestly reports when the backend route is unmounted."*

### Q3: "How does Metric 4 handle multi-currency stores?"
* **Answer**:
  *"Because the engine currently lacks an automated currency exchange-rate conversion service, combining different currencies into a single sum would produce skewed financial reporting. We adopted **Contract A**: the query requires a mandatory `:currency` filter (e.g. `currency = 'USD'`). This guarantees that `LIMIT 10` returns exactly ten distinct products rather than ten product-currency combinations."*

### Q4: "How does the daily orders chart handle days with zero orders?"
* **Answer**:
  *"Standard SQL `GROUP BY date` queries omit dates where no orders occurred, producing broken time-series charts. Metric 3 utilizes PostgreSQL's `generate_series()` function to generate all 30 calendar dates in the window and executes a `LEFT JOIN` against the orders table with `COALESCE(count, 0)`. This guarantees exactly 30 chronological points are returned, even for brand-new stores."*

### Q5: "How does the platform handle mobile devices?"
* **Answer**:
  *"The frontend uses an off-canvas drawer navigation for viewports below 768px, complete with background backdrop overlay and Escape key listener. All tables are wrapped in touch-scrolling containers to prevent page overflow, and all charts are built with pure responsive SVG `viewBox` coordinates."*
