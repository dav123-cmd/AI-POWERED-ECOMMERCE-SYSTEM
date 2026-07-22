"""
ShopAI — Fraud Detection Engine
PyTorch Autoencoder that learns normal transaction patterns.
High reconstruction error = anomaly = suspicious order.

Features extracted per order:
  0:  amount_norm          — order total / 99th percentile
  1:  items_count_norm     — number of items / max seen
  2:  hour_of_day_norm     — 0-1
  3:  day_of_week_norm     — 0-1
  4:  is_new_user          — account age < 7 days
  5:  device_mismatch      — different IP from usual (proxy)
  6:  high_value_item      — any item > 10x avg item price
  7:  quantity_spike       — any single item qty > 5
  8:  shipping_billing_diff — shipping != billing country
  9:  payment_attempts     — failed payment attempts before success
  10: email_domain_risk    — disposable email domain
  11: address_velocity     — same address used in multiple orders today
  12: repeat_customer      — has previous paid orders
  13: cart_abandonment_hist— user's historical cart abandonment rate
  14: time_since_register  — normalized account age
"""
import torch
import torch.nn as nn
import numpy as np
from pathlib import Path
from django.conf import settings

MODEL_PATH = Path(settings.AI_MODELS_DIR) / 'fraud_detector.pth'
_fraud_model   = None
_threshold     = 0.15   # reconstruction error threshold
FEATURE_DIM    = 15

# Known disposable email domains
DISPOSABLE_DOMAINS = {
    'mailinator.com','guerrillamail.com','10minutemail.com',
    'throwaway.email','tempmail.com','yopmail.com','sharklasers.com',
}


# ── Model Architecture ────────────────────────────────────

class FraudAutoencoder(nn.Module):
    """
    Autoencoder trained on normal transactions.
    Normal orders → low reconstruction error
    Fraudulent orders → high reconstruction error (anomalous pattern)
    """
    def __init__(self, input_dim=FEATURE_DIM, latent_dim=6):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 32), nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(32, 16),        nn.ReLU(),
            nn.Linear(16, latent_dim),nn.ReLU(),
        )
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 16),nn.ReLU(),
            nn.Linear(16, 32),        nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(32, input_dim), nn.Sigmoid(),
        )

    def forward(self, x):
        return self.decoder(self.encoder(x))

    def reconstruction_error(self, x):
        with torch.no_grad():
            recon = self.forward(x)
            return torch.mean((recon - x) ** 2, dim=1)


# ── Feature Extraction ────────────────────────────────────

def _extract_order_features(order):
    """Convert an order to a 15-dim feature vector."""
    from orders.models import Order
    from django.utils import timezone
    from datetime import timedelta

    now = timezone.now()

    # 0: Amount normalized (use 50k KES as reference max)
    amount_norm = min(float(order.total) / 50000.0, 1.0)

    # 1: Items count
    items_count = order.items.count()
    items_norm  = min(items_count / 20.0, 1.0)

    # 2-3: Time features
    hour_norm   = now.hour / 23.0
    day_norm    = now.weekday() / 6.0

    # 4: New user (account < 7 days)
    is_new = 0.0
    if order.user:
        days_old = (now - order.user.date_joined).days
        is_new   = 1.0 if days_old < 7 else 0.0

    # 5: Device mismatch proxy (simplified — always 0 without device tracking)
    device_mismatch = 0.0

    # 6: High value item (any item > 3x avg item price in order)
    item_prices = [float(i.unit_price) for i in order.items.all()]
    avg_price   = np.mean(item_prices) if item_prices else 0
    high_value  = 1.0 if any(p > avg_price * 3 for p in item_prices) else 0.0

    # 7: Quantity spike (any single item qty > 5)
    qty_spike = 1.0 if any(i.quantity > 5 for i in order.items.all()) else 0.0

    # 8: Shipping != usual country
    ship_diff = 1.0 if order.shipping_country not in ('Kenya', 'KE') else 0.0

    # 9: Payment attempts (count failed payments for this order)
    from payments.models import Payment
    failed_attempts = Payment.objects.filter(order=order, status='failed').count()
    pay_attempts    = min(failed_attempts / 3.0, 1.0)

    # 10: Disposable email domain
    domain     = order.email.split('@')[-1].lower() if '@' in order.email else ''
    email_risk = 1.0 if domain in DISPOSABLE_DOMAINS else 0.0

    # 11: Address velocity (same address used multiple times today)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    addr_count  = Order.objects.filter(
        shipping_line1=order.shipping_line1,
        created_at__gte=today_start
    ).count()
    addr_vel    = min(addr_count / 5.0, 1.0)

    # 12: Repeat customer
    repeat = 0.0
    if order.user:
        paid_orders = order.user.orders.filter(payment_status='paid').count()
        repeat      = min(paid_orders / 5.0, 1.0)

    # 13: Cart abandonment history (proxy: 0 if no data)
    cart_abandon = 0.0

    # 14: Time since register (normalized, max 365 days)
    time_since = 0.5
    if order.user:
        days = (now - order.user.date_joined).days
        time_since = min(days / 365.0, 1.0)

    return np.array([
        amount_norm, items_norm, hour_norm, day_norm, is_new,
        device_mismatch, high_value, qty_spike, ship_diff, pay_attempts,
        email_risk, addr_vel, repeat, cart_abandon, time_since
    ], dtype=np.float32)


# ── Training ──────────────────────────────────────────────

def train_fraud_detector(epochs=80):
    """
    Train the autoencoder on historical legitimate orders.
    Uses only paid/delivered orders as 'normal' training data.
    """
    from orders.models import Order

    print('Training fraud detection model...')

    orders = Order.objects.filter(
        payment_status='paid',
        status__in=['confirmed','processing','shipped','delivered']
    )[:3000]

    if len(orders) < 50:
        print('   Insufficient data — using synthetic training')
        return _train_fraud_synthetic()

    X_list = []
    for order in orders:
        try:
            X_list.append(_extract_order_features(order))
        except Exception:
            continue

    if not X_list:
        return _train_fraud_synthetic()

    X = np.array(X_list, dtype=np.float32)
    return _fit_fraud_model(X, epochs)


def _train_fraud_synthetic(n_samples=3000, epochs=80):
    """Synthetic training when real data is scarce."""
    np.random.seed(42)
    # Normal transactions: low amounts, few items, established users
    X = np.random.beta(2, 5, (n_samples, FEATURE_DIM)).astype(np.float32)
    # Zero out high-risk features for 'normal' patterns
    X[:, 4]  = np.random.choice([0.0, 1.0], n_samples, p=[0.95, 0.05])  # is_new
    X[:, 10] = np.random.choice([0.0, 1.0], n_samples, p=[0.99, 0.01])  # email_risk
    X[:, 7]  = np.random.choice([0.0, 1.0], n_samples, p=[0.97, 0.03])  # qty_spike
    return _fit_fraud_model(X, epochs)


def _fit_fraud_model(X, epochs=80):
    X_t     = torch.from_numpy(X)
    model   = FraudAutoencoder(FEATURE_DIM)
    opt     = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.MSELoss()
    ds      = torch.utils.data.TensorDataset(X_t)
    loader  = torch.utils.data.DataLoader(ds, batch_size=64, shuffle=True)

    model.train()
    for epoch in range(epochs):
        for (xb,) in loader:
            opt.zero_grad()
            recon = model(xb)
            loss_fn(recon, xb).backward()
            opt.step()

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), MODEL_PATH)
    model.eval()
    global _fraud_model
    _fraud_model = model
    print(f'   Fraud detector saved. Trained on {len(X)} transactions.')
    return model


def _get_fraud_model():
    global _fraud_model
    if _fraud_model is not None:
        return _fraud_model
    model = FraudAutoencoder(FEATURE_DIM)
    if MODEL_PATH.exists():
        model.load_state_dict(torch.load(MODEL_PATH, map_location='cpu'))
    else:
        return _train_fraud_synthetic()
    model.eval()
    _fraud_model = model
    return model


# ── Inference ─────────────────────────────────────────────

RISK_LEVELS = [
    (0.05,  'low',      'L', 'Low Risk'),
    (0.10,  'medium',   'M', 'Medium Risk'),
    (0.18,  'high',     'H', 'High Risk'),
    (1.00,  'critical', 'C', 'Critical — Review Required'),
]


def analyze_order(order):
    """
    Analyze an order for fraud risk.

    Returns dict:
        score:       float 0–1 (reconstruction error)
        risk_level:  'low' | 'medium' | 'high' | 'critical'
        emoji:       risk emoji
        label:       human-readable label
        flags:       list of specific risk flags
        action:      'approve' | 'review' | 'block'
    """
    try:
        model    = _get_fraud_model()
        features = _extract_order_features(order)
        tensor   = torch.from_numpy(features).unsqueeze(0)
        error    = model.reconstruction_error(tensor).item()

        # Determine risk level
        risk_level, emoji, label = 'low', 'L', 'Low Risk'
        for threshold, level, emj, lbl in RISK_LEVELS:
            if error <= threshold:
                risk_level, emoji, label = level, emj, lbl
                break

        # Build specific flags
        flags = _build_flags(features, order)

        # Determine action
        if risk_level == 'critical':
            action = 'block'
        elif risk_level == 'high':
            action = 'review'
        else:
            action = 'approve'

        return {
            'score':      round(error, 4),
            'risk_level': risk_level,
            'emoji':      emoji,
            'label':      label,
            'flags':      flags,
            'action':     action,
            'features':   features.tolist(),
        }
    except Exception as e:
        return {'score': 0.0, 'risk_level': 'low', 'emoji': 'L',
                'label': 'Analysis Failed', 'flags': [], 'action': 'approve'}


def _build_flags(features, order):
    """Generate human-readable risk flags from features."""
    flags = []
    if features[4]  > 0.5: flags.append(' New account (< 7 days)')
    if features[6]  > 0.5: flags.append(' Unusually high-value item')
    if features[7]  > 0.5: flags.append(' Large quantity single item')
    if features[8]  > 0.5: flags.append(' International shipping (unusual)')
    if features[9]  > 0.3: flags.append(' Multiple failed payment attempts')
    if features[10] > 0.5: flags.append(' Disposable email address detected')
    if features[11] > 0.5: flags.append(' Address used in multiple orders today')
    if features[0]  > 0.8: flags.append(' Very high order value')
    if not flags:
        flags.append('No suspicious patterns detected')
    return flags


def score_and_update_order(order):
    """Analyze order and save fraud score to DB."""
    from orders.models import Order
    result = analyze_order(order)
    Order.objects.filter(pk=order.pk).update(fraud_score=result['score'])
    if result['action'] == 'block':
        Order.objects.filter(pk=order.pk).update(status='cancelled')
    return result
