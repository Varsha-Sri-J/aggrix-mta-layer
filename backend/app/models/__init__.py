"""Models package registering all entities with SQLAlchemy Base metadata."""

from app.models.analytics_consumer_event import AnalyticsConsumerEvent
from app.models.analytics_dead_letter_event import AnalyticsDeadLetterEvent
from app.models.customer import Customer
from app.models.daily_product_metric import DailyProductMetric
from app.models.daily_tenant_metric import DailyTenantMetric
from app.models.manager_tenant_assignment import ManagerTenantAssignment
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.outbox_event import OutboxEvent
from app.models.product import Product
from app.models.tenant import Tenant
from app.models.user import User, UserRole

__all__ = [
    "Tenant",
    "Customer",
    "Product",
    "Order",
    "OrderItem",
    "OutboxEvent",
    "DailyTenantMetric",
    "DailyProductMetric",
    "AnalyticsConsumerEvent",
    "AnalyticsDeadLetterEvent",
    "User",
    "UserRole",
    "ManagerTenantAssignment",
]



