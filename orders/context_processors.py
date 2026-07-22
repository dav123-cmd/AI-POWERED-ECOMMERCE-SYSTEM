from .cart_utils import get_cart_count


def order_status(request):
    # 1. Calculate or define the value you want to pass to your templates
    # For example, let's say you want to pass a string or a database result
    status_value = "Pending" 
    
    # 2. Return the dictionary with both key AND value
    return {
        'order_status': status_value 
    }


"""def cart_count(request):
    try:
        return {'cart_count': get_cart_count(request)}
    except Exception:
        return {'cart_count': 0}"""
