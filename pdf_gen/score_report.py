"""Path 2: Generate PDF from structured score data."""

import os
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML


TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")


def generate_score_pdf(
    data: dict,
    show_sections: dict[str, bool],
    source_filename: str,
    output_path: str,
) -> str:
    """Generate a PDF from structured extraction data.

    Args:
        data: The structured JSON from Job 2
        show_sections: Dict of section_key → bool (which sections to include)
        source_filename: Original uploaded filename
        output_path: Where to save the PDF
    """
    # Handle case where data is a list (Unstructured may wrap in array)
    if isinstance(data, list):
        # Find the structured extraction result
        for item in data:
            if isinstance(item, dict) and ("examinee_information" in item or "full_scale_iq" in item):
                data = item
                break
        else:
            # Try first item
            data = data[0] if data else {}

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    template = env.get_template("score_report.html")

    html_content = template.render(
        source_file=source_filename,
        data=data,
        show_examinee=show_sections.get("examinee_information", True),
        show_administration=show_sections.get("test_administration", True),
        show_fsiq=show_sections.get("full_scale_iq", True),
        show_subtests=show_sections.get("subtest_scores", True),
        show_composites=show_sections.get("composite_scores", True),
        show_strengths=show_sections.get("index_strengths_weaknesses", True),
        show_pairwise=show_sections.get("pairwise_comparisons", True),
        show_process=show_sections.get("process_scores", True),
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    HTML(string=html_content).write_pdf(output_path)
    return output_path
