import pytest
import sys

def run_all_tests():
    """
    Centralized test runner for Curate.ai.
    Runs all tests in the tests/ directory with verbose output.
    """
    print("🚀 Starting Curate.ai Test Suite...\n")
    
    # Arguments for pytest
    args = [
        "tests",
        "-v",
    ]
    
    exit_code = pytest.main(args)
    
    if exit_code == 0:
        print("\n✅ All tests passed!")
    else:
        print(f"\n❌ Tests failed with exit code: {exit_code}")
        
    sys.exit(exit_code)

if __name__ == "__main__":
    run_all_tests()
