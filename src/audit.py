"""Audit module for tracking PDF generation metadata."""
import json
import os
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path


class AuditMetadata:
    """Handles collection and storage of audit metadata for PDF generation."""

    def __init__(self):
        """Initialize audit metadata tracker."""
        self.metadata: Dict[str, Any] = {}

    def set_metadata(
        self,
        timestamp: Optional[str] = None,
        gps_latitude: Optional[float] = None,
        gps_longitude: Optional[float] = None,
        device_id: Optional[str] = None,
        officer_name: Optional[str] = None,
    ) -> None:
        """
        Set audit metadata for PDF generation.

        Args:
            timestamp: ISO format timestamp of PDF generation
            gps_latitude: GPS latitude coordinate
            gps_longitude: GPS longitude coordinate
            device_id: Unique device identifier
            officer_name: Name of the officer generating the PDF
        """
        if timestamp is None:
            timestamp = datetime.utcnow().isoformat()

        self.metadata = {
            "timestamp": timestamp,
            "gps_latitude": gps_latitude,
            "gps_longitude": gps_longitude,
            "device_id": device_id,
            "officer_name": officer_name,
        }

    def get_metadata(self) -> Dict[str, Any]:
        """Get current audit metadata."""
        return self.metadata.copy()

    def save_to_json(
        self, pdf_path: str, metadata_dir: Optional[str] = None
    ) -> str:
        """
        Save audit metadata to a JSON file alongside the PDF.

        Args:
            pdf_path: Path to the generated PDF file
            metadata_dir: Optional directory to save metadata (defaults to same as PDF)

        Returns:
            Path to the saved metadata JSON file
        """
        if not self.metadata:
            raise ValueError("No metadata set. Call set_metadata() first.")

        pdf_path_obj = Path(pdf_path)
        if metadata_dir:
            metadata_path = Path(metadata_dir) / f"{pdf_path_obj.stem}_audit.json"
        else:
            metadata_path = pdf_path_obj.parent / f"{pdf_path_obj.stem}_audit.json"

        # Ensure directory exists
        metadata_path.parent.mkdir(parents=True, exist_ok=True)

        # Save metadata to JSON
        with open(metadata_path, "w") as f:
            json.dump(self.metadata, f, indent=2)

        return str(metadata_path)

    def load_from_json(self, json_path: str) -> None:
        """
        Load audit metadata from a JSON file.

        Args:
            json_path: Path to the audit metadata JSON file
        """
        with open(json_path, "r") as f:
            self.metadata = json.load(f)

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary format."""
        return self.get_metadata()

    def to_json_string(self) -> str:
        """Convert metadata to JSON string."""
        return json.dumps(self.metadata, indent=2)
