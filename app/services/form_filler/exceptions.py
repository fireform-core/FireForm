class ModelNotInstalledError(Exception):
    def __init__(self, model: str):
        self.model = model
        super().__init__(f"Model '{model}' is not installed in Ollama.")
