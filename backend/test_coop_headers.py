#!/usr/bin/env python3
"""
Test script to verify COOP headers are properly set by our middleware.
This script simulates the requests that would cause COOP errors.
"""

import requests
import sys
import os

# Add the Django project to Python path
sys.path.append('/Users/abid-macbook-air/Developer/Projects-dev/Hybrid-Quantum-AI-Exam-Questions-Analysics/backend')

# Set Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eduquantum.settings')

import django
django.setup()

from django.test import RequestFactory
from django.http import HttpResponse
from predictor.middleware import SecurityHeadersMiddleware

def test_coop_headers():
    """Test that our SecurityHeadersMiddleware sets correct COOP headers."""
    
    # Create a mock response function
    def mock_get_response(request):
        return HttpResponse("Test response")
    
    # Initialize middleware
    middleware = SecurityHeadersMiddleware(mock_get_response)
    
    # Create a request factory
    factory = RequestFactory()
    
    # Test cases
    test_cases = [
        {
            'name': 'Localhost Origin Request',
            'path': '/predictions/create/',
            'headers': {'HTTP_ORIGIN': 'http://localhost:3000'},
            'expected_coop': 'unsafe-none'
        },
        {
            'name': '127.0.0.1 Origin Request', 
            'path': '/predictions/create/',
            'headers': {'HTTP_ORIGIN': 'http://127.0.0.1:3000'},
            'expected_coop': 'unsafe-none'
        },
        {
            'name': 'Direct Create Route Access',
            'path': '/predictions/create/',
            'headers': {},
            'expected_coop': 'unsafe-none'
        },
        {
            'name': 'OPTIONS Preflight Request',
            'path': '/predictions/create/',
            'method': 'OPTIONS',
            'headers': {'HTTP_ORIGIN': 'http://localhost:3000'},
            'expected_coop': 'unsafe-none'
        }
    ]
    
    print("🧪 Testing COOP Headers Implementation")
    print("=" * 50)
    
    for test_case in test_cases:
        print(f"\n📋 Test: {test_case['name']}")
        print(f"   Path: {test_case['path']}")
        
        # Create request
        method = test_case.get('method', 'GET')
        if method == 'OPTIONS':
            request = factory.options(test_case['path'], **test_case['headers'])
        else:
            request = factory.get(test_case['path'], **test_case['headers'])
        
        # Process through middleware
        response = middleware(request)
        
        # Check COOP header
        coop_header = response.get('Cross-Origin-Opener-Policy', 'NOT_SET')
        expected_coop = test_case['expected_coop']
        
        if coop_header == expected_coop:
            print(f"   ✅ COOP Header: {coop_header} (Expected: {expected_coop})")
        else:
            print(f"   ❌ COOP Header: {coop_header} (Expected: {expected_coop})")
        
        # Show other relevant headers
        coep_header = response.get('Cross-Origin-Embedder-Policy', 'NOT_SET')
        corp_header = response.get('Cross-Origin-Resource-Policy', 'NOT_SET')
        
        print(f"   📄 COEP Header: {coep_header}")
        print(f"   📄 CORP Header: {corp_header}")
        
        if method == 'OPTIONS' or 'origin' in test_case['headers'].get('HTTP_ORIGIN', '').lower():
            cors_origin = response.get('Access-Control-Allow-Origin', 'NOT_SET')
            cors_credentials = response.get('Access-Control-Allow-Credentials', 'NOT_SET')
            print(f"   🌐 CORS Origin: {cors_origin}")
            print(f"   🔑 CORS Credentials: {cors_credentials}")
    
    print("\n" + "=" * 50)
    print("🎯 Test Summary:")
    print("   The middleware should set 'Cross-Origin-Opener-Policy: unsafe-none'")
    print("   for localhost requests to prevent COOP errors in development.")
    print("\n💡 If you're still seeing COOP errors:")
    print("   1. Restart your Django server to load the new middleware")
    print("   2. Clear your browser cache")
    print("   3. Check browser DevTools Network tab for response headers")
    print("   4. Ensure requests are coming from localhost:3000 to localhost:8001")

if __name__ == '__main__':
    test_coop_headers()