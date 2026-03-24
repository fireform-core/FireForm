from pypdf import PdfReader, PdfWriter
from pypdf.generic import TextStringObject, NameObject
from src.llm import LLM
import uuid
import logging
import os
import re
from pathlib import Path

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
        
        # Check file exists and is readable
        if not os.path.exists(pdf_form):
            raise FileNotFoundError(f"PDF file not found: {pdf_form}")
        
        if not os.access(pdf_form, os.R_OK):
            raise PermissionError(f"Cannot read PDF file: {pdf_form}")
        
        # Check file size to prevent memory exhaustion
        file_size = os.path.getsize(pdf_form)
        if file_size > 50 * 1024 * 1024:  # 50MB limit for PDF processing
            raise ValueError("PDF file too large for processing (max 50MB)")
        
        output_pdf = f"{Path(pdf_form).stem}_{uuid.uuid4()}_filled.pdf"
        final_output_pdf = None
        
        # Create output directory with proper error handling
        output_dir = os.path.dirname(output_pdf)
        if output_dir:
            try:
                os.makedirs(output_dir, exist_ok=True)
            except OSError as e:
                logger.error(f"Failed to create output directory {output_dir}: {e}")
                raise RuntimeError(f"Cannot create output directory: {e}")

        pdf_reader = None
        pdf_writer = None
        temp_files = []
        
        try:
            # Get dictionary of answers from LLM with validation
            try:
                t2j = llm.main_loop()
                if not t2j:
                    raise ValueError("LLM returned no data structure")
                
                textbox_answers = t2j.get_data()
                if not isinstance(textbox_answers, dict):
                    logger.warning(f"LLM returned non-dict data: {type(textbox_answers)}")
                    textbox_answers = {}
            except Exception as llm_error:
                logger.error(f"LLM processing failed: {llm_error}", exc_info=True)
                raise ValueError("LLM data extraction failed") from llm_error

            if not textbox_answers:
                logger.warning("No data extracted from LLM")
                textbox_answers = {}

            # Filter and validate answers
            answers_list = []
            for key, value in textbox_answers.items():
                if value is not None and str(value).strip():
                    answers_list.append(str(value).strip())
            
            if not answers_list:
                logger.warning("No valid answers extracted from LLM data")

            # Initialize field processing variables
            field_index = 0
            total_fields_filled = 0
            max_fields_to_process = min(len(answers_list), 1000)  # Prevent infinite processing

            # Read PDF with proper resource management
            try:
                with open(pdf_form, 'rb') as pdf_file:
                    pdf_reader = PdfReader(pdf_file)
                    
                    # Check PDF structure
                    if not pdf_reader.pages:
                        raise ValueError("PDF has no pages")
                    
                    if len(pdf_reader.pages) > 100:  # Prevent processing huge PDFs
                        raise ValueError("PDF has too many pages (max 100)")

                    # Create writer for output
                    pdf_writer = PdfWriter()
                    
                    # Process each page
                    for page_num, page in enumerate(pdf_reader.pages):
                        # Add page to writer
                        pdf_writer.add_page(page)
                        
                        # Check for form fields
                        if '/Annots' in page and page['/Annots']:
                            annotations = page['/Annots']
                            
                            # Filter and sort annotations
                            valid_annots = self._filter_valid_annotations_pypdf(annotations)
                            
                            if valid_annots:
                                sorted_annots = self._sort_annotations_pypdf(valid_annots, page_num)
                                
                                for annot in sorted_annots:
                                    if field_index >= len(answers_list) or field_index >= max_fields_to_process:
                                        break
                                        
                                    if self._is_fillable_field_pypdf(annot):
                                        try:
                                            answer = self.sanitize_pdf_value(answers_list[field_index])
                                            if answer:  # Only fill non-empty values
                                                # Update field value using pypdf API - always set the value
                                                annot[NameObject('/V')] = TextStringObject(str(answer))
                                                # Remove appearance to force regeneration
                                                if '/AP' in annot:
                                                    del annot['/AP']
                                                total_fields_filled += 1
                                                logger.debug(f"Filled field {total_fields_filled}: {str(answer)[:50]}...")
                                            
                                            field_index += 1
                                            
                                        except (IndexError, ValueError, AttributeError) as e:
                                            logger.warning(f"Error filling field {field_index}: {e}", exc_info=True)
                                            field_index += 1  # Skip this field but continue
                                            continue
                                        except Exception as e:
                                            logger.error(f"Unexpected error filling field {field_index}: {e}", exc_info=True)
                                            field_index += 1  # Skip this field but continue
                                            continue

            except (OSError, IOError, ValueError) as e:
                logger.error(f"Cannot read PDF file {pdf_form}: {e}", exc_info=True)
                raise ValueError("Cannot read PDF file") from e
            except Exception as e:
                logger.error(f"Unexpected error reading PDF file {pdf_form}: {e}", exc_info=True)
                raise RuntimeError("PDF file access failed") from e

            # Write PDF with proper resource management
            try:
                # Avoid file collision with proper error handling
                final_output_pdf = self._get_unique_filename(output_pdf)
                temp_files.append(final_output_pdf)
                
                with open(final_output_pdf, 'wb') as output_file:
                    pdf_writer.write(output_file)
            except (OSError, IOError, ValueError) as e:
                logger.error(f"Failed to write PDF: {e}", exc_info=True)
                raise RuntimeError("PDF write operation failed") from e
            except Exception as e:
                logger.error(f"Unexpected error writing PDF: {e}", exc_info=True)
                raise RuntimeError("PDF write operation failed") from e
            
            logger.info(f"Successfully created PDF: {final_output_pdf} ({total_fields_filled} fields filled)")
            return final_output_pdf
            
        except (ValueError, RuntimeError, OSError, FileNotFoundError, PermissionError) as e:
            logger.error(f"PDF filling operation failed: {e}", exc_info=True)
            # Clean up partial files
            for temp_file in temp_files:
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                        logger.debug(f"Cleaned up partial file: {temp_file}")
                    except OSError as cleanup_error:
                        logger.warning(f"Failed to clean up partial file: {cleanup_error}")
            raise ValueError("PDF filling failed") from e
        except Exception as e:
            logger.error(f"Unexpected error in PDF filling: {e}", exc_info=True)
            # Clean up partial files
            for temp_file in temp_files:
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                        logger.debug(f"Cleaned up partial file: {temp_file}")
                    except OSError as cleanup_error:
                        logger.warning(f"Failed to clean up partial file: {cleanup_error}")
            raise RuntimeError("PDF filling failed") from e
            
        finally:
            # Explicit cleanup with proper error handling
            self._cleanup_resources_pypdf(pdf_reader, pdf_writer)

    def _filter_valid_annotations_pypdf(self, annotations):
        """Filter out malformed annotations for pypdf"""
        valid_annots = []
        for annot_ref in annotations:
            try:
                annot = annot_ref.get_object()
                if (annot and '/Rect' in annot and annot['/Rect'] and 
                    len(annot['/Rect']) >= 4 and 
                    all(self._is_valid_coordinate_pypdf(coord) for coord in annot['/Rect'][:4])):
                    valid_annots.append(annot)
            except (AttributeError, TypeError, ValueError, KeyError):
                continue
        return valid_annots

    def _is_valid_coordinate_pypdf(self, coord):
        """Check if coordinate is valid number for pypdf"""
        try:
            float(coord)
            return True
        except (ValueError, TypeError):
            return False

    def _sort_annotations_pypdf(self, annotations, page_num):
        """Sort annotations with error handling for pypdf"""
        try:
            return sorted(
                annotations, 
                key=lambda a: (-float(a['/Rect'][1]) if '/Rect' in a and len(a['/Rect']) > 1 else 0, 
                             float(a['/Rect'][0]) if '/Rect' in a and len(a['/Rect']) > 0 else 0)
            )
        except (ValueError, TypeError, AttributeError, KeyError) as e:
            logger.warning(f"Error sorting annotations on page {page_num}: {e}", exc_info=True)
            return annotations  # Return unsorted if sorting fails
        except Exception as e:
            logger.error(f"Unexpected error sorting annotations on page {page_num}: {e}", exc_info=True)
            return annotations  # Return unsorted if sorting fails

    def _is_fillable_field_pypdf(self, annot):
        """Check if annotation is a fillable field for pypdf"""
        try:
            return (annot and '/Subtype' in annot and annot['/Subtype'] == '/Widget' and 
                   '/T' in annot and annot['/T'])
        except (AttributeError, TypeError, KeyError):
            return False

    def _cleanup_resources_pypdf(self, pdf_reader, pdf_writer):
        """Clean up PDF resources with proper error handling for pypdf"""
        resources = [
            ("pdf_reader", pdf_reader),
            ("pdf_writer", pdf_writer)
        ]
        
        for resource_name, resource in resources:
            if resource:
                try:
                    # pypdf resources are automatically managed
                    # Just log successful cleanup
                    logger.debug(f"Cleaned up {resource_name}")
                        
                except Exception as e:
                    logger.debug(f"Error cleaning up {resource_name}: {e}")
                    # Don't raise - cleanup should be best effort

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

    def _sort_annotations(self, annotations, page_num):
        """Sort annotations with error handling"""
        try:
            return sorted(
                annotations, 
                key=lambda a: (-float(a.Rect[1]) if a.Rect and len(a.Rect) > 1 else 0, 
                             float(a.Rect[0]) if a.Rect and len(a.Rect) > 0 else 0)
            )
        except (ValueError, TypeError, AttributeError) as e:
            logger.warning(f"Error sorting annotations on page {page_num}: {e}", exc_info=True)
            return annotations  # Return unsorted if sorting fails
        except Exception as e:
            logger.error(f"Unexpected error sorting annotations on page {page_num}: {e}", exc_info=True)
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
            base_name = Path(base_path).stem  # Remove .pdf extension
            candidate = f"{base_name}_v{collision_count}.pdf"
            if not os.path.exists(candidate):
                return candidate
                
        raise RuntimeError("Unable to create unique filename after 100 attempts")

    def _cleanup_resources(self, pdf_reader, pdf_writer):
        """Clean up PDF resources with proper error handling"""
        resources = [
            ("pdf_reader", pdf_reader),
            ("pdf_writer", pdf_writer)
        ]
        
        for resource_name, resource in resources:
            if resource:
                try:
                    # Close different resource types
                    if hasattr(resource, 'stream') and resource.stream:
                        resource.stream.close()
                        logger.debug(f"Closed {resource_name} stream")
                    
                    # Close file handles
                    if hasattr(resource, 'close'):
                        resource.close()
                        logger.debug(f"Closed {resource_name}")
                        
                    # Close pdfrw specific resources
                    if hasattr(resource, 'source') and hasattr(resource.source, 'close'):
                        resource.source.close()
                        logger.debug(f"Closed {resource_name} source")
                        
                except Exception as e:
                    logger.debug(f"Error closing {resource_name}: {e}")
                    # Don't raise - cleanup should be best effort

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
        
        # Use pypdf TextStringObject for proper PDF string handling
        try:
            return TextStringObject(value)
        except (ImportError, AttributeError):
            # Fallback: only remove control characters, keep legitimate chars
            return value
