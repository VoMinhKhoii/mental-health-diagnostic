"""Unstructured Platform API client setup."""

import os
from dotenv import load_dotenv
from unstructured_client import UnstructuredClient

load_dotenv()


def _get_secret(key: str) -> str | None:
    """Read from Streamlit secrets first, then env vars."""
    try:
        import streamlit as st
        return st.secrets.get(key)
    except Exception:
        return os.getenv(key)


def get_client() -> UnstructuredClient:
    api_key = _get_secret("UNSTRUCTURED_API_KEY")
    api_url = os.getenv("UNSTRUCTURED_API_URL", "https://platform.unstructuredapp.io")

    if not api_key or api_key == "<your-api-key>":
        raise ValueError("Set UNSTRUCTURED_API_KEY in .env or Streamlit secrets")

    return UnstructuredClient(api_key_auth=api_key, server_url=api_url)


def detect_content_type(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(ext, "application/octet-stream")
