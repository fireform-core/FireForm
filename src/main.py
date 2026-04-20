from commonforms import prepare_form
from pypdf import PdfReader
feat/voice-transcription
from voice_manager import VoiceManager

def get_user_input(input_path):
    """Auto-detect input type (audio or text file) and return text."""
    ext = os.path.splitext(input_path)[1].lower()
    audio_extensions = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm"}

    if ext in audio_extensions:
        print(f"[INPUT] Audio file detected: {input_path}")
        vm = VoiceManager()
        transcript = vm.transcribe(input_path)
        print(f"[INPUT] Transcription complete ({len(transcript)} chars)")
        return transcript
    else:
        print(f"[INPUT] Text file detected: {input_path}")
        with open(input_path, "r", encoding="utf-8") as f:
            return f.read()

from controller import Controller
main

if __name__ == "__main__":
    file = "./src/inputs/file.pdf"
    user_input = "Hi. The employee's name is John Doe. His job title is managing director. His department supervisor is Jane Doe. His phone number is 123456. His email is jdoe@ucsc.edu. The signature is <Mamañema>, and the date is 01/02/2005"
    fields = [
        "Employee's name",
        "Employee's job title",
        "Employee's department supervisor",
        "Employee's phone number",
        "Employee's email",
        "Signature",
        "Date",
    ]
    prepared_pdf = "temp_outfile.pdf"
    prepare_form(file, prepared_pdf)

    reader = PdfReader(prepared_pdf)
    fields = reader.get_fields()
    if fields:
        num_fields = len(fields)
    else:
        num_fields = 0

    controller = Controller()
    controller.fill_form(user_input, fields, file)
