from django.shortcuts import render

# Create your views here.
"""
ShopAI — AI Search Views
"""
import json
from django.shortcuts import render
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.views.decorators.http import require_GET, require_POST
from .semantic_search import search_products, get_suggestions
from .visual_search import visual_search_products
from .models import SearchQuery
from django.contrib.auth.decorators import login_required

def search_results(request):
    """Main AI-powered search results page."""
    query    = request.GET.get('q', '').strip()
    filters  = {
        'category':  request.GET.get('category'),
        'min_price': request.GET.get('min_price'),
        'max_price': request.GET.get('max_price'),
        'in_stock':  request.GET.get('in_stock'),
        'on_sale':   request.GET.get('on_sale'),
    }

    products     = []
    result_count = 0

    if query:
        qs           = search_products(query, top_k=48, filters=filters)
        result_count = qs.count() if hasattr(qs, 'count') else len(qs)
        paginator    = Paginator(qs, 24)
        products     = paginator.get_page(request.GET.get('page', 1))

        # Log the search
        _log_search(request, query, 'semantic', result_count)

    from products.models import Category, Brand
    return render(request, 'ai_search/search_results.html', {
        'query':        query,
        'products':     products,
        'result_count': result_count,
        'filters':      filters,
        'categories':   Category.objects.filter(parent=None),
        'brands':       Brand.objects.all(),
        'page_obj':     products,
    })


@require_GET
def search_suggest(request):
    """AJAX endpoint for search autocomplete."""
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'suggestions': []})
    suggestions = get_suggestions(query)
    return JsonResponse({'suggestions': suggestions, 'query': query})

@login_required
def visual_search_page(request):
    """Visual search — upload an image to find similar products."""
    results = []
    error   = None

    if request.method == 'POST' and request.FILES.get('image'):
        img_file = request.FILES['image']
        try:
            image_bytes = img_file.read()
            qs = visual_search_products(image_bytes, top_k=20)
            results = list(qs)
            _log_search(request, f'[visual:{img_file.name}]', 'visual', len(results))
        except Exception as e:
            error = f'Could not process image: {str(e)}'

    return render(request, 'ai_search/visual_search.html', {
        'results': results, 'error': error,
    })


@require_POST
def visual_search_api(request):
    """AJAX visual search endpoint."""
    if not request.FILES.get('image'):
        return JsonResponse({'success': False, 'error': 'No image uploaded.'})
    try:
        image_bytes = request.FILES['image'].read()
        qs          = visual_search_products(image_bytes, top_k=12)
        data = [{
            'id':       str(p.id),
            'name':     p.name,
            'price':    float(p.effective_price),
            'url':      p.get_absolute_url(),
            'image':    p.primary_image.image.url if p.primary_image else '',
            'category': p.category.name if p.category else '',
        } for p in qs]
        return JsonResponse({'success': True, 'results': data})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@require_GET
def search_history(request):
    """Return user's recent search history."""
    if not request.user.is_authenticated:
        return JsonResponse({'history': []})
    history = request.user.searches.values_list('query', flat=True)\
                          .order_by('-searched_at').distinct()[:10]
    return JsonResponse({'history': list(history)})


def _log_search(request, query, search_type, result_count):
    """Async-safe search logging."""
    try:
        SearchQuery.objects.create(
            user         = request.user if request.user.is_authenticated else None,
            session_key  = request.session.session_key or '',
            query        = query[:500],
            search_type  = search_type,
            results_count= result_count,
            ip_address   = request.META.get('REMOTE_ADDR'),
        )
    except Exception:
        pass
