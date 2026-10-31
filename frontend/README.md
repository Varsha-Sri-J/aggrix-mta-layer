# AGGRIX MTA Layer — Frontend Analytics & Governance Dashboard

Modern, responsive web dashboard and multi-tenant analytics client for the **AGGRIX Multi-Tenant Analytics & Aggregation Engine** (Shopify-inspired architecture).

---

## 1. Project Overview

The AGGRIX frontend provides specialized, role-tailored operational and governance interfaces for three key e-commerce personas:
1. **Merchant / Tenant Portal**: Store-isolated operational analytics (order volume, gross sales turnover, 30-day zero-filled daily trends, and top 10 merchandise revenue).
2. **Store Manager Multi-Tenant Portal**: Consolidated portfolio oversight across multiple assigned tenant stores, comparative metrics, and stream health.
3. **Platform Admin & Governance**: Relational database schema registry, real-time live FastAPI/PostgreSQL health diagnostics, and transactional outbox event stream monitoring.

---

## 2. Technology Stack

* **Build Tooling**: Vite 6.0 (`@vitejs/plugin-react`)
* **Core Framework**: React 18.3 + TypeScript 5.6 (Strict Type Checking)
* **Client Routing**: React Router DOM 6.28
* **Iconography**: Lucide React
* **Test Runner**: Vitest 3.0
* **Data Visualization**: Custom responsive SVG charts & CSS flex distribution meters
* **Design System**: High-contrast, accessibility-focused slate theme (WCAG 2.1 AA compliant)

---

## 3. Prerequisites

* **Node.js**: v20.0.0 or higher (v24.19.0 verified)
* **npm**: v10.0.0 or higher (v11.17.0 verified)
* **FastAPI Backend**: Python 3.11+ running on `http://localhost:8000` (optional for offline preview, required for live health checks)

---

## 4. Installation & Setup

1. **Navigate to the frontend directory**:
   ```bash
   cd frontend
   ```

2. **Install dependencies using the lockfile**:
   ```bash
   npm ci
   ```

3. **Configure Environment Variables**:
   Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

---

## 5. Environment Configuration

The frontend consumes environment variables prefixed with `VITE_` via [`src/config/env.ts`](src/config/env.ts):

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Target URL for the FastAPI backend service |
| `VITE_APP_ENV` | `development` | Deployment environment label (`development`, `staging`, `production`) |

---

## 6. Development & Build Commands

* **Start Development Server** (hot module reloading on `http://localhost:5173`):
  ```bash
  npm run dev
  ```
* **Run Unit Tests** (29 tests across API client, auth readiness, and dashboard components):
  ```bash
  npm test
  ```
* **Run TypeScript Type Check**:
  ```bash
  npm run lint
  ```
* **Production Build** (compiles TypeScript and bundles via Vite to `dist/`):
  ```bash
  npm run build
  ```
* **Preview Production Build** (serves `dist/` locally on `http://localhost:4173`):
  ```bash
  npm run preview
  ```

---

## 7. API Architecture & Connectivity

The centralized API client in [`src/services/api.ts`](src/services/api.ts) provides typed request handling, automatic JSON serialization, cancellation via `AbortSignal`, and a structured error hierarchy:
* `NetworkError`: Offline or unreachable backend.
* `AuthenticationError` (HTTP 401): Missing or expired credentials.
* `ForbiddenError` (HTTP 403): Unauthorized tenant scope.
* `NotFoundError` (HTTP 404): Unmounted backend route.
* `ValidationError` (HTTP 422): Pydantic validation failure.
* `ServerError` (HTTP 500+): Backend exception or database failure.

### Verified Backend Endpoints
* `GET /`: System metadata, version, and documentation location.
* `GET /health`: Operational status and PostgreSQL database connection check (`SELECT 1`).
* `GET /api/v1/health`: Versioned health check for reverse proxy monitoring.

---

## 8. Dashboard Route Reference

| Route Path | View Name | Target Persona | Key Capabilities |
| :--- | :--- | :--- | :--- |
| `/` | System Overview | All | API endpoint availability ledger and engine diagnostics |
| `/dashboard/merchant` | Merchant Dashboard | Merchant | 7d orders, 7d sales, 30d daily SVG chart, status breakdown, top 10 products |
| `/dashboard/manager` | Manager Dashboard | Store Manager | Multi-store portfolio comparison matrix, aggregate sales, sync health |
| `/dashboard/admin` | Platform Admin | Platform Admin | Live FastAPI/PostgreSQL diagnostic card, 6-table schema registry |
| `/stores` | Store Topology | All | Relational tenancy model, composite foreign key explanation |
| `/analytics` | SQL Contracts | Developers | Mathematical specifications for the 5 core analytics queries |
| `/health` | Diagnostic Probe | Ops / QA | Interactive tool probing `GET /` and `GET /api/v1/health` with JSON viewer |
| `/login` | Auth & RBAC Probe | All | Live contract verification against `POST /api/v1/auth/login` and Stage 4 disclosure |
| `/settings` | System Settings | Admin | Runtime client parameters and security headers |

---

## 9. Backend Limitations & Demo-Data Disclaimer

> [!WARNING]
> **Stage 4 Backend Limitations & Demo-Data Notice**
> 
> * **No Authentication / RBAC in Backend**: The FastAPI backend currently lacks `POST /api/v1/auth/login` and `GET /api/v1/auth/me`. The frontend does **not** fabricate fake JWTs, dummy accounts, or simulated sessions. The login page provides an honest probe showing actual HTTP responses and explaining backend status.
> * **No Analytics Routes in Backend**: Endpoints under `/api/v1/analytics/*` are scheduled for Stage 4 backend deployment.
> * **Visual Mockups Labeled**: To facilitate UX evaluation, all mockup metric cards, charts, and product tables are prominently labeled with:
>   `DEMO DATA — NOT LIVE`
> * **Live Platform Diagnostics**: Platform health cards connect directly to the real backend (`GET /` and `GET /api/v1/health`). When PostgreSQL is offline, the status correctly reflects `DISCONNECTED` without fabrication.
