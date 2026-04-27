"""Download and unpack a workspace-local Docling runtime bundle under .vendor/."""

from __future__ import annotations

import argparse
import json
import shutil
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

NON_PDF_PACKAGES: list[tuple[str, str | None]] = [
    ("docling", "py3-none-any.whl"),
    ("docling-core", "py3-none-any.whl"),
    ("docling-parse", "cp313-cp313-win_amd64.whl"),
    ("docling-ibm-models", "py3-none-any.whl"),
    ("marko", "py3-none-any.whl"),
    ("beautifulsoup4", "py3-none-any.whl"),
    ("soupsieve", "py3-none-any.whl"),
    ("python-docx", "py3-none-any.whl"),
    ("python-pptx", "py3-none-any.whl"),
    ("pylatexenc", None),
    ("lxml", "cp313-cp313-win_amd64.whl"),
    ("numpy", "cp313-cp313-win_amd64.whl"),
    ("pandas", "cp313-cp313-win_amd64.whl"),
    ("jsonschema", "py3-none-any.whl"),
    ("jsonschema-specifications", "py3-none-any.whl"),
    ("jsonref", "py3-none-any.whl"),
    ("referencing", "py3-none-any.whl"),
    ("rpds-py", "cp313-cp313-win_amd64.whl"),
    ("attrs", "py3-none-any.whl"),
    ("tabulate", "py3-none-any.whl"),
    ("latex2mathml", "py3-none-any.whl"),
    ("typer", "py3-none-any.whl"),
    ("defusedxml", "py2.py3-none-any.whl"),
    ("pyyaml", "cp313-cp313-win_amd64.whl"),
    ("transformers", "py3-none-any.whl"),
    ("huggingface_hub", "py3-none-any.whl"),
    ("safetensors", "cp38-abi3-win_amd64.whl"),
    ("tokenizers", "cp39-abi3-win_amd64.whl"),
    ("tqdm", "py3-none-any.whl"),
    ("regex", "cp313-cp313-win_amd64.whl"),
    ("packaging", "py3-none-any.whl"),
    ("filelock", "py3-none-any.whl"),
    ("fsspec", "py3-none-any.whl"),
    ("hf-xet", "cp37-abi3-win_amd64.whl"),
    ("semchunk", "py3-none-any.whl"),
    ("tree-sitter", "cp313-cp313-win_amd64.whl"),
    ("tree-sitter-python", "cp310-abi3-win_amd64.whl"),
    ("tree-sitter-c", "cp310-abi3-win_amd64.whl"),
    ("tree-sitter-javascript", "cp310-abi3-win_amd64.whl"),
    ("tree-sitter-typescript", "cp39-abi3-win_amd64.whl"),
    ("pywin32", "cp313-cp313-win_amd64.whl"),
    ("pypdfium2", "py3-none-win_amd64.whl"),
]

PDF_EXTRA_PACKAGES: list[tuple[str, str | None]] = [
    ("torch", "cp313-cp313-win_amd64.whl"),
    ("torchvision", "cp313-cp313-win_amd64.whl"),
]


def _pypi_metadata(package: str) -> dict:
    with urllib.request.urlopen(f"https://pypi.org/pypi/{package}/json", timeout=60) as response:
        return json.load(response)


def _choose_file(metadata: dict, preferred_suffix: str | None) -> dict:
    version = metadata["info"]["version"]
    files = [item for item in metadata["releases"][version] if item["filename"].endswith((".whl", ".tar.gz"))]
    if preferred_suffix:
        for item in files:
            if preferred_suffix in item["filename"]:
                return item
    for item in files:
        if item["filename"].endswith(".whl") and "py3-none-any" in item["filename"]:
            return item
    for item in files:
        if item["filename"].endswith(".whl"):
            return item
    if files:
        return files[0]
    raise RuntimeError(f"No downloadable artifacts found for {metadata['info']['name']}")


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            urllib.request.urlretrieve(url, destination)
            return
        except Exception as exc:  # pragma: no cover - network retry path
            last_error = exc
            time.sleep(attempt)
    if last_error is not None:
        raise last_error


def _unpack(artifact: Path, vendor_root: Path) -> None:
    if artifact.suffix == ".whl" or artifact.name.endswith(".whl"):
        with zipfile.ZipFile(artifact) as archive:
            archive.extractall(vendor_root)
        return
    if artifact.name.endswith(".tar.gz"):
        with tarfile.open(artifact, "r:gz") as archive:
            members = archive.getmembers()
            top_level = members[0].name.split("/", 1)[0] if members else None
            for member in members:
                original_name = member.name
                if top_level and original_name.startswith(f"{top_level}/"):
                    member.name = original_name.split("/", 1)[1]
                if not member.name:
                    continue
                destination = vendor_root / member.name
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                extracted = archive.extractfile(member)
                if extracted is None:
                    continue
                destination.write_bytes(extracted.read())
        return
    raise RuntimeError(f"Unsupported artifact type: {artifact}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor-root", type=Path, default=Path(".vendor/docling_runtime"))
    parser.add_argument("--download-dir", type=Path, default=Path(".tmp/docling_vendor_downloads"))
    parser.add_argument("--include-pdf-stack", action="store_true")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    packages = list(NON_PDF_PACKAGES)
    if args.include_pdf_stack:
        packages.extend(PDF_EXTRA_PACKAGES)

    if args.reset and args.vendor_root.exists():
        shutil.rmtree(args.vendor_root, ignore_errors=True)
    args.vendor_root.mkdir(parents=True, exist_ok=True)

    for package, preferred_suffix in packages:
        metadata = _pypi_metadata(package)
        artifact_info = _choose_file(metadata, preferred_suffix)
        artifact_path = args.download_dir / artifact_info["filename"]
        _download(artifact_info["url"], artifact_path)
        _unpack(artifact_path, args.vendor_root)
        print(f"[docling-vendor] added {artifact_info['filename']}")

    print(f"[docling-vendor] completed -> {args.vendor_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
