"""
ShopAI — Collaborative Filtering Recommender
PyTorch Matrix Factorization with embeddings.

Architecture:
  - User embedding  (n_users  × embedding_dim)
  - Product embedding (n_products × embedding_dim)
  - Dot product → predicted interaction score
  - Trained with MSE loss on weighted interactions

Usage:
  from apps.ai_recommendations.recommender import get_recommendations
  products = get_recommendations(user, top_k=8)
"""
import os
import json
import numpy as np
import torch
import torch.nn as nn
from pathlib import Path
from django.conf import settings

EMBEDDING_DIM = settings.AI_CONFIG.get('RECOMMENDATION_EMBEDDING_DIM', 64)
MODEL_PATH    = Path(settings.AI_CONFIG.get('RECOMMENDATION_MODEL_PATH',
                     settings.BASE_DIR / 'ai_models/recommender.pth'))

# ── Model Definition ──────────────────────────────────────

class RecommenderNet(nn.Module):
    """
    Neural Collaborative Filtering model.
    Learns dense embeddings for users and products.
    """
    def __init__(self, n_users, n_products, embedding_dim=64, dropout=0.2):
        super().__init__()
        self.user_embedding    = nn.Embedding(n_users,    embedding_dim, padding_idx=0)
        self.product_embedding = nn.Embedding(n_products, embedding_dim, padding_idx=0)

        # MLP layers for non-linear interactions
        self.mlp = nn.Sequential(
            nn.Linear(embedding_dim * 2, 128),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, 1),
        )

        # Initialize embeddings
        nn.init.normal_(self.user_embedding.weight,    std=0.01)
        nn.init.normal_(self.product_embedding.weight, std=0.01)

    def forward(self, user_ids, product_ids):
        u = self.user_embedding(user_ids)       # (batch, emb_dim)
        p = self.product_embedding(product_ids) # (batch, emb_dim)

        # Concatenate for MLP path
        concat = torch.cat([u, p], dim=1)       # (batch, emb_dim*2)
        return self.mlp(concat).squeeze(1)       # (batch,)

    def get_user_embedding(self, user_id):
        with torch.no_grad():
            return self.user_embedding(torch.tensor([user_id])).squeeze().numpy()

    def get_product_embedding(self, product_id):
        with torch.no_grad():
            return self.product_embedding(torch.tensor([product_id])).squeeze().numpy()


# ── Training ──────────────────────────────────────────────

def train_recommender(epochs=30, batch_size=512, lr=1e-3, min_interactions=50):
    """
    Train the collaborative filtering model on interaction data.
    Saves model + ID mappings to disk.
    Returns: trained model or None if insufficient data.
    """
    from ai_recommendations.models import UserProductInteraction, RecommenderModel

    print(' Training recommendation model...')

    # Load interaction data
    interactions = list(
        UserProductInteraction.objects.values('user_id', 'product_id', 'weight')
    )
    if len(interactions) < min_interactions:
        print(f'Only {len(interactions)} interactions (need {min_interactions}). Skipping train.')
        return None

    # Build ID maps (0-indexed for embeddings)
    user_ids    = sorted(set(str(i['user_id'])    for i in interactions))
    product_ids = sorted(set(str(i['product_id']) for i in interactions))
    user_map    = {uid: idx+1 for idx, uid in enumerate(user_ids)}    # 0=padding
    product_map = {pid: idx+1 for idx, pid in enumerate(product_ids)}

    n_users    = len(user_ids)    + 1
    n_products = len(product_ids) + 1

    # Build tensors
    u_tensor = torch.tensor([user_map[str(i['user_id'])]    for i in interactions], dtype=torch.long)
    p_tensor = torch.tensor([product_map[str(i['product_id'])] for i in interactions], dtype=torch.long)
    w_tensor = torch.tensor([i['weight'] for i in interactions], dtype=torch.float32)

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model  = RecommenderNet(n_users, n_products, EMBEDDING_DIM).to(device)
    opt    = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    loss_fn= nn.MSELoss()

    dataset = torch.utils.data.TensorDataset(u_tensor, p_tensor, w_tensor)
    loader  = torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=True)

    model.train()
    for epoch in range(epochs):
        total_loss = 0.0
        for u_batch, p_batch, w_batch in loader:
            u_batch = u_batch.to(device)
            p_batch = p_batch.to(device)
            w_batch = w_batch.to(device)
            opt.zero_grad()
            preds = model(u_batch, p_batch)
            loss  = loss_fn(preds, w_batch)
            loss.backward()
            opt.step()
            total_loss += loss.item()
        if (epoch + 1) % 10 == 0:
            avg = total_loss / len(loader)
            print(f'  Epoch {epoch+1}/{epochs} | Loss: {avg:.4f}')

    # Save model + mappings
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    maps_path = MODEL_PATH.parent / 'recommender_maps.json'

    torch.save({
        'model_state':  model.state_dict(),
        'n_users':      n_users,
        'n_products':   n_products,
        'embedding_dim':EMBEDDING_DIM,
    }, MODEL_PATH)

    with open(maps_path, 'w') as f:
        json.dump({'user_map': user_map, 'product_map': product_map,
                   'user_ids': user_ids, 'product_ids': product_ids}, f)

    avg_loss = total_loss / len(loader)
    print(f' Model saved. Final loss: {avg_loss:.4f} | Users: {n_users} | Products: {n_products}')

    # Record in DB
    from django.utils import timezone
    RecommenderModel.objects.filter(is_active=True).update(is_active=False)
    RecommenderModel.objects.create(
        version       = timezone.now().strftime('%Y%m%d_%H%M'),
        model_path    = str(MODEL_PATH),
        n_users       = n_users,
        n_products    = n_products,
        embedding_dim = EMBEDDING_DIM,
        train_loss    = avg_loss,
        is_active     = True,
    )

    # Pre-compute similar products
    _compute_similar_products(model, product_map, product_ids, device)
    return model


def _compute_similar_products(model, product_map, product_ids, device, top_k=10):
    """Pre-compute top-K similar products for each product using embedding cosine similarity."""
    from ai_recommendations.models import SimilarProduct
    from products.models import Product

    print('  Computing product similarities...')
    model.eval()
    with torch.no_grad():
        all_ids  = torch.tensor(list(product_map.values()), dtype=torch.long).to(device)
        embeds   = model.product_embedding(all_ids).cpu().numpy()  # (n_products, emb_dim)

    # Normalize
    norms  = np.linalg.norm(embeds, axis=1, keepdims=True) + 1e-8
    embeds = embeds / norms

    # Cosine similarity matrix
    sim_matrix = embeds @ embeds.T  # (n, n)

    SimilarProduct.objects.all().delete()
    bulk = []
    db_products = {str(p.id): p for p in Product.objects.filter(is_active=True)}

    for i, pid in enumerate(product_ids):
        if pid not in db_products:
            continue
        sims   = sim_matrix[i]
        top_ix = np.argsort(sims)[::-1][1:top_k+1]  # exclude self
        for j in top_ix:
            other_pid = product_ids[j]
            if other_pid in db_products and sims[j] > 0.3:
                bulk.append(SimilarProduct(
                    product=db_products[pid],
                    similar=db_products[other_pid],
                    score=float(sims[j])
                ))

    SimilarProduct.objects.bulk_create(bulk, ignore_conflicts=True)
    print(f' Computed {len(bulk)} product similarity pairs')


# ── Inference ─────────────────────────────────────────────

_cached_model   = None
_cached_maps    = None


def _load_model():
    global _cached_model, _cached_maps
    if _cached_model is not None:
        return _cached_model, _cached_maps

    maps_path = MODEL_PATH.parent / 'recommender_maps.json'
    if not MODEL_PATH.exists() or not maps_path.exists():
        return None, None

    checkpoint = torch.load(MODEL_PATH, map_location='cpu')
    model = RecommenderNet(
        checkpoint['n_users'], checkpoint['n_products'], checkpoint['embedding_dim']
    )
    model.load_state_dict(checkpoint['model_state'])
    model.eval()

    with open(maps_path) as f:
        maps = json.load(f)

    _cached_model, _cached_maps = model, maps
    return model, maps


def get_recommendations(user, top_k=8, exclude_ids=None):
    """
    Get personalized product recommendations for a user.

    Falls back to popularity-based if model not available.
    """
    from products.models import Product

    model, maps = _load_model()

    if model is None or str(user.id) not in maps.get('user_map', {}):
        return _popularity_fallback(user, top_k, exclude_ids)

    user_idx   = maps['user_map'][str(user.id)]
    product_ids= maps['product_ids']

    # Get scores for all products
    u_tensor = torch.tensor([user_idx] * len(product_ids), dtype=torch.long)
    p_tensor = torch.tensor([maps['product_map'][pid] for pid in product_ids], dtype=torch.long)

    with torch.no_grad():
        scores = model(u_tensor, p_tensor).numpy()

    # Sort by score, filter already purchased
    purchased = set(str(pid) for pid in
                    user.orders.filter(payment_status='paid')
                               .values_list('items__product_id', flat=True))
    if exclude_ids:
        purchased.update(str(x) for x in exclude_ids)

    ranked = sorted(zip(product_ids, scores), key=lambda x: x[1], reverse=True)
    top_ids= [pid for pid, _ in ranked if pid not in purchased][:top_k]

    if not top_ids:
        return _popularity_fallback(user, top_k, exclude_ids)

    from django.db.models import Case, When
    qs = Product.objects.filter(id__in=top_ids, is_active=True).prefetch_related('images')
    preserved = Case(*[When(id=pid, then=pos) for pos, pid in enumerate(top_ids)])
    return qs.order_by(preserved)


def get_similar_products(product, top_k=6):
    """Get products similar to a given product using pre-computed embeddings."""
    from ai_recommendations.models import SimilarProduct
    from products.models import Product

    similar_ids = SimilarProduct.objects.filter(product=product)\
                                        .order_by('-score')\
                                        .values_list('similar_id', flat=True)[:top_k]
    if not similar_ids:
        # Fallback: same category
        return Product.objects.filter(
            category=product.category, is_active=True
        ).exclude(pk=product.pk).prefetch_related('images')[:top_k]

    from django.db.models import Case, When
    qs = Product.objects.filter(id__in=similar_ids, is_active=True).prefetch_related('images')
    preserved = Case(*[When(id=pid, then=pos) for pos, pid in enumerate(similar_ids)])
    return qs.order_by(preserved)


def get_frequently_bought_together(product, top_k=4):
    """Find products frequently co-purchased with this product."""
    from orders.models import OrderItem
    from products.models import Product
    from django.db.models import Count

    # Find orders containing this product
    order_ids = OrderItem.objects.filter(product=product).values_list('order_id', flat=True)

    # Find other products in those orders
    co_products = OrderItem.objects.filter(order_id__in=order_ids)\
                                   .exclude(product=product)\
                                   .values('product_id')\
                                   .annotate(freq=Count('product_id'))\
                                   .order_by('-freq')[:top_k]

    ids = [c['product_id'] for c in co_products]
    if not ids:
        return Product.objects.filter(is_active=True).exclude(pk=product.pk)\
                              .order_by('-purchase_count').prefetch_related('images')[:top_k]

    from django.db.models import Case, When
    qs = Product.objects.filter(id__in=ids, is_active=True).prefetch_related('images')
    preserved = Case(*[When(id=pid, then=pos) for pos, pid in enumerate(ids)])
    return qs.order_by(preserved)


def _popularity_fallback(user, top_k, exclude_ids=None):
    """Return popular products when model isn't available."""
    from products.models import Product
    qs = Product.objects.filter(is_active=True).order_by('-purchase_count', '-rating_avg')
    if exclude_ids:
        qs = qs.exclude(id__in=exclude_ids)
    return qs.prefetch_related('images')[:top_k]


def record_interaction(user, product, interaction_type):
    """Helper to record a user-product interaction."""
    from ai_recommendations.models import UserProductInteraction
    if not user.is_authenticated:
        return
    UserProductInteraction.objects.get_or_create(
        user=user, product=product, interaction=interaction_type,
        defaults={'weight': UserProductInteraction.WEIGHTS.get(interaction_type, 1.0)}
    )
