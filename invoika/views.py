from django.shortcuts import render, redirect
from django.views.generic import TemplateView
from django.http import JsonResponse

def check_auth(view_func):
    def wrapper(request, *args, **kwargs):
        token = request.session.get('auth_token')
        if not token:
            return redirect('pages:login')

        user_data = request.session.get('user_data', {}) or {}
        role = str(user_data.get('role', '')).upper()

        if role == 'CUSTOMER':
            resolver = getattr(request, 'resolver_match', None)
            url_name = resolver.url_name if resolver else None
            customer_allowed_views = {
                'catalog',
                'catalog_by_channel',
                'product_detail',
                'cart_add_item_proxy',
                'cart_items_proxy',
                'cart_update_quantity_proxy',
                'cart_remove_item_proxy',
                'cart_clear_proxy',
                'cart_summary_proxy',
                'catalog_pdf_generate_proxy',
            }

            if url_name and url_name not in customer_allowed_views:
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({
                        'status': '403',
                        'statusMsg': 'Access denied for customer role.',
                    }, status=403)
                return redirect('pages:catalog')

        return view_func(request, *args, **kwargs)
    return wrapper

class DashboardView(TemplateView):
    template_name = "index.html"
    
    @classmethod
    def as_view(cls, **initkwargs):
        view = super().as_view(**initkwargs)
        return check_auth(view)

dashboard_view = DashboardView.as_view()
    
    
