"""
ShopAI — Sentiment Analysis & Fake Review Detection
Two PyTorch models:
  1. SentimentNet  — classifies review text as positive/neutral/negative
  2. FakeReviewNet — detects suspicious/fake reviews
"""
import re
import torch
import torch.nn as nn
import numpy as np
from pathlib import Path
from django.conf import settings

SENTIMENT_PATH   = Path(settings.AI_MODELS_DIR) / 'sentiment_model.pth'
FAKE_DETECT_PATH = Path(settings.AI_MODELS_DIR) / 'fake_review_detector.pth'
VOCAB_PATH       = Path(settings.AI_MODELS_DIR) / 'sentiment_vocab.json'

MAX_LEN   = 128
VOCAB_SIZE = 8000

_sentiment_model = None
_fake_model      = None
_vocab           = None


# ── Tokenizer ─────────────────────────────────────────────

def _build_vocab(texts):
    """Simple word-level vocab from training texts."""
    from collections import Counter
    words   = []
    for t in texts:
        words.extend(_tokenize(t))
    counts  = Counter(words)
    vocab   = {'<PAD>': 0, '<UNK>': 1}
    for word, _ in counts.most_common(VOCAB_SIZE - 2):
        vocab[word] = len(vocab)
    return vocab


def _tokenize(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    return text.split()


def _text_to_ids(text, vocab, max_len=MAX_LEN):
    tokens = _tokenize(text)[:max_len]
    ids    = [vocab.get(t, 1) for t in tokens]  # 1 = UNK
    ids    = ids + [0] * (max_len - len(ids))   # pad
    return torch.tensor(ids, dtype=torch.long)


def _get_vocab():
    global _vocab
    if _vocab is not None:
        return _vocab
    import json
    if VOCAB_PATH.exists():
        with open(VOCAB_PATH) as f:
            _vocab = json.load(f)
    else:
        _vocab = {'<PAD>': 0, '<UNK>': 1}
    return _vocab


# ── Model 1: Sentiment Classifier ────────────────────────

class SentimentNet(nn.Module):
    """
    Bidirectional GRU for sentiment classification.
    Classes: 0=negative, 1=neutral, 2=positive
    """
    def __init__(self, vocab_size=VOCAB_SIZE, embed_dim=64,
                 hidden_dim=128, num_classes=3, dropout=0.3):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embed_dim, padding_idx=0)
        self.gru       = nn.GRU(embed_dim, hidden_dim, batch_first=True,
                                 bidirectional=True, num_layers=2, dropout=dropout)
        self.attn      = nn.Linear(hidden_dim * 2, 1)   # attention over timesteps
        self.dropout   = nn.Dropout(dropout)
        self.fc        = nn.Linear(hidden_dim * 2, num_classes)

        nn.init.xavier_uniform_(self.embedding.weight)

    def forward(self, x):
        emb     = self.dropout(self.embedding(x))          # (B, T, E)
        out, _  = self.gru(emb)                            # (B, T, H*2)
        # Attention pooling
        weights = torch.softmax(self.attn(out), dim=1)     # (B, T, 1)
        pooled  = (out * weights).sum(dim=1)               # (B, H*2)
        return self.fc(self.dropout(pooled))               # (B, 3)


# ── Model 2: Fake Review Detector ────────────────────────

class FakeReviewNet(nn.Module):
    """
    Binary classifier: real(0) vs fake(1) review.
    Uses both text features + behavioral features.

    Text features:   same as sentiment (GRU embedding)
    Behavioral:      rating, review_length, has_images, days_since_purchase,
                     user_review_count, review_velocity
    """
    def __init__(self, vocab_size=VOCAB_SIZE, embed_dim=64, hidden_dim=64,
                 behavioral_dim=6, dropout=0.3):
        super().__init__()
        self.embedding    = nn.Embedding(vocab_size, embed_dim, padding_idx=0)
        self.gru          = nn.GRU(embed_dim, hidden_dim, batch_first=True,
                                    bidirectional=True, dropout=dropout)
        self.text_project = nn.Linear(hidden_dim * 2, 32)
        self.behavioral   = nn.Sequential(
            nn.Linear(behavioral_dim, 16), nn.ReLU(), nn.Dropout(dropout),
        )
        self.classifier   = nn.Sequential(
            nn.Linear(32 + 16, 32), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(32, 1), nn.Sigmoid(),
        )

    def forward(self, text_ids, behavior):
        emb = self.embedding(text_ids)
        _, hidden = self.gru(emb)
        h   = torch.cat([hidden[-2], hidden[-1]], dim=1)   # (B, hidden*2)
        t   = torch.relu(self.text_project(h))             # (B, 32)
        b   = self.behavioral(behavior)                    # (B, 16)
        return self.classifier(torch.cat([t, b], dim=1)).squeeze(1)


# ── Training ──────────────────────────────────────────────

# Seed training data: (text, label) where label 0=neg, 1=neutral, 2=pos
SENTIMENT_SEEDS = [
    # Positive
    ("absolutely love this product amazing quality","positive"),
    ("fast delivery exactly as described perfect","positive"),
    ("exceeded my expectations highly recommend","positive"),
    ("great value for money works perfectly","positive"),
    ("brilliant product top notch quality","positive"),
    ("very happy with purchase will buy again","positive"),
    ("outstanding quality fast shipping","positive"),
    ("exactly what I needed great product","positive"),
    # Neutral
    ("its okay nothing special average quality","neutral"),
    ("product works as expected nothing more","neutral"),
    ("decent product for the price","neutral"),
    ("average quality does the job","neutral"),
    ("its fine not bad not great","neutral"),
    ("okay product arrived on time","neutral"),
    # Negative
    ("terrible quality broke after one day","negative"),
    ("very disappointed does not work as advertised","negative"),
    ("waste of money cheap materials","negative"),
    ("horrible product do not buy","negative"),
    ("completely different from description","negative"),
    ("poor quality arrived damaged","negative"),
    ("worst purchase ever not worth it","negative"),
    ("broke immediately terrible quality","negative"),
]


def train_sentiment_model(epochs=60):
    """Train sentiment classifier on seed data + real reviews."""
    import json

    texts, labels = [], []
    label_map = {'negative': 0, 'neutral': 1, 'positive': 2}

    for text, label in SENTIMENT_SEEDS:
        texts.append(text)
        labels.append(label_map[label])

    # Add real reviews from DB
    try:
        from .models import Review
        for r in Review.objects.filter(is_approved=True, sentiment__in=['positive','neutral','negative']):
            texts.append(r.comment[:500])
            labels.append(label_map.get(r.sentiment, 1))
    except Exception:
        pass

    print(f'Training sentiment model on {len(texts)} samples...')
    vocab = _build_vocab(texts)

    # Save vocab
    VOCAB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(VOCAB_PATH, 'w') as f:
        json.dump(vocab, f)

    global _vocab
    _vocab = vocab

    X = torch.stack([_text_to_ids(t, vocab) for t in texts])
    y = torch.tensor(labels, dtype=torch.long)

    model   = SentimentNet(len(vocab))
    opt     = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
    loss_fn = nn.CrossEntropyLoss()
    ds      = torch.utils.data.TensorDataset(X, y)
    loader  = torch.utils.data.DataLoader(ds, batch_size=16, shuffle=True)

    model.train()
    for epoch in range(epochs):
        for xb, yb in loader:
            opt.zero_grad()
            loss_fn(model(xb), yb).backward()
            opt.step()

    SENTIMENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    torch.save({'state': model.state_dict(), 'vocab_size': len(vocab)}, SENTIMENT_PATH)
    model.eval()
    global _sentiment_model
    _sentiment_model = model
    print(f'Sentiment model saved.')
    return model


def train_fake_detector(epochs=50):
    """Train fake review detector on synthetic + real data."""
    np.random.seed(42)
    n     = 500
    # Synthetic real reviews: varied length, not all 5-star
    X_text_real = ["this product is good quality satisfied customer"] * (n // 2)
    X_text_fake = ["best product ever five stars amazing love it buy now"] * (n // 2)

    # Behavioral features: [rating_norm, length_norm, has_image, days_since, user_count_norm, velocity]
    B_real  = np.column_stack([
        np.random.uniform(0.4, 1.0, n//2),   # varied ratings
        np.random.uniform(0.2, 0.8, n//2),   # varied length
        np.random.binomial(1, 0.3, n//2),    # 30% have images
        np.random.uniform(0.1, 1.0, n//2),   # varied purchase gap
        np.random.uniform(0.1, 0.5, n//2),   # moderate review count
        np.random.uniform(0.0, 0.3, n//2),   # low velocity
    ]).astype(np.float32)

    B_fake  = np.column_stack([
        np.ones(n//2) * 1.0,                  # always 5-star
        np.random.uniform(0.05, 0.2, n//2),  # very short
        np.zeros(n//2),                       # no images
        np.random.uniform(0.0, 0.1, n//2),   # reviewed immediately
        np.random.uniform(0.8, 1.0, n//2),   # many reviews
        np.random.uniform(0.7, 1.0, n//2),   # high velocity
    ]).astype(np.float32)

    texts   = X_text_real + X_text_fake
    B_all   = np.vstack([B_real, B_fake])
    y_all   = np.array([0] * (n//2) + [1] * (n//2), dtype=np.float32)

    vocab   = _get_vocab()
    if len(vocab) < 10:
        train_sentiment_model()
        vocab = _get_vocab()

    X_ids   = torch.stack([_text_to_ids(t, vocab) for t in texts])
    B_t     = torch.from_numpy(B_all)
    y_t     = torch.from_numpy(y_all)

    model   = FakeReviewNet(len(vocab))
    opt     = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.BCELoss()
    ds      = torch.utils.data.TensorDataset(X_ids, B_t, y_t)
    loader  = torch.utils.data.DataLoader(ds, batch_size=32, shuffle=True)

    model.train()
    for epoch in range(epochs):
        for xb, bb, yb in loader:
            opt.zero_grad()
            loss_fn(model(xb, bb), yb).backward()
            opt.step()

    torch.save(model.state_dict(), FAKE_DETECT_PATH)
    model.eval()
    global _fake_model
    _fake_model = model
    print(f'Fake review detector saved.')
    return model


# ── Model Loaders ─────────────────────────────────────────

def _get_sentiment_model():
    global _sentiment_model
    if _sentiment_model is not None:
        return _sentiment_model
    if SENTIMENT_PATH.exists():
        ck    = torch.load(SENTIMENT_PATH, map_location='cpu')
        vocab = _get_vocab()
        model = SentimentNet(ck.get('vocab_size', len(vocab)))
        model.load_state_dict(ck['state'])
    else:
        model = train_sentiment_model()
    model.eval()
    _sentiment_model = model
    return model


def _get_fake_model():
    global _fake_model
    if _fake_model is not None:
        return _fake_model
    if FAKE_DETECT_PATH.exists():
        vocab = _get_vocab()
        model = FakeReviewNet(max(len(vocab), 10))
        model.load_state_dict(torch.load(FAKE_DETECT_PATH, map_location='cpu'))
    else:
        model = train_fake_detector()
    model.eval()
    _fake_model = model
    return model


# ── Inference ─────────────────────────────────────────────

LABEL_MAP  = {0: 'negative', 1: 'neutral', 2: 'positive'}
SCORE_MAP  = {'negative': -1.0, 'neutral': 0.0, 'positive': 1.0}


def analyze_sentiment(text):
    """
    Classify sentiment of review text.
    Returns: (sentiment_str, score_float, confidence_float)
    """
    # Rule-based fast path
    text_lower = text.lower()
    pos_words  = ['excellent','amazing','love','perfect','brilliant','outstanding','fantastic']
    neg_words  = ['terrible','awful','horrible','hate','broken','waste','disappointed','poor']

    pos_count = sum(1 for w in pos_words if w in text_lower)
    neg_count = sum(1 for w in neg_words if w in text_lower)

    try:
        model = _get_sentiment_model()
        vocab = _get_vocab()
        ids   = _text_to_ids(text, vocab).unsqueeze(0)

        with torch.no_grad():
            logits = model(ids)
            probs  = torch.softmax(logits, dim=1).squeeze()
            conf, idx = probs.max(0)

        sentiment  = LABEL_MAP[idx.item()]
        confidence = conf.item()

        # Blend rule-based with model
        if pos_count >= 2 and sentiment != 'negative':
            sentiment = 'positive'
        elif neg_count >= 2 and sentiment != 'positive':
            sentiment = 'negative'

        score = SCORE_MAP[sentiment] * confidence
        return sentiment, round(score, 4), round(confidence, 4)

    except Exception:
        # Fallback: keyword-based
        if pos_count > neg_count:
            return 'positive', 0.7, 0.7
        elif neg_count > pos_count:
            return 'negative', -0.7, 0.7
        return 'neutral', 0.0, 0.5


def _extract_behavioral_features(review):
    """Extract 6-dim behavioral features for fake detection."""
    from django.utils import timezone
    now = timezone.now()

    rating_norm   = (review.rating - 1) / 4.0
    length_norm   = min(len(review.comment) / 1000.0, 1.0)
    has_image     = 1.0 if review.images else 0.0

    days_since    = 0.5
    if review.order and review.order.created_at:
        days = (now - review.order.created_at).days
        days_since = min(days / 30.0, 1.0)

    user_reviews  = review.user.reviews.count()
    user_norm     = min(user_reviews / 20.0, 1.0)

    # Velocity: reviews in last 24h by this user
    from datetime import timedelta
    recent = review.user.reviews.filter(created_at__gte=now - timedelta(hours=24)).count()
    velocity_norm = min(recent / 5.0, 1.0)

    return np.array([rating_norm, length_norm, has_image, days_since,
                     user_norm, velocity_norm], dtype=np.float32)


def detect_fake_review(review):
    """
    Estimate probability that a review is fake.
    Returns: (is_fake_bool, probability_float)
    """
    try:
        model    = _get_fake_model()
        vocab    = _get_vocab()
        text_ids = _text_to_ids(review.comment, vocab).unsqueeze(0)
        behavior = torch.from_numpy(_extract_behavioral_features(review)).unsqueeze(0)

        with torch.no_grad():
            prob = model(text_ids, behavior).item()

        is_fake = prob > 0.65
        return is_fake, round(prob, 4)
    except Exception:
        return False, 0.0


def analyze_review(review):
    """
    Full pipeline: sentiment + fake detection for a new review.
    Updates and saves the review object.
    """
    sentiment, score, conf = analyze_sentiment(review.comment)
    is_fake, fake_prob      = detect_fake_review(review)

    review.sentiment        = sentiment
    review.sentiment_score  = score
    review.is_fake_flag     = is_fake
    review.fake_probability = fake_prob
    review.is_approved      = not is_fake    # auto-approve if not fake
    review.is_flagged       = is_fake

    review.save(update_fields=[
        'sentiment','sentiment_score','is_fake_flag',
        'fake_probability','is_approved','is_flagged'
    ])
    update_product_sentiment(review.product)
    return sentiment, score, is_fake


def update_product_sentiment(product):
    """Rebuild sentiment summary for a product after new review."""
    from .models import Review, ProductSentimentSummary

    reviews = Review.objects.filter(product=product, is_approved=True)
    if not reviews.exists():
        return

    counts = {'positive': 0, 'neutral': 0, 'negative': 0}
    scores = []
    pos_phrases, neg_phrases = [], []

    for r in reviews:
        if r.sentiment in counts:
            counts[r.sentiment] += 1
        if r.sentiment_score:
            scores.append(r.sentiment_score)
        if r.sentiment == 'positive' and r.title:
            pos_phrases.append(r.title)
        elif r.sentiment == 'negative' and r.title:
            neg_phrases.append(r.title)

    avg_score = float(np.mean(scores)) if scores else 0.0

    summary, _ = ProductSentimentSummary.objects.get_or_create(product=product)
    summary.positive_count       = counts['positive']
    summary.neutral_count        = counts['neutral']
    summary.negative_count       = counts['negative']
    summary.avg_sentiment_score  = avg_score
    summary.top_positive_phrases = pos_phrases[:5]
    summary.top_negative_phrases = neg_phrases[:5]
    summary.save()

    # Update product rating
    from django.db.models import Avg, Count
    agg = reviews.aggregate(avg=Avg('rating'), cnt=Count('id'))
    from products.models import Product as P
    P.objects.filter(pk=product.pk).update(
        rating_avg=round(agg['avg'] or 0, 2),
        rating_count=agg['cnt']
    )
