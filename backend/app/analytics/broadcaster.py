"""Real-time Event Broadcaster for AGGRIX Analytics Engine.

Provides an in-memory pub/sub event distribution system with PostgreSQL LISTEN/NOTIFY
support, powering Server-Sent Events (SSE) for live analytics dashboards.

Architectural Guarantees:
1. Strict Tenant Isolation: Subscribers receive only events matching their authorized tenant IDs.
2. Zero Data Leakage: Cross-tenant events are filtered before queue dispatch.
3. Connection Resilience: Tracks heartbeats, handles graceful client disconnection, and supports
   event replay via Last-Event-ID.
4. Memory Safety: Fixed-size event ring buffer and per-client queue limits prevent unbounded memory growth.
5. Dual-Mode Operation: Works in single-process mode (in-memory queues) and distributed mode
   (PostgreSQL LISTEN/NOTIFY channel 'aggrix_events').
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Deque, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Maximum number of recent events retained in memory for Last-Event-ID replay
MAX_EVENT_BUFFER_SIZE: int = 500

# Per-client queue max size to avoid slow consumers causing memory leaks
MAX_CLIENT_QUEUE_SIZE: int = 100

# Heartbeat interval in seconds to keep SSE connections alive through reverse proxies
HEARTBEAT_INTERVAL_SECONDS: float = 15.0


@dataclass
class BroadcastEvent:
    """Structured real-time analytics event payload."""

    id: str
    event_type: str
    tenant_id: uuid.UUID
    order_id: uuid.UUID
    external_order_id: Optional[str]
    status: str
    total_amount: float
    currency: str
    created_at: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to JSON-serializable dictionary."""
        return {
            "id": self.id,
            "event_type": self.event_type,
            "tenant_id": str(self.tenant_id),
            "order_id": str(self.order_id),
            "external_order_id": self.external_order_id,
            "status": self.status,
            "total_amount": float(self.total_amount),
            "currency": self.currency,
            "created_at": self.created_at,
            "timestamp": self.timestamp,
        }

    def to_sse_message(self) -> str:
        """Format as a W3C-compliant Server-Sent Event message."""
        payload = json.dumps(self.to_dict())
        return f"id: {self.id}\nevent: {self.event_type}\ndata: {payload}\n\n"


@dataclass
class ClientSubscription:
    """Represents an active SSE client connection and its authorized tenancy scope."""

    client_id: str
    user_id: uuid.UUID
    role: str
    # If None, client is authorized for all tenants (platform_admin)
    authorized_tenant_ids: Optional[Set[uuid.UUID]]
    # Optional filter requested by client (must be a subset of authorized_tenant_ids)
    filter_tenant_id: Optional[uuid.UUID]
    queue: asyncio.Queue[Optional[BroadcastEvent]]
    loop: Optional[asyncio.AbstractEventLoop] = None
    created_at: float = field(default_factory=time.time)

    def is_authorized_for_tenant(self, tenant_id: uuid.UUID) -> bool:
        """Verify whether this subscription is permitted to receive events for the tenant."""
        # 1. If a specific tenant filter is applied, must match exactly
        if self.filter_tenant_id is not None and self.filter_tenant_id != tenant_id:
            return False

        # 2. If authorized_tenant_ids is None, user is platform_admin (can view all)
        if self.authorized_tenant_ids is None:
            return True

        # 3. Otherwise must be in authorized tenant set (tenant_user or store_manager)
        return tenant_id in self.authorized_tenant_ids


class EventBroadcaster:
    """Thread-safe, tenant-aware real-time event broadcaster for AGGRIX."""

    _instance: Optional[EventBroadcaster] = None
    _lock = threading.Lock()

    def __new__(cls) -> EventBroadcaster:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._subscriptions: Dict[str, ClientSubscription] = {}
        self._history_buffer: Deque[BroadcastEvent] = deque(maxlen=MAX_EVENT_BUFFER_SIZE)
        self._seen_ids: Set[str] = set()
        self._counter: int = 0
        self._sub_lock = asyncio.Lock() if hasattr(asyncio, "Lock") else None
        self._thread_lock = threading.Lock()
        self._listener_thread: Optional[threading.Thread] = None
        self._stop_listener = threading.Event()
        self._initialized = True
        logger.info("AGGRIX EventBroadcaster initialized (buffer_size=%d)", MAX_EVENT_BUFFER_SIZE)

    def generate_event_id(self) -> str:
        """Generate monotonically increasing event sequence identifier."""
        with self._thread_lock:
            self._counter += 1
            return f"evt-{int(time.time() * 1000)}-{self._counter:06d}"

    def subscribe(
        self,
        user_id: uuid.UUID,
        role: str,
        authorized_tenant_ids: Optional[Set[uuid.UUID]],
        filter_tenant_id: Optional[uuid.UUID] = None,
    ) -> ClientSubscription:
        """Register a new client subscription with strict tenancy boundaries."""
        client_id = f"client-{uuid.uuid4()}"
        queue: asyncio.Queue[Optional[BroadcastEvent]] = asyncio.Queue(maxsize=MAX_CLIENT_QUEUE_SIZE)
        ev_loop: Optional[asyncio.AbstractEventLoop] = None
        try:
            ev_loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        sub = ClientSubscription(
            client_id=client_id,
            user_id=user_id,
            role=role,
            authorized_tenant_ids=authorized_tenant_ids,
            filter_tenant_id=filter_tenant_id,
            queue=queue,
            loop=ev_loop,
        )

        with self._thread_lock:
            self._subscriptions[client_id] = sub

        logger.info(
            "Client %s subscribed (user=%s, role=%s, filter_tenant=%s, total_clients=%d)",
            client_id,
            user_id,
            role,
            filter_tenant_id,
            len(self._subscriptions),
        )
        return sub

    def unsubscribe(self, client_id: str) -> None:
        """Remove a client subscription and clean up associated resources."""
        with self._thread_lock:
            sub = self._subscriptions.pop(client_id, None)

        if sub is not None:
            logger.info("Client %s unsubscribed (remaining_clients=%d)", client_id, len(self._subscriptions))

    def publish_event(
        self,
        event_type: str,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        status: str,
        total_amount: float,
        currency: str,
        external_order_id: Optional[str] = None,
        created_at: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> BroadcastEvent:
        """Publish a real-time event, broadcast to matching subscribers, and record in history."""
        eid = event_id or self.generate_event_id()
        c_at = created_at or datetime.now(timezone.utc).isoformat()

        t_uuid = tenant_id if isinstance(tenant_id, uuid.UUID) else uuid.UUID(str(tenant_id))
        o_uuid = order_id if isinstance(order_id, uuid.UUID) else uuid.UUID(str(order_id))

        with self._thread_lock:
            # Deduplicate by event ID if previously processed
            if eid in self._seen_ids:
                for past in reversed(self._history_buffer):
                    if past.id == eid:
                        return past

            event = BroadcastEvent(
                id=eid,
                event_type=event_type,
                tenant_id=t_uuid,
                order_id=o_uuid,
                external_order_id=external_order_id,
                status=status,
                total_amount=float(total_amount),
                currency=currency,
                created_at=c_at,
            )

            if len(self._history_buffer) >= MAX_EVENT_BUFFER_SIZE:
                oldest = self._history_buffer[0]
                self._seen_ids.discard(oldest.id)

            self._history_buffer.append(event)
            self._seen_ids.add(eid)
            subs = list(self._subscriptions.values())

        dispatched_count = 0
        for sub in subs:
            if sub.is_authorized_for_tenant(event.tenant_id):
                def _enqueue(s=sub, ev=event):
                    try:
                        if s.queue.full():
                            try:
                                s.queue.get_nowait()
                            except asyncio.QueueEmpty:
                                pass
                        s.queue.put_nowait(ev)
                    except Exception as exc:
                        logger.debug("Failed to dispatch to client %s: %s", s.client_id, exc)

                try:
                    if sub.loop is not None and not sub.loop.is_closed():
                        sub.loop.call_soon_threadsafe(_enqueue)
                    else:
                        _enqueue()
                    dispatched_count += 1
                except Exception as exc:
                    logger.debug("Failed to schedule dispatch for client %s: %s", sub.client_id, exc)

        logger.debug(
            "Published event %s (%s, tenant=%s) to %d/%d subscribers",
            eid,
            event_type,
            tenant_id,
            dispatched_count,
            len(subs),
        )
        return event

    def get_events_since(
        self,
        last_event_id: str,
        sub: ClientSubscription,
    ) -> List[BroadcastEvent]:
        """Retrieve historical events that occurred after last_event_id for reconnection."""
        replayed: List[BroadcastEvent] = []
        with self._thread_lock:
            events_snapshot = list(self._history_buffer)

        found = False
        for ev in events_snapshot:
            if found:
                if sub.is_authorized_for_tenant(ev.tenant_id):
                    replayed.append(ev)
            elif ev.id == last_event_id:
                found = True

        return replayed

    @property
    def active_subscribers_count(self) -> int:
        """Return total active client connections."""
        with self._thread_lock:
            return len(self._subscriptions)

    def start_postgres_listener(self, db_url: Optional[str] = None) -> None:
        """Start background daemon thread listening to PostgreSQL LISTEN aggrix_events channel."""
        with self._thread_lock:
            if self._listener_thread is not None and self._listener_thread.is_alive():
                return
            self._stop_listener.clear()
            self._listener_thread = threading.Thread(
                target=self._postgres_listen_worker,
                args=(db_url,),
                daemon=True,
                name="aggrix-pg-listener",
            )
            self._listener_thread.start()
            logger.info("AGGRIX PostgreSQL LISTEN worker thread started.")

    def stop_postgres_listener(self) -> None:
        """Stop background PostgreSQL listener thread."""
        self._stop_listener.set()
        if self._listener_thread is not None and self._listener_thread.is_alive():
            self._listener_thread.join(timeout=3.0)
            self._listener_thread = None
            logger.info("AGGRIX PostgreSQL LISTEN worker thread stopped.")

    def _postgres_listen_worker(self, db_url: Optional[str]) -> None:
        """Background worker executing LISTEN aggrix_events loop using psycopg2."""
        import select
        from app.core.config import settings

        raw_url = db_url or settings.sqlalchemy_database_uri
        if "postgresql" not in raw_url and "postgres" not in raw_url:
            logger.info("Non-PostgreSQL dialect configured (%s); skipping LISTEN worker.", raw_url.split("://")[0])
            return

        # Sanitize dialect string for psycopg2 (strip +psycopg2)
        psycopg_dsn = raw_url.replace("postgresql+psycopg2://", "postgresql://")

        while not self._stop_listener.is_set():
            conn = None
            try:
                import psycopg2
                import psycopg2.extensions

                conn = psycopg2.connect(psycopg_dsn)
                conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
                cursor = conn.cursor()
                cursor.execute("LISTEN aggrix_events;")
                logger.info("Subscribed to PostgreSQL NOTIFY channel 'aggrix_events'.")

                while not self._stop_listener.is_set():
                    if select.select([conn], [], [], 1.0) == ([], [], []):
                        continue
                    conn.poll()
                    while conn.notifies:
                        notify = conn.notifies.pop(0)
                        try:
                            payload_dict = json.loads(notify.payload)
                            self.publish_event(
                                event_type=payload_dict["event_type"],
                                tenant_id=uuid.UUID(payload_dict["tenant_id"]),
                                order_id=uuid.UUID(payload_dict["order_id"]),
                                status=payload_dict.get("status", "pending"),
                                total_amount=float(payload_dict.get("total_amount", 0.0)),
                                currency=payload_dict.get("currency", "USD"),
                                external_order_id=payload_dict.get("external_order_id"),
                                created_at=payload_dict.get("created_at"),
                                event_id=payload_dict.get("id"),
                            )
                        except Exception as p_err:
                            logger.error("Failed to parse PG notification payload: %s", p_err)
            except Exception as err:
                if not self._stop_listener.is_set():
                    logger.warning("PostgreSQL LISTEN worker error (retrying in 3s): %s", err)
                    time.sleep(3.0)
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass

    def clear_all(self) -> None:
        """Reset subscriptions and history buffer (primarily for test isolation)."""
        with self._thread_lock:
            self._subscriptions.clear()
            self._history_buffer.clear()
            self._seen_ids.clear()
            self._counter = 0


# Singleton global instance
broadcaster = EventBroadcaster()

