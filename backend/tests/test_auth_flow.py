import requests
import sys

BASE_URL = "http://localhost:8001"

def test_auth_flow():
    print("Testing Auth Flow...")
    
    # 1. Signup
    email = "testuser@example.com"
    password = "password123"
    full_name = "Test User"
    
    print(f"\n1. Testing Signup ({email})...")
    signup_data = {
        "email": email,
        "password": password,
        "full_name": full_name
    }
    
    try:
        response = requests.post(f"{BASE_URL}/auth/signup", json=signup_data)
        if response.status_code == 200:
            print("✅ Signup successful")
            print(response.json())
        elif response.status_code == 400 and "Email already registered" in response.text:
            print("⚠️ User already exists, proceeding to login...")
        else:
            print(f"❌ Signup failed: {response.status_code} - {response.text}")
            return
    except Exception as e:
        print(f"❌ Signup failed with exception: {e}")
        return

    # 2. Login
    print(f"\n2. Testing Login ({email})...")
    login_data = {
        "email": email,
        "password": password
    }
    
    token = None
    try:
        response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
        if response.status_code == 200:
            data = response.json()
            token = data["access_token"]
            print("✅ Login successful")
            print(f"Token: {token[:20]}...")
        else:
            print(f"❌ Login failed: {response.status_code} - {response.text}")
            return
    except Exception as e:
        print(f"❌ Login failed with exception: {e}")
        return

    # 3. Get Me (Protected Route)
    print("\n3. Testing /auth/me (Protected Route)...")
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(f"{BASE_URL}/auth/me", headers=headers)
        if response.status_code == 200:
            user_data = response.json()
            print("✅ Protected route access successful")
            print(f"User: {user_data['email']} ({user_data['full_name']})")
            
            if user_data['email'] == email:
                 print("✅ Verified user email matches")
            else:
                 print("❌ User email mismatch")
        else:
            print(f"❌ Protected route failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Protected route failed with exception: {e}")

if __name__ == "__main__":
    test_auth_flow()
