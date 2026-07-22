"""
ShopAI — PyTorch Intent Classifier
Classifies user messages into intents before routing to Claude API.

Intents:
  order_status    — "where is my order", "track order #123"
  product_search  — "find red shoes", "show me laptops under 50k"
  recommendation  — "what should I buy", "suggest something for my wife"
  price_query     — "how much is the iPhone", "price of Nike shoes"
  cart_help       — "add to cart", "remove item", "clear cart"
  return_refund   — "return policy", "how to get refund"
  shipping_info   — "delivery time", "shipping to Nairobi"
  greeting        — "hi", "hello", "hey ARIA"
  farewell        — "bye", "thanks", "goodbye"
  general         — everything else → route to Claude
"""
import os
import json
import torch
import torch.nn as nn
import numpy as np
from pathlib import Path
from django.conf import settings

# ── Intent Definitions ────────────────────────────────────

INTENTS = [
    'order_status', 'product_search', 'recommendation',
    'price_query',  'cart_help',      'return_refund',
    'shipping_info','greeting',       'farewell',       'general',
]

INTENT_IDX = {intent: i for i, intent in enumerate(INTENTS)}
IDX_INTENT = {i: intent for intent, i in INTENT_IDX.items()}

# Training seed phrases for each intent
SEED_DATA = {
    'greeting':      ['hi','hello','hey','good morning','good evening','hey aria','what\'s up'],
    'farewell':      ['bye','goodbye','thanks','thank you','see you','that\'s all','done'],
    'order_status':  ['where is my order','track my order','order status','when will it arrive',
                      'my package','delivery update','order number','has it shipped'],
    'product_search':['find','search for','show me','looking for','do you have',
                      'I need','I want','where can I find'],
    'recommendation':['recommend','suggest','what should I buy','best product','what do you think',
                      'help me choose','advice','opinion','top picks'],
    'price_query':   ['how much','price','cost','expensive','cheap','discount','offer','deal'],
    'cart_help':     ['add to cart','remove from cart','clear cart','my cart','cart total',
                      'update quantity','checkout'],
    'return_refund': ['return','refund','exchange','damaged','wrong item','send back','money back'],
    'shipping_info': ['shipping','delivery','how long','when will','free shipping','fast delivery',
                      'nairobi','kenya','deliver to'],
    'general':       ['help','support','contact','what can you do','how does this work'],
}


# ── Model Architecture ────────────────────────────────────

class IntentClassifier(nn.Module):
    """
    Lightweight LSTM-based intent classifier.
    Input: tokenized text (char-level for simplicity)
    Output: intent probability distribution
    """
    def __init__(self, vocab_size=128, embed_dim=64, hidden_dim=128, num_intents=10, dropout=0.3):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embed_dim, padding_idx=0)
        self.lstm      = nn.LSTM(embed_dim, hidden_dim, batch_first=True,
                                  num_layers=2, dropout=dropout, bidirectional=True)
        self.dropout   = nn.Dropout(dropout)
        self.fc        = nn.Linear(hidden_dim * 2, num_intents)

    def forward(self, x):
        emb = self.embedding(x)                          # (B, T, embed_dim)
        out, (hidden, _) = self.lstm(emb)                # hidden: (2*2, B, hidden)
        # Concat last fwd + last bwd
        hidden = torch.cat([hidden[-2], hidden[-1]], dim=1)  # (B, hidden*2)
        return self.fc(self.dropout(hidden))              # (B, num_intents)


MODEL_PATH = Path(settings.AI_MODELS_DIR) / 'intent_classifier.pth'
_clf_model = None
_clf_trained = False


def _text_to_tensor(text, max_len=64):
    """Convert text to char-level tensor (ASCII codes)."""
    text   = text.lower().strip()[:max_len]
    codes  = [min(ord(c), 127) for c in text]
    # Pad or truncate
    codes  = codes + [0] * (max_len - len(codes))
    return torch.tensor([codes], dtype=torch.long)


def _get_model():
    global _clf_model, _clf_trained
    if _clf_model is not None:
        return _clf_model, _clf_trained

    model = IntentClassifier(vocab_size=128, num_intents=len(INTENTS))
    if MODEL_PATH.exists():
        try:
            state = torch.load(MODEL_PATH, map_location='cpu')
            model.load_state_dict(state)
            _clf_trained = True
        except Exception:
            _clf_trained = False
    model.eval()
    _clf_model = model
    return model, _clf_trained


# ── Training ──────────────────────────────────────────────

def train_classifier(epochs=60, lr=1e-3):
    """
    Train the intent classifier on seed data + any DB-stored labels.
    Fast training — runs in seconds on CPU.
    """
    # Build dataset
    texts, labels = [], []
    for intent, phrases in SEED_DATA.items():
        for phrase in phrases:
            texts.append(phrase)
            labels.append(INTENT_IDX[intent])

    # Add DB training data if available
    try:
        from .models import IntentLabel
        for row in IntentLabel.objects.all():
            if row.intent in INTENT_IDX:
                texts.append(row.text)
                labels.append(INTENT_IDX[row.intent])
    except Exception:
        pass

    if len(texts) < 10:
        return None

    # Tensorize
    max_len = 64
    X = torch.stack([_text_to_tensor(t, max_len).squeeze(0) for t in texts])
    y = torch.tensor(labels, dtype=torch.long)

    model   = IntentClassifier(vocab_size=128, num_intents=len(INTENTS))
    opt     = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.CrossEntropyLoss()
    ds      = torch.utils.data.TensorDataset(X, y)
    loader  = torch.utils.data.DataLoader(ds, batch_size=32, shuffle=True)

    model.train()
    for epoch in range(epochs):
        for xb, yb in loader:
            opt.zero_grad()
            loss = loss_fn(model(xb), yb)
            loss.backward()
            opt.step()

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), MODEL_PATH)

    global _clf_model, _clf_trained
    _clf_model, _clf_trained = model, True
    model.eval()
    print(f'Intent classifier trained on {len(texts)} samples')
    return model


# ── Inference ─────────────────────────────────────────────

def classify_intent(text, confidence_threshold=0.5):
    """
    Classify the intent of a user message.

    Returns: (intent_str, confidence_float)
    """
    # Rule-based pre-filter for speed
    text_lower = text.lower().strip()

    # Direct keyword rules (fast path)
    RULES = [
        (['hi','hello','hey','good morning','good evening'], 'greeting'),
        (['bye','goodbye','thank you','thanks','done'],       'farewell'),
        (['track','order #','order status','where is my order','my package'], 'order_status'),
        (['refund','return','exchange','damaged','wrong item'],               'return_refund'),
        (['shipping','delivery','when will it arrive','free shipping'],       'shipping_info'),
        (['how much','price of','cost of','is it expensive'],                'price_query'),
        (['my cart','add to cart','remove from cart'],                       'cart_help'),
        (['recommend','suggest','what should i','best product'],             'recommendation'),
    ]
    for keywords, intent in RULES:
        if any(kw in text_lower for kw in keywords):
            return intent, 0.95

    # Neural classification
    model, trained = _get_model()
    if not trained:
        return 'general', 0.5

    with torch.no_grad():
        tensor = _text_to_tensor(text)
        logits = model(tensor)
        probs  = torch.softmax(logits, dim=1).squeeze()
        conf, idx = probs.max(0)
        intent = IDX_INTENT[idx.item()]
        conf   = conf.item()

    if conf < confidence_threshold:
        return 'general', conf
    return intent, conf
