# gemini-mcp

An MCP (Model Context Protocol) server that sends images and PDFs to Google Gemini for OCR and returns the extracted content as markdown.

## How it works

The container runs on demand via a wrapper script. Claude reads files directly from its workspace, base64-encodes them, and sends the content to the container over the MCP protocol. The container forwards them to the Gemini API and returns markdown.

```
Claude / Claude Cowork (host)      Docker Desktop
  reads src/invoice.pdf
  → base64 encodes it       →      gemini-mcp container
                                     → Gemini API
  ← markdown result         ←           ← markdown
```

To OCR a whole folder, Claude lists the files in `src/`, then calls `ocr_to_markdown` for each one — no special batch tool needed.

## Tool

**`ocr_to_markdown(base64_data, mime_type)`**

Claude reads any image or PDF from the workspace, base64-encodes it, and passes it here. Returns extracted text as markdown.

Supported MIME types: `image/jpeg`, `image/png`, `image/gif`, `image/webp`, `application/pdf`

**File size:** Files under 5 MB are sent as inline base64. Files 5 MB and larger are automatically uploaded via the Gemini File API — no special handling needed from the caller's side.

## Quick Start

### 1. Get a Gemini API key

Visit [Google AI Studio](https://aistudio.google.com/app/apikey) and create an API key. A paid plan is required — the free tier quota is too low for regular use.

### 2. Build the Docker image

```bash
cd gemini-mcp
docker build -t gemini-mcp .
```

### 3. Create the wrapper script

The wrapper kills any lingering `gemini-mcp` containers before starting a fresh one, preventing container buildup when the Claude app closes uncleanly.

```bash
mkdir -p ~/bin
cat > ~/bin/gemini-mcp-run << 'EOF'
#!/usr/bin/env bash
DOCKER=/Applications/Docker.app/Contents/Resources/bin/docker

$DOCKER ps -q --filter ancestor=gemini-mcp:latest | xargs -r $DOCKER stop > /dev/null 2>&1

exec $DOCKER run --rm -i "$@" gemini-mcp:latest
EOF
chmod +x ~/bin/gemini-mcp-run
```

### 4. Configure Claude Desktop

In `~/Library/Application Support/Claude/claude_desktop_config.json`, add to `mcpServers`:

```json
{
  "mcpServers": {
    "gemini-ocr": {
      "command": "/Users/YOUR_USERNAME/bin/gemini-mcp-run",
      "args": [
        "-e", "GEMINI_API_KEY=your_api_key_here",
        "-e", "GEMINI_MODEL=gemini-2.0-flash"
      ]
    }
  }
}
```

Pass the API key directly in `args` — the `env` block is not reliably forwarded into the Docker container.

Restart the Claude app after saving.

### 5. Use in Claude

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
| `GEMINI_API_KEY` | Yes | — | Google Gemini API key (paid plan required) |
| `GEMINI_MODEL` | No | `gemini-2.0-flash` | Model to use (`gemini-2.0-flash`, `gemini-2.5-pro`, etc.) |

## Container cleanup

The wrapper script (`gemini-mcp-run`) stops any running `gemini-mcp` containers each time it's invoked. Each container also uses `--rm` so it is removed automatically on clean exit. This prevents stale containers from accumulating if the Claude app is force-quit.

To manually clean up any lingering containers:

```bash
docker ps -q --filter ancestor=gemini-mcp:latest | xargs docker stop
```

## Local Development (without Docker)

```bash
pip install -e .
export GEMINI_API_KEY=your_key
python src/server.py
```
