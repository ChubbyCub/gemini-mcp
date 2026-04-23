import asyncio
import base64
import os
import re
import tempfile
from dataclasses import dataclass
from typing import List, Optional

from google import genai
from mcp.server.fastmcp import FastMCP
from pdf2image import convert_from_path

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

# PDF-to-image settings (mirrors zerox defaults)
_DPI = 300
_FORMAT = "png"
_PAGE_HEIGHT = 1056  # px, width auto-scaled
_THREAD_COUNT = 4
_CONCURRENCY = 5

_SYSTEM_PROMPT = (
    "Convert the following document page to markdown. "
    "Return only the markdown with no explanation text. "
    "Do not include delimiters like ```markdown or ```html.\n\n"
    "RULES:\n"
    "- Include all information on the page. Do not exclude headers, footers, or subtext.\n"
    "- Reproduce tables exactly, including all rows, columns, and numeric values.\n"
    "- Charts and infographics must be interpreted into markdown. Prefer table format when applicable.\n"
    "- Page numbers should be wrapped in brackets. Ex: <page_number>14<page_number>\n"
    "- Watermarks should be wrapped in brackets. Ex: <watermark>OFFICIAL COPY<watermark>\n"
    "- Prefer using ☐ and ☑ for checkboxes.\n"
    "- If a section is handwritten or unclear, transcribe your best reading and append [uncertain] inline."
)

_MATCH_MARKDOWN_BLOCKS = re.compile(r"^```[a-z]*\n([\s\S]*?)\n```$", re.MULTILINE)
_MATCH_CODE_BLOCKS = re.compile(r"^```\n([\s\S]*?)\n```$", re.MULTILINE)

mcp = FastMCP("gemini-ocr")


@dataclass
class Page:
    page: int
    content: str


def _build_client() -> genai.Client:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set")
    return genai.Client(api_key=GEMINI_API_KEY)


def _strip_markdown_fences(text: str) -> str:
    text = _MATCH_MARKDOWN_BLOCKS.sub(r"\1", text)
    text = _MATCH_CODE_BLOCKS.sub(r"\1", text)
    return text.strip()


async def _pdf_to_images(pdf_path: str, temp_dir: str) -> List[str]:
    image_paths = await asyncio.to_thread(
        convert_from_path,
        pdf_path=pdf_path,
        output_folder=temp_dir,
        dpi=_DPI,
        fmt=_FORMAT,
        size=(None, _PAGE_HEIGHT),
        thread_count=_THREAD_COUNT,
        use_pdftocairo=True,
        paths_only=True,
    )
    return image_paths


async def _process_page(
    client: genai.Client,
    image_path: str,
    page_num: int,
    prior_page: str,
    semaphore: asyncio.Semaphore,
) -> Page:
    async with semaphore:
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        contents = []

        # System instruction
        system_instruction = _SYSTEM_PROMPT
        if prior_page:
            system_instruction += (
                f'\n\nMarkdown must maintain consistent formatting with the following page:\n\n"""{prior_page}"""'
            )

        response = await asyncio.to_thread(
            client.models.generate_content,
            model=GEMINI_MODEL,
            config={"system_instruction": system_instruction},
            contents=[{
                "role": "user",
                "parts": [{"inline_data": {"mime_type": "image/png", "data": image_data}}],
            }],
        )

        content = _strip_markdown_fences(response.text)
        return Page(page=page_num, content=content)


@mcp.tool()
async def ocr_to_markdown(file_path: str, maintain_format: bool = False) -> str:
    """Extract all text from a PDF or image using Gemini vision and return it as markdown.

    Mimics zerox's approach: converts each PDF page to a PNG image at 300 DPI,
    then sends each image to Gemini individually for high-fidelity extraction.
    Pages are reassembled in correct order after processing.

    ## File size
    Any size PDF is supported — there are no inline limits since pages are
    processed as images one at a time.

    ## When to use
    Use this tool whenever the user wants to read, extract, search, or process
    text from a scanned document, image, or PDF — including invoices, reports,
    forms, lab results, or any file where text is embedded in an image.

    ## How to call
    Pass the absolute path to the file on disk. The file must be accessible
    inside the Docker container (home directory is mounted automatically).

    ## maintain_format
    Set to true to process pages sequentially and pass each page's output as
    context to the next, improving formatting consistency across pages.
    Slower but produces more uniform output for multi-page documents.

    ## After receiving the result
    - Present the extracted markdown directly to the user.
    - For batches, call this tool once per file then combine or summarize.
    - If the user asks to save output, write it to a .md file alongside the original.

    Args:
        file_path:       Absolute path to the PDF or image file on disk.
        maintain_format: If true, process pages sequentially for consistent formatting.
                         Defaults to false (concurrent processing).

    Returns the full extracted text as a markdown string, pages in order.
    """
    file_path = os.path.expanduser(file_path)
    client = _build_client()

    with tempfile.TemporaryDirectory() as temp_dir:
        # Convert PDF to per-page images (or treat image as single page)
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            image_paths = await _pdf_to_images(file_path, temp_dir)
        else:
            # Single image — wrap in list
            image_paths = [file_path]

        # Sort image paths to guarantee page order (pdf2image names them sequentially)
        image_paths = sorted(image_paths)

        pages: List[Page] = []

        if maintain_format:
            # Sequential: pass prior page content for formatting consistency
            prior_page = ""
            for i, image_path in enumerate(image_paths):
                semaphore = asyncio.Semaphore(1)
                page = await _process_page(client, image_path, i + 1, prior_page, semaphore)
                pages.append(page)
                prior_page = page.content
        else:
            # Concurrent: all pages in parallel, re-sort by page number after
            semaphore = asyncio.Semaphore(_CONCURRENCY)
            tasks = [
                _process_page(client, image_path, i + 1, "", semaphore)
                for i, image_path in enumerate(image_paths)
            ]
            pages = await asyncio.gather(*tasks)
            # asyncio.gather preserves order, but sort by page number to be safe
            pages = sorted(pages, key=lambda p: p.page)

    return "\n\n".join(page.content for page in pages)


if __name__ == "__main__":
    mcp.run(transport="stdio")
