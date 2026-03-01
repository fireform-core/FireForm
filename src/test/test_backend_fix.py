import unittest
import sys
import os

# --- PATH CONFIGURATION ---
# This ensures that the script can find 'backend.py' in the parent directory
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

try:
    from backend import textToJSON
except ImportError:
    print("Error: Could not find backend.py. Ensure the file is in the src/ folder.")
    sys.exit(1)

class TestBackendFix(unittest.TestCase):
    """
    Test suite to verify the stability of JSON field handling in FireForm.
    Specifically targets the AttributeError when adding multiple responses to a single field.
    """

    def setUp(self):
        """
        Initial setup before each test.
        Initializes the textToJSON class with a sample transcript.
        Note: This triggers the local LLM (Ollama), which may take some time.
        """
        self.definitions = ["Date", "Location", "Incident_Type"]
        self.transcript = "The incident happened on Monday in Agadir."
        
        print("\n" + "-"*34)
        print("Starting LLM initialization...")
        self.t2j = textToJSON(self.transcript, self.definitions)
        print("Initialization complete.")
        print("-"*34)

    def test_json_append_logic(self):
        """
        Verifies that add_response_to_json correctly converts string fields 
        into lists when a duplicate key is added, preventing an AttributeError.
        """
        field = "Date"
        
        # Get data state BEFORE manual insertion
        data_before = self.t2j.get_data()
        initial_val = data_before.get(field)
        
        # Determine how many items are already in the field (extracted by LLM)
        if initial_val is None or initial_val == [None]:
            initial_count = 0
        elif isinstance(initial_val, list):
            initial_count = len(initial_val)
        else:
            initial_count = 1
            
        print(f"[LOG] Initial items in '{field}': {initial_count}")

        # Manually add a new response (This is where the bug used to happen)
        new_response = "2026-03-01"
        try:
            print(f"[LOG] Attempting to append: '{new_response}'")
            self.t2j.add_response_to_json(field, new_response)
        except AttributeError as e:
            self.fail(f"CRITICAL FAILURE: add_response_to_json() raised AttributeError: {e}")

        # Get data state AFTER manual insertion
        data_after = self.t2j.get_data()
        
        # --- VERIFICATIONS ---
        
        # 1. Check if the field is now a list
        self.assertIsInstance(data_after[field], list, f"Field '{field}' should be a list.")
        
        # 2. Check if the count increased correctly
        final_count = len(data_after[field])
        self.assertEqual(final_count, initial_count + 1, 
                         f"Expected {initial_count + 1} items, but found {final_count}.")
        
        # 3. Check if our manual response is actually stored
        self.assertIn(new_response, data_after[field], f"The new response '{new_response}' was not found in the JSON.")

        print("[LOG] Test passed: No AttributeError, and list count is correct.")

if __name__ == '__main__':
    unittest.main()