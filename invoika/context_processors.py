from django.conf import settings

def api_urls(request):
    return {
        'IMAGE_SERVICE_URL': settings.IMAGE_SERVICE_URL,
        'JAVA_API_URL': settings.INTERNAL_JAVA_API_URL,
        'INTERNAL_JAVA_API_URL': settings.INTERNAL_JAVA_API_URL
    }
