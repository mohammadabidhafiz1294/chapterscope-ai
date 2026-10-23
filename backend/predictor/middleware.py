"""
Custom middleware for handling security headers in development environment.
This middleware helps resolve Cross-Origin-Opener-Policy and other CORS-related issues.
"""
import logging
import uuid


logger = logging.getLogger("predictor.request")


class SecurityHeadersMiddleware:
    """
    Custom middleware to handle security headers for cross-origin requests.
    Specifically designed to resolve COOP (Cross-Origin-Opener-Policy) issues in development.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        logger.info(
            "request_completed request_id=%s method=%s path=%s status=%s",
            request.request_id,
            request.method,
            request.path,
            response.status_code,
        )
        
        # Only apply these headers in development (when DEBUG=True)
        from django.conf import settings
        if settings.DEBUG:
            # Handle Cross-Origin-Opener-Policy for localhost development
            # This prevents the COOP warning when serving over HTTP
            origin = request.headers.get('Origin', '')
            referer = request.headers.get('Referer', '')
            
            # Check if this is a localhost request (from frontend or direct browser access)
            host = request.get_host()
            is_localhost_request = (
                'localhost' in origin or '127.0.0.1' in origin or
                'localhost' in referer or '127.0.0.1' in referer or
                'localhost' in host or '127.0.0.1' in host or
                host in ['localhost:8001', '127.0.0.1:8001', 'localhost', '127.0.0.1'] or
                # For direct browser access (no origin/referer), assume localhost if on development server
                (not origin and not referer and settings.DEBUG)
            )
            
            if is_localhost_request:
                # For localhost origins, we can be more permissive
                response['Cross-Origin-Opener-Policy'] = 'unsafe-none'
                
                # Additional headers to improve cross-origin communication
                response['Cross-Origin-Embedder-Policy'] = 'unsafe-none'
                response['Cross-Origin-Resource-Policy'] = 'cross-origin'
                
                # Special handling for create routes that might trigger COOP errors
                if '/create' in request.path or '/predictions/' in request.path:
                    # Be extra permissive for prediction creation routes
                    response['Cross-Origin-Opener-Policy'] = 'unsafe-none'
                    response['Referrer-Policy'] = 'unsafe-url'  # Allow full referrer for localhost
                
                # Ensure CORS headers are present for preflight requests
                if request.method == 'OPTIONS':
                    response['Access-Control-Allow-Origin'] = origin if origin else 'http://localhost:3000'
                    response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
                    response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-CSRFToken, X-Requested-With'
                    response['Access-Control-Allow-Credentials'] = 'true'
                    response['Access-Control-Max-Age'] = '86400'  # 24 hours
                else:
                    # For non-OPTIONS requests, also set CORS headers
                    response['Access-Control-Allow-Origin'] = origin if origin else 'http://localhost:3000'
                    response['Access-Control-Allow-Credentials'] = 'true'
            
            # For non-localhost origins in development, be cautious
            else:
                response['Cross-Origin-Opener-Policy'] = 'same-origin'
        
        # In production, always use secure settings
        else:
            response['Cross-Origin-Opener-Policy'] = 'same-origin'
            response['Cross-Origin-Embedder-Policy'] = 'require-corp'
        
        return response


class CORSPreflightMiddleware:
    """
    Middleware to handle CORS preflight requests more efficiently.
    This helps reduce the number of preflight requests and improves performance.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Handle preflight requests
        if request.method == 'OPTIONS':
            from django.http import HttpResponse
            
            response = HttpResponse()
            response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
            response['Access-Control-Allow-Headers'] = (
                'Content-Type, Authorization, X-CSRFToken, X-Requested-With'
            )
            response['Access-Control-Max-Age'] = '86400'  # Cache preflight for 24 hours
            
            # Copy CORS settings from django-cors-headers if available
            from django.conf import settings
            if hasattr(settings, 'CORS_ALLOWED_ORIGINS'):
                origin = request.headers.get('Origin', '')
                if origin in settings.CORS_ALLOWED_ORIGINS:
                    response['Access-Control-Allow-Origin'] = origin
                    response['Access-Control-Allow-Credentials'] = 'true'
            
            return response
        
        return self.get_response(request)