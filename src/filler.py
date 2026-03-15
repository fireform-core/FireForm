from pdfrw import PdfReader, PdfWriter
from src.llm import LLM
import uuid
import logging
import os
import re

logger = logging.getLogger(__name__)


class Filler:
    def __init__(self):
        pass

    def fill_form(self, pdf_form: str, llm: LLM):
        """
        Fill a PDF form with values from user_input using LLM.
        Fields are filled in the visual order (top-to-bottom, left-to-right).
        """
        if not pdf_form or not isinstance(pdf_form, str):
            raise ValueError("PDF form path must be a non-empty string")
        
        if not llm or not isinstance(llm, LLM):
            raise ValueError("LLM instance is required")
        
        output_pdf = f"{pdf_form[:-4]}_{uuid.uuid4()}_filled.pdf"
        final_output_pdf = None
        
        # Ensure output directory exists
        output_dir = os.path.dirname(output_pdf)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        pdf_reader = None
        pdf_writer = None
        
        try:
            # Generate dictionary of answers from LLM
            t2j = llm.main_loop()
            textbox_answers = t2j.get_data()
            
            if not textbox_answers:
                logger.warning("No data extracted from LLM")
                textbox_answers = {}

            answers_list = [v for v in textbox_answers.values() if v is not None]

            # Read PDF with proper resource management
            pdf_reader = PdfReader(pdf_form)
            
            # Validate PDF structure
            if not pdf_reader.pages:
                raise ValueError("PDF has no pages")

            # Process all pages and fields
            field_index = 0
            total_fields_filled = 0
            
            for page_num, page in enumerate(pdf_reader.pages):
                if not hasattr(page, 'Annots') or not page.Annots:
                    continue
                    
                # Filter out bad annotations before sorting
                valid_annots = self._filter_valid_annotations(page.Annots)
                
                if valid_annots:
                    sorted_annots = self._sort_annotations_safely(valid_annots, page_num)
                    
                    for annot in sorted_annots:
                        if field_index >= len(answers_list):
                            break
                            
                        if self._is_fillable_field(annot):
                            try:
                                answer = self.sanitize_pdf_value(answers_list[field_index])
                                annot.V = answer
                                annot.AP = None
                                field_index += 1
                                total_fields_filled += 1
                                
                                logger.debug(f"Filled field {total_fields_filled}: {answer}")
                                
                            except Exception as e:
                                logger.warning(f"Error filling field {field_index}: {e}")
                                continue

            # Handle file collision with proper error handling
            final_output_pdf = self._get_unique_filename(output_pdf)
            
            # Write PDF with proper resource management
            pdf_writer = PdfWriter()
            pdf_writer.write(final_output_pdf, pdf_reader)
            
            logger.info(f"Successfully created PDF: {final_output_pdf} ({total_fields_filled} fields filled)")
            return final_output_pdf
            
        except Exception as e:
            logger.error(f"Error in PDF filling: {e}")
            # Clean up partial file if it exists
            if final_output_pdf and os.path.exists(final_output_pdf):
                try:
                    os.remove(final_output_pdf)
                    logger.debug(f"Cleaned up partial file: {final_output_pdf}")
                except OSError as cleanup_error:
                    logger.warning(f"Failed to clean up partial file: {cleanup_error}")
            raise
            
        finally:
            # Explicit cleanup with proper error handling
            self._cleanup_resources(pdf_reader, pdf_writer)

    def _filter_valid_annotations(self, annotations):
        """Filter out malformed annotations"""
        valid_annots = []
        for annot in annotations:
            try:
                if (hasattr(annot, 'Rect') and annot.Rect and 
                    len(annot.Rect) >= 2 and 
                    all(self._is_valid_coordinate(coord) for coord in annot.Rect[:2])):
                    valid_annots.append(annot)
            except (AttributeError, TypeError, ValueError):
                continue
        return valid_annots

    def _is_valid_coordinate(self, coord):
        """Check if coordinate is valid number"""
        try:
            float(coord)
            return True
        except (ValueError, TypeError):
            return False

    def _sort_annotations_safely(self, annotations, page_num):
        """Sort annotations with error handling"""
        try:
            return sorted(
                annotations, 
                key=lambda a: (-float(a.Rect[1]) if a.Rect and len(a.Rect) > 1 else 0, 
                             float(a.Rect[0]) if a.Rect and len(a.Rect) > 0 else 0)
            )
        except Exception as e:
            logger.warning(f"Error sorting annotations on page {page_num}: {e}")
            return annotations  # Return unsorted if sorting fails

    def _is_fillable_field(self, annot):
        """Check if annotation is a fillable field"""
        try:
            return (hasattr(annot, 'Subtype') and annot.Subtype == "/Widget" and 
                   hasattr(annot, 'T') and annot.T)
        except (AttributeError, TypeError):
            return False

    def _get_unique_filename(self, base_path):
        """Generate unique filename to avoid collisions"""
        if not os.path.exists(base_path):
            return base_path
            
        collision_count = 0
        while collision_count < 100:  # Increased limit
            collision_count += 1
            base_name = base_path[:-4]  # Remove .pdf
            candidate = f"{base_name}_v{collision_count}.pdf"
            if not os.path.exists(candidate):
                return candidate
                
        raise RuntimeError("Unable to create unique filename after 100 attempts")

    def _cleanup_resources(self, pdf_reader, pdf_writer):
        """Clean up PDF resources safely"""
        for resource in [pdf_reader, pdf_writer]:
            if resource:
                try:
                    if hasattr(resource, 'stream') and resource.stream:
                        resource.stream.close()
                except Exception as e:
                    logger.debug(f"Error closing PDF resource: {e}")
                    pass

    def sanitize_pdf_value(self, value):
        """
        Sanitize values before inserting into PDF to prevent corruption
        """
        if value is None:
            return ""
        
        if not isinstance(value, str):
            value = str(value)
        
        # Remove null bytes and other problematic characters
        value = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', value)
        
        # Limit length to prevent PDF corruption (ensure exactly 1000 chars max)
        if len(value) > 1000:
            value = value[:997] + "..."
        
        # Use safer PDF string handling instead of aggressive character removal
        try:
            from pdfrw.objects import PdfString
            return PdfString.encode(value)
        except (ImportError, AttributeError):
            # Fallback: only remove control characters, keep legitimate chars
            return value
