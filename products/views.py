

# Create your views here.
from django.shortcuts import render, get_object_or_404
from django.db.models import Q, Avg, Count
from django.core.paginator import Paginator
from django.http import JsonResponse
from .models import Product, Category, Brand, TeamMember, CompanyValue,Tag, ProductView,FloatingProduct
from django.contrib.auth.decorators import login_required



def _record_view(request, product):
    """Record product view for AI tracking."""
    uid  = str(request.user.id) if request.user.is_authenticated else None
    sess = request.session.session_key or ''
    if not ProductView.objects.filter(
        product=product,
        user_id=uid,
        session_key=sess,
        viewed_at__date=__import__('datetime').date.today()
    ).exists():
        ProductView.objects.create(
            product=product,
            user=request.user if request.user.is_authenticated else None,
            session_key=sess,
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        Product.objects.filter(pk=product.pk).update(view_count=product.view_count + 1)



def home(request):
    # 1. Hero & Shared Data (Visible to EVERYONE)
    categories = Category.objects.filter(is_featured=True, parent=None)
    floating_products = FloatingProduct.objects.filter(is_active=True)
    big_card = floating_products.filter(card_type='big').first()
    small_card = floating_products.filter(card_type='small').first()

    context = {
        'categories': categories,
        'big_card': big_card,
        'small_card': small_card,
    }

    # 2. Product Data (Visible ONLY to LOGGED IN users)
    if request.user.is_authenticated:
        context['featured'] = Product.objects.filter(is_active=True, is_featured=True).prefetch_related('images')[:8]
        context['new_arrivals'] = Product.objects.filter(is_active=True, is_new=True).prefetch_related('images')[:8]
        context['bestsellers'] = Product.objects.filter(is_active=True).order_by('-purchase_count').prefetch_related('images')[:8]
        context['on_sale'] = Product.objects.filter(is_active=True, compare_price__isnull=False).prefetch_related('images')[:4]
    
    return render(request, 'products/home.html', context)





@login_required
def product_list(request):
    products = Product.objects.filter(is_active=True).prefetch_related('images').select_related('category', 'brand')

    # Filters
    cat_slug = request.GET.get('category')
    brand_id = request.GET.get('brand')
    min_p    = request.GET.get('min_price')
    max_p    = request.GET.get('max_price')
    sort     = request.GET.get('sort', '-created_at')
    q        = request.GET.get('q', '').strip()
    on_sale  = request.GET.get('sale')
    in_stock = request.GET.get('in_stock')

    if q:
        products = products.filter(Q(name__icontains=q) | Q(description__icontains=q) | Q(brand__name__icontains=q))
    if cat_slug:
        try:
            cat = Category.objects.get(slug=cat_slug)
            products = products.filter(Q(category=cat) | Q(category__parent=cat))
        except Category.DoesNotExist:
            pass
    if brand_id:
        products = products.filter(brand_id=brand_id)
    if min_p:
        products = products.filter(price__gte=min_p)
    if max_p:
        products = products.filter(price__lte=max_p)
    if on_sale:
        products = products.filter(compare_price__isnull=False)
    if in_stock:
        products = products.filter(stock__gt=0)

    SORT_MAP = {
        '-created_at': '-created_at', 'price': 'price',
        '-price': '-price', '-rating_avg': '-rating_avg',
        '-purchase_count': '-purchase_count',
    }
    products = products.order_by(SORT_MAP.get(sort, '-created_at'))

    paginator = Paginator(products, 24)
    page      = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'products/product_list.html', {
        'page_obj': page, 'products': page,
        'categories': Category.objects.filter(parent=None).annotate(cnt=Count('products')),
        'brands': Brand.objects.annotate(cnt=Count('products')).filter(cnt__gt=0),
        'total_count': paginator.count,
        'current_filters': {'q': q, 'category': cat_slug, 'brand': brand_id,
                            'sort': sort, 'min_price': min_p, 'max_price': max_p},
    })


def product_detail(request, slug):
    product  = get_object_or_404(Product.objects.prefetch_related('images','variants','tags')
                                 .select_related('category','brand'), slug=slug, is_active=True)
    _record_view(request, product)

    related  = Product.objects.filter(category=product.category, is_active=True)\
                              .exclude(pk=product.pk).prefetch_related('images')[:6]
    reviews  = product.reviews.filter(is_approved=True).select_related('user').order_by('-created_at')[:10]

    return render(request, 'products/product_detail.html', {
        'product': product, 'related': related, 'reviews': reviews,
        'images': product.images.all(),
        'variants': product.variants.all(),
        'in_wishlist': request.user.is_authenticated and
                       product.wishlist_items.filter(user=request.user).exists()
                       if hasattr(product, 'wishlist_items') else False,
    })

@login_required
def categories_page(request):
    cats = Category.objects.filter(parent=None).prefetch_related('children').annotate(
        cnt=Count('products', filter=Q(products__is_active=True))
    )
    return render(request, 'products/categories.html', {'categories': cats})


def category_detail(request, slug):
    category = get_object_or_404(Category, slug=slug)
    products = Product.objects.filter(
        Q(category=category) | Q(category__parent=category), is_active=True
    ).prefetch_related('images')
    paginator = Paginator(products, 24)
    page      = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'products/product_list.html', {
        'page_obj': page, 'products': page,
        'current_category': category,
        'total_count': paginator.count,
        'categories': Category.objects.filter(parent=None),
        'brands': Brand.objects.all(),
        'current_filters': {},
    })

@login_required
def deals(request):
    # Initialize variables as None
    page_obj = None
    
    if request.user.is_authenticated:
        # Only query and paginate if the user is logged in
        products_queryset = Product.objects.filter(
            is_active=True, 
            compare_price__isnull=False
        ).prefetch_related('images').order_by('-compare_price')
        
        paginator = Paginator(products_queryset, 24)
        page_obj = paginator.get_page(request.GET.get('page', 1))

    # Pass the variables to the template. 
    # If not authenticated, they will be None, triggering your "Login Wall" in the HTML.
    return render(request, 'products/deals.html', {
        'page_obj': page_obj, 
        'products': page_obj  # Keeping your naming convention for consistency
    })





def new_arrivals(request):
    products = Product.objects.filter(is_active=True, is_new=True)\
                              .prefetch_related('images').order_by('-created_at')
    paginator = Paginator(products, 24)
    page      = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'products/product_list.html', {
        'page_obj': page, 'products': page, 'page_title': 'New Arrivals',
        'total_count': paginator.count, 'categories': Category.objects.filter(parent=None),
        'brands': Brand.objects.all(), 'current_filters': {},
    })


def bestsellers(request):
    products = Product.objects.filter(is_active=True)\
                              .order_by('-purchase_count').prefetch_related('images')
    paginator = Paginator(products, 24)
    page      = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'products/product_list.html', {
        'page_obj': page, 'products': page, 'page_title': 'Best Sellers',
        'total_count': paginator.count, 'categories': Category.objects.filter(parent=None),
        'brands': Brand.objects.all(), 'current_filters': {},
    })


def quick_view(request, slug):
    """AJAX quick view for product modal."""
    product = get_object_or_404(Product, slug=slug, is_active=True)
    return render(request, 'products/partials/quick_view.html', {'product': product})

# views.py
def about_page(request):
    values = CompanyValue.objects.all()
    members = TeamMember.objects.all()
    context = {
        'values': values,
        'members': members
    }
    return render(request, 'about_us.html', context)









