"""Job 1: Partition-only — extract document sections without LLM extraction.

Returns the raw partitioned elements (sections, tables, text blocks).
Each element represents a potential "section" the user can select/deselect.
"""

import json
import os
import time

from unstructured_client.models import operations, shared

from .client import get_client, detect_content_type


PARTITION_SETTINGS = {
    "strategy": "hi_res",
    "infer_table_structure": True,
    "include_page_breaks": True,
    "coordinates": False,
    "extract_image_block_types": ["Table", "Image", "Figure"],
}


def run_partition_job(file_path: str, progress_callback=None) -> list[dict]:
    """Run partition-only job on a document. Returns list of elements."""
    client = get_client()

    with open(file_path, "rb") as f:
        file_content = f.read()

    filename = os.path.basename(file_path)
    content_type = detect_content_type(filename)

    job_config = {
        "job_nodes": [
            {
                "name": "Partitioner",
                "type": "partition",
                "subtype": "unstructured_api",
                "settings": PARTITION_SETTINGS,
            }
        ]
    }

    if progress_callback:
        progress_callback("Creating partition job...")

    create_response = client.jobs.create_job(
        request=operations.CreateJobRequest(
            body_create_job=shared.BodyCreateJob(
                request_data=json.dumps(job_config),
                input_files=[
                    shared.InputFiles(
                        content=file_content,
                        file_name=filename,
                        content_type=content_type,
                    )
                ],
            )
        )
    )

    job_id = create_response.job_information.id
    if progress_callback:
        progress_callback(f"Job created: {job_id}")

    # Poll for completion
    start_time = time.time()
    while True:
        status_response = client.jobs.get_job(
            request=operations.GetJobRequest(job_id=job_id)
        )
        status = status_response.job_information.status
        elapsed = int(time.time() - start_time)

        if progress_callback:
            progress_callback(f"Status: {status} ({elapsed}s)")

        if status == "COMPLETED":
            break
        elif status in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"Partition job {status.lower()} after {elapsed}s")

        time.sleep(3)

    # Download output
    # Try output_node_files first, fall back to input_file_ids
    file_id = None
    if hasattr(create_response.job_information, "output_node_files") and create_response.job_information.output_node_files:
        file_id = create_response.job_information.output_node_files[0].file_id
    if not file_id:
        file_id = create_response.job_information.input_file_ids[0]

    download_response = client.jobs.download_job_output(
        request=operations.DownloadJobOutputRequest(
            job_id=job_id, file_id=file_id
        )
    )

    elements = download_response.any if hasattr(download_response, "any") else download_response
    if progress_callback:
        progress_callback(f"Done — {len(elements)} elements extracted")

    return elements
