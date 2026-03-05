import os
from src.filler import Filler
from src.llm import LLM
from commonforms import prepare_form


class FileManipulator:
    def __init__(self):
        self.filler = Filler()
        # NOTE: We intentionally do NOT store a shared LLM instance here.
        # LLM holds per-request mutable state (_transcript_text, _target_fields, _json).
        # Sharing one instance across concurrent requests would cause a race condition
        # where two requests overwrite each other's data.  A fresh LLM is created
        # inside fill_form() so each request owns its own isolated instance.

    def create_template(self, pdf_path: str):
        """
        By using commonforms, we create an editable .pdf template and we store it.
        """
        template_path = pdf_path[:-4] + "_template.pdf"
        prepare_form(pdf_path, template_path)
        return template_path

    def fill_form(self, user_input: str, fields: dict, pdf_form_path: str):
        """
        Receives the raw transcript + template fields, runs the LLM extraction +
        PDF filling pipeline, and returns the path to the newly created filled PDF.

        A new LLM instance is created on every call to guarantee full isolation
        between concurrent requests — no shared mutable state.
        """
        print("[1] Received request from frontend.")
        print(f"[2] PDF template path: {pdf_form_path}")

        if not os.path.exists(pdf_form_path):
            raise FileNotFoundError(
                f"PDF template not found at '{pdf_form_path}'. "
                "Please verify the template path stored in the database is correct."
            )

        print("[3] Starting extraction and PDF filling process...")

        # Fresh LLM instance scoped to this request only.
        llm = LLM(transcript_text=user_input, target_fields=fields)

        output_name = self.filler.fill_form(pdf_form=pdf_form_path, llm=llm)

        print("\n----------------------------------")
        print("✅ Process Complete.")
        print(f"Output saved to: {output_name}")

        return output_name
