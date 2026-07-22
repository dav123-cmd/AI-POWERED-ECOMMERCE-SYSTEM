"""
ShopAI — Semantic Search Engine
Uses Sentence Transformers + FAISS for AI-powered product search.

Architecture:
  1. Encode product names/descriptions into 384-dim vectors
  2. Store in FAISS flat index on disk
  3. At query time: encode query → cosine similarity search → return ranked products
"""
import os
import json
import numpy as np
import faiss
from pathlib import Path
from django.conf import settings

# Lazy-load the model to avoid startup delay
_model = None
_index = None
_product_ids = []


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        model_name = settings.AI_CONFIG.get('SEARCH_MODEL_NAME', 'all-MiniLM-L6-v2')
        _model = SentenceTransformer(model_name)
    return _model


def _get_index_path(index_type='text'):
    base = Path(settings.AI_CONFIG.get('FAISS_INDEX_PATH', settings.BASE_DIR / 'ai_models/faiss_index.bin'))
    return base.parent / f'faiss_{index_type}.bin'


def _get_ids_path(index_type='text'):
    base = _get_index_path(index_type)
    return base.parent / f'faiss_{index_type}_ids.json'


# ── Index Building ────────────────────────────────────────

def build_text_index(force=False):
    """
    Build FAISS index from all active products.
    Run this via management command or Celery task.
    Returns: (index, product_ids list)
    """
    from products.models import Product

    index_path = _get_index_path('text')
    ids_path   = _get_ids_path('text')

    if index_path.exists() and not force:
        return load_text_index()

    print('Building FAISS text index...')
    products = Product.objects.filter(is_active=True).values('id', 'name', 'description', 'short_desc')

    if not products:
        print('No products found.')
        return None, []

    model    = _get_model()
    texts    = []
    prod_ids = []

    for p in products:
        text = f"{p['name']} {p['short_desc'] or ''} {p['description'][:200]}"
        texts.append(text.strip())
        prod_ids.append(str(p['id']))

    print(f'  Encoding {len(texts)} products...')
    embeddings = model.encode(texts, batch_size=32, show_progress_bar=True,
                               convert_to_numpy=True, normalize_embeddings=True)

    # FAISS IndexFlatIP = cosine similarity (with normalized vectors)
    dimension = embeddings.shape[1]
    index     = faiss.IndexFlatIP(dimension)
    index.add(embeddings.astype(np.float32))

    # Save
    index_path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_path))
    with open(ids_path, 'w') as f:
        json.dump(prod_ids, f)

    print(f'FAISS index built: {len(prod_ids)} products, dim={dimension}')

    # Update DB record
    try:
        from ai_search.models import FAISSIndex
        FAISSIndex.objects.filter(index_type='text', is_active=True).update(is_active=False)
        FAISSIndex.objects.create(
            index_type='text', product_count=len(prod_ids),
            index_path=str(index_path), is_active=True
        )
    except Exception:
        pass

    global _index, _product_ids
    _index, _product_ids = index, prod_ids
    return index, prod_ids


def load_text_index():
    """Load FAISS index from disk into memory."""
    global _index, _product_ids
    index_path = _get_index_path('text')
    ids_path   = _get_ids_path('text')

    if not index_path.exists():
        return None, []

    _index = faiss.read_index(str(index_path))
    with open(ids_path) as f:
        _product_ids = json.load(f)
    return _index, _product_ids


# ── Search ────────────────────────────────────────────────

def semantic_search(query, top_k=20, threshold=0.3):
    """
    Perform semantic search over product catalog.

    Args:
        query:     Natural language search string
        top_k:     Number of results to return
        threshold: Minimum cosine similarity score (0-1)

    Returns:
        List of (product_id, score) tuples, sorted by relevance
    """
    global _index, _product_ids

    if _index is None:
        _index, _product_ids = load_text_index()
    if _index is None or not _product_ids:
        return []

    model          = _get_model()
    query_vector   = model.encode([query], normalize_embeddings=True, convert_to_numpy=True)
    query_vector   = query_vector.astype(np.float32)

    k      = min(top_k, _index.ntotal)
    scores, indices = _index.search(query_vector, k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or score < threshold:
            continue
        product_id = _product_ids[idx]
        results.append((product_id, float(score)))

    return results  # Already sorted by FAISS (highest score first)


def search_products(query, top_k=24, filters=None):
    """
    Full search pipeline: semantic search → fetch products → apply filters.

    Args:
        query:   Search string
        top_k:   Max results
        filters: dict with optional keys: category, min_price, max_price, in_stock

    Returns:
        QuerySet of Product objects ordered by AI relevance
    """
    from products.models import Product
    from django.db.models import Case, When, FloatField

    if not query or len(query.strip()) < 2:
        return Product.objects.none()

    results    = semantic_search(query, top_k=top_k * 2)
    if not results:
        # Fallback to keyword search
        qs = Product.objects.filter(is_active=True, name__icontains=query)
        return apply_filters(qs, filters)[:top_k]

    product_ids = [pid for pid, _ in results]
    score_map   = {pid: score for pid, score in results}

    qs = Product.objects.filter(id__in=product_ids, is_active=True)\
                        .prefetch_related('images').select_related('category', 'brand')
    qs = apply_filters(qs, filters)

    # Preserve AI ranking order
    preserved = Case(*[When(id=pid, then=pos) for pos, pid in enumerate(product_ids)])
    qs        = qs.order_by(preserved)

    return qs[:top_k]


def apply_filters(qs, filters):
    if not filters:
        return qs
    if filters.get('category'):
        qs = qs.filter(category__slug=filters['category'])
    if filters.get('min_price'):
        qs = qs.filter(price__gte=filters['min_price'])
    if filters.get('max_price'):
        qs = qs.filter(price__lte=filters['max_price'])
    if filters.get('in_stock'):
        qs = qs.filter(stock__gt=0)
    if filters.get('on_sale'):
        qs = qs.filter(compare_price__isnull=False)
    return qs


# ── Autocomplete / Suggestions ────────────────────────────

def get_suggestions(query, limit=8):
    """
    Return search suggestions combining:
    - Recent popular searches
    - Product name matches
    - Category matches
    """
    from products.models import Product, Category
    from ai_search.models import SearchQuery

    suggestions = []

    # Recent popular queries
    popular = SearchQuery.objects.filter(
        query__istartswith=query, results_count__gt=0
    ).values_list('query', flat=True).order_by('-searched_at').distinct()[:3]

    for q in popular:
        suggestions.append({'type': 'popular', 'label': q, 'query': q, 'icon': 'F'})

    # Product name matches
    products = Product.objects.filter(
        name__icontains=query, is_active=True
    ).values('name', 'id')[:4]

    for p in products:
        suggestions.append({'type': 'product', 'label': p['name'], 'query': p['name'], 'icon': 'P'})

    # Category matches
    cats = Category.objects.filter(name__icontains=query)[:2]
    for c in cats:
        suggestions.append({'type': 'category', 'label': f'{c.name} (category)', 'query': c.name, 'icon': 'F'})

    return suggestions[:limit]
