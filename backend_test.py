import requests
import json
import time
from datetime import datetime

class OptionsBacktestTester:
    def __init__(self, base_url):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.test_strategy_id = None

    def run_test(self, name, method, endpoint, expected_status, data=None):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers)
            
            status_success = response.status_code == expected_status
            
            if status_success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    return True, response.json()
                except:
                    return True, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    print(f"Response: {response.text}")
                    return False, response.json()
                except:
                    return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_polygon_connection(self):
        """Test Polygon API connection"""
        print("\n📊 Testing Polygon API Connection...")
        success, response = self.run_test(
            "Polygon API Connection",
            "GET",
            "api/polygon-test",
            200
        )
        
        if success:
            if response.get("status") == "success":
                print(f"✅ Polygon API connected successfully: {response.get('message')}")
                return True
            else:
                print(f"❌ Polygon API connection failed: {response.get('message')}")
                return False
        return False

    def test_backtest_endpoint(self, test_data):
        """Test the backtest endpoint with test data"""
        print("\n📈 Testing Backtest Endpoint...")
        success, response = self.run_test(
            "Backtest Endpoint",
            "POST",
            "api/backtest",
            200,
            data=test_data
        )
        
        if success:
            # Validate response structure
            if "performance_metrics" in response and "results" in response:
                print("✅ Backtest response contains performance metrics and results")
                
                # Validate key metrics
                metrics = response["performance_metrics"]
                if "total_return" in metrics and "sharpe_ratio" in metrics and "max_drawdown" in metrics:
                    print(f"✅ Performance metrics validated: Total Return: {metrics['total_return']:.2%}, Sharpe: {metrics['sharpe_ratio']:.2f}, Max Drawdown: {metrics['max_drawdown']:.2%}")
                else:
                    print("❌ Missing key performance metrics")
                
                # Validate covered call metrics
                cc_metrics = response.get("covered_call_metrics", {})
                if "win_rate" in cc_metrics and "pct_expired_worthless" in cc_metrics and "pct_called_away" in cc_metrics:
                    print(f"✅ Covered call metrics validated: Win Rate: {cc_metrics['win_rate']:.2%}, Expired Worthless: {cc_metrics['pct_expired_worthless']:.2%}, Called Away: {cc_metrics['pct_called_away']:.2%}")
                else:
                    print("❌ Missing key covered call metrics")
                
                return True
            else:
                print("❌ Backtest response missing required data")
        
        return False

    def test_strategies_management(self, test_data):
        """Test strategy management endpoints"""
        print("\n📚 Testing Strategy Management...")
        
        # First, get current strategies
        success, response = self.run_test(
            "Get Strategies",
            "GET",
            "api/strategies",
            200
        )
        
        if success:
            initial_count = len(response.get("strategies", []))
            print(f"✅ Found {initial_count} existing strategies")
            
            # Run a backtest with a named strategy to save it
            test_data["strategy_name"] = f"Test Strategy {datetime.now().strftime('%H%M%S')}"
            success, backtest_response = self.run_test(
                "Create Strategy via Backtest",
                "POST",
                "api/backtest",
                200,
                data=test_data
            )
            
            if success:
                # Verify strategy was created
                time.sleep(1)  # Give the database a moment to update
                success, response = self.run_test(
                    "Verify Strategy Created",
                    "GET",
                    "api/strategies",
                    200
                )
                
                if success:
                    new_count = len(response.get("strategies", []))
                    if new_count > initial_count:
                        print(f"✅ Strategy created successfully: {initial_count} → {new_count}")
                        
                        # Find our test strategy
                        for strategy in response.get("strategies", []):
                            if strategy.get("name") == test_data["strategy_name"]:
                                self.test_strategy_id = strategy.get("id")
                                print(f"✅ Found test strategy with ID: {self.test_strategy_id}")
                                break
                        
                        # Test deleting the strategy
                        if self.test_strategy_id:
                            success, delete_response = self.run_test(
                                "Delete Strategy",
                                "DELETE",
                                f"api/strategies/{self.test_strategy_id}",
                                200
                            )
                            
                            if success:
                                print("✅ Strategy deleted successfully")
                                
                                # Verify deletion
                                success, response = self.run_test(
                                    "Verify Strategy Deleted",
                                    "GET",
                                    "api/strategies",
                                    200
                                )
                                
                                if success:
                                    final_count = len(response.get("strategies", []))
                                    if final_count < new_count:
                                        print(f"✅ Strategy deletion verified: {new_count} → {final_count}")
                                        return True
                                    else:
                                        print("❌ Strategy count did not decrease after deletion")
                            else:
                                print("❌ Failed to delete strategy")
                        else:
                            print("❌ Could not find test strategy ID")
                    else:
                        print("❌ Strategy count did not increase after creation")
                else:
                    print("❌ Failed to verify strategy creation")
            else:
                print("❌ Failed to create strategy via backtest")
        else:
            print("❌ Failed to get strategies")
        
        return False

def main():
    # Base URL from the request
    base_url = "https://366b7b09-1a66-4366-a71c-b0f7491df281.preview.emergentagent.com"
    
    # Test data from the request
    test_data = {
        "ticker": "TSLA",
        "start_date": "2023-01-01", 
        "end_date": "2023-12-31",
        "strategy_name": "Test Strategy 30-Delta",
        "initial_capital": 100000,
        "strategy_params": {
            "delta_target": 0.30,
            "dte_target": 45,
            "profit_target": 0.50,
            "loss_limit": 2.0,
            "strategy_type": "weekly",
            "entry_day": "Monday"
        }
    }
    
    # Initialize tester
    tester = OptionsBacktestTester(base_url)
    
    # Run tests
    polygon_test = tester.test_polygon_connection()
    backtest_test = tester.test_backtest_endpoint(test_data)
    strategy_test = tester.test_strategies_management(test_data)
    
    # Print summary
    print("\n" + "="*50)
    print("📊 TEST SUMMARY")
    print("="*50)
    print(f"Tests Run: {tester.tests_run}")
    print(f"Tests Passed: {tester.tests_passed}")
    print(f"Success Rate: {tester.tests_passed/tester.tests_run:.0%}")
    print("\nFeature Tests:")
    print(f"Polygon API Connection: {'✅ PASS' if polygon_test else '❌ FAIL'}")
    print(f"Backtest Functionality: {'✅ PASS' if backtest_test else '❌ FAIL'}")
    print(f"Strategy Management: {'✅ PASS' if strategy_test else '❌ FAIL'}")
    print("="*50)
    
    return 0 if tester.tests_passed == tester.tests_run else 1

if __name__ == "__main__":
    main()
