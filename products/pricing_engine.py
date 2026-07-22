"""
ShopAI — Dynamic Pricing Engine
PyTorch neural network that adjusts product prices based on:
  - Demand (view/purchase velocity)
  - Stock level (scarcity pricing)
  - Competitor price signals
  - Day of week / time patterns
  - Category trends
  - User segment (if logged in)

Output: optimal price multiplier (0.7x – 1.3x base price)
"""
import torch
import torch.nn as nn
import numpy as np
from pathlib import Path
from django.conf import settings
from django.utils import timezone

MODEL_PATH = Path(settings.AI_MODELS_DIR) / 'pricing_model.pth'
_pricing_model = None


# ── Model Architecture ────────────────────────────────────

class PricingNet(nn.Module):
    """
    Feedforward network for price optimization.
    Input:  10 features (demand, stock, time, category, etc.)
    Output: 1 scalar — price multiplier (sigmoid scaled to 0.7–1.3)
    """
    def __init__(self, input_dim=10, hidden_dims=[64, 32, 16]):
        super().__init__()
        layers = []
        prev   = input_dim
        for h in hidden_dims:
            layers += [nn.Linear(prev, h), nn.BatchNorm1d(h), nn.ReLU(), nn.Dropout(0.2)]
            prev = h
        layers.append(nn.Linear(prev, 1))
        layers.append(nn.Sigmoid())   # output in [0,1] → scale to [0.7, 1.3]
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        raw = self.net(x)             # (B, 1) in [0,1]
        return 0.7 + raw * 0.6        # scale to [0.7, 1.3]


# ── Feature Engineering ───────────────────────────────────

def _extract_features(product, user=None):
    """
    Build the 10-dim feature vector for a product.

    Features:
      0: view_velocity        — views in last 7 days / avg
      1: purchase_velocity    — purchases last 7 days / avg
      2: stock_ratio          — current stock / max stock (scarcity signal)
      3: discount_history     — has been on sale before (0/1)
      4: rating_score         — normalized rating
      5: category_demand      — category-level demand score
      6: day_of_week_norm     — 0 (Mon) – 1 (Sun) → peak on Fri-Sat
      7: hour_of_day_norm     — 0–1 normalized hour
      8: is_premium_user      — 1 if user has premium/loyalty status
      9: margin_ratio         — (price - cost) / price
    """
    from products.models import ProductView
    from django.db.models import Count
    from datetime import timedelta

    now       = timezone.now()
    week_ago  = now - timedelta(days=7)

    # View velocity (last 7 days vs all-time daily avg)
    recent_views  = ProductView.objects.filter(product=product, viewed_at__gte=week_ago).count()
    total_views   = max(product.view_count, 1)
    days_since    = max((now - product.created_at).days, 1)
    avg_daily     = total_views / days_since
    view_vel      = min(recent_views / max(avg_daily * 7, 1), 3.0) / 3.0  # clamp & normalize

    # Purchase velocity
    purchase_vel  = min(product.purchase_count / max(days_since, 1) * 7, 5.0) / 5.0

    # Stock ratio (low stock → higher multiplier)
    if product.track_inventory and product.stock is not None:
        stock_ratio = 1.0 - min(product.stock / max(product.stock + 10, 1), 1.0)
    else:
        stock_ratio = 0.5

    # Discount history
    discount_hist = 1.0 if product.compare_price else 0.0

    # Rating (normalized 0–1)
    rating_score  = float(product.rating_avg) / 5.0

    # Category demand (avg purchase_count in category)
    cat_demand = 0.5
    if product.category:
        from products.models import Product
        cat_avg = Product.objects.filter(
            category=product.category, is_active=True
        ).aggregate(avg=__import__('django.db.models', fromlist=['Avg']).Avg('purchase_count'))['avg'] or 0
        cat_demand = min(float(cat_avg) / max(product.purchase_count, 1), 2.0) / 2.0

    # Time features
    day_norm  = now.weekday() / 6.0            # 0=Mon, 1=Sun
    hour_norm = now.hour / 23.0

    # User segment
    is_premium = 0.0
    if user and user.is_authenticated:
        order_count = user.orders.filter(payment_status='paid').count()
        is_premium  = min(order_count / 10.0, 1.0)

    # Margin ratio
    if product.cost_price and product.price > 0:
        margin = float((product.price - product.cost_price) / product.price)
        margin = max(min(margin, 1.0), 0.0)
    else:
        margin = 0.5

    return np.array([
        view_vel, purchase_vel, stock_ratio, discount_hist,
        rating_score, cat_demand, day_norm, hour_norm,
        is_premium, margin
    ], dtype=np.float32)


# ── Training ──────────────────────────────────────────────

def train_pricing_model(epochs=50):
    """
    Train pricing model on historical order data.
    Uses actual purchase prices as training signal.
    """
    print(' Training dynamic pricing model...')

    try:
        from orders.models import OrderItem
    except Exception:
        print('    Order history app not available — using synthetic training')
        return _train_synthetic(epochs=epochs)

    items = OrderItem.objects.select_related('product', 'order').filter(product__isnull=False)[:5000]

    if len(items) < 100:
        print('   Insufficient order data — using synthetic training')
        return _train_synthetic()

    X_list, y_list = [], []
    for item in items:
        try:
            feats = _extract_features(item.product)
            # Target: actual unit_price / base_price ratio
            ratio = float(item.unit_price / max(item.product.price, 1))
            ratio = max(0.7, min(1.3, ratio))
            X_list.append(feats)
            y_list.append((ratio - 0.7) / 0.6)  # normalize to [0,1]
        except Exception:
            continue

    return _fit_model(np.array(X_list), np.array(y_list, dtype=np.float32), epochs)


def _train_synthetic(n_samples=2000, epochs=50):
    """Generate synthetic training data when real data is scarce."""
    np.random.seed(42)
    X = np.random.rand(n_samples, 10).astype(np.float32)
    # Rule: high demand + low stock → higher price; low margin → lower price
    y = (0.3 * X[:,0] + 0.25 * X[:,2] + 0.2 * X[:,4] - 0.15 * X[:,9] + 0.5 * np.random.rand(n_samples))
    y = np.clip(y, 0, 1).astype(np.float32)
    return _fit_model(X, y, epochs)


def _fit_model(X, y, epochs=50):
    X_t   = torch.from_numpy(X)
    y_t   = torch.from_numpy(y).unsqueeze(1)
    model = PricingNet()
    opt   = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
    loss_fn = nn.MSELoss()
    ds    = torch.utils.data.TensorDataset(X_t, y_t)
    loader= torch.utils.data.DataLoader(ds, batch_size=64, shuffle=True)

    model.train()
    for epoch in range(epochs):
        for xb, yb in loader:
            opt.zero_grad()
            # Scale model output back to [0,1] for loss
            pred = (model(xb) - 0.7) / 0.6
            loss_fn(pred, yb).backward()
            opt.step()

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), MODEL_PATH)
    print(f'  Pricing model saved to {MODEL_PATH}')
    global _pricing_model
    model.eval()
    _pricing_model = model
    return model


def _get_model():
    global _pricing_model
    if _pricing_model is not None:
        return _pricing_model
    model = PricingNet()
    if MODEL_PATH.exists():
        model.load_state_dict(torch.load(MODEL_PATH, map_location='cpu'))
    else:
        _train_synthetic()
        return _pricing_model
    model.eval()
    _pricing_model = model
    return model


# ── Inference ─────────────────────────────────────────────

def get_dynamic_price(product, user=None):
    """
    Compute AI-optimized price for a product.
    Returns Decimal price, or None if dynamic pricing disabled.
    """
    from decimal import Decimal

    try:
        model    = _get_model()
        features = _extract_features(product, user)
        tensor   = torch.from_numpy(features).unsqueeze(0)

        with torch.no_grad():
            multiplier = model(tensor).item()

        # Clamp multiplier: never above compare_price, never below 70% base
        base_price = float(product.price)
        ai_price   = base_price * multiplier

        # Floor: at least 70% of base price
        ai_price = max(ai_price, base_price * 0.70)

        # Ceiling: at most the compare_price (original price)
        if product.compare_price:
            ai_price = min(ai_price, float(product.compare_price))

        # Round to nearest 50 KES for clean pricing
        ai_price = round(ai_price / 50) * 50

        return Decimal(str(ai_price)), round(multiplier, 4)
    except Exception as e:
        return None, None


def update_product_ai_prices(batch_size=100):
    """
    Celery task helper: update ai_price for all active products.
    """
    from products.models import Product

    products = Product.objects.filter(is_active=True).iterator()
    updated  = 0
    bulk     = []

    for product in products:
        ai_price, mult = get_dynamic_price(product)
        if ai_price:
            product.ai_price = ai_price
            bulk.append(product)
            updated += 1
        if len(bulk) >= batch_size:
            Product.objects.bulk_update(bulk, ['ai_price'])
            bulk.clear()

    if bulk:
        Product.objects.bulk_update(bulk, ['ai_price'])

    print(f' Updated AI prices for {updated} products')
    return updated
