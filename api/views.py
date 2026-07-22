"""
ShopAI — REST API Views
A second, JSON-only front door onto the exact same backend the web app
uses: cart_utils for the cart, sentiment_engine for reviews, the ARIA
engine for chat, and the semantic/visual search + recommender modules
for AI. Nothing here re-implements business logic — it wraps it.
"""
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, viewsets, status, mixins
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes

from products.models import Category, Product
from orders.models import Cart, CartItem, Order, OrderItem, OrderStatusHistory
from orders.cart_utils import get_or_create_cart
from reviews.models import Review
from wishlist.models import WishlistItem
from notifications.models import Notification
from Users.models import Address

from .serializers import (
    RegisterSerializer, UserSerializer, UserUpdateSerializer, AddressSerializer,
    CategorySerializer, ProductListSerializer, ProductDetailSerializer,
    CartSerializer, CartAddSerializer, CartUpdateSerializer,
    OrderSerializer, CheckoutSerializer,
    ReviewSerializer, ReviewCreateSerializer,
    WishlistItemSerializer, NotificationSerializer,
    SemanticSearchQuerySerializer, ChatMessageSerializer, ChatReplySerializer,
    HealthCheckSerializer, SearchResponseSerializer, VisualSearchResponseSerializer,
    RecommendationsResponseSerializer, WishlistToggleSerializer, WishlistToggleRequestSerializer,
    SimpleSuccessSerializer,
)
from .permissions import IsOwner
from .pagination import StandardResultsPagination
from .throttles import AIUserThrottle, AIAnonThrottle

User = get_user_model()


# ── Health ────────────────────────────────────────────────

class HealthCheckView(APIView):
    """Lightweight liveness probe — no auth, no DB hit."""
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(responses=HealthCheckSerializer, summary='Liveness probe')
    def get(self, request):
        return Response({'status': 'ok', 'service': 'ShopAI API', 'version': 'v1'})


# ── Auth ──────────────────────────────────────────────────

class RegisterView(generics.CreateAPIView):
    """Creates a user and immediately returns a JWT pair, mirroring web signup."""
    queryset           = User.objects.all()
    serializer_class   = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            'user':    UserSerializer(user, context={'request': request}).data,
            'access':  str(refresh.access_token),
            'refresh': str(refresh),
        }, status=status.HTTP_201_CREATED)


class ProfileView(generics.RetrieveUpdateAPIView):
    """GET/PATCH the authenticated user's own profile."""
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        return UserUpdateSerializer if self.request.method in ('PUT', 'PATCH') else UserSerializer

    def update(self, request, *args, **kwargs):
        super().update(request, *args, **kwargs)
        return Response(UserSerializer(request.user, context={'request': request}).data)


class AddressViewSet(viewsets.ModelViewSet):
    """CRUD for the authenticated user's saved addresses."""
    serializer_class   = AddressSerializer
    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Address.objects.none()
        return Address.objects.filter(user=self.request.user)


# ── Products / Categories ────────────────────────────────

class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset           = Category.objects.all()
    serializer_class   = CategorySerializer
    permission_classes = [AllowAny]
    lookup_field        = 'slug'
    pagination_class    = None


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Filterable, paginated product catalogue.
    Query params: ?category=<slug>&brand=<id>&min_price=&max_price=
                  &on_sale=1&in_stock=1&search=&ordering=
    """
    permission_classes = [AllowAny]
    pagination_class    = StandardResultsPagination
    lookup_field         = 'slug'

    def get_serializer_class(self):
        return ProductDetailSerializer if self.action == 'retrieve' else ProductListSerializer

    def get_queryset(self):
        qs = Product.objects.filter(is_active=True).select_related('category', 'brand')\
                            .prefetch_related('images', 'variants', 'tags')
        p = self.request.query_params

        if p.get('search'):
            qs = qs.filter(Q(name__icontains=p['search']) | Q(description__icontains=p['search']))
        if p.get('category'):
            qs = qs.filter(category__slug=p['category'])
        if p.get('brand'):
            qs = qs.filter(brand_id=p['brand'])
        if p.get('min_price'):
            qs = qs.filter(price__gte=p['min_price'])
        if p.get('max_price'):
            qs = qs.filter(price__lte=p['max_price'])
        if p.get('on_sale') == '1':
            qs = qs.filter(compare_price__isnull=False)
        if p.get('in_stock') == '1':
            qs = qs.filter(stock__gt=0)

        ordering = p.get('ordering', '-created_at')
        ALLOWED = {'-created_at', 'created_at', 'price', '-price', '-rating_avg', '-purchase_count'}
        qs = qs.order_by(ordering if ordering in ALLOWED else '-created_at')
        return qs

    @action(detail=True, methods=['get'])
    def similar(self, request, slug=None):
        """AI-recommended products similar to this one (embedding cosine similarity)."""
        from ai_recommendations.recommender import get_similar_products
        product  = self.get_object()
        similar  = get_similar_products(product, top_k=6)
        data     = ProductListSerializer(similar, many=True, context={'request': request}).data
        return Response(data)

    @action(detail=True, methods=['get'], url_path='bought-together')
    def bought_together(self, request, slug=None):
        from ai_recommendations.recommender import get_frequently_bought_together
        product = self.get_object()
        items   = get_frequently_bought_together(product, top_k=4)
        data    = ProductListSerializer(items, many=True, context={'request': request}).data
        return Response(data)

    @extend_schema(responses=ReviewSerializer(many=True), summary="A product's approved reviews")
    @action(detail=True, methods=['get'])
    def reviews(self, request, slug=None):
        product = self.get_object()
        qs      = product.reviews.filter(is_approved=True).select_related('user').order_by('-created_at')
        page    = self.paginate_queryset(qs)
        data    = ReviewSerializer(page, many=True, context={'request': request}).data
        return self.get_paginated_response(data)


# ── Cart ──────────────────────────────────────────────────

class CartView(APIView):
    """GET the current user/session cart."""
    permission_classes = [AllowAny]

    @extend_schema(responses=CartSerializer, summary='Get current cart')
    def get(self, request):
        cart = get_or_create_cart(request)
        return Response(CartSerializer(cart, context={'request': request}).data)


class CartAddView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=CartAddSerializer, responses=CartSerializer, summary='Add item to cart')
    def post(self, request):
        serializer = CartAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        product = get_object_or_404(Product, id=d['product_id'], is_active=True)
        if not product.is_in_stock:
            return Response({'error': 'Product is out of stock.'}, status=status.HTTP_400_BAD_REQUEST)

        variant = None
        if d.get('variant_id'):
            variant = get_object_or_404(product.variants, id=d['variant_id'])

        cart = get_or_create_cart(request)
        item, created = CartItem.objects.get_or_create(
            cart=cart, product=product, variant=variant, defaults={'quantity': d['quantity']}
        )
        if not created:
            item.quantity = min(item.quantity + d['quantity'], product.stock or 99)
            item.save()

        return Response(CartSerializer(cart, context={'request': request}).data)


class CartUpdateView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=CartUpdateSerializer, responses=CartSerializer, summary='Update cart item quantity')
    def post(self, request):
        serializer = CartUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        cart = get_or_create_cart(request)
        item = get_object_or_404(CartItem, id=d['item_id'], cart=cart)

        if d['quantity'] <= 0:
            item.delete()
        else:
            item.quantity = d['quantity']
            item.save()

        return Response(CartSerializer(cart, context={'request': request}).data)


class CartRemoveView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=CartSerializer, summary='Remove an item from the cart')
    def delete(self, request, item_id):
        cart = get_or_create_cart(request)
        item = get_object_or_404(CartItem, id=item_id, cart=cart)
        item.delete()
        return Response(CartSerializer(cart, context={'request': request}).data)


# ── Orders / Checkout ─────────────────────────────────────

class OrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                    mixins.CreateModelMixin, viewsets.GenericViewSet):
    """List/retrieve the authenticated user's own orders; create = checkout from cart."""
    serializer_class    = OrderSerializer
    permission_classes  = [IsAuthenticated]
    pagination_class     = StandardResultsPagination
    lookup_field          = 'order_number'

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Order.objects.none()
        return Order.objects.filter(user=self.request.user)\
                            .prefetch_related('items').order_by('-created_at')

    def create(self, request, *args, **kwargs):
        cart = get_or_create_cart(request)
        if not cart.items.exists():
            return Response({'error': 'Your cart is empty.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        shipping_fee = 0 if cart.total >= 2000 else 200
        tax_amount   = cart.total * 0.16
        grand_total  = cart.total + shipping_fee + tax_amount

        order = Order.objects.create(
            user=request.user, email=d['email'], phone=d.get('phone', ''),
            shipping_name=d['shipping_name'], shipping_line1=d['shipping_line1'],
            shipping_line2=d.get('shipping_line2', ''), shipping_city=d['shipping_city'],
            shipping_state=d['shipping_state'], shipping_country=d['shipping_country'],
            shipping_postal=d.get('shipping_postal', ''),
            subtotal=cart.subtotal, discount_amount=cart.discount_amount,
            shipping_fee=shipping_fee, tax_amount=tax_amount, total=grand_total,
            coupon_code=cart.coupon.code if cart.coupon else '',
            notes=d.get('notes', ''), payment_method=d['payment_method'],
        )
        for item in cart.items.select_related('product', 'variant'):
            OrderItem.objects.create(
                order=order, product=item.product, product_name=item.product.name,
                variant_info=f'{item.variant.name}: {item.variant.value}' if item.variant else '',
                sku=item.product.sku, quantity=item.quantity,
                unit_price=item.unit_price, total_price=item.line_total,
            )
            Product.objects.filter(pk=item.product.pk).update(
                stock=max(item.product.stock - item.quantity, 0),
                purchase_count=item.product.purchase_count + item.quantity,
            )
        OrderStatusHistory.objects.create(order=order, status='pending', note='Order placed via API')
        cart.items.all().delete()
        cart.coupon = None
        cart.save()

        try:
            from notifications.services import notify_order_placed
            notify_order_placed(order)
        except Exception:
            pass

        return Response(OrderSerializer(order, context={'request': request}).data,
                         status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def cancel(self, request, order_number=None):
        order = self.get_object()
        if not order.is_cancellable:
            return Response({'error': 'This order can no longer be cancelled.'},
                             status=status.HTTP_400_BAD_REQUEST)
        order.status = 'cancelled'
        order.save()
        OrderStatusHistory.objects.create(
            order=order, status='cancelled', note='Cancelled via API', changed_by=request.user
        )
        try:
            from notifications.services import notify_order_status_changed
            notify_order_status_changed(order)
        except Exception:
            pass
        return Response(OrderSerializer(order, context={'request': request}).data)


# ── Reviews ───────────────────────────────────────────────

class ReviewViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """?product=<uuid> filters by product. Creating runs full AI sentiment + fake-review analysis."""
    permission_classes = [IsAuthenticatedOrReadOnly]
    pagination_class    = StandardResultsPagination

    def get_queryset(self):
        qs = Review.objects.filter(is_approved=True).select_related('user', 'product')
        product_id = self.request.query_params.get('product')
        if product_id:
            qs = qs.filter(product_id=product_id)
        return qs.order_by('-created_at')

    def get_serializer_class(self):
        return ReviewCreateSerializer if self.action == 'create' else ReviewSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        review = serializer.save()

        from reviews.sentiment_engine import analyze_review
        sentiment, score, is_fake = analyze_review(review)

        return Response({
            **ReviewSerializer(review, context={'request': request}).data,
            'ai_message': 'Review published!' if review.is_approved else
                          'Review submitted — pending moderation.',
        }, status=status.HTTP_201_CREATED)


# ── Wishlist ──────────────────────────────────────────────

class WishlistViewSet(mixins.ListModelMixin, mixins.CreateModelMixin,
                       mixins.DestroyModelMixin, viewsets.GenericViewSet):
    serializer_class   = WishlistItemSerializer
    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return WishlistItem.objects.none()
        return WishlistItem.objects.filter(user=self.request.user)\
                                   .select_related('product').order_by('-added_at')

    @extend_schema(request=WishlistToggleRequestSerializer, responses=WishlistToggleSerializer,
                   summary='Toggle a product in/out of the wishlist')
    @action(detail=False, methods=['post'])
    def toggle(self, request):
        from wishlist.services import toggle_wishlist
        product = get_object_or_404(Product, id=request.data.get('product_id'), is_active=True)
        added, count = toggle_wishlist(request.user, product)
        return Response({'added': added, 'count': count})


# ── Notifications ─────────────────────────────────────────

class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class   = NotificationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class    = StandardResultsPagination

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Notification.objects.none()
        return Notification.objects.filter(user=self.request.user)

    @extend_schema(request=None, responses=SimpleSuccessSerializer, summary='Mark one notification as read')
    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        notif = get_object_or_404(Notification, id=pk, user=request.user)
        notif.mark_read()
        return Response({'success': True})

    @extend_schema(request=None, responses=SimpleSuccessSerializer, summary='Mark all notifications as read')
    @action(detail=False, methods=['post'], url_path='read-all')
    def read_all(self, request):
        from django.utils import timezone
        self.get_queryset().filter(is_read=False).update(is_read=True, read_at=timezone.now())
        return Response({'success': True})


# ── AI: Semantic Search / Visual Search / Recommendations / Chat ──

class SemanticSearchView(APIView):
    """GET ?q=...&category=&min_price=&max_price=&top_k= — AI semantic product search."""
    permission_classes = [AllowAny]
    throttle_classes    = [AIUserThrottle, AIAnonThrottle]

    @extend_schema(parameters=[
        OpenApiParameter('q', OpenApiTypes.STR, description='Natural-language search query', required=True),
        OpenApiParameter('category', OpenApiTypes.STR, description='Category slug filter'),
        OpenApiParameter('min_price', OpenApiTypes.NUMBER),
        OpenApiParameter('max_price', OpenApiTypes.NUMBER),
        OpenApiParameter('top_k', OpenApiTypes.INT, description='Max results (1–48)'),
    ], responses=SearchResponseSerializer, summary='Semantic product search (Sentence Transformers + FAISS)')
    def get(self, request):
        serializer = SemanticSearchQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        from ai_search.semantic_search import search_products
        filters = {
            'category':  d.get('category'),
            'min_price': d.get('min_price'),
            'max_price': d.get('max_price'),
        }
        results = search_products(d['q'], top_k=d['top_k'], filters=filters)
        data    = ProductListSerializer(results, many=True, context={'request': request}).data
        return Response({'query': d['q'], 'count': len(data), 'results': data})


class VisualSearchView(APIView):
    """POST multipart 'image' file — finds visually similar products via ResNet50 + FAISS."""
    permission_classes = [AllowAny]
    throttle_classes    = [AIUserThrottle, AIAnonThrottle]

    @extend_schema(
        request={'multipart/form-data': {
            'type': 'object',
            'properties': {'image': {'type': 'string', 'format': 'binary'}},
            'required': ['image'],
        }},
        responses=VisualSearchResponseSerializer,
        summary='Visual product search (ResNet50 + FAISS)',
    )
    def post(self, request):
        image_file = request.FILES.get('image')
        if not image_file:
            return Response({'error': 'No image uploaded.'}, status=status.HTTP_400_BAD_REQUEST)

        from ai_search.visual_search import visual_search_products
        try:
            results = visual_search_products(image_file.read(), top_k=12)
            data    = ProductListSerializer(results, many=True, context={'request': request}).data
            return Response({'count': len(data), 'results': data})
        except Exception as e:
            return Response({'error': f'Could not process image: {e}'}, status=status.HTTP_400_BAD_REQUEST)


class RecommendationsView(APIView):
    """Personalized picks for authenticated users, popularity fallback for anonymous."""
    permission_classes = [AllowAny]
    throttle_classes    = [AIUserThrottle, AIAnonThrottle]

    @extend_schema(
        parameters=[OpenApiParameter('top_k', OpenApiTypes.INT, description='Max results (≤24)')],
        responses=RecommendationsResponseSerializer,
        summary='AI product recommendations (collaborative filtering)',
    )
    def get(self, request):
        top_k = min(int(request.query_params.get('top_k', 8)), 24)
        if request.user.is_authenticated:
            from ai_recommendations.recommender import get_recommendations
            products = get_recommendations(request.user, top_k=top_k)
        else:
            products = Product.objects.filter(is_active=True)\
                                      .order_by('-purchase_count')[:top_k]
        data = ProductListSerializer(products, many=True, context={'request': request}).data
        return Response({'personalized': request.user.is_authenticated, 'results': data})


class ChatMessageView(APIView):
    """
    POST {"message": "..."} — routes through the same ARIA intent classifier +
    Claude fallback used by the web widget, and persists to the same
    ChatSession/ChatMessage models so history is shared across channels.
    """
    permission_classes = [AllowAny]
    throttle_classes    = [AIUserThrottle, AIAnonThrottle]

    @extend_schema(request=ChatMessageSerializer, responses=ChatReplySerializer,
                   summary='Send a message to ARIA (AI shopping assistant)')
    def post(self, request):
        serializer = ChatMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = serializer.validated_data['message']

        from ai_chatbot.models import ChatSession, ChatMessage
        from ai_chatbot.aria_engine import process_message

        if request.user.is_authenticated:
            session, _ = ChatSession.objects.get_or_create(user=request.user, is_active=True)
        else:
            if not request.session.session_key:
                request.session.create()
            session, _ = ChatSession.objects.get_or_create(
                session_key=request.session.session_key, user=None, is_active=True
            )

        history = list(session.messages.order_by('-created_at')[:10])[::-1]
        conv_history = [{'role': m.role, 'content': m.content} for m in history]

        ChatMessage.objects.create(session=session, role='user', content=message)
        reply, meta, intent, confidence = process_message(request.user, message, conv_history)
        ChatMessage.objects.create(
            session=session, role='assistant', content=reply,
            intent=intent, confidence=confidence, metadata=meta,
        )
        session.save()

        return Response({
            'reply': reply, 'intent': intent, 'confidence': round(confidence, 3),
            'session_id': str(session.id), 'metadata': meta,
        })
