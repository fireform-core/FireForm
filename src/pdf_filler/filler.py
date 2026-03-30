import os
import fitz  # PyMuPDF
import numpy as np
from typing import Dict, List, Any
from sentence_transformers import SentenceTransformer

class VectorSemanticMapper:
    """
    Decouples JSON keys from PDF form fields using a Vector-Semantic Alignment Engine.
    Uses 'all-MiniLM-L6-v2' to perform zero-shot alignment between adjacent PDF text and extracted keys.
    """
    def __init__(self, model_name: str = 'all-MiniLM-L6-v2'):
        # In a real deployed app, this model loads once at startup or via a singleton.
        self.model = SentenceTransformer(model_name)

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute the cosine similarity between two 1D numpy arrays."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return np.dot(a, b) / (norm_a * norm_b)

    def _extract_adjacent_text(self, page: fitz.Page, widget: fitz.Widget) -> str:
        """
        Extracts visible text immediately surrounding the PDF widget.
        Expands the bounding box to capture the preceding text label.
        """
        rect = widget.rect
        # Expand bounding box to the left and slightly up to catch preceding label text
        expanded_rect = fitz.Rect(max(0, rect.x0 - 150), max(0, rect.y0 - 20), rect.x1, rect.y1 + 10)
        
        words = page.get_text("words")
        adjacent_words = []
        for w in words:
            # Each w is (x0, y0, x1, y1, word, block_no, line_no, word_no)
            w_rect = fitz.Rect(w[:4])
            if w_rect.intersects(expanded_rect):
                adjacent_words.append(w[4])
                
        # If no text adjacent, handles error gracefully
        return " ".join(adjacent_words).strip() if adjacent_words else "Unknown Field"

    def align_pdf_fields(self, pdf_path: str, json_keys: List[str]) -> Dict[str, str]:
        """
        Dynamically aligns the PDF's unconfigured widget names to the target JSON keys.
        Returns a mapping of { 'JSON Key' : 'PDF Widget Name' }.
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF template not found: {pdf_path}")

        mapping = {}
        
        # Pre-compute target key embeddings
        # Replace underscores with spaces for better semantic match
        cleaned_keys = [k.replace('_', ' ') for k in json_keys]
        key_embeddings = self.model.encode(cleaned_keys)

        doc = fitz.open(pdf_path)
        for page in doc:
            for widget in page.widgets():
                pdf_field_name = widget.field_name
                # Skip unnamable/hidden widgets
                if not pdf_field_name:
                    continue

                # 1. Extract physical visual context adjacent to widget
                visual_text = self._extract_adjacent_text(page, widget)
                
                # 2. Embed the visual context
                visual_embedding = self.model.encode(visual_text)

                # 3. Calculate Cosine Similarity against all keys
                best_sim = -1.0
                best_key = None
                
                for i, k_emb in enumerate(key_embeddings):
                    sim = self._cosine_similarity(visual_embedding, k_emb)
                    if sim > best_sim:
                        best_sim = sim
                        best_key = json_keys[i]

                # 4. Filter by confidence threshold (0.75)
                # Graceful handling if no match meets the threshold
                if best_sim > 0.75 and best_key:
                    mapping[best_key] = pdf_field_name
                    print(f"[VectorMapper] Aligned PDF Field '{pdf_field_name}' "
                          f"<>(text: '{visual_text}')<> to JSON Key '{best_key}' (Confidence: {best_sim:.2f})")
                else:
                    print(f"[VectorMapper] Ignored PDF Field '{pdf_field_name}', "
                          f"text: '{visual_text}' (Max Confidence: {best_sim:.2f})")
        doc.close()
        return mapping

    def fill_pdf(self, template_path: str, data_dict: dict, dynamic_mapping: dict = None) -> bytes:
        """
        Refactored fill_pdf using PyMuPDF (fitz) directly instead of pdfrw.
        Uses the dynamically generated semantic mapping to determine which fields to fill.
        """
        doc = fitz.open(template_path)
        if not dynamic_mapping:
            # Fallback alignment if no explicit mapping given
            json_keys = list(data_dict.keys())
            dynamic_mapping = self.align_pdf_fields(template_path, json_keys)
            
        # Mapping is JSON Key -> PDF Field Name
        # We need PDF Field Name -> Value for writing
        field_to_value = {}
        for json_key, pdf_field in dynamic_mapping.items():
            val = data_dict.get(json_key, "")
            if val is None: val = ""
            if isinstance(val, list): val = ", ".join(str(i) for i in val)
            if isinstance(val, tuple): val = ", ".join(str(i) for i in val)
            if isinstance(val, bool): val = "Yes" if val else "No"
            field_to_value[pdf_field] = str(val)

        for page in doc:
            for widget in page.widgets():
                if widget.field_name in field_to_value:
                    widget.field_value = field_to_value[widget.field_name]
                    widget.update()
        
        return doc.write()

# Helper execution if run locally
if __name__ == "__main__":
    # Provides mock usage 
    mapper = VectorSemanticMapper()
    print("Mapper initialized.")
