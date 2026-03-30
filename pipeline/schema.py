"""WAIS-V extraction schema for the Structured Data Extractor node.

Key changes from the original:
- Most fields are NOT required (resilient to missing data)
- Added extraction_guidance for better LLM context
- Schema is a Python dict (easier to maintain than a JSON string)
"""


EXTRACTION_GUIDANCE = """This is a psychological assessment score report, likely from the
Wechsler Adult Intelligence Scale (WAIS-V, 2024) or similar standardised test generated
by Pearson Q-Global or another scoring platform.

Extract ALL numerical scores, demographics, and statistical analyses from the document.
Pay special attention to:
- Tables containing subtest scores (raw scores, scaled scores, percentiles)
- Composite/Index score summary tables
- Full Scale IQ (FSIQ) score and confidence interval
- Pairwise comparison tables (statistical significance)
- Strengths and weaknesses analysis tables
- Process scores and error analyses

If a field is not present in the document, omit it (return null).
If a table is partially readable, extract what you can and skip unreadable cells.
Scores are always integers or small decimals. Percentiles range 0-100. Scaled scores
typically range 1-19. Composite/IQ scores typically range 40-160."""


WAISV_SCHEMA = {
    "type": "object",
    "properties": {
        "examinee_information": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Full name of the examinee"},
                "examinee_id": {"type": "string", "description": "Unique identifier for the examinee"},
                "date_of_birth": {"type": "string", "description": "Examinee's date of birth"},
                "sex": {"type": "string", "description": "Examinee's sex"},
                "race_ethnicity": {"type": "string", "description": "Examinee's race or ethnicity"},
                "years_of_education": {"type": "integer", "description": "Total years of formal education"},
                "primary_language": {"type": "string", "description": "Primary language spoken"},
                "handedness": {"type": "string", "description": "Dominant hand preference"},
            },
            "additionalProperties": True,
            "description": "Demographic and identifying information about the test examinee",
        },
        "test_administration": {
            "type": "object",
            "properties": {
                "date_of_testing": {"type": "string", "description": "Date when the test was administered"},
                "date_of_report": {"type": "string", "description": "Date when the report was generated"},
                "age_at_testing": {"type": "string", "description": "Examinee's age at time of testing"},
                "examiner_name": {"type": "string", "description": "Name of the examiner"},
                "is_retest": {"type": "boolean", "description": "Whether this is a retest administration"},
            },
            "additionalProperties": True,
            "description": "Information about when and how the test was administered",
        },
        "subtest_scores": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "Cognitive domain assessed"},
                    "subtest_name": {"type": "string", "description": "Full name of the subtest"},
                    "abbreviation": {"type": "string", "description": "Standard abbreviation"},
                    "total_raw_score": {"type": "integer", "description": "Raw score obtained"},
                    "scaled_score": {"type": "integer", "description": "Age-adjusted scaled score"},
                    "percentile_rank": {"type": "integer", "description": "Percentile rank"},
                    "reference_group_scaled_score": {"type": "integer", "description": "Scaled score vs reference group ages 20-34"},
                    "standard_error_of_measurement": {"type": "number", "description": "Standard error of measurement"},
                    "is_primary": {"type": "boolean", "description": "Whether this subtest derives the FSIQ"},
                },
                "additionalProperties": True,
            },
            "description": "Individual subtest performance scores",
        },
        "composite_scores": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "composite_name": {"type": "string", "description": "Full name of the composite index"},
                    "abbreviation": {"type": "string", "description": "Standard abbreviation"},
                    "sum_of_scaled_scores": {"type": "integer", "description": "Sum of contributing subtest scaled scores"},
                    "composite_score": {"type": "integer", "description": "Standard score for the composite"},
                    "percentile_rank": {"type": "integer", "description": "Percentile rank"},
                    "confidence_interval_lower": {"type": "integer", "description": "Lower bound of 95% CI"},
                    "confidence_interval_upper": {"type": "integer", "description": "Upper bound of 95% CI"},
                    "qualitative_description": {"type": "string", "description": "Qualitative interpretation"},
                    "standard_error_of_measurement": {"type": "number", "description": "Standard error of measurement"},
                    "is_primary": {"type": "boolean", "description": "Whether this is a primary composite"},
                },
                "additionalProperties": True,
            },
            "description": "Composite index scores derived from subtests",
        },
        "full_scale_iq": {
            "type": "object",
            "properties": {
                "score": {"type": "integer", "description": "Full Scale IQ standard score"},
                "percentile_rank": {"type": "integer", "description": "Percentile rank for FSIQ"},
                "confidence_interval_lower": {"type": "integer", "description": "Lower bound of 95% CI"},
                "confidence_interval_upper": {"type": "integer", "description": "Upper bound of 95% CI"},
                "qualitative_description": {"type": "string", "description": "Qualitative interpretation of FSIQ"},
            },
            "additionalProperties": True,
            "description": "Overall Full Scale IQ score and interpretation",
        },
        "index_strengths_weaknesses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index_abbreviation": {"type": "string"},
                    "index_score": {"type": "integer"},
                    "comparison_score": {"type": "number"},
                    "difference": {"type": "number"},
                    "critical_value": {"type": "number"},
                    "is_strength": {"type": "boolean"},
                    "is_weakness": {"type": "boolean"},
                    "base_rate": {"type": "string"},
                },
                "additionalProperties": True,
            },
            "description": "Statistical analysis of index-level strengths and weaknesses",
        },
        "pairwise_comparisons": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "comparison_type": {"type": "string"},
                    "score_1_name": {"type": "string"},
                    "score_1_value": {"type": "integer"},
                    "score_2_name": {"type": "string"},
                    "score_2_value": {"type": "integer"},
                    "difference": {"type": "integer"},
                    "critical_value": {"type": "number"},
                    "is_significant": {"type": "boolean"},
                    "base_rate": {"type": "string"},
                },
                "additionalProperties": True,
            },
            "description": "Statistical comparisons between pairs of indices or subtests",
        },
        "process_scores": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "process_score_name": {"type": "string"},
                    "abbreviation": {"type": "string"},
                    "raw_score": {"type": "integer"},
                    "scaled_score": {"type": "integer"},
                    "base_rate": {"type": "string"},
                },
                "additionalProperties": True,
            },
            "description": "Additional process-level scores and error analyses",
        },
    },
    "additionalProperties": True,
}


def get_extraction_schema() -> dict:
    """Return the schema config for the structured data extractor node."""
    import json
    return {
        "json_schema": json.dumps(WAISV_SCHEMA),
        "extraction_guidance": EXTRACTION_GUIDANCE,
    }
