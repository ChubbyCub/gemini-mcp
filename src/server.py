import base64
import io
import os

from google import genai
from mcp.server.fastmcp import FastMCP

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

SUPPORTED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "application/pdf",
}

# Use File API for files 5 MB and above to stay well within inline request limits
_INLINE_SIZE_LIMIT = 5 * 1024 * 1024

_SYSTEM_INSTRUCTION = (
    "You are an expert document digitizer. "
    "Extract all text from the provided image or PDF with high fidelity. "
    "Rules:\n"
    "- Preserve document structure: use markdown headings, lists, and tables to match the original layout.\n"
    "- Reproduce tables exactly, including all rows, columns, and numeric values.\n"
    "- Keep section order and hierarchy as it appears in the document.\n"
    "- Do not summarize, interpret, or add commentary — output only the extracted content.\n"
    "- If a section is handwritten or unclear, transcribe your best reading and append [uncertain] inline.\n"
    "- Output only the markdown. No preamble, no closing remarks."
)

mcp = FastMCP("gemini-ocr")


def _build_client() -> genai.Client:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set")
    return genai.Client(api_key=GEMINI_API_KEY)


@mcp.tool()
async def ocr_to_markdown(base64_data: str, mime_type: str) -> str:
    """Extract all text from an image or PDF using Gemini and return it as markdown.

    ## File size
    - Under 5 MB: sent as inline base64 data.
    - 5 MB or larger: automatically uploaded to the Gemini File API. No change
      needed on the caller side, but large uploads may take a moment.

    ## When to use
    Use this tool whenever the user wants to read, extract, search, or process
    text from a scanned document, image, or PDF — including invoices, reports,
    forms, lab results, or any file where text is embedded in an image.

    ## How to call
    1. Read the file from disk (binary).
    2. Base64-encode the raw bytes.
    3. Pass the encoded string and the correct MIME type here.

    ## After receiving the result
    - Present the extracted markdown directly to the user.
    - For batches, call this tool once per file then combine or summarize.
    - If the user asks to save output, write it to a .md file alongside the original.

    Args:
        base64_data: Base64-encoded contents of the image or PDF file.
        mime_type:   MIME type of the file. Supported values:
                       image/jpeg, image/png, image/gif, image/webp, application/pdf

    Returns the extracted text as a markdown string.
    """
    if mime_type not in SUPPORTED_MIME_TYPES:
        raise ValueError(
            f"Unsupported MIME type '{mime_type}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_MIME_TYPES))}"
        )

    client = _build_client()
    raw_bytes = base64.b64decode(base64_data)

    if len(raw_bytes) > _INLINE_SIZE_LIMIT:
        uploaded = client.files.upload(
            file=io.BytesIO(raw_bytes),
            config={"mime_type": mime_type},
        )
        part = {"file_data": {"mime_type": mime_type, "file_uri": uploaded.uri}}
    else:
        part = {"inline_data": {"mime_type": mime_type, "data": base64_data}}

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        config={"system_instruction": _SYSTEM_INSTRUCTION},
        contents=[{"role": "user", "parts": [part]}],
    )

    return response.text


if __name__ == "__main__":
    mcp.run(transport="stdio")
