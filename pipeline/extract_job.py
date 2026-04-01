"""Job 2: Structured Data Extraction via Google Gemini.

Uses Unstructured partition output (Job 1) as input, then calls Gemini
directly to extract structured score data matching the WAIS-V schema.

Architecture: Unstructured (partition) → Gemini (extraction)
This decouples the LLM step from Unstructured's platform, giving us
provider flexibility (Gemini has a free tier).
"""

import json
import os

from google import genai
from google.genai import types
from dotenv import load_dotenv

from .schema import WAISV_SCHEMA, EXTRACTION_GUIDANCE

load_dotenv()


def _elements_to_text(elements: list[dict]) -> str:
    """Convert partitioned elements into a structured text document for the LLM.

    For tables, sends BOTH the HTML representation (for structure) and plain
    text (for accurate cell values), since the OCR in text_as_html can have
    truncated scores, garbled abbreviations, and missing values.
    """
    parts = []
    for elem in elements:
        if not isinstance(elem, dict):
            continue

        etype = elem.get("type", "")
        text = elem.get("text", "")

        meta = elem.get("metadata", {})
        if etype == "Table" and isinstance(meta, dict) and meta.get("text_as_html"):
            # Send both representations so the LLM can cross-reference
            # HTML structure with the more accurate plain-text values
            html = meta["text_as_html"]
            plain = text.strip()
            table_block = f"[TABLE_HTML]\n{html}\n[/TABLE_HTML]"
            if plain:
                table_block += f"\n[TABLE_TEXT]\n{plain}\n[/TABLE_TEXT]"
            parts.append(table_block)
        elif etype == "PageBreak":
            parts.append("--- PAGE BREAK ---")
        elif text.strip():
            parts.append(f"[{etype}] {text}")

    return "\n\n".join(parts)


def run_extract_job(
    elements: list[dict],
    progress_callback=None,
    model_name: str = "gemini-3-flash-preview",
) -> dict:
    """Extract structured data from partitioned elements using Gemini.

    Args:
        elements: Partition output from Job 1 (run_partition_job)
        progress_callback: Optional status callback
        model_name: Gemini model to use
    """
    def _get_secret(key: str) -> str | None:
        try:
            import streamlit as st
            return st.secrets.get(key)
        except Exception:
            return os.getenv(key)

    api_key = (
        _get_secret("GOOGLE_GEMENI_API_KEY")
        or _get_secret("GOOGLE_GEMINI_API_KEY")
    )
    if not api_key:
        raise ValueError("Set GOOGLE_GEMENI_API_KEY or GOOGLE_GEMINI_API_KEY in .env or Streamlit secrets")

    client = genai.Client(api_key=api_key)

    if progress_callback:
        progress_callback("Preparing document text from partition output...")

    document_text = _elements_to_text(elements)

    if progress_callback:
        progress_callback(f"Document text: {len(document_text)} chars from {len(elements)} elements")

    prompt = f"""You are an expert at extracting structured data from psychological assessment reports.

{EXTRACTION_GUIDANCE}

Below is a partitioned document. Tables are provided in TWO formats:
- [TABLE_HTML]: HTML table structure (use for column/row layout)
- [TABLE_TEXT]: Plain text version (use for accurate cell values when HTML seems corrupted)

When values differ between HTML and text versions, PREFER the plain text values — the HTML
OCR can truncate leading digits (e.g. showing "24" instead of "124") or garble text.

IMPORTANT: You MUST extract ALL of the following sections if present in the document:
1. examinee_information (name, DOB, sex, etc.)
2. test_administration (dates, examiner, etc.)
3. subtest_scores (ALL subtests — typically 10-20 rows)
4. composite_scores (ALL composites — typically 5 rows: VCI, VSI, FRI, WMI, PSI)
5. full_scale_iq (FSIQ score, percentile, CI — this is critical)
6. index_strengths_weaknesses (S/W analysis for each index)
7. pairwise_comparisons (index vs index comparisons with significance)
8. process_scores (BDN, DSF, DSB, etc.)

Return ONLY valid JSON matching the schema. If a field is not found, use null.

--- DOCUMENT START ---
{document_text}
--- DOCUMENT END ---

--- JSON SCHEMA ---
{json.dumps(WAISV_SCHEMA, indent=2)}
--- END SCHEMA ---

Extract ALL sections listed above and return valid JSON:"""

    if progress_callback:
        progress_callback(f"Calling Gemini ({model_name})...")

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )

    if progress_callback:
        progress_callback("Parsing Gemini response...")

    raw_text = response.text
    result = _parse_json_response(raw_text)

    if result is None:
        # Retry once with a repair prompt
        if progress_callback:
            progress_callback("JSON malformed — asking Gemini to repair...")
        repair_response = client.models.generate_content(
            model=model_name,
            contents=f"The following JSON is malformed. Fix it and return ONLY valid JSON, nothing else:\n\n{raw_text}",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
            ),
        )
        result = _parse_json_response(repair_response.text)

    if result is None:
        raise ValueError(f"Failed to parse Gemini response as JSON. First 500 chars: {raw_text[:500]}")

    # Completeness check: retry if critical sections are missing
    expected_keys = {"full_scale_iq", "composite_scores", "subtest_scores",
                     "pairwise_comparisons", "index_strengths_weaknesses"}
    missing = expected_keys - set(result.keys())
    # Also check for sections that exist but are empty/incomplete
    if isinstance(result.get("composite_scores"), list) and len(result["composite_scores"]) < 3:
        missing.add("composite_scores")

    if missing and isinstance(result, dict):
        if progress_callback:
            progress_callback(f"Missing sections ({', '.join(missing)}) — retrying full extraction...")
        retry_response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
            ),
        )
        retry_result = _parse_json_response(retry_response.text)
        if retry_result and isinstance(retry_result, dict):
            # Merge: use retry for missing sections, keep original for existing
            for key in expected_keys:
                if key in retry_result and retry_result[key]:
                    if key not in result or not result[key]:
                        result[key] = retry_result[key]
                    # Replace incomplete composites
                    elif key == "composite_scores" and isinstance(retry_result[key], list) and len(retry_result[key]) > len(result.get(key, [])):
                        result[key] = retry_result[key]

    if progress_callback:
        progress_callback("Extraction complete")

    return result


def _parse_json_response(text: str) -> dict | None:
    """Try multiple strategies to parse JSON from LLM response."""
    # Strategy 1: direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    # Strategy 2: strip markdown fences
    cleaned = text.strip()
    for prefix in ("```json", "```"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    try:
        return json.loads(cleaned.strip())
    except (json.JSONDecodeError, TypeError):
        pass

    # Strategy 3: find the outermost { ... } block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    return None
