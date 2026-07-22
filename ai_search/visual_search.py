"""
ShopAI — Visual Search Engine
Uses ResNet50 (PyTorch) to extract image features,
then FAISS for similarity search.

Pipeline:
  1. Load all product images → extract CNN features (2048-dim)
  2. Store in FAISS index
  3. Query: upload image → extract features → find similar products
"""
import io
import os
import json
import numpy as np
import faiss
import torch
import torch.nn as nn
import torchvision.transforms as transforms
import torchvision.models as models
from PIL import Image
from pathlib import Path
from django.conf import settings

# Lazy-load to avoid startup cost
_visual_model = None
_visual_index = None
_visual_ids   = []

TRANSFORM = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                         std =[0.229, 0.224, 0.225]),
])


def _get_visual_model():
    """Load ResNet50 feature extractor (removes final FC layer)."""
    global _visual_model
    if _visual_model is None:
        resnet = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V1)
        # Remove the classification head — keep feature extractor
        _visual_model = nn.Sequential(*list(resnet.children())[:-1])
        _visual_model.eval()
        if torch.cuda.is_available():
            _visual_model = _visual_model.cuda()
    return _visual_model


def extract_features(image_input):
    """
    Extract 2048-dim feature vector from an image.

    Args:
        image_input: PIL Image, file path string, or bytes

    Returns:
        numpy array of shape (2048,)
    """
    model = _get_visual_model()

    if isinstance(image_input, (str, Path)):
        img = Image.open(image_input).convert('RGB')
    elif isinstance(image_input, bytes):
        img = Image.open(io.BytesIO(image_input)).convert('RGB')
    elif isinstance(image_input, Image.Image):
        img = image_input.convert('RGB')
    else:
        raise ValueError('Unsupported image input type')

    tensor = TRANSFORM(img).unsqueeze(0)  # (1, 3, 224, 224)
    if torch.cuda.is_available():
        tensor = tensor.cuda()

    with torch.no_grad():
        features = model(tensor)           # (1, 2048, 1, 1)
        features = features.squeeze()      # (2048,)
        # L2 normalize for cosine similarity
        features = features / (features.norm() + 1e-8)

    return features.cpu().numpy()


def _get_visual_index_path():
    base = Path(settings.AI_MODELS_DIR)
    return base / 'faiss_visual.bin', base / 'faiss_visual_ids.json'


def build_visual_index(force=False):
    """
    Build FAISS visual index from all product images.
    This is resource-intensive — run as Celery task.
    """
    index_path, ids_path = _get_visual_index_path()

    if index_path.exists() and not force:
        return load_visual_index()

    from products.models import ProductImage

    print('   Building FAISS visual index...')
    images   = ProductImage.objects.filter(
        product__is_active=True, is_primary=True
    ).select_related('product')

    vectors  = []
    prod_ids = []

    for img_obj in images:
        try:
            path = img_obj.image.path
            feat = extract_features(path)
            vectors.append(feat)
            prod_ids.append(str(img_obj.product.id))
        except Exception as e:
            print(f'     Skipping {img_obj.id}: {e}')

    if not vectors:
        print('No images processed.')
        return None, []

    matrix    = np.array(vectors, dtype=np.float32)
    dimension = matrix.shape[1]
    index     = faiss.IndexFlatIP(dimension)
    index.add(matrix)

    index_path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_path))
    with open(ids_path, 'w') as f:
        json.dump(prod_ids, f)

    print(f'   Visual index built: {len(prod_ids)} images, dim={dimension}')

    try:
        from ai_search.models import FAISSIndex
        FAISSIndex.objects.filter(index_type='visual', is_active=True).update(is_active=False)
        FAISSIndex.objects.create(
            index_type='visual', product_count=len(prod_ids),
            index_path=str(index_path), is_active=True
        )
    except Exception:
        pass

    global _visual_index, _visual_ids
    _visual_index, _visual_ids = index, prod_ids
    return index, prod_ids


def load_visual_index():
    global _visual_index, _visual_ids
    index_path, ids_path = _get_visual_index_path()
    if not index_path.exists():
        return None, []
    _visual_index = faiss.read_index(str(index_path))
    with open(ids_path) as f:
        _visual_ids = json.load(f)
    return _visual_index, _visual_ids


def visual_search(image_input, top_k=12, threshold=0.5):
    """
    Find products visually similar to the uploaded image.

    Returns:
        List of (product_id, similarity_score) tuples
    """
    global _visual_index, _visual_ids

    if _visual_index is None:
        _visual_index, _visual_ids = load_visual_index()
    if _visual_index is None or not _visual_ids:
        return []

    query_vec = extract_features(image_input).reshape(1, -1).astype(np.float32)
    k         = min(top_k, _visual_index.ntotal)
    scores, indices = _visual_index.search(query_vec, k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or score < threshold:
            continue
        results.append((_visual_ids[idx], float(score)))
    return results


def visual_search_products(image_input, top_k=12):
    """Full pipeline: image → similar products QuerySet."""
    from products.models import Product
    from django.db.models import Case, When

    results = visual_search(image_input, top_k=top_k)
    if not results:
        return Product.objects.none()

    product_ids = [pid for pid, _ in results]
    qs = Product.objects.filter(id__in=product_ids, is_active=True)\
                        .prefetch_related('images').select_related('category')
    preserved = Case(*[When(id=pid, then=pos) for pos, pid in enumerate(product_ids)])
    return qs.order_by(preserved)
