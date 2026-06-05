# modelteam: AI-Powered Skill Validation for Engineers

**[modelteam](https://modelteam.ai)** analyzes your real-world code contributions and produces a developer profile
showcasing your skills. Everything runs locally via [Ollama](https://ollama.com) — your code never leaves your machine.

Supports **15+ programming languages**: Python, JavaScript, TypeScript, Java, Go, C, C++, PHP, Ruby, C#, Rust, Scala,
Swift, Kotlin, Lua, Dart, Elixir.

## How It Works

1. **Extract** — scans your git history, identifies significant code contributions, and sends each snippet to a local
   LLM for skill extraction (with few-shot examples for AI/ML, backend, frontend patterns).
2. **Filter & Rank** — a multi-stage pipeline cleans up raw skills:
   - Programming language names stripped automatically
   - Hierarchical canonicalization merges duplicates (`useEffect` → `React`, `QLoRA` → `LoRA`)
   - TF-IDF-style chunk-frequency analysis measures skill specificity
   - LLM-based generic filter drops vague concepts (`Error Handling`, `Data Processing`) while keeping
     named technologies (`NetworkX`, `FastAPI`, `PyTorch`)
   - LLM ranks which skills are profile-worthy given your full skill + language mix
3. **Score** — skills are weighted by IDF (inverse document frequency across code chunks), so niche skills
   like `LoRA` or `Web Scraping` are boosted relative to ubiquitous ones.
4. **Report** — generates two outputs:
   - **HTML profile** — standalone, publicly hostable (no repo names, file paths, or commit messages)
   - **GitHub README** — with skill badges, language activity line chart, and grouped skill activity charts
     (skills auto-clustered into domain categories by LLM)

## Security & Privacy

Your code and data remain **on your local machine**. Skill extraction runs locally via Ollama.

The HTML and README profiles are **safe to host publicly**: they contain only aggregate skill and language metrics.

---

## Prerequisites

- Python 3.9 - 3.12
- Pip
- Python-venv (if not included in Python installation)
- Git (command line)
- [Ollama](https://ollama.com) — `setup.py` auto-installs it on Mac (via Homebrew) and Linux (via the official
  installer). On Windows, install it manually first.
- Turn off sleep mode so the script can run without interruptions
    - Optional: caffeine (for linux)
- You should have made contributions for a **minimum period of 3 months**.

## Getting Started

### Video Tutorial
[![Build your Modelteam profile](images/engVideo.png)](https://www.youtube.com/watch?v=s1MHhtoiMCk)

### 1. Install modelteam Locally (in a virtual environment)

<details open>
  <summary><b>Mac/Linux</b></summary>

```
mkdir ~/modelteam && cd ~/modelteam
git clone https://github.com/modelteam-ai/modelteam.ai.git
cd ~/modelteam/modelteam.ai
python3 setup.py
```
</details>
<details> <summary><b>Windows</b></summary>

```
mkdir %USERPROFILE%\modelteam && cd %USERPROFILE%\modelteam
git clone https://github.com/modelteam-ai/modelteam.ai.git
cd %USERPROFILE%\modelteam\modelteam.ai
python setup.py
```
</details>

This script:

- Sets up a virtual environment (**does not affect your system Python**)
- Installs dependencies in the virtual environment
- Pulls the Ollama model for skill extraction

<details open>
  <summary><h2>Profile Builder Tool (Mac & Windows)</h2></summary>

### 2. Profile Builder Tool
- Use the GUI helper to build your profile:
  1. Select repos
  2. Select git email(s) — multiple emails are merged into one profile
  3. Extract skills
  4. Edit skills (mark relevant / not relevant)
```
python3 user_profile_helper.py
```
or
```
python user_profile_helper.py
```

### 3. Open your profile

After the helper finishes, find the outputs in `model_team_profile/<name>/<date>/`:

- `modelteam_profile.html` — open in any browser. Standalone, safe to host publicly.
- `README.md` + `images/` — copy to your GitHub profile repo (`username/username`).

</details>


<details> <summary><h2>Detailed Profile Building Steps (Linux / CLI)</h2></summary>

### 2. Gather your Git Repositories & Git Email ID

#### 2.1 Repo List

Clone the repos to your local machine and add the full paths to a text file, one line per repo.
If all repos are in a single directory, you can pass the directory path directly.

<details open>
  <summary><b>Mac/Linux</b></summary>

```
find ~ 2>/dev/null | grep "/\.git$" | sed 's/\/\.git$//' > ~/modelteam/repo_list.txt
```

</details>
<details> <summary><b>Windows</b></summary>

```
dir /s /b %USERPROFILE% | findstr "\\.git$" > %USERPROFILE%\modelteam\repo_list.txt
```

</details>

#### 2.2 Finding Your Git Email ID

```
git config --get user.email
```

or

<details open>
  <summary><b>Mac/Linux</b></summary>

```
git log | grep Author | grep -i $USER | sed 's/.*<\(.*\)>.*/\1/' | sort | uniq
```

</details>
<details> <summary><b>Windows</b></summary>

```
git log --author=%USERNAME% --pretty=format:"%%ae"
```
</details>

### 3. Extract Skills from Your Code

No internet access required — Ollama runs locally. The script analyzes your git history to extract skills and stats.

<details open>
  <summary><b>Mac/Linux</b></summary>

```
cd ~/modelteam/modelteam.ai
python3 gen_git_stats.py -r <repo_list> -g <git_email_id> [-n <number_of_years>]
```

</details>
<details> <summary><b>Windows</b></summary>

```
cd %USERPROFILE%\modelteam\modelteam.ai
python gen_git_stats.py -r <repo_list> -g <git_email_id> [-n <number_of_years>]
```

</details>

Number of years defaults to 5. Multiple git email IDs can be comma-separated; they'll be merged into
one profile.

**Examples**

```
python3 gen_git_stats.py -r ~/modelteam/repo_list.txt -g john@org.ai -n 5
python3 gen_git_stats.py -r /Users/john/repos/ -g john@org.ai,john@personal.com -n 5
```

To force re-run, delete `model_team_profile/<name>` and run the script again.

### 4. Edit Skills & Generate Outputs

<details open>
  <summary><b>Mac/Linux</b></summary>

```
python3 edit_skills.py -g <git_email_id> [--cli_mode]
```

</details>
<details> <summary><b>Windows</b></summary>

```
python edit_skills.py -g <git_email_id> [--cli_mode]
```

</details>

- Review and edit the predicted skills (remove anything confidential or irrelevant).
- After saving, outputs are written to `model_team_profile/<name>/<date>/`:
    - `modelteam_profile.html` — standalone HTML profile, publicly hostable.
    - `README.md` + `images/` — GitHub profile README with charts.
- On Linux without a GUI, pass `--cli_mode`.

### 5. Re-render reports without re-editing (optional)

Once you've edited skills, you can regenerate reports from the filtered JSON:

```
python3 -m modelteam_utils.html_report \
    --profile_json model_team_profile/<name>/<date>/mt_stats_<date>.json \
    --output_dir   model_team_profile/<name>/<date>/
```

```
python3 -m modelteam_utils.md_report \
    --profile_json model_team_profile/<name>/<date>/mt_stats_<date>.json \
    --output_dir   model_team_profile/<name>/<date>/
```

</details>
