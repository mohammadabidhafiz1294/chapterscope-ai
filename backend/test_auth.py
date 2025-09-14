#!/usr/bin/env python3
import requests
import json

# Test the authentication endpoints
base_url = "http://127.0.0.1:8000/api/auth"

def test_csrf_token():
    try:
        response = requests.get(f"{base_url}/csrf-token/", headers={'Accept': 'application/json'})
        print(f"CSRF Token Status: {response.status_code}")
        print(f"Response: {response.text}")
        print(f"CORS Headers: {dict(response.headers)}")
        return response
    except Exception as e:
        print(f"Error testing CSRF token: {e}")
        return None

def test_login():
    try:
        # First get CSRF token
        csrf_response = requests.get(f"{base_url}/csrf-token/", headers={'Accept': 'application/json'})
        if csrf_response.status_code == 200:
            csrf_token = csrf_response.json().get('csrfToken')
            print(f"Got CSRF token: {csrf_token}")

            # Test login with dummy data
            login_data = {
                'username': 'testuser',
                'password': 'testpass'
            }
            headers = {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrf_token,
                'Accept': 'application/json'
            }
            response = requests.post(f"{base_url}/login/", json=login_data, headers=headers)
            print(f"Login Status: {response.status_code}")
            print(f"Response: {response.text}")
            return response
    except Exception as e:
        print(f"Error testing login: {e}")
        return None

if __name__ == "__main__":
    print("Testing EduQuantum Authentication API...")
    test_csrf_token()
    print("\n" + "="*50 + "\n")
    test_login()
