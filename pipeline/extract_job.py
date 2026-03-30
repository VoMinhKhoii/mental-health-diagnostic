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
    """Convert partitioned elements into a structured text document for the LLM."""
    parts = []
    for elem in elements:
        if not isinstance(elem, dict):
            continue

        etype = elem.get("type", "")
        text = elem.get("text", "")

        # Use HTML representation for tables (preserves structure)
        meta = elem.get("metadata", {})
        if isinstance(meta, dict) and meta.get("text_as_html") and etype == "Table":
            parts.append(f"[TABLE]\n{meta['text_as_html']}\n[/TABLE]")
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

Below is a partitioned document. Extract all data matching the JSON schema provided.
Return ONLY valid JSON matching the schema. If a field is not found, use null.

--- DOCUMENT START ---
{document_text}
--- DOCUMENT END ---

--- JSON SCHEMA ---
{json.dumps(WAISV_SCHEMA, indent=2)}
--- END SCHEMA ---

Extract the data and return valid JSON:"""

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
