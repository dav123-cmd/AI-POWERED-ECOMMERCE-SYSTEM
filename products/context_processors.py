from .models import Category
from products.models import CompanyValue, TeamMember

def categories(request):
    return {
        'nav_categories': Category.objects.filter(parent=None, is_featured=True)[:8],
        'values': CompanyValue.objects.all(),
        'members': TeamMember.objects.all(),
    }


"""def cart_data(request):
    if request.user.is_authenticated:
        # Assuming you have a Cart model
        count = Cart.objects.filter(user=request.user).count()
        return {'cart_count': count}
    return {'cart_count': 0}'"""

