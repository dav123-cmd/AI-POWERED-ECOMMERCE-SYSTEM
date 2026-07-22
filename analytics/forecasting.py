"""
ShopAI — LSTM Sales Forecasting
PyTorch LSTM that learns temporal patterns in daily revenue data.

Architecture:
  - Input:  sequence of 30 days of revenue values (normalized)
  - LSTM:   2 layers, 64 hidden units, dropout 0.2
  - Output: next N days of predicted revenue
  - Uncertainty: uses Monte Carlo dropout for confidence intervals

Usage:
  from apps.analytics.forecasting import generate_forecast
  forecasts = generate_forecast(days_ahead=14)
"""
import torch
import torch.nn as nn
import numpy as np
from pathlib import Path
from django.conf import settings
from django.utils import timezone

FORECAST_MODEL_PATH = Path(settings.AI_MODELS_DIR) / 'sales_forecast.pth'
SEQ_LEN    = 30    # lookback window in days
HIDDEN_DIM = 64
NUM_LAYERS = 2

_forecast_model  = None
_revenue_mean    = 1.0
_revenue_std     = 1.0


# ── Model ─────────────────────────────────────────────────

class SalesForecastLSTM(nn.Module):
    """
    Stacked LSTM for multivariate time-series forecasting.
    Predicts next-day revenue given a 30-day window.
    """
    def __init__(self, input_dim=1, hidden_dim=HIDDEN_DIM,
                 num_layers=NUM_LAYERS, dropout=0.2):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers

        self.lstm = nn.LSTM(
            input_size  = input_dim,
            hidden_size = hidden_dim,
            num_layers  = num_layers,
            batch_first = True,
            dropout     = dropout if num_layers > 1 else 0.0,
        )
        self.dropout = nn.Dropout(dropout)
        self.fc      = nn.Sequential(
            nn.Linear(hidden_dim, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, 1),
        )

    def forward(self, x):
        """x: (batch, seq_len, 1)"""
        out, _ = self.lstm(x)               # (batch, seq_len, hidden)
        last   = self.dropout(out[:, -1, :])# (batch, hidden)
        return self.fc(last).squeeze(1)     # (batch,)


# ── Data Preparation ──────────────────────────────────────

def _get_daily_revenue(days=365):
    """Pull daily revenue from DB, fill missing days with 0."""
    from orders.models import Order
    from django.db.models import Sum
    from datetime import timedelta, date

    end_date   = timezone.now().date()
    start_date = end_date - timedelta(days=days)

    # Query aggregated revenue per day
    qs = Order.objects.filter(
        payment_status='paid',
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
    ).extra(
        select={'day': "DATE(created_at)"}
    ).values('day').annotate(rev=Sum('total')).order_by('day')

    # Build complete date series
    rev_map  = {row['day']: float(row['rev']) for row in qs}
    revenues = []
    d        = start_date
    while d <= end_date:
        revenues.append(rev_map.get(d, 0.0))
        d += timedelta(days=1)

    return np.array(revenues, dtype=np.float32)


def _normalize(data, mean=None, std=None):
    if mean is None:
        mean = data.mean()
        std  = data.std() + 1e-8
    return (data - mean) / std, mean, std


def _make_sequences(data, seq_len=SEQ_LEN):
    """Slide window over data to create (X, y) pairs."""
    X, y = [], []
    for i in range(len(data) - seq_len):
        X.append(data[i:i+seq_len])
        y.append(data[i+seq_len])
    return np.array(X), np.array(y)


# ── Training ──────────────────────────────────────────────

def train_forecast_model(epochs=100, min_days=60):
    """
    Train LSTM on historical revenue data.
    Requires at least min_days of data.
    """
    global _forecast_model, _revenue_mean, _revenue_std

    revenues = _get_daily_revenue(days=365)

    if len(revenues) < min_days or revenues.sum() == 0:
        print(f'Only {len(revenues)} days of data — using synthetic training')
        revenues = _generate_synthetic_revenues()

    print(f'Training LSTM forecast model on {len(revenues)} days...')

    norm, mean, std = _normalize(revenues)
    _revenue_mean, _revenue_std = float(mean), float(std)

    X, y = _make_sequences(norm, SEQ_LEN)
    X_t  = torch.from_numpy(X).unsqueeze(2)  # (N, SEQ_LEN, 1)
    y_t  = torch.from_numpy(y)

    model   = SalesForecastLSTM()
    opt     = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
    sched   = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=10, factor=0.5)
    loss_fn = nn.HuberLoss()                 # robust to outliers
    ds      = torch.utils.data.TensorDataset(X_t, y_t)
    loader  = torch.utils.data.DataLoader(ds, batch_size=32, shuffle=True)

    model.train()
    best_loss = float('inf')
    best_state= None

    for epoch in range(epochs):
        epoch_loss = 0.0
        for xb, yb in loader:
            opt.zero_grad()
            pred = model(xb)
            loss = loss_fn(pred, yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            epoch_loss += loss.item()
        avg_loss = epoch_loss / len(loader)
        sched.step(avg_loss)
        if avg_loss < best_loss:
            best_loss  = avg_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        if (epoch + 1) % 20 == 0:
            print(f'  Epoch {epoch+1}/{epochs} | Loss: {avg_loss:.6f}')

    model.load_state_dict(best_state)
    model.eval()
    _forecast_model = model

    FORECAST_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        'state':        model.state_dict(),
        'revenue_mean': _revenue_mean,
        'revenue_std':  _revenue_std,
        'seq_len':      SEQ_LEN,
    }, FORECAST_MODEL_PATH)
    print(f'Forecast model saved. Best loss: {best_loss:.6f}')
    return model


def _generate_synthetic_revenues(days=400):
    """Generate realistic synthetic revenue curve for training."""
    np.random.seed(42)
    t      = np.arange(days)
    trend  = 50000 + 200 * t                           # growing trend
    weekly = 15000 * np.sin(2 * np.pi * t / 7)        # weekly cycle
    monthly= 10000 * np.sin(2 * np.pi * t / 30)       # monthly cycle
    noise  = np.random.normal(0, 8000, days)
    return np.maximum(trend + weekly + monthly + noise, 0).astype(np.float32)


# ── Inference ─────────────────────────────────────────────

def _load_model():
    global _forecast_model, _revenue_mean, _revenue_std
    if _forecast_model is not None:
        return _forecast_model
    if FORECAST_MODEL_PATH.exists():
        ck = torch.load(FORECAST_MODEL_PATH, map_location='cpu')
        model = SalesForecastLSTM()
        model.load_state_dict(ck['state'])
        model.eval()
        _revenue_mean = ck.get('revenue_mean', 1.0)
        _revenue_std  = ck.get('revenue_std',  1.0)
        _forecast_model = model
        return model
    return train_forecast_model()


def _mc_predict(model, x_tensor, n_samples=50):
    """
    Monte Carlo Dropout inference for uncertainty estimation.
    Keep dropout active during inference to get prediction distribution.
    """
    model.train()   # enable dropout
    preds = []
    with torch.no_grad():
        for _ in range(n_samples):
            preds.append(model(x_tensor).item())
    model.eval()
    return np.array(preds)


def generate_forecast(days_ahead=14):
    """
    Generate sales forecast for next N days with confidence intervals.

    Returns:
        List of dicts: [{date, predicted, lower, upper, confidence}]
    """
    from datetime import timedelta, date
    from decimal import Decimal

    model    = _load_model()
    revenues = _get_daily_revenue(days=SEQ_LEN + 30)

    if len(revenues) < SEQ_LEN:
        revenues = np.concatenate([
            np.zeros(SEQ_LEN - len(revenues)), revenues
        ])

    # Normalize with training stats
    norm_rev = (revenues - _revenue_mean) / (_revenue_std + 1e-8)
    window   = norm_rev[-SEQ_LEN:].copy()

    forecasts = []
    today     = timezone.now().date()

    for i in range(days_ahead):
        x_t    = torch.from_numpy(window).float().unsqueeze(0).unsqueeze(2)

        # MC dropout for uncertainty
        samples = _mc_predict(model, x_t, n_samples=30)
        mean_p  = samples.mean()
        std_p   = samples.std()

        # Denormalize
        pred_rev    = float(mean_p  * _revenue_std + _revenue_mean)
        lower_rev   = float((mean_p - 1.96 * std_p) * _revenue_std + _revenue_mean)
        upper_rev   = float((mean_p + 1.96 * std_p) * _revenue_std + _revenue_mean)
        pred_rev    = max(pred_rev,  0)
        lower_rev   = max(lower_rev, 0)
        upper_rev   = max(upper_rev, 0)

        fcast_date  = today + timedelta(days=i+1)
        forecasts.append({
            'date':      fcast_date,
            'predicted': Decimal(str(round(pred_rev,  2))),
            'lower':     Decimal(str(round(lower_rev, 2))),
            'upper':     Decimal(str(round(upper_rev, 2))),
            'confidence':round(1.0 - min(std_p / (abs(mean_p) + 1e-8), 0.5), 3),
        })

        # Roll window forward
        window = np.append(window[1:], mean_p)

    return forecasts


def save_forecasts(days_ahead=14):
    """Generate and persist forecasts to DB."""
    from .models import SalesForecast

    forecasts  = generate_forecast(days_ahead)
    model_ver  = timezone.now().strftime('%Y%m%d')

    SalesForecast.objects.filter(model_version=model_ver).delete()
    bulk = [
        SalesForecast(
            forecast_date     = f['date'],
            predicted_revenue = f['predicted'],
            lower_bound       = f['lower'],
            upper_bound       = f['upper'],
            confidence        = f['confidence'],
            model_version     = model_ver,
        )
        for f in forecasts
    ]
    SalesForecast.objects.bulk_create(bulk, ignore_conflicts=True)
    print(f' Saved {len(bulk)} forecast days')
    return forecasts
