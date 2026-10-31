"""Models package registering all entities with SQLAlchemy Base metadata."""

from app.models.customer import Customer
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.outbox_event import OutboxEvent
from app.models.product import Product
from app.models.tenant import Tenant

__all__ = [
    "Tenant",
    "Customer",
    "Product",
    "Order",
    "OrderItem",
    "OutboxEvent",
]

