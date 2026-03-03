import os
from pathlib import Path
from typing import Union
from backend import Fill  

def run_dynamic_report_process(user_input: str, input_path: Path, output_path: Path):
    """
    Main entry point to run the AI-driven dynamic report generation.
    Exports the final PDF to the specified output path (src/outputs/).
    """
    
    print(f"[1] Received request for dynamic report generation.")
    print(f"[2] Analyzing transcript text (Length: {len(user_input)} characters)...")

    try:
        # We pass the full path string to the backend
        generated_file = Fill.fill_form(
            user_input=user_input,
            input_path=input_path,
            output_filename=str(output_path)
        )
        
        print("\n----------------------------------")
        print(f"✅ Process Complete.")
        print(f"Dynamic Report saved to: {generated_file}")
        
        return generated_file
        
    except Exception as e:
        print(f"[ERROR] An error occurred during PDF generation: {e}")
        raise e


if __name__ == "__main__":
    # 1. Setup base directory and input file path
    BASE_DIR = Path(__file__).resolve().parent
    INPUT_FILE_PATH = BASE_DIR / "inputs" / "input.txt"

    # 2. Define and create the output directory (src/outputs)
    OUTPUT_DIR = BASE_DIR / "outputs"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True) # Creates folder if it doesn't exist
    
    # Full path for the output PDF
    FINAL_OUTPUT_PATH = OUTPUT_DIR / "dynamic_extraction_result.pdf"

    print("--- Starting FireForm Dynamic Mode ---")
    
    # 3. Dynamic Loading: Read the content from the input.txt file
    if INPUT_FILE_PATH.exists():
        try:
            with open(INPUT_FILE_PATH, "r", encoding="utf-8") as f:
                dynamic_content = f.read().strip()
            
            if not dynamic_content:
                print(f"[WARNING] The file {INPUT_FILE_PATH} is empty. Please add some text.")
            else:
                print(f"[LOG] Successfully loaded dynamic text from: {INPUT_FILE_PATH}")
                
                # 4. Run the process using the file's content and the new output path
                run_dynamic_report_process(
                    user_input=dynamic_content, 
                    input_path=INPUT_FILE_PATH,
                    output_path=FINAL_OUTPUT_PATH
                )
        except Exception as e:
            print(f"[ERROR] Could not read the file: {e}")
    else:
        print(f"[ERROR] Input file NOT FOUND at: {INPUT_FILE_PATH}")
        print("Please create the 'src/inputs/input.txt' file and add your transcript.")