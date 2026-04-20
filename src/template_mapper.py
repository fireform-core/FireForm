class TemplateMapper:
    def __init__(self, mapping_config: dict):
        """
        mapping_config: dict mapping JSON fields → PDF field names
        """
        self.mapping = mapping_config

    def map_to_pdf_fields(self, structured_data: dict) -> dict:
        mapped_data = {}

        for json_field, pdf_field in self.mapping.items():
            if json_field in structured_data:
                mapped_data[pdf_field] = structured_data[json_field]

        return mapped_data
