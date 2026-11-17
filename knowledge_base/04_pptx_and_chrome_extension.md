# 4. PPTX Engines & Chrome Extension

## Chrome / Edge Extension (`chrome_extension/`)

Adds a **`⬇ Native PPTX`** button to the top-right corner of the Agentspace Web UI (`https://agentspace.ioh.co.id` / `https://vertexaisearch.cloud.google`):

1. Start the local bridge server:
   ```powershell
   python agentspace_cli.py --serve-chrome
   ```
   *(Listens on `http://127.0.0.1:18765`.)*
2. Open `chrome://extensions` (or `edge://extensions`), enable **Developer mode**, click **Load unpacked**, and select `chrome_extension/`.
3. Open any Agentspace session containing slides and click **`⬇ Native PPTX`**.

---

## Local & Agentspace OOXML Compilers

- **`dom_pptx_compiler.py`**: Compiles HTML/Tailwind Canvas slides via Playwright DOM inspection into native `python-pptx` shapes.
- **`pptx_lxml_wrapper.py`**: Reusable `python-pptx` + `lxml` consulting design system wrapper (supports dynamic KPI font scaling and `prs.run_visual_qa()`).
- **`knowledge_bundle_v2/`**: Zero-dependency OOXML engines (`01_pptx_lxml_engine_and_brand_logos.md`, `02_xlsx_inmemory_engine.md`, `03_docx_inmemory_engine.md`) used by `Office File Creator 2.0` (`deploy_office_creator_v2.py` / `office_creator_v2_created.json`).
- **OneDrive Connector (`pptx_payload.txt`)**: For Mode 3B `.pptx` uploads, Agentspace writes `/home/bard/pptx_payload.txt` and calls `onedrive_agent__upload_file` with `HasBytes: false` and `ContentBytes: ""` to avoid Base64 token bloat and Vertex AI `HTTP 500` MIME errors.
