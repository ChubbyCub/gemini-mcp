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

# Gemini inline_data limit is 20 MB of raw bytes
_INLINE_SIZE_LIMIT = 20 * 1024 * 1024

_SYSTEM_INSTRUCTION = (
    "Extract text from documents into markdown. "
    "Preserve structure (headings, lists, tables). "
    "Return only the extracted content, no commentary."
)

mcp = FastMCP("gemini-ocr")


def _build_client() -> genai.Client:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set")
    return genai.Client(api_key=GEMINI_API_KEY)


@mcp.tool()
async def ocr_to_markdown(base64_data: str, mime_type: str) -> str:
    """Extract all text from an image or PDF and return it as well-formatted markdown.

    Claude should read the file from the workspace, base64-encode its contents,
    and pass them here along with the correct MIME type.

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
