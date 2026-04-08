class ExtractionValidator:
    REQUIRED_FIELDS = ["location", "time", "severity", "description"]

    def validate(self, data: dict):
        missing_fields = []
        confidence_score = 100

        for field in self.REQUIRED_FIELDS:
            value = data.get(field)

            if value is None or value == "" or value == "-1":
                missing_fields.append(field)
                confidence_score -= 25

        requires_review = len(missing_fields) > 0

        return {
            "requires_review": requires_review,
            "missing_fields": missing_fields,
            "confidence_score": confidence_score
        }