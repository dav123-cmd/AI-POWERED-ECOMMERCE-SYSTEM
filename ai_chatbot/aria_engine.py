"""
ShopAI — ARIA Engine
Routes classified intents to appropriate handlers.
Falls back to Claude API for general/complex queries.
"""
import anthropic
from django.conf import settings
from .intent_classifier import classify_intent


# ── Intent Handlers ───────────────────────────────────────

def handle_order_status(user, message):
    """Look up order status from DB."""
    import re
    from orders.models import Order

    # Try to extract order number from message
    match = re.search(r'SAI[-\s]?\w+', message.upper())
    order = None

    if match:
        order_num = match.group().replace(' ', '-')
        try:
            q = Order.objects.filter(order_number__icontains=order_num)
            if user and user.is_authenticated:
                q = q.filter(user=user)
            order = q.first()
        except Exception:
            pass
    elif user and user.is_authenticated:
        order = user.orders.order_by('-created_at').first()

    if order:
        STATUS_EMOJI = {
            'pending':'Pending ','confirmed':'Confirmed','processing':'Processing',
            'shipped':'Shipped','delivered':'Delivered','cancelled':'Cancelled','refunded':'Refunded'
        }
        emoji = STATUS_EMOJI.get(order.status, 'Unknown')
        reply = (
            f"{emoji} **Order {order.order_number}**\n\n"
            f"**Status:** {order.get_status_display()}\n"
            f"**Total:** KES {order.total:,.0f}\n"
            f"**Placed:** {order.created_at.strftime('%d %b %Y')}\n"
        )
        if order.tracking_number:
            reply += f"**Tracking #:** {order.tracking_number}\n"
        if order.status == 'shipped':
            reply += "\n Your order is on its way! Expected delivery in 2–3 business days."
        elif order.status == 'delivered':
            reply += "\n Your order has been delivered. Enjoy your purchase!"
        elif order.status == 'pending':
            reply += "\n Your order is being confirmed. You'll receive an email shortly."
        return reply, {'order_id': str(order.id), 'order_number': order.order_number}
    else:
        if user and user.is_authenticated:
            return ("I couldn't find a recent order for your account. "
                    "You can view all your orders at [Order History](/orders/history/).\n\n"
                    "If you have a specific order number, please share it and I'll look it up! "), {}
        return ("Please sign in to check your order status, or provide your order number "
                "(format: SAI-XXXXXX-XXXX) and the email used at checkout."), {}


def handle_product_search(user, message):
    """Trigger semantic search and return top results."""
    from ai_search.semantic_search import search_products
    products = search_products(message, top_k=4)
    if not products:
        return (f"I searched for **\"{message}\"** but couldn't find exact matches. "
                "Try [browsing our categories](/shop/categories/) or use our "
                "[visual search](/search/visual/) to find products by photo! 📸"), {}

    lines = [f"Here are the top results for **\"{message}\"**:\n"]
    for p in products:
        price = f"KES {p.effective_price:,.0f}"
        disc  = f" ~~KES {p.compare_price:,.0f}~~" if p.is_on_sale else ""
        lines.append(f"• **[{p.name}]({p.get_absolute_url()})** — {price}{disc}")
    lines.append(f"\n[View all results →](/search/?q={message.replace(' ', '+')})")
    return "\n".join(lines), {'search_query': message}


def handle_recommendation(user, message):
    """Return personalized or popular recommendations."""
    from ai_recommendations.recommender import get_recommendations, _popularity_fallback
    if user and user.is_authenticated:
        products = get_recommendations(user, top_k=4)
        intro    = "Based on your taste, here are my top picks for you:\n"
    else:
        from products.models import Product
        products = Product.objects.filter(is_active=True).order_by('-purchase_count')[:4]
        intro    = "Here are our most popular products right now:\n"

    if not products:
        return "I'm still learning your preferences! Browse around and I'll get smarter ", {}

    lines = [intro]
    for p in products:
        lines.append(f"• **[{p.name}]({p.get_absolute_url()})** — KES {p.effective_price:,.0f}")
    lines.append(f"\n[See all recommendations →](/ai/recommend/)")
    return "\n".join(lines), {}


def handle_shipping(user, message):
    return (
        " **ShopAI Shipping Info:**\n\n"
        "• **Free delivery** on orders over KES 2,000\n"
        "• **Standard shipping:** KES 200 · 3–5 business days\n"
        "• **Express shipping:** KES 500 · 1–2 business days\n"
        "• We deliver **nationwide across Kenya** 🇰🇪\n"
        "• Nairobi same-day delivery available on select items\n\n"
        "Want to track an existing order? Share your order number! "
    ), {}


def handle_return(user, message):
    return (
        "↩**ShopAI Returns & Refunds:**\n\n"
        "• **30-day** hassle-free return policy\n"
        "• Items must be in original condition with tags\n"
        "• Refunds processed within **3–5 business days**\n"
        "• Damaged or wrong items? We cover return shipping!\n\n"
        "To start a return, go to [Order History](/orders/history/) → "
        "Select order → **Request Refund**\n\n"
        "Need more help? I can connect you to our support team. "
    ), {}


def handle_greeting(user, message):
    name = user.get_short_name() if user and user.is_authenticated else "there"
    return (
        f" Hey {name}! I'm **ARIA**, ShopAI's AI assistant.\n\n"
        "I can help you with:\n"
        " **Find products** — just describe what you need\n"
        " **Track orders** — share your order number\n"
        " **Recommendations** — personalized picks for you\n"
        " **Any questions** — shipping, returns, pricing\n\n"
        "What can I help you with today?"
    ), {}


def handle_farewell(user, message):
    name = user.get_short_name() if user and user.is_authenticated else "friend"
    return (
        f"Goodbye {name}! Happy shopping!\n\n"
        "Come back anytime — I'm always here 24/7. "
    ), {}


# ── Claude API Fallback ───────────────────────────────────

SYSTEM_PROMPT = """You are ARIA, the AI shopping assistant for ShopAI — a cutting-edge 
AI-powered e-commerce platform in Kenya. You are helpful, friendly, and knowledgeable 
about products, shopping, and the platform.

Key facts:
- Platform: ShopAI (shopai.com)
- Currency: Kenyan Shillings (KES)
- Payment methods: M-Pesa, Stripe cards, PayPal
- Free shipping on orders over KES 2,000
- 30-day return policy
- You support order tracking, product recommendations, and shopping assistance

Keep responses concise (under 150 words), friendly, and use markdown formatting.
Always offer to help further. Never make up product prices or order details."""


def call_claude(conversation_history, user_message):
    """Call Anthropic Claude API for general queries."""
    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        messages = []
        # Include last 6 messages for context
        for msg in conversation_history[-6:]:
            if msg['role'] in ('user', 'assistant'):
                messages.append({'role': msg['role'], 'content': msg['content']})
        messages.append({'role': 'user', 'content': user_message})

        response = client.messages.create(
            model      = 'claude-sonnet-4-20250514',
            max_tokens = 400,
            system     = SYSTEM_PROMPT,
            messages   = messages,
        )
        return response.content[0].text
    except Exception as e:
        return (
            "I'm having a moment!  Try rephrasing your question, or visit our "
            "[Help Center](/help/) for quick answers.\n\n"
            f"*(Technical note: {str(e)[:80]})*"
        )


# ── Main Router ───────────────────────────────────────────

INTENT_HANDLERS = {
    'greeting':      handle_greeting,
    'farewell':      handle_farewell,
    'order_status':  handle_order_status,
    'shipping_info': handle_shipping,
    'return_refund': handle_return,
    'product_search':handle_product_search,
    'recommendation':handle_recommendation,
}


def process_message(user, message, conversation_history=None):
    """
    Main ARIA pipeline:
    1. Classify intent
    2. Route to handler or Claude API
    3. Return (reply, metadata, intent, confidence)
    """
    if not conversation_history:
        conversation_history = []

    intent, confidence = classify_intent(message)

    # Route to specific handler
    if intent in INTENT_HANDLERS and confidence >= 0.6:
        handler = INTENT_HANDLERS[intent]
        try:
            reply, meta = handler(user, message)
            return reply, meta, intent, confidence
        except Exception as e:
            pass  # Fall through to Claude

    # General / low-confidence → Claude API
    reply = call_claude(conversation_history, message)
    return reply, {}, 'general', confidence
