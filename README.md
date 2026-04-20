# gemini-mcp

An MCP (Model Context Protocol) server that sends images and PDFs to Google Gemini for OCR and returns the extracted content as markdown.

## How it works

The container runs persistently in Docker Desktop with no volume mounts needed. Claude reads files directly from its workspace, base64-encodes them, and sends the content to the container over the MCP protocol. The container forwards them to the Gemini API and returns markdown.

```
Claude Code (host)                 Docker Desktop
  reads src/invoice.pdf
  → base64 encodes it       →      gemini-mcp container
                                     → Gemini API
  ← markdown result         ←           ← markdown
```

To OCR a whole folder, Claude lists the files in `src/`, then calls `ocr_to_markdown` for each one — no special batch tool needed.

## Tool

**`ocr_to_markdown(base64_data, mime_type)`**

Claude reads any image or PDF from the workspace, encodes it, and passes it here. Returns extracted text as markdown.

Supported MIME types: `image/jpeg`, `image/png`, `image/gif`, `image/webp`, `application/pdf`

## Quick Start

### 1. Get a Gemini API key

Visit [Google AI Studio](https://aistudio.google.com/app/apikey) and create an API key.

### 2. Build the Docker image

```bash
cd gemini-mcp
docker build -t gemini-mcp .
```

### 3. Add to Claude Code MCP settings

In your Claude Code settings (`.claude/settings.json`):

```json
{
  "mcpServers": {
    "gemini-ocr": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-e", "GEMINI_API_KEY",
        "-e", "GEMINI_MODEL",
        "gemini-mcp:latest"
      ],
      "env": {
        "GEMINI_API_KEY": "your_api_key_here",
        "GEMINI_MODEL": "gemini-2.0-flash"
      }
    }
  }
}
```

No volume mounts required.

### 4. Use in Claude

```
OCR the file src/invoice.pdf and show me the result
```
```
Go through all the PDFs in src/ and OCR each one, saving the results to src/output/
```

Claude will read each file from the workspace, send it to the gemini-ocr tool, and return the markdown.

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GEMINI_API_KEY` | Yes | — | Google Gemini API key |
| `GEMINI_MODEL` | No | `gemini-2.0-flash` | Model to use (`gemini-1.5-pro`, `gemini-2.0-flash`, etc.) |

## Local Development (without Docker)

```bash
pip install -e .
export GEMINI_API_KEY=your_key
python src/server.py
```
