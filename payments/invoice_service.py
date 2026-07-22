"""
ShopAI — Invoice PDF Generator
Uses ReportLab for professional PDF invoices
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
from reportlab.lib.enums import TA_RIGHT, TA_LEFT, TA_CENTER
from io import BytesIO
from django.utils import timezone


# Brand colors
GOLD   = colors.HexColor('#C9A84C')
DARK   = colors.HexColor('#0A0A0F')
GREY   = colors.HexColor('#9996A0')
LIGHT  = colors.HexColor('#F0EDE8')
GREEN  = colors.HexColor('#10B981')


def generate_invoice_pdf(order):
    """Generate a professional PDF invoice and return bytes."""
    buf    = BytesIO()
    doc    = SimpleDocTemplate(buf, pagesize=A4,
                                leftMargin=20*mm, rightMargin=20*mm,
                                topMargin=15*mm, bottomMargin=15*mm)
    styles = getSampleStyleSheet()
    story  = []

    # ── Header ─────────────────────────────────────────────
    header_data = [[
        Paragraph('<font size="22"><b>ShopAI</b></font><br/>'
                  '<font size="9" color="#9996A0">AI-Powered E-Commerce</font>', styles['Normal']),
        Paragraph(f'<font size="18"><b>INVOICE</b></font><br/>'
                  f'<font size="9" color="#9996A0">{getattr(order, "invoice", None) and order.invoice.invoice_number or "INV-DRAFT"}</font>',
                  ParagraphStyle('right', parent=styles['Normal'], alignment=TA_RIGHT)),
    ]]
    header_tbl = Table(header_data, colWidths=[95*mm, 75*mm])
    header_tbl.setStyle(TableStyle([
        ('BACKGROUND',  (0,0),(-1,-1), DARK),
        ('TEXTCOLOR',   (0,0),(-1,-1), LIGHT),
        ('TOPPADDING',  (0,0),(-1,-1), 10),
        ('BOTTOMPADDING',(0,0),(-1,-1), 10),
        ('LEFTPADDING', (0,0),(0,-1),  12),
        ('RIGHTPADDING',(-1,0),(-1,-1),12),
        ('ROUNDEDCORNERS', [6]),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 8*mm))

    # ── Meta row (bill to + dates) ──────────────────────────
    meta_data = [[
        Paragraph(f'<font size="7" color="#9996A0"><b>BILL TO</b></font><br/>'
                  f'<b>{order.shipping_name}</b><br/>'
                  f'{order.email}<br/>'
                  f'{order.phone or ""}<br/>'
                  f'{order.shipping_line1}<br/>'
                  f'{order.shipping_city}, {order.shipping_country}', styles['Normal']),
        Paragraph(f'<font size="7" color="#9996A0"><b>ORDER DETAILS</b></font><br/>'
                  f'<b>Order #:</b> {order.order_number}<br/>'
                  f'<b>Date:</b> {order.created_at.strftime("%d %b %Y")}<br/>'
                  f'<b>Status:</b> {order.get_payment_status_display()}<br/>'
                  f'<b>Method:</b> {order.payment_method.upper() if order.payment_method else "—"}',
                  ParagraphStyle('right', parent=styles['Normal'], alignment=TA_RIGHT)),
    ]]
    meta_tbl = Table(meta_data, colWidths=[95*mm, 75*mm])
    meta_tbl.setStyle(TableStyle([
        ('VALIGN', (0,0),(-1,-1), 'TOP'),
        ('LINEBELOW', (0,0),(-1,-1), 0.5, colors.HexColor('#1A1A28')),
        ('BOTTOMPADDING',(0,0),(-1,-1), 6),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 8*mm))

    # ── Items table ─────────────────────────────────────────
    col_heads = ['#', 'Product', 'SKU', 'Qty', 'Unit Price', 'Total']
    rows      = [col_heads]
    for i, item in enumerate(order.items.all(), 1):
        rows.append([
            str(i),
            item.product_name + (f'\n{item.variant_info}' if item.variant_info else ''),
            item.sku or '—',
            str(item.quantity),
            f'KES {item.unit_price:,.2f}',
            f'KES {item.total_price:,.2f}',
        ])

    items_tbl = Table(rows, colWidths=[8*mm, 65*mm, 25*mm, 12*mm, 25*mm, 25*mm])
    items_tbl.setStyle(TableStyle([
        # Header
        ('BACKGROUND',   (0,0),(-1,0),  DARK),
        ('TEXTCOLOR',    (0,0),(-1,0),  GOLD),
        ('FONTNAME',     (0,0),(-1,0),  'Helvetica-Bold'),
        ('FONTSIZE',     (0,0),(-1,0),  8),
        ('TOPPADDING',   (0,0),(-1,0),  6),
        ('BOTTOMPADDING',(0,0),(-1,0),  6),
        # Data rows
        ('FONTSIZE',     (0,1),(-1,-1), 8),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white, colors.HexColor('#F8F7F5')]),
        ('GRID',         (0,0),(-1,-1), 0.3, colors.HexColor('#E0DDD8')),
        ('ALIGN',        (0,0),(0,-1),  'CENTER'),
        ('ALIGN',        (3,0),(-1,-1), 'RIGHT'),
        ('TOPPADDING',   (0,1),(-1,-1), 5),
        ('BOTTOMPADDING',(0,1),(-1,-1), 5),
        ('LEFTPADDING',  (0,0),(-1,-1), 5),
        ('RIGHTPADDING', (0,0),(-1,-1), 5),
    ]))
    story.append(items_tbl)
    story.append(Spacer(1, 6*mm))

    # ── Totals ──────────────────────────────────────────────
    totals = []
    totals.append(['Subtotal', f'KES {order.subtotal:,.2f}'])
    if order.discount_amount:
        totals.append(['Discount', f'- KES {order.discount_amount:,.2f}'])
    if order.shipping_fee:
        totals.append(['Shipping', f'KES {order.shipping_fee:,.2f}'])
    if order.tax_amount:
        totals.append(['VAT (16%)', f'KES {order.tax_amount:,.2f}'])
    totals.append(['TOTAL DUE', f'KES {order.total:,.2f}'])

    totals_tbl = Table(totals, colWidths=[130*mm, 40*mm])
    style_list  = [
        ('ALIGN',        (1,0), (1,-1), 'RIGHT'),
        ('FONTSIZE',     (0,0), (-1,-1), 9),
        ('TOPPADDING',   (0,0), (-1,-1), 4),
        ('BOTTOMPADDING',(0,0), (-1,-1), 4),
        ('RIGHTPADDING', (1,0), (1,-1), 4),
        ('LINEABOVE',    (0,-1),(-1,-1), 1.5, GOLD),
        ('FONTNAME',     (0,-1),(-1,-1), 'Helvetica-Bold'),
        ('FONTSIZE',     (0,-1),(-1,-1), 11),
        ('TEXTCOLOR',    (0,-1),(-1,-1), DARK),
        ('BACKGROUND',   (0,-1),(-1,-1), GOLD),
        ('TOPPADDING',   (0,-1),(-1,-1), 6),
        ('BOTTOMPADDING',(0,-1),(-1,-1), 6),
    ]
    if order.discount_amount:
        style_list.append(('TEXTCOLOR', (0,1),(1,1), GREEN))
    totals_tbl.setStyle(TableStyle(style_list))
    story.append(totals_tbl)

    # ── Footer ──────────────────────────────────────────────
    story.append(Spacer(1, 10*mm))
    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#1A1A28')))
    story.append(Spacer(1, 4*mm))
    footer_style = ParagraphStyle('footer', parent=styles['Normal'],
                                   fontSize=7, textColor=GREY, alignment=TA_CENTER)
    story.append(Paragraph(
        'Thank you for shopping with ShopAI  &nbsp;|&nbsp; support@shopai.com &nbsp;|&nbsp; www.shopai.com<br/>'
        f'Generated on {timezone.now().strftime("%d %b %Y %H:%M")} &nbsp;|&nbsp; '
        'Powered by PyTorch AI',
        footer_style
    ))

    doc.build(story)
    return buf.getvalue()


def create_and_save_invoice(order):
    """Generate PDF and save to Invoice model."""
    from .models import Invoice
    from django.core.files.base import ContentFile

    invoice, _ = Invoice.objects.get_or_create(order=order)
    pdf_bytes   = generate_invoice_pdf(order)
    filename    = f'invoice_{invoice.invoice_number}.pdf'
    invoice.pdf_file.save(filename, ContentFile(pdf_bytes), save=True)
    return invoice
