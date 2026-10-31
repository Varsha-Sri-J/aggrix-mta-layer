# AGGRIX Real-Time Analytics Engine & Live Dashboard Architecture

## 1. Architectural Overview

AGGRIX Stage 3 delivers an end-to-end, event-driven real-time analytics engine and live dashboard. The system propagates transactional events from database writes down to connected browser dashboards with sub-second latency while guaranteeing strict tenant isolation, exact financial correctness, and zero full-page refreshes.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               EVENT-TO-DASHBOARD PIPELINE                               │
└────────────────────────────────────────────────────────────────────────────────────────┘

  [ Client Order Placed ]
             │
             ▼
  ┌───────────────────────┐
  │  PostgreSQL Database  │
  │  • orders             │
  │  • order_items        │
  │  • outbox_events      │  <-- Atomic Transactional Outbox Pattern
  └──────────┬────────────┘
             │
             │ Polled with FOR UPDATE SKIP LOCKED
             ▼
  ┌────────────────────────────────────────────────────────┐
  │             Analytics Worker Daemon                    │
  │  • Advisory Locking (Mutual exclusion)                 │
  │  • Idempotency via analytics_consumer_events           │
  │  • Incremental rollups into daily_tenant_metrics       │
  │  • DLQ Quarantine via analytics_dead_letter_events     │
  └──────────┬─────────────────────────────┬───────────────┘
             │                             │
    In-Process Dispatch             PostgreSQL NOTIFY
             │                      channel: 'aggrix_events'
             │                             │
             ▼                             ▼
  ┌────────────────────────────────────────────────────────┐
  │                 EventBroadcaster                       │
  │  • Monotonic Sequence IDs (evt-<timestamp>-<seq>)      │
  │  • Monitored Ring Buffer (Last-Event-ID Replay)        │
  │  • Role-Aware Tenancy Filtering                        │
  │  • Bounded Per-Client Queues (MAX=100)                 │
  └──────────┬─────────────────────────────────────────────┘
             │
             ▼
  ┌────────────────────────────────────────────────────────┐
  │            FastAPI Server-Sent Events (SSE)            │
  │            GET /api/v1/analytics/stream                │
  │  • Authenticated via Header or ?token=<jwt>            │
  │  • 15-Second Keep-Alive Heartbeats (: heartbeat)       │
  │  • Clean Unsubscribe on Connection Termination         │
  └──────────┬─────────────────────────────────────────────┘
             │
             ▼
  ┌────────────────────────────────────────────────────────┐
  │         Real-Time Live Dashboard (Vanilla JS)          │
  │  • Live KPI Cards (Gross, Net, Total Orders, AOV)      │
  │  • Dynamic SVG Area & Donut Charts                     │
  │  • Top Products Leaderboard                            │
  │  • Real-Time Activity Feed with Pulse Animations       │
  │  • Zero Full-Page Refresh Required                     │
  └────────────────────────────────────────────────────────┘
```

---

## 2. Workstream Implementations

### Workstream 1: Real-Time Event Propagation
* **EventBroadcaster Singleton**: Thread-safe publisher-subscriber core managing client subscriptions with bounded ring buffers (`MAX_EVENT_BUFFER_SIZE = 500`) and per-client asyncio queues (`MAX_CLIENT_QUEUE_SIZE = 100`).
* **Dual-Mode Propagation**:
  1. *In-Process Mode*: Worker directly invokes `broadcaster.publish_event` for low-latency local execution and test environments.
  2. *Distributed Mode*: Worker issues PostgreSQL `NOTIFY aggrix_events, :payload`. The FastAPI backend runs a background daemon thread that performs `LISTEN aggrix_events` via `psycopg2` and feeds notifications into `broadcaster`.
* **Deduplication Engine**: Monotonically tracked event IDs eliminate duplicate broadcasts if both in-process and PostgreSQL notifications fire.
* **Connection Resilience & Reconnection**:
  * Emits W3C standard `id: <event_id>` headers with each SSE payload.
  * Honors `Last-Event-ID` request headers (and `?last_event_id=` query param) to replay missed events during brief network drops.
  * Heartbeat comments (`: heartbeat\n\n`) emitted every 15 seconds to prevent reverse-proxy timeout disconnects.
* **Strict Tenant Isolation**: Each subscriber is registered with its authorized tenancy boundary (`Platform Admin`: all; `Store Manager`: assigned set; `Tenant User`: home tenant only). Events outside authorized scope are discarded before queue dispatch.

### Workstream 2: Real-Time Analytics APIs
* **Average Order Value (AOV)**: Computed dynamically as $\text{Gross Sales} / \text{Total Orders}$ with exact Decimal quantizing.
* **Active Customers**: Count of distinct `customer_id` values placing orders within the specified filter window.
* **Order Status Distribution (`/status-distribution`)**: Aggregates order volume and gross revenue per lifecycle status (`pending`, `paid`, `fulfilled`, `cancelled`) with computed percentage breakdowns.
* **Recent Activity Feed (`/recent-orders`)**: Paginated chronological feed joining `orders` with `customers` and line-item counts.
* **Store Switcher (`/tenants`)**: Retrieves accessible stores based on caller RBAC permissions.
* **Composite Dashboard Overview (`/overview`)**: Single high-efficiency endpoint combining KPI summaries, status breakdown, recent orders, and top products.

### Workstream 3: Live Dashboard Experience
* **Design System**: Modern, dark-mode glassmorphic interface built with vanilla HTML5, CSS3, and JavaScript, following the AGGRIX visual guidelines:
  * Vibrant, tailored HSL accents (indigo, emerald, cyan, amber, rose).
  * Modern typography (`Plus Jakarta Sans` and `JetBrains Mono`).
  * Glassmorphic panels with subtle borders, backdrop blur, and smooth card hover transitions.
* **Zero Full-Page Refresh**:
  * Incoming SSE events dynamically update KPI values and trigger subtle green flash animations (`.flash-update`).
  * New orders prepend directly to the live activity stream with smooth slide-in animations.
* **Pure SVG Visualizations**:
  * *Revenue Trajectory*: Responsive SVG timeseries area chart with smooth gradients, gridlines, and interactive point hover tooltips.
  * *Status Donut*: Scaled SVG donut chart with animated stroke offsets and centered count indicators.

### Workstream 4: End-to-End Automated Validation
* **Full E2E Chain**: `test_complete_realtime_order_to_dashboard_pipeline` validates that order creation in the transactional database flows through outbox, worker aggregation, rollup verification, API retrieval, and SSE delivery.
* **Multi-Tenant Isolation**: Verified that tenant users cannot receive or filter events for foreign stores.
* **Duplicate Event Defense**: Verified that identical outbox events are skipped idempotently and never trigger duplicate SSE broadcasts.
* **DLQ Quarantine**: Verified that malformed events are isolated into `analytics_dead_letter_events` without halting the stream.
* **100% Test Pass Rate**: 209 passing automated tests (191 baseline tests + 18 new Stage 3 tests).

---

## 3. SSE Protocol Specification

### Endpoint
* `GET /api/v1/analytics/stream`
* `GET /api/analytics/stream` (Root alias)

### Query Parameters
| Parameter | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `token` | `string` | Optional | JWT bearer token for native browser `EventSource`. |
| `tenant_id` | `UUID` | Optional | Restricts stream to a specific tenant (caller must possess access). |
| `last_event_id` | `string` | Optional | Reconnection marker to replay events since this ID. |
| `max_events` | `integer` | Optional | Bounds event stream to $N$ events (useful for probes and testing). |

### Wire Message Format
```
id: init
event: connected
data: {"status": "connected", "client_id": "client-...", "user_id": "...", "role": "platform_admin", "timestamp": "2026-11-01T00:00:00Z"}

id: evt-1730419200000-000001
event: order.created
data: {"id": "evt-...", "event_type": "order.created", "tenant_id": "...", "order_id": "...", "status": "pending", "total_amount": 150.00, "currency": "USD", "created_at": "..."}

: heartbeat
```
