from src.file_manipulator import FileManipulator

class Controller:
    """
    Main controller class that orchestrates PDF form filling operations.
    
    This class serves as the primary interface for form filling functionality,
    coordinating between file manipulation, AI extraction, and PDF generation.
    """
    
    def __init__(self):
        """Initialize the controller with a file manipulator instance."""
        self.file_manipulator = FileManipulator()

    def fill_form(self, user_input: str, fields: list, pdf_form_path: str):
        """
        Fill a PDF form with AI-extracted data from user input.
        
        Args:
            user_input (str): Natural language text containing form data
            fields (list): List of field names to extract from the input
            pdf_form_path (str): Path to the PDF template file
            
        Returns:
            tuple: (output_path, requires_review_flag)
                - output_path (str): Path to the generated filled PDF file
                - requires_review_flag (bool): True if manual review is recommended
            
        Raises:
            FileNotFoundError: If the PDF template doesn't exist
            RuntimeError: If AI extraction or PDF generation fails
            
        Example:
            >>> controller = Controller()
            >>> path, needs_review = controller.fill_form(
            ...     "Employee John Doe, Manager",
            ...     ["name", "title"],
            ...     "./template.pdf"
            ... )
            >>> print(f"Output: {path}, Review needed: {needs_review}")
            Output: ./template_abc123_filled.pdf, Review needed: False
        """
        path, review_flag = self.file_manipulator.fill_form(
            user_input=user_input,
            fields=fields,
            pdf_form_path=pdf_form_path
        )
        return path, review_flag
    
    def create_template(self, pdf_path: str) -> str:
        """
        Create an editable PDF template from a regular PDF.
        
        Args:
            pdf_path (str): Path to the source PDF file
            
        Returns:
            str: Path to the created template file
            
        Raises:
            FileNotFoundError: If the source PDF doesn't exist
            
        Example:
            >>> controller = Controller()
            >>> template = controller.create_template("./form.pdf")
            >>> print(template)
            './form_template.pdf'
        """
        return self.file_manipulator.create_template(pdf_path)