import unittest
import requests
import json
import threading
import time

# Note: In a real environment, this test script would run outside Houdini,
# and communicate with the Houdini instance running `hwebserver.py`.
# For testing locally without Houdini, we can start the server in a thread 
# and mock `hou` behavior mildly, but `hwebserver.py` expects `hou` to be present.

class TestHoudiniBackend(unittest.TestCase):
    BASE_URL = "http://localhost:9000"

    def test_health_endpoint(self):
        """Test if the server is up and responding to /health"""
        try:
            response = requests.get(f"{self.BASE_URL}/health")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data.get("alive"))
        except requests.exceptions.ConnectionError:
            self.fail("Server is not running. Please start hwebserver.py inside Houdini first.")

    def test_execute_endpoint(self):
        """Test code execution via /execute"""
        payload = {
            "code": "result['test'] = 'success'"
        }
        try:
            response = requests.post(f"{self.BASE_URL}/execute", json=payload)
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["status"], "ok")
            self.assertEqual(data["data"]["test"], "success")
        except requests.exceptions.ConnectionError:
            self.fail("Server is not running.")
            
    def test_execute_error_handling(self):
        """Test error handling in /execute"""
        payload = {
            "code": "1 / 0" # Intentional Division by zero
        }
        try:
            response = requests.post(f"{self.BASE_URL}/execute", json=payload)
            self.assertEqual(response.status_code, 200) # Fast API returns 200 but status is 'error'
            data = response.json()
            self.assertEqual(data["status"], "error")
            self.assertTrue("division by zero" in data["error"])
            self.assertTrue(data["traceback"] is not None)
        except requests.exceptions.ConnectionError:
            self.fail("Server is not running.")
            
    def test_scene_endpoint(self):
        """Test fetching scene data via /scene"""
        try:
            response = requests.get(f"{self.BASE_URL}/scene")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            # If hou is not mocking/running, it will return an error or basic context
            self.assertTrue("status" in data)
        except requests.exceptions.ConnectionError:
            self.fail("Server is not running.")

if __name__ == "__main__":
    unittest.main()
