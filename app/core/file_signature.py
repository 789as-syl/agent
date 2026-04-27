"""核心基础设施模块：file_signature。"""

from dataclasses import dataclass
from typing import BinaryIO


@dataclass
class FileSignature:
    """File signature definition."""
    magic_bytes: bytes
    offset: int = 0
    description: str = ""


COMMON_FILE_SIGNATURES: dict[str, FileSignature] = {
    "pdf": FileSignature(
        magic_bytes=b"%PDF",
        offset=0,
        description="PDF Document"
    ),
    "md": FileSignature(
        magic_bytes=b"#",
        offset=0,
        description="Markdown (text-based, heuristic)"
    ),
    "txt": FileSignature(
        magic_bytes=b"",
        offset=0,
        description="Plain Text (fallback for unknown text files)"
    ),
    "docx": FileSignature(
        magic_bytes=b"PK\x03\x04",
        offset=0,
        description="Office Open XML (DOCX)"
    ),
    "cfb": FileSignature(
        magic_bytes=b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
        offset=0,
        description="Microsoft Office Legacy Compound Binary"
    ),
}

UNSAFE_EXTENSIONS = {"exe", "bat", "cmd", "sh", "ps1", "js", "jar", "scr", "msi"}


def detect_file_type(content: bytes | BinaryIO) -> str | None:
    """
    Detect the actual file type through magic bytes.

    Args:
        content: File content (bytes or BinaryIO)

    Returns:
        Detected file type (lowercase), such as 'pdf', 'docx', 'cfb', or None if unrecognized
    """
    header = content.read(8192) if hasattr(content, "read") else content[:8192]

    if len(header) < 4:
        return None

    for file_type, sig in COMMON_FILE_SIGNATURES.items():
        if not sig.magic_bytes:
            continue
        if header[sig.offset:sig.offset + len(sig.magic_bytes)] == sig.magic_bytes:
            return file_type

    return None


def is_unsafe_extension(file_name: str) -> bool:
    """
    Check if file extension is potentially dangerous.

    Args:
        file_name: File name

    Returns:
        True if extension is potentially dangerous
    """
    import os
    ext = os.path.splitext(file_name)[1].lower().lstrip(".")
    return ext in UNSAFE_EXTENSIONS


def verify_uploaded_file(
    file_name: str,
    file_content: bytes | BinaryIO,
    allowed_extensions: set[str]
) -> tuple[bool, str | None, str]:
    """
    Comprehensive verification of uploaded file type and safety.

    Args:
        file_name: Original file name
        file_content: File content
        allowed_extensions: Set of allowed extensions

    Returns:
        (is_valid, detected_type, error_message)
    """
    import os

    ext = os.path.splitext(file_name)[1].lower().lstrip(".")

    if is_unsafe_extension(file_name):
        return False, None, f"Dangerous file type forbidden from upload: {ext}"

    if ext not in allowed_extensions:
        return False, None, f"File extension not allowed: {ext}"

    if ext == "txt":
        try:
            text_sample = file_content.read(512) if hasattr(file_content, "read") else file_content[:512]
            text_sample.decode("utf-8")
            return True, "txt", ""
        except UnicodeDecodeError:
            return False, None, "Unrecognized file type, content is not valid text"

    detected_type = detect_file_type(file_content)

    if detected_type is None:
        return False, None, "Unable to identify file type, please upload a supported PDF, Office, Markdown, HTML or text document"

    if detected_type == "docx" and ext not in ("docx",):
        return False, None, f"File content is {detected_type.upper()}, but extension is .{ext}, type mismatch"

    if detected_type == "cfb" and ext not in ("doc", "ppt"):
        return False, None, f"Legacy Office container detected, but extension is .{ext}, type mismatch"

    return True, detected_type, ""
