"""
Auto-record interactions via Django signals.
Hooks into order completion and cart adds.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver


def track_purchase_interactions(order):
    """Record purchase interactions when an order is marked paid."""
    if not order.user:
        return
    from .tasks import record_interaction_async
    for item in order.items.all():
        if item.product:
            record_interaction_async.delay(
                str(order.user.id), str(item.product.id), 'purchase'
            )
