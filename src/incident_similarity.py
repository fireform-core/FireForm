from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import os
import pickle


class IncidentSimilarity:
    def __init__(self, index_path="faiss_index.bin", data_path="incidents.pkl"):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.dimension = 384

        self.index_path = index_path
        self.data_path = data_path

        self.index = faiss.IndexFlatL2(self.dimension)
        self.incidents = []

        self._load()

    def add_incident(self, text: str):
        embedding = self.model.encode([text])
        embedding = np.array(embedding).astype("float32")

        self.index.add(embedding)
        self.incidents.append(text)

        self._save()

    def search(self, query: str, top_k: int = 3):
        if len(self.incidents) == 0:
            return []

        query_embedding = self.model.encode([query])
        query_embedding = np.array(query_embedding).astype("float32")

        distances, indices = self.index.search(query_embedding, top_k)

        results = []

        for i, idx in enumerate(indices[0]):
            if idx < len(self.incidents):
                distance = distances[0][i]
                similarity_score = 1 / (1 + distance)
                results.append({
                    "incident": self.incidents[idx],
                    "score": round(similarity_score, 4)
                })

        return results

    def _save(self):
        faiss.write_index(self.index, self.index_path)
        with open(self.data_path, "wb") as f:
            pickle.dump(self.incidents, f)

    def _load(self):
        if os.path.exists(self.index_path):
            self.index = faiss.read_index(self.index_path)

        if os.path.exists(self.data_path):
            with open(self.data_path, "rb") as f:
                self.incidents = pickle.load(f)