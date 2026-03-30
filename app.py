"""Mental Health Diagnostic — Document Processing Spike

Two-path pipeline:
  Path 1 (Sections): Upload → Partition → Select sections → PDF
  Path 2 (Structured): Upload → Partition + Extract → Select fields → PDF
"""

import json
import os
import tempfile
import streamlit as st

st.set_page_config(page_title="Assessment Report Processor", layout="wide")

# ── Lazy imports (avoid loading heavy modules before needed) ──────────────
def _import_partition():
    from pipeline.partition_job import run_partition_job
    return run_partition_job

def _import_extract():
    from pipeline.extract_job import run_extract_job
    return run_extract_job

def _import_section_pdf():
    from pdf_gen.section_report import generate_section_pdf
    return generate_section_pdf

def _import_score_pdf():
    from pdf_gen.score_report import generate_score_pdf
    return generate_score_pdf


# ── Header ────────────────────────────────────────────────────────────────
st.title("🧠 Assessment Report Processor")
st.caption("Technical Spike — Unstructured Platform API + PDF Generation")

# ── File Upload ───────────────────────────────────────────────────────────
uploaded = st.file_uploader(
    "Upload a score report (PDF, DOCX, DOC, XLSX)",
    type=["pdf", "docx", "doc", "xlsx"],
)

if not uploaded:
    st.info("Upload a document to begin processing.")
    st.stop()

# Save uploaded file to temp
tmp_dir = tempfile.mkdtemp()
tmp_path = os.path.join(tmp_dir, uploaded.name)
with open(tmp_path, "wb") as f:
    f.write(uploaded.getvalue())

st.success(f"Uploaded: **{uploaded.name}** ({len(uploaded.getvalue()) / 1024:.1f} KB)")

# ── Processing ────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    run_partition = st.button("🔍 Run Section Parser (Job 1)", use_container_width=True)
with col2:
    run_extract = st.button("📊 Run Score Extractor (Job 2)", use_container_width=True)

# ── Job 1: Partition ──────────────────────────────────────────────────────
if run_partition:
    with st.spinner("Running partition job... (this may take 30-120s)"):
        status_area = st.empty()
        def partition_progress(msg):
            status_area.text(msg)

        try:
            partition_fn = _import_partition()
            elements = partition_fn(tmp_path, progress_callback=partition_progress)
            st.session_state["partition_elements"] = elements
            st.session_state["partition_file"] = uploaded.name
            status_area.empty()
            st.success(f"✅ Partition complete — {len(elements)} elements extracted")
        except Exception as e:
            st.error(f"❌ Partition failed: {e}")

if run_extract:
    # Extraction requires partition output first
    if "partition_elements" not in st.session_state:
        with st.spinner("Step 1/2: Running partition job first..."):
            status_area = st.empty()
            def partition_first_progress(msg):
                status_area.text(f"[Partition] {msg}")
            try:
                partition_fn = _import_partition()
                elements = partition_fn(tmp_path, progress_callback=partition_first_progress)
                st.session_state["partition_elements"] = elements
                st.session_state["partition_file"] = uploaded.name
                status_area.empty()
            except Exception as e:
                st.error(f"❌ Partition failed: {e}")
                st.stop()

    with st.spinner("Running extraction via Gemini... (this may take 15-60s)"):
        status_area = st.empty()
        def extract_progress(msg):
            status_area.text(msg)

        try:
            extract_fn = _import_extract()
            result = extract_fn(
                st.session_state["partition_elements"],
                progress_callback=extract_progress,
            )
            st.session_state["extract_result"] = result
            st.session_state["extract_file"] = uploaded.name
            status_area.empty()
            st.success("✅ Extraction complete (via Gemini)")
        except Exception as e:
            st.error(f"❌ Extraction failed: {e}")

# ── Results Tabs ──────────────────────────────────────────────────────────
has_partition = "partition_elements" in st.session_state
has_extract = "extract_result" in st.session_state

if not has_partition and not has_extract:
    st.stop()

tabs = []
tab_labels = []
if has_partition:
    tab_labels.append("📄 Sections (Path 1)")
if has_extract:
    tab_labels.append("📊 Structured Data (Path 2)")
if has_partition or has_extract:
    tab_labels.append("🗂 Raw JSON")

tabs = st.tabs(tab_labels)
tab_idx = 0

# ── Tab: Sections ─────────────────────────────────────────────────────────
if has_partition:
    with tabs[tab_idx]:
        elements = st.session_state["partition_elements"]
        st.subheader(f"Document Sections ({len(elements)} elements)")

        # Group by type for overview
        type_counts = {}
        for e in elements:
            t = e.get("type", "Unknown") if isinstance(e, dict) else "Unknown"
            type_counts[t] = type_counts.get(t, 0) + 1
        st.write("**Element types:**", type_counts)

        st.divider()

        # Section selection
        st.write("**Select sections to include in the PDF:**")
        selected = []
        for i, elem in enumerate(elements):
            if not isinstance(elem, dict):
                continue
            etype = elem.get("type", "Unknown")
            text = elem.get("text", "")
            preview = text[:120] + "..." if len(text) > 120 else text
            label = f"[{etype}] {preview}"

            if st.checkbox(label, value=True, key=f"sec_{i}"):
                selected.append(i)

        if selected:
            st.write(f"**{len(selected)} sections selected**")
            if st.button("📥 Generate Section PDF", key="gen_section_pdf"):
                with st.spinner("Generating PDF..."):
                    try:
                        gen_fn = _import_section_pdf()
                        out_path = os.path.join(tmp_dir, "section_report.pdf")
                        gen_fn(elements, selected, st.session_state["partition_file"], out_path)
                        with open(out_path, "rb") as pdf_file:
                            st.session_state["section_pdf_bytes"] = pdf_file.read()
                    except Exception as e:
                        st.error(f"PDF generation failed: {e}")

            if "section_pdf_bytes" in st.session_state:
                st.download_button(
                    "⬇️ Download Section Report PDF",
                    data=st.session_state["section_pdf_bytes"],
                    file_name="section_report.pdf",
                    mime="application/pdf",
                    key="dl_section_pdf",
                )
    tab_idx += 1

# ── Tab: Structured Data ─────────────────────────────────────────────────
if has_extract:
    with tabs[tab_idx]:
        result = st.session_state["extract_result"]
        st.subheader("Extracted Structured Data")

        # Normalize: handle list wrapper
        data = result
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and ("examinee_information" in item or "full_scale_iq" in item or "subtest_scores" in item):
                    data = item
                    break
            else:
                data = data[0] if data else {}

        # Section toggles
        st.write("**Select sections to include in the PDF:**")
        section_keys = {
            "examinee_information": "Examinee Information",
            "test_administration": "Test Administration",
            "full_scale_iq": "Full Scale IQ",
            "subtest_scores": "Subtest Scores",
            "composite_scores": "Composite / Index Scores",
            "index_strengths_weaknesses": "Strengths & Weaknesses",
            "pairwise_comparisons": "Pairwise Comparisons",
            "process_scores": "Process Scores",
        }

        show_sections = {}
        for key, label in section_keys.items():
            has_data = key in data and data[key]
            count = ""
            if isinstance(data.get(key), list):
                count = f" ({len(data[key])} items)"
            elif isinstance(data.get(key), dict):
                filled = sum(1 for v in data[key].values() if v is not None)
                count = f" ({filled} fields)"

            show_sections[key] = st.checkbox(
                f"{label}{count}",
                value=bool(has_data),
                disabled=not has_data,
                key=f"score_{key}",
            )

        # Preview selected data
        for key, label in section_keys.items():
            if show_sections.get(key) and key in data and data[key]:
                with st.expander(f"Preview: {label}", expanded=False):
                    if isinstance(data[key], list):
                        st.dataframe(data[key])
                    else:
                        st.json(data[key])

        if st.button("📥 Generate Score Report PDF", key="gen_score_pdf"):
            with st.spinner("Generating PDF..."):
                try:
                    gen_fn = _import_score_pdf()
                    out_path = os.path.join(tmp_dir, "score_report.pdf")
                    gen_fn(data, show_sections, st.session_state["extract_file"], out_path)
                    with open(out_path, "rb") as pdf_file:
                        st.session_state["score_pdf_bytes"] = pdf_file.read()
                except Exception as e:
                    st.error(f"PDF generation failed: {e}")

        if "score_pdf_bytes" in st.session_state:
            st.download_button(
                "⬇️ Download Score Report PDF",
                data=st.session_state["score_pdf_bytes"],
                file_name="score_report.pdf",
                mime="application/pdf",
                key="dl_score_pdf",
            )
    tab_idx += 1

# ── Tab: Raw JSON ─────────────────────────────────────────────────────────
with tabs[tab_idx]:
    st.subheader("Raw API Responses")

    if has_partition:
        with st.expander("Partition Elements (Job 1)", expanded=False):
            st.json(st.session_state["partition_elements"])

        # Save raw output
        raw_partition_path = os.path.join("output", "partition_elements.json")
        os.makedirs("output", exist_ok=True)
        with open(raw_partition_path, "w") as f:
            json.dump(st.session_state["partition_elements"], f, indent=2, default=str)
        st.caption(f"Saved to {raw_partition_path}")

    if has_extract:
        with st.expander("Extraction Result (Job 2)", expanded=False):
            st.json(st.session_state["extract_result"])

        raw_extract_path = os.path.join("output", "extraction_result.json")
        with open(raw_extract_path, "w") as f:
            json.dump(st.session_state["extract_result"], f, indent=2, default=str)
        st.caption(f"Saved to {raw_extract_path}")
