"""
Department Profile System for FireForm

This module provides pre-mapped field definitions for common first responder forms.
Profiles map human-readable field labels to internal PDF field identifiers,
enabling accurate LLM extraction without requiring manual field mapping.
"""

import json
import os
from typing import Dict, List, Optional


class ProfileLoader:
    """Loads and manages department profile configurations."""
    
    PROFILES_DIR = os.path.join(os.path.dirname(__file__))
    
    @classmethod
    def list_profiles(cls) -> List[str]:
        """
        List all available department profiles.
        
        Returns:
            List of profile names (without .json extension)
        """
        profiles = []
        for filename in os.listdir(cls.PROFILES_DIR):
            if filename.endswith('.json') and filename != '__init__.py':
                profiles.append(filename[:-5])  # Remove .json extension
        return sorted(profiles)
    
    @classmethod
    def load_profile(cls, profile_name: str) -> Dict:
        """
        Load a department profile by name.
        
        Args:
            profile_name: Name of the profile (e.g., 'fire_department')
        
        Returns:
            Dictionary containing profile configuration
        
        Raises:
            FileNotFoundError: If profile doesn't exist
            json.JSONDecodeError: If profile JSON is invalid
        """
        profile_path = os.path.join(cls.PROFILES_DIR, f"{profile_name}.json")
        
        if not os.path.exists(profile_path):
            available = cls.list_profiles()
            raise FileNotFoundError(
                f"Profile '{profile_name}' not found. "
                f"Available profiles: {', '.join(available)}"
            )
        
        with open(profile_path, 'r') as f:
            return json.load(f)
    
    @classmethod
    def get_field_mapping(cls, profile_name: str) -> Dict[str, str]:
        """
        Get the field mapping from a profile.
        
        Args:
            profile_name: Name of the profile
        
        Returns:
            Dictionary mapping human-readable labels to PDF field IDs
        """
        profile = cls.load_profile(profile_name)
        return profile.get('fields', {})
    
    @classmethod
    def get_profile_info(cls, profile_name: str) -> Dict[str, str]:
        """
        Get metadata about a profile.
        
        Args:
            profile_name: Name of the profile
        
        Returns:
            Dictionary with department, description, and example_transcript
        """
        profile = cls.load_profile(profile_name)
        return {
            'department': profile.get('department', ''),
            'description': profile.get('description', ''),
            'example_transcript': profile.get('example_transcript', '')
        }
    
    @classmethod
    def apply_profile_to_fields(cls, profile_name: str, pdf_fields: Dict) -> Dict[str, str]:
        """
        Apply a profile mapping to PDF fields, creating a mapping from
        human-readable labels to actual PDF field values.
        
        Args:
            profile_name: Name of the profile to apply
            pdf_fields: Dictionary of PDF fields extracted from the form
        
        Returns:
            Dictionary mapping human-readable labels to PDF field names
        """
        profile_mapping = cls.get_field_mapping(profile_name)
        
        # Reverse the mapping: profile maps label -> field_id
        # We need to map label -> actual_pdf_field_name
        result = {}
        
        # Convert pdf_fields keys to list for indexed access
        pdf_field_names = list(pdf_fields.keys())
        
        for label, field_id in profile_mapping.items():
            # Extract index from field_id (e.g., "textbox_0_5" -> 5)
            try:
                # Handle various field ID formats
                if '_' in field_id:
                    parts = field_id.split('_')
                    index = int(parts[-1])
                    if index < len(pdf_field_names):
                        result[label] = pdf_field_names[index]
                    else:
                        result[label] = field_id  # Fallback to field_id
                else:
                    result[label] = field_id
            except (ValueError, IndexError):
                result[label] = field_id  # Fallback to field_id
        
        return result


__all__ = ['ProfileLoader']
