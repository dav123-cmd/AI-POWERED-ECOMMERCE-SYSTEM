from django.db import models

# Create your models here.
from django.conf import settings
import uuid


class Payment(models.Model):
    STATUS = [
        ('pending',   'Pending'),
        ('processing','Processing'),
        ('completed', 'Completed'),
        ('failed',    'Failed'),
        ('cancelled', 'Cancelled'),
        ('refunded',  'Refunded'),
    ]
    METHOD = [
        ('stripe',  'Stripe Card'),
        ('paypal',  'PayPal'),
        ('mpesa',   'M-Pesa'),
    ]

    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order           = models.ForeignKey('orders.Order', on_delete=models.CASCADE, related_name='payments')
    user            = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                        null=True, blank=True, related_name='payments')
    method          = models.CharField(max_length=10, choices=METHOD)
    status          = models.CharField(max_length=12, choices=STATUS, default='pending')
    amount          = models.DecimalField(max_digits=12, decimal_places=2)
    currency        = models.CharField(max_length=5, default='KES')

    # Gateway references
    gateway_payment_id   = models.CharField(max_length=200, blank=True, db_index=True)
    gateway_order_id     = models.CharField(max_length=200, blank=True)
    gateway_response     = models.JSONField(default=dict, blank=True)

    # M-Pesa specific
    mpesa_phone          = models.CharField(max_length=20, blank=True)
    mpesa_checkout_id    = models.CharField(max_length=100, blank=True)
    mpesa_receipt        = models.CharField(max_length=100, blank=True)

    failure_reason       = models.TextField(blank=True)
    created_at           = models.DateTimeField(auto_now_add=True)
    updated_at           = models.DateTimeField(auto_now=True)
    completed_at         = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.method.upper()} | {self.amount} | {self.status}'


class Refund(models.Model):
    STATUS = [('pending','Pending'),('approved','Approved'),('rejected','Rejected'),('processed','Processed')]
    REASON = [
        ('defective',    'Defective Product'),
        ('wrong_item',   'Wrong Item Sent'),
        ('not_received', 'Not Received'),
        ('changed_mind', 'Changed Mind'),
        ('other',        'Other'),
    ]

    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment        = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='refunds')
    order          = models.ForeignKey('orders.Order', on_delete=models.CASCADE, related_name='refunds')
    user           = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                       null=True, blank=True)
    amount         = models.DecimalField(max_digits=12, decimal_places=2)
    reason         = models.CharField(max_length=20, choices=REASON)
    description    = models.TextField(blank=True)
    status         = models.CharField(max_length=10, choices=STATUS, default='pending')
    gateway_refund_id = models.CharField(max_length=200, blank=True)
    admin_note     = models.TextField(blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    processed_at   = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'Refund {self.amount} for {self.order}'


class Invoice(models.Model):
    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order          = models.OneToOneField('orders.Order', on_delete=models.CASCADE, related_name='invoice')
    invoice_number = models.CharField(max_length=30, unique=True, blank=True)
    pdf_file       = models.FileField(upload_to='invoices/', null=True, blank=True)
    sent_at        = models.DateTimeField(null=True, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            from django.utils import timezone
            ts = timezone.now().strftime('%y%m%d%H%M')
            self.invoice_number = f'INV-{ts}-{str(self.id)[:4].upper()}'
        super().save(*args, **kwargs)

    def __str__(self):
        return self.invoice_number
