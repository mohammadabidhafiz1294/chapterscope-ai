#!/usr/bin/env python3
"""
API Connection Test Script
Tests the EduQuantum backend API endpoints
"""

import requests
import json
import sys

BASE_URL = "http://localhost:8001"

def test_endpoint(name, method, url, **kwargs):
    """Test an API endpoint"""
    try:
        if method.upper() == 'GET':
            response = requests.get(url, **kwargs)
        elif method.upper() == 'POST':
            response = requests.post(url, **kwargs)
        else:
            print(f"❌ {name}: Unsupported method {method}")
            return False

        if response.status_code in [200, 201]:
            print(f"✅ {name}: {response.status_code} - Success")
            return True
        else:
            print(f"❌ {name}: {response.status_code} - {response.text}")
            return False

    except requests.exceptions.ConnectionError:
        print(f"❌ {name}: Connection failed - Is the server running?")
        return False
    except Exception as e:
        print(f"❌ {name}: Error - {str(e)}")
        return False

def main():
    print("🚀 Testing EduQuantum Backend API Connection")
    print("=" * 50)

    # Test CSRF token endpoint
    test_endpoint(
        "CSRF Token",
        "GET",
        f"{BASE_URL}/api/auth/csrf-token/",
        headers={'Accept': 'application/json'}
    )

    # Test login endpoint (will fail without valid user, but should return proper error)
    test_endpoint(
        "Login",
        "POST",
        f"{BASE_URL}/api/auth/login/",
        headers={'Content-Type': 'application/json'},
        data=json.dumps({'username': 'test', 'password': 'test'})
    )

    # Test dashboard endpoint (may require authentication)
    test_endpoint(
        "Dashboard",
        "GET",
        f"{BASE_URL}/"
    )

    print("\n" + "=" * 50)
    print("📝 API Base URL:", BASE_URL)
    print("🔗 Frontend should connect to:", BASE_URL)
    print("📚 See README.md for complete API documentation")

if __name__ == "__main__":
    main()
