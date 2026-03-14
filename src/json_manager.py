import json

class JsonManager():
    def __init__(self):
        pass

    def load_json(self, path_to_file):
        try:
            with open(path_to_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"Warning: File not found at {path_to_file}. Returning empty list.")
            data = []
        except json.JSONDecodeError:
            raise IOError(f"JSON file at {path_to_file} is corrupted.")
        
        return data

    def save_json(self, data_to_save, path_to_file):
        try:
            with open(path_to_file, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, indent=2)
            print(f"Successfully saved data to {path_to_file}")
        
        except FileNotFoundError as e:
            raise FileNotFoundError from e
        
        except TypeError as e:
            print(f"Error saving JSON: {e}")
