import requests
import unittest
import json
from datetime import datetime

class GuardiaoAPITester:
    def __init__(self, base_url="https://6b7124a8-35cb-40b2-a1d9-86a45ac9a4c0.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.token = None
        self.user = None
        self.tests_run = 0
        self.tests_passed = 0
        self.visit_id = None

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        
        if headers is None:
            headers = {'Content-Type': 'application/json'}
            if self.token:
                headers['Authorization'] = f'Bearer {self.token}'

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    return success, response.json()
                except:
                    return success, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    print(f"Response: {response.json()}")
                except:
                    print(f"Response: {response.text}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_health_check(self):
        """Test the health check endpoint"""
        success, response = self.run_test(
            "Health Check",
            "GET",
            "health",
            200
        )
        return success

    def test_login(self, email, password):
        """Test login and get token"""
        success, response = self.run_test(
            f"Login as {email}",
            "POST",
            "auth/login",
            200,
            data={"email": email, "password": password}
        )
        if success and 'access_token' in response:
            self.token = response['access_token']
            self.user = response['user']
            print(f"Logged in as {self.user['role']}")
            return True
        return False

    def test_get_current_user(self):
        """Test getting current user info"""
        success, response = self.run_test(
            "Get Current User",
            "GET",
            "auth/me",
            200
        )
        return success

    def test_create_visit(self):
        """Test creating a new visit"""
        visit_data = {
            "visitor_name": f"Test Visitor {datetime.now().strftime('%H%M%S')}",
            "visitor_document": "123456789",
            "destination": "Apt 101",
            "purpose": "Testing",
            "notes": "This is a test visit"
        }
        
        success, response = self.run_test(
            "Create Visit",
            "POST",
            "visits",
            200,
            data=visit_data
        )
        
        if success and 'id' in response:
            self.visit_id = response['id']
            return True
        return False

    def test_get_visits(self):
        """Test getting all visits"""
        success, response = self.run_test(
            "Get All Visits",
            "GET",
            "visits",
            200
        )
        return success

    def test_get_visit_by_id(self):
        """Test getting a specific visit"""
        if not self.visit_id:
            print("❌ No visit ID available for testing")
            return False
            
        success, response = self.run_test(
            "Get Visit by ID",
            "GET",
            f"visits/{self.visit_id}",
            200
        )
        return success

    def test_update_visit_status(self, status):
        """Test updating a visit status"""
        if not self.visit_id:
            print("❌ No visit ID available for testing")
            return False
            
        success, response = self.run_test(
            f"Update Visit Status to {status}",
            "PUT",
            f"visits/{self.visit_id}",
            200,
            data={"status": status}
        )
        return success

    def test_get_dashboard_stats(self):
        """Test getting dashboard statistics"""
        success, response = self.run_test(
            "Get Dashboard Stats",
            "GET",
            "dashboard/stats",
            200
        )
        return success

    def test_delete_visit(self):
        """Test deleting a visit"""
        if not self.visit_id:
            print("❌ No visit ID available for testing")
            return False
            
        success, _ = self.run_test(
            "Delete Visit",
            "DELETE",
            f"visits/{self.visit_id}",
            200
        )
        return success

    def run_all_tests(self):
        """Run all tests for a specific user role"""
        print(f"\n===== Testing as {self.user['role']} =====")
        
        # Test getting current user
        self.test_get_current_user()
        
        # Test visit creation
        self.test_create_visit()
        
        # Test getting visits
        self.test_get_visits()
        
        # Test getting a specific visit
        self.test_get_visit_by_id()
        
        # Test updating visit status
        if self.user['role'] in ['Administrador', 'Segurança', 'Síndico']:
            self.test_update_visit_status('approved')
            self.test_update_visit_status('completed')
        
        # Test dashboard stats
        self.test_get_dashboard_stats()
        
        # Test deleting a visit (only for admin and síndico)
        if self.user['role'] in ['Administrador', 'Síndico']:
            self.test_delete_visit()

def main():
    print("=== GUARDIÃO API Testing ===")
    
    # Initialize the tester
    tester = GuardiaoAPITester()
    
    # Test health check
    if not tester.test_health_check():
        print("❌ Health check failed, stopping tests")
        return
    
    # Test login with different roles
    roles = [
        {"email": "admin@guardiao.com", "password": "admin123"},
        {"email": "seguranca@guardiao.com", "password": "seg123"},
        {"email": "sindico@guardiao.com", "password": "sind123"}
    ]
    
    for role in roles:
        # Reset token and user for each role
        tester.token = None
        tester.user = None
        
        # Test login
        if tester.test_login(role["email"], role["password"]):
            # Run all tests for this role
            tester.run_all_tests()
        else:
            print(f"❌ Login failed for {role['email']}, skipping tests for this role")
    
    # Print results
    print(f"\n=== Test Results ===")
    print(f"Tests passed: {tester.tests_passed}/{tester.tests_run}")
    print(f"Success rate: {tester.tests_passed/tester.tests_run*100:.2f}%")

if __name__ == "__main__":
    main()