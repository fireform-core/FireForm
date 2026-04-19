class ExtractionValidator:
    FIELD_WEIGHTS = {
        "location": 30,
        "time": 20,
        "severity": 30,
        "description": 20
    }

    def validate(self, data: dict):
        missing_fields = []
        confidence_score = 100

        for field, weight in self.FIELD_WEIGHTS.items():
            value = data.get(field)

            if value is None or value == "" or value == "-1":
                missing_fields.append(field)
                confidence_score -= weight

        confidence_score = max(confidence_score, 0)

        requires_review = confidence_score < 70

        return {
            "requires_review": requires_review,
            "missing_fields": missing_fields,
            "confidence_score": confidence_score
        }