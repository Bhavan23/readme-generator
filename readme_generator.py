#!/usr/bin/env python3
"""
README Generator for Frappe/ERPNext apps
Reads a GitHub repo and auto-generates a comprehensive README.md

Usage:
    python readme_generator.py --repo aerele/india-banking --branch version-16-dev --token ghp_xxx
    python readme_generator.py --repo aerele/india-banking --branch version-16-dev --token ghp_xxx --pr

Requirements:
    pip install requests anthropic
"""

import argparse
import base64
import json
import sys
from pathlib import Path

import requests

# ── Config ────────────────────────────────────────────────────────────────────

PRIORITY_FILES = [
    "hooks.py",
    "default.py",
    "utils.py",
    "install.py",
    "api.py",
    "README.md",
]

SKIP_PATHS = [
    "__pycache__",
    ".git",
    "node_modules",
    "dist",
    "build",
    ".eggs",
    "test_",
    "migrations",
]

MAX_FILES = 30          # Max files to read for analysis
MAX_FILE_SIZE = 30000   # Max bytes per file (skip large files)


# ── GitHub helpers ────────────────────────────────────────────────────────────

def gh_headers(token):
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}


def get_file_tree(repo, branch, token):
    url = f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
    resp = requests.get(url, headers=gh_headers(token))
    resp.raise_for_status()
    return resp.json().get("tree", [])


def read_file(repo, branch, path, token):
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
    resp = requests.get(url, headers={"Authorization": f"token {token}"})
    if resp.status_code == 200:
        return resp.text
    return None


def select_files(tree):
    """Pick the most relevant files for README generation."""
    all_files = [f for f in tree if f["type"] == "blob" and f.get("size", 0) < MAX_FILE_SIZE]

    # Filter out noise
    all_files = [
        f for f in all_files
        if not any(skip in f["path"] for skip in SKIP_PATHS)
    ]

    selected = []

    # Priority files first
    for pf in PRIORITY_FILES:
        matches = [f for f in all_files if f["path"].endswith(pf) or f["path"] == pf]
        selected.extend(matches[:1])

    # Doctype JSONs (most informative for structure)
    doctype_jsons = [
        f for f in all_files
        if f["path"].endswith(".json") and "doctype" in f["path"]
        and f not in selected
    ]
    selected.extend(doctype_jsons[:10])

    # Main Python files (controllers, doc_events)
    py_files = [
        f for f in all_files
        if f["path"].endswith(".py")
        and f not in selected
        and not f["path"].endswith("test_" + f["path"].split("/")[-1])
    ]
    # Sort by size descending (larger files = more logic)
    py_files.sort(key=lambda x: x.get("size", 0), reverse=True)
    selected.extend(py_files[:MAX_FILES - len(selected)])

    return selected[:MAX_FILES]


# ── AI README generation ──────────────────────────────────────────────────────

def build_prompt(repo, branch, files_content):
    files_block = "\n\n".join(
        f"### File: {path}\n```\n{content[:3000]}\n```"
        for path, content in files_content.items()
        if content
    )

    return f"""You are a senior Frappe/ERPNext developer writing technical documentation.

Analyse the following source files from the GitHub repo `{repo}` (branch: `{branch}`) and generate a comprehensive, accurate `README.md`.

The README must include:
1. **Title & badges** (license, ERPNext version)
2. **Overview** — what the app does in 2-3 sentences
3. **Features** — bullet list of key capabilities
4. **Architecture** — folder structure with what each module does
5. **Key Doctypes** — name, purpose, important fields
6. **Installation** — bench commands
7. **Configuration** — step-by-step setup with field descriptions
8. **Usage** — how to use the main features
9. **API Reference** — whitelisted endpoints (if any)
10. **License & Support**

Rules:
- Be accurate — only document what the code actually does
- Use tables for field descriptions
- Use code blocks for commands and code examples
- Write for experienced Frappe developers onboarding the codebase
- Do NOT hallucinate features that aren't in the code

---

SOURCE FILES:

{files_block}

---

Generate the complete README.md now (markdown only, no preamble):"""


def generate_readme_with_anthropic(prompt, api_key):
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-haiku-3-5",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text


def generate_readme_simple(files_content, repo, branch):
    """Fallback: generate a basic README without AI."""
    hooks_content = files_content.get("hooks.py", "")
    app_name = "Unknown"
    app_description = ""

    for line in hooks_content.split("\n"):
        if line.startswith("app_title"):
            app_name = line.split("=")[1].strip().strip('"\'')
        if line.startswith("app_description"):
            app_description = line.split("=")[1].strip().strip('"\'')

    doctypes = [
        path.split("/")[-2]
        for path in files_content
        if "doctype" in path and path.endswith(".json")
    ]

    return f"""# {app_name}

{app_description}

## Installation

```bash
bench get-app https://github.com/{repo} --branch {branch}
bench --site <your-site> install-app {app_name.lower().replace(' ', '_')}
bench --site <your-site> migrate
```

## Key Doctypes

{chr(10).join(f'- {dt.replace("_", " ").title()}' for dt in doctypes)}

## License

See [LICENSE](LICENSE)
"""


# ── PR creation ───────────────────────────────────────────────────────────────

def create_pr(repo, branch, readme_content, token):
    headers = gh_headers(token)
    new_branch = "docs/auto-readme"

    # Get base SHA
    resp = requests.get(f"https://api.github.com/repos/{repo}/branches/{branch}", headers=headers)
    sha = resp.json()["commit"]["sha"]

    # Create branch
    resp = requests.post(f"https://api.github.com/repos/{repo}/git/refs", headers=headers, json={
        "ref": f"refs/heads/{new_branch}",
        "sha": sha
    })

    # Check existing README
    resp = requests.get(f"https://api.github.com/repos/{repo}/contents/README.md?ref={new_branch}", headers=headers)
    existing_sha = resp.json().get("sha") if resp.status_code == 200 else None

    # Push README
    payload = {
        "message": "docs: auto-generate comprehensive README",
        "content": base64.b64encode(readme_content.encode()).decode(),
        "branch": new_branch
    }
    if existing_sha:
        payload["sha"] = existing_sha

    resp = requests.put(f"https://api.github.com/repos/{repo}/contents/README.md", headers=headers, json=payload)
    if resp.status_code not in (200, 201):
        print(f"Failed to push file: {resp.json()}")
        return None

    # Create PR
    resp = requests.post(f"https://api.github.com/repos/{repo}/pulls", headers=headers, json={
        "title": "docs: auto-generate comprehensive README",
        "body": "Auto-generated README by [readme-generator](https://github.com/Bhavan23/readme-generator) 🌸",
        "head": new_branch,
        "base": branch
    })
    return resp.json().get("html_url")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Auto-generate README for a Frappe/ERPNext app")
    parser.add_argument("--repo", required=True, help="GitHub repo (e.g. aerele/india-banking)")
    parser.add_argument("--branch", default="main", help="Branch to analyse")
    parser.add_argument("--token", required=True, help="GitHub personal access token")
    parser.add_argument("--anthropic-key", help="Anthropic API key for AI-powered generation")
    parser.add_argument("--pr", action="store_true", help="Create a PR with the README")
    parser.add_argument("--output", default="README.md", help="Output file path")
    args = parser.parse_args()

    print(f"🔍 Fetching file tree for {args.repo}@{args.branch}...")
    tree = get_file_tree(args.repo, args.branch, args.token)
    selected = select_files(tree)
    print(f"📂 Selected {len(selected)} files for analysis")

    print("📥 Reading files...")
    files_content = {}
    for f in selected:
        content = read_file(args.repo, args.branch, f["path"], args.token)
        if content:
            files_content[f["path"]] = content
            print(f"   ✅ {f['path']} ({len(content)} chars)")

    print("✍️  Generating README...")
    if args.anthropic_key:
        prompt = build_prompt(args.repo, args.branch, files_content)
        readme = generate_readme_with_anthropic(prompt, args.anthropic_key)
        print("   Used: Anthropic claude-haiku-3-5")
    else:
        readme = generate_readme_simple(files_content, args.repo, args.branch)
        print("   Used: template-based (no AI key provided)")

    # Save locally
    Path(args.output).write_text(readme)
    print(f"💾 Saved to {args.output}")

    if args.pr:
        print("🚀 Creating PR...")
        pr_url = create_pr(args.repo, args.branch, readme, args.token)
        if pr_url:
            print(f"✅ PR created: {pr_url}")
        else:
            print("❌ PR creation failed")

    print("\nDone! 🌸")


if __name__ == "__main__":
    main()
