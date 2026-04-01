"""Path 1: Generate PDF from selected document sections."""

import os
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML


TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")


def generate_section_pdf(
    sections: list[dict],
    selected_indices: list[int],
    source_filename: str,
    output_path: str,
) -> str:
    """Generate a PDF from selected sections.

    Args:
        sections: All partitioned elements from Job 1
        selected_indices: Indices of sections to include
        source_filename: Original uploaded filename
        output_path: Where to save the PDF
    """
    selected = [sections[i] for i in selected_indices if i < len(sections)]

    # Normalize section data
    normalized = []
    for s in selected:
        elem = {
            "type": s.get("type", "Unknown"),
            "text": s.get("text", ""),
            "text_as_html": None,
        }
        # Unstructured returns table HTML in metadata.text_as_html
        meta = s.get("metadata", {})
        if isinstance(meta, dict) and meta.get("text_as_html"):
            elem["text_as_html"] = meta["text_as_html"]
        normalized.append(elem)

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)
    template = env.get_template("section_report.html")

    html_content = template.render(
        title="Assessment Report — Selected Sections",
        source_file=source_filename,
        section_count=len(normalized),
        total_count=len(sections),
        sections=normalized,
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    HTML(string=html_content).write_pdf(output_path)
    return output_path
