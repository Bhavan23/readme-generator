# readme-generator

Auto-generate a comprehensive `README.md` for any Frappe/ERPNext app directly from its source code — and optionally raise a PR.

## Features

- Reads key files (hooks.py, doctypes, controllers, utils) from any GitHub repo
- Generates structured, accurate documentation
- AI-powered via Anthropic Claude (optional — falls back to template mode)
- Automatically creates a PR with the generated README

## Installation

```bash
git clone https://github.com/Bhavan23/readme-generator
cd readme-generator
pip install -r requirements.txt
```

## Usage

### Basic (template mode, no AI key needed)
```bash
python readme_generator.py \
  --repo aerele/india-banking \
  --branch version-16-dev \
  --token ghp_your_github_token
```

### With AI (recommended)
```bash
python readme_generator.py \
  --repo aerele/india-banking \
  --branch version-16-dev \
  --token ghp_your_github_token \
  --anthropic-key sk-ant-your_key
```

### Auto-create PR
```bash
python readme_generator.py \
  --repo aerele/india-banking \
  --branch version-16-dev \
  --token ghp_your_github_token \
  --anthropic-key sk-ant-your_key \
  --pr
```

## Options

| Flag | Description |
|---|---|
| `--repo` | GitHub repo in `owner/name` format |
| `--branch` | Branch to analyse (default: `main`) |
| `--token` | GitHub personal access token (needs `repo` scope) |
| `--anthropic-key` | Anthropic API key for AI generation |
| `--pr` | Create a PR with the generated README |
| `--output` | Output file path (default: `README.md`) |

## How it works

1. Fetches the full file tree from GitHub
2. Selects the most relevant files (hooks.py, doctype JSONs, controllers, utils)
3. Reads up to 30 files (skipping test files and large binaries)
4. Sends to Claude for analysis and README generation
5. Saves locally and optionally raises a PR

## License

MIT
