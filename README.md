# Python Shiny Tabulator Demo

An interactive [Shiny for Python](https://shiny.posit.co/py/) app that combines the
py-tabulator widget for fast, spreadsheet-like exploration with an accompanying
Plotly chart for high-level insight into the Titanic dataset.

## Features

- Tabular exploration via `pytabulator.Tabulator`, including row-click feedback
- Plotly bar chart embedded with `shinywidgets.render_widget`
- Cached dataset fetch so network access happens only once per process

## Getting Started

1. Create and activate a virtual environment (example shown for macOS/Linux):
	```bash
	python3 -m venv .venv
	source .venv/bin/activate
	```
2. Install the required packages:
	```bash
	pip install -r requirements.txt
	```
3. **(Optional)** If using the Databot feature, install and patch `mcp-run-python`:
	```bash
	pip install mcp-run-python
	./apply-mcp-patch.sh
	```
	> **Note:** The patch reverts `mcp-run-python` to use `minimist` instead of Deno's standard library for compatibility. Re-run the patch script after any package reinstall.
4. Launch the Shiny app (the `app` object lives inside `app.py`):
	```bash
	shiny run --reload --port 8000 app:app
	```
5. Open the reported URL in a browser to interact with the Tabulator grid and Plotly chart.

## Project Layout

- `app.py` – Shiny UI/server definitions plus data preparation helpers
- `requirements.txt` – Minimal runtime dependencies for the app
- `.github/copilot-instructions.md` – Workspace-specific automation checklist

## Dataset Notes

The demo pulls the Titanic manifest from the `datasciencedojo/datasets` GitHub
repository. If you prefer to work offline, download the CSV once and update the
`DATA_URL` constant in `app.py` to point at your local copy.
