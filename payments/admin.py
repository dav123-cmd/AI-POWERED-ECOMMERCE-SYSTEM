
# Register your models here.
from django.contrib import admin
from django.utils import timezone
from .models import Payment, Refund, Invoice
from .stripe_service import process_refund as stripe_refund

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display  = ('id','order','method','amount','status','created_at')
    list_filter   = ('method','status','currency')
    search_fields = ('gateway_payment_id','mpesa_receipt','order__order_number')
    readonly_fields = ('id','created_at','updated_at','gateway_response')

@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display  = ('id','order','amount','reason','status','created_at')
    list_filter   = ('status','reason')
    search_fields = ('order__order_number',)
    actions       = ['approve_refunds']

    def approve_refunds(self, request, queryset):
        for refund in queryset.filter(status='pending'):
            payment = refund.payment
            if payment.method == 'stripe':
                try:
                    r = stripe_refund(payment, refund.amount)
                    refund.gateway_refund_id = r['id']
                    refund.status = 'processed'
                    refund.processed_at = timezone.now()
                    refund.save()
                    refund.order.payment_status = 'refunded'
                    refund.order.save()
                except Exception as e:
                    self.message_user(request, f'Stripe refund failed: {e}', level='error')
            else:
                refund.status = 'approved'
                refund.save()
        self.message_user(request, 'Refunds processed.')
    approve_refunds.short_description = 'Approve & Process Refunds'

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number','order','created_at')
    search_fields = ('invoice_number','order__order_number')
