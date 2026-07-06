# Installation and Usage Guide

## Prerequisites

Install the following before starting:

* Python 3.11 or later
* Git
* A Gemini API key
* Optional: a read-only GitHub personal access token

## Clone the Project

```powershell
git clone <your-repository-url>
cd github-repository-optimizer-agent
```

## Create and Activate a Virtual Environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

You should see:

```text
(.venv)
```

at the beginning of your terminal prompt.

## Install Dependencies

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

Verify package health:

```powershell
pip check
```

Expected result:

```text
No broken requirements found.
```

## Configure Environment Variables

Create this file:

```text
app/.env
```

Add:

```env
GOOGLE_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash
APP_NAME=github_repository_optimizer

# Optional but recommended for higher GitHub API limits.
GITHUB_TOKEN=your_read_only_github_token
```

Do not commit `app/.env`.

The project `.gitignore` should include:

```gitignore
app/.env
.env
.env.*
```

## Test Basic ADK Configuration

Run:

```powershell
python -m app.main
```

Expected output should confirm:

* Application name loaded
* Gemini model loaded
* Gemini API key loaded

## Run the ADK Agent

Start the multi-agent workflow:

```powershell
adk run app
```

Then enter a prompt:

```text
Analyze https://github.com/google/adk-python
```

Expected behavior:

1. Coordinator Agent receives the request.
2. Repository Analysis Agent retrieves and analyzes repository structure.
3. Documentation Analysis Agent reviews documentation coverage.
4. Coordinator Agent returns one combined report.

## Run the Streamlit Interface

Start the web application:

```powershell
streamlit run ui/streamlit_app.py
```

Open the local address printed in the terminal. It is commonly:

```text
http://localhost:8501
```

## Use the Streamlit Interface

1. Enter a public GitHub repository URL.

```text
https://github.com/owner/repository
```

2. Click **Analyze Repository**.
3. Wait for the analysis to complete.
4. Review:

   * Repository Summary
   * Repository Analysis
   * Documentation Analysis
   * Recommendations
   * Analysis Limitations

## Test the GitHub Tool Directly

```powershell
python -c "from app.tools.github_tool import fetch_github_repository; import json; result = fetch_github_repository('https://github.com/google/adk-python'); print(json.dumps(result, indent=2))"
```

## Test the Repository Analysis Agent Directly

```powershell
python -c "from app.agents.repository_agent import analyze_public_repository; import json; result = analyze_public_repository('https://github.com/google/adk-python'); print(json.dumps(result, indent=2))"
```

## Test the Documentation Analysis Agent Directly

```powershell
python -c "from app.agents.documentation_agent import analyze_repository_documentation; import json; result = analyze_repository_documentation('https://github.com/google/adk-python'); print(json.dumps(result, indent=2))"
```

## Common Errors

### GitHub API rate limit

Error:

```text
github_rate_limit
```

Solution:

Add a read-only GitHub token to `app/.env`:

```env
GITHUB_TOKEN=your_read_only_github_token
```

Restart the terminal after updating environment configuration.

### Gemini 503 unavailable error

Error:

```text
503 UNAVAILABLE
```

Cause:

The selected Gemini model is temporarily under high demand.

Solution:

Try again after a short time. You can also use another Gemini model available to your API key.

### Invalid repository URL

Use this format:

```text
https://github.com/owner/repository
```

Do not use:

```text
https://github.com/owner/repository/tree/main
http://github.com/owner/repository
https://gitlab.com/owner/repository
```

### Streamlit command not found

Run:

```powershell
pip install -r requirements.txt
```

Then use:

```powershell
python -m streamlit run ui/streamlit_app.py
```

## Capture Screenshots for README

After the UI works, save these screenshots:

1. `docs/assets/streamlit-home.png`

   * Show the URL input field before analysis.

2. `docs/assets/streamlit-analysis.png`

   * Shows the repository analysis result.

Use real screenshots from your local application. Do not add placeholder or edited screenshots.
