from pypdf import PdfReader
import sys
import os


def extract_fields(pdf_path):
    if not os.path.exists(pdf_path):
        print(f"File not found: {pdf_path}", file=sys.stderr)
        return 1
    try: 
        reader = PdfReader(pdf_path)
    except Exception as e:
        print(f"Error reading PDF: {e}", file=sys.stderr)
        return 1
    
    fields = reader.get_fields()

    if not fields:
        print("No form fields found.", file=sys.stderr)
        return 1

    print("PDF Form Fields:\n")
    for field in fields.keys():
        print(field)

    return 0

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_pdf_fields.py <pdf_path>", file=sys.stderr)
        sys.exit(1)

    sys.exit(extract_fields(sys.argv[1]))