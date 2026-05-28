"""Filter extracted skills down to job-search-relevant ones.

Three passes:

  1. Deterministic strip of programming-language names — these belong in the
     ``langs`` dimension of the profile, not in the skills list.

  2. LLM judgment via the same Ollama model used for extraction. For each
     remaining skill, the model returns ``{canonical, keep}``:

       - canonical merges sub-skill variants under an umbrella
         (``JSON Parsing``/``JSON Handling``/``JSON Schema`` → ``JSON``;
         ``useState``/``useEffect`` → ``React Hooks``).
       - keep applies a strict job-search rubric (concrete framework or
         discipline → keep; generic programming concept / vague umbrella → drop).

  3. Group surviving originals by canonical, summing scores so the dialog
     and the rendered HTML show one consolidated row per real skill.

Decisions are cached on disk (``skill_filter_v2_cache.json`` in the profile
directory) so re-runs of ``edit_skills.py`` don't re-call the LLM.
"""

import hashlib
import json
import os
import time

import requests

from .utils import get_extension_to_language_map

BATCH_SIZE = 10
CACHE_FILENAME = "skill_filter_cache.json"

FILTER_PROMPT = """You curate the SKILLS section of a software engineer's resume.

For each input, return {"input": str, "canonical": str, "keep": bool}.

============================================================
STEP 1 — pick CANONICAL (consolidate variants):
============================================================
- "useState", "useEffect", "useRef", "useContext", "Hooks", "Refs", "JSX",
  "Component Lifecycle", "Component Props", "Component Composition",
  "Component Structure", "Component Development", "Conditional Rendering",
  "Event Handling", "DOM Manipulation", "react" -> "React"
- "API Communication", "API Calls", "API Fetching", "API Integration",
  "API Interaction", "API Response Handling", "API Design", "REST API",
  "Web APIs", "HTTP Requests", "HTTP Exception Handling", "Fetch API",
  "Query Parameters", "Range Requests", "Requests Library" -> "REST APIs"
- "File I/O", "File Handling", "File System Operations", "File System Interaction",
  "File Writing", "File Downloading", "Pathlib", "Path Handling",
  "Path Manipulation" -> "File System I/O"
- "Async/Await", "Promises", "Promise Handling", "Asynchronous Functions",
  "Asynchronous Operations", "Asynchronous Tasks" -> "Asynchronous Programming"
- "JSON Parsing", "JSON Handling", "JSON Schema", "JSON Serialization",
  "JSON Processing" -> "JSON"
- "Date Manipulation", "Date Handling", "Date Formatting",
  "Date/Time Manipulation", "Date and Time Manipulation", "Datetime",
  "Datetime Handling", "Datetime Manipulation", "Timestamp Handling" ->
  "Date/Time Handling"
- "Data Manipulation", "Data Processing", "Data Transformation",
  "Data Filtering", "Data Extraction", "Data Mapping", "Data Structuring",
  "Data Display", "Data Fetching", "Data Persistence", "Data Serialization",
  "Data Aggregation", "Data Imputation", "Text Processing",
  "data analysis", "data retrieval" -> "Data Processing"
- "OOP", "Object-Oriented Programming (OOP)", "Class Inheritance",
  "Class Design", "Class Instantiation", "Inheritance" ->
  "Object-Oriented Programming"
- "Database Interaction", "Database Querying", "Database Modeling",
  "SQL Querying", "sqlite3", "Foreign Keys", "Schema Definition",
  "Schema Initialization", "Query Building", "data modeling",
  "data retrieval" -> "SQL"
- "ORM", "Object-Relational Mapping (ORM)", "object relational mapping",
  "SQLAlchemy (or similar ORM)" -> "SQLAlchemy" if SQLAlchemy in input set,
  else "Object-Relational Mapping"
- "Centrality Measures", "Community Detection", "Graph Theory",
  "Graph Algorithms", "Network Analysis" -> "NetworkX" if NetworkX in input set,
  else "Graph Algorithms"
- "DataFrame", "DataFrames", "DataFrame Operations", "Rolling Statistics",
  "Parquet" -> "pandas"
- "Vectorization", "Numerical Computation", "Mathematical Functions" -> "NumPy"
- "Subprocess", "subprocess", "Process Management",
  "Command Line Execution", "Background Tasks" -> "Subprocess Management"
- "State Management", "State Management (implied)" -> if Redux/Zustand/etc named
  in input set merge under that library; otherwise -> "State Management"
- "Image Manipulation", "image processing" -> "Image Processing"
- "Pytest", "pytest", "Assertion Testing", "testing", "unit testing" -> "pytest"
- "Token Management", "Google Sign-In", "authentication" -> "Authentication"
- "Mocking", "Mocking/Stubbing", "unittest.mock" -> "Mocking"
- "pytorch", "Pytorch" -> "PyTorch"
- "postgresql" -> "PostgreSQL"
- "Caching" -> "Redis" if Redis in input set, else drop the merge
- otherwise the canonical is the input unchanged

============================================================
STEP 2 — KEEP=true ONLY IF the CANONICAL is in the KEEP list.
============================================================
KEEP these canonical forms (and only these or similar specific named tools):
   Frameworks: React, React Native, Django, FastAPI, Flask, Express, Spring,
   Pydantic, SQLAlchemy, Boto3, NetworkX, OpenCV, pandas, NumPy, PyTorch,
   pytest, Redux Toolkit, Zustand, Expo, Expo Router, requests, argparse.
   Platforms: Kubernetes, Docker, Terraform, Redis, PostgreSQL, MongoDB, SQLite,
   Kafka, Snowflake, AWS S3, Google Cloud Storage, Vercel, Chrome Extension API,
   Google GenAI SDK, Chrome Extension, FFmpeg, CSS-in-JS, Service Worker.
   Concrete disciplines: Authentication, OAuth, Web Scraping, Image Processing,
   Video Processing, Time Series Analysis, Feature Engineering, Machine Learning,
   Computer Vision, Distributed Systems, LLM Integration, Prompt Engineering,
   Function Calling, Vector Search, Vector Database Interaction.
   Concrete engineering practices: Unit Testing, Integration Testing,
   Microservices, Database Design, Rate Limiting, Mocking, Subprocess Management,
   Dependency Injection.

============================================================
STEP 3 — these CANONICAL forms are ALWAYS keep=false. They are too generic:
============================================================
   REST APIs
   File System I/O
   Date/Time Handling
   JSON
   Object-Oriented Programming
   Asynchronous Programming
   Data Processing
   Data Structures
   State Management            (when no library named)
   API Design
   API Development
   Web Development
   Frontend Development
   Backend Development
   Algorithm Design
   Algorithm
   Error Handling
   Exception Handling
   Logging
   Type Hinting / Type Safety / Type Definition / Immutability
   Conditional Logic / Loops / Iteration / Mapping / Aggregation / Grouping
   String Manipulation / String Formatting / Dictionary Manipulation
   List Comprehension / Array Manipulation / Array Methods
   Object Manipulation / Object Access / Object Destructuring
   Method Design / Function Definition / Function Design / Class Design
   Module System (ESM) / Style Modules / StyleSheet / Styling / ClassNames /
   Flexbox / Local Storage / Service Layer / Command Pattern
   URL Parsing / Form Handling / Session Management / Configuration Management
   Environment Variables
   Code Quality / Best Practices / Maintainability / Refactoring
   Programming language names: Python, JavaScript, TypeScript, Java, Go, C,
   C++, Ruby, Rust, PHP, HTML, CSS, JSON, YAML, XML.

============================================================
RULE: when uncertain -> DROP. Aim for 20-40 sharp, specific skills.
============================================================

Return ONLY JSON: {"results": [{"input": "<exact input>", "canonical": "<form>", "keep": true|false}, ...]}. Include every input skill exactly once."""

PROMPT_HASH = hashlib.sha256(FILTER_PROMPT.encode("utf-8")).hexdigest()[:16]


def _language_blocklist():
    """Lower-cased set of programming-language names that should never appear as skills."""
    langs = set(get_extension_to_language_map().values())
    langs.update({"python", "javascript", "typescript", "java", "go", "golang",
                  "c", "c++", "cpp", "c#", "csharp", "php", "ruby", "rust",
                  "scala", "swift", "kotlin", "lua", "dart", "elixir",
                  "shell", "bash", "html", "css", "scss", "sass", "json", "yaml", "xml"})
    return {name.lower() for name in langs}


def _load_cache(cache_path):
    """Load the per-model decision cache. Auto-invalidates when the prompt changes."""
    if not cache_path or not os.path.exists(cache_path):
        return {}
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("prompt_hash") != PROMPT_HASH:
            return {}
        models = data.get("models")
        return models if isinstance(models, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache_path, cache):
    if not cache_path:
        return
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"prompt_hash": PROMPT_HASH, "models": cache},
                      f, indent=2, sort_keys=True)
    except OSError:
        pass


def _ollama_filter_call(skills, model_data):
    """Ask the LLM about a batch. Returns {skill: {"canonical": str, "keep": bool}} or {} on failure."""
    url = f"{model_data['endpoint']}/api/chat"
    payload = {
        "model": model_data["model"],
        "messages": [
            {"role": "system", "content": FILTER_PROMPT},
            {"role": "user", "content": "Evaluate these skills:\n" + json.dumps(skills)},
        ],
        "stream": False,
        "format": "json",
        "think": False,
        "options": {"temperature": 0.0, "num_predict": 4096},
    }
    try:
        resp = requests.post(url, json=payload, timeout=180)
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        parsed = json.loads(content)
        results = parsed.get("results") if isinstance(parsed, dict) else None
        if not isinstance(results, list):
            return {}
        out = {}
        for r in results:
            if not isinstance(r, dict):
                continue
            inp = r.get("input")
            canonical = r.get("canonical") or inp
            if not isinstance(inp, str) or not isinstance(canonical, str):
                continue
            out[inp] = {"canonical": canonical.strip() or inp, "keep": bool(r.get("keep"))}
        return out
    except Exception as e:
        print(f"  LLM filter call failed: {e}", flush=True)
        return {}


def filter_profile_skills(merged_skills, model_data, cache_path=None):
    """Filter + canonicalize a merged skill dict for job-search relevance.

    Returns ``(language_drops, llm_drops, canonical_map, surviving_scores)``:

      - ``language_drops``     set[str] of skills stripped as programming languages
      - ``llm_drops``          set[str] of original skills the LLM dropped
      - ``canonical_map``      dict[original → canonical] for every skill kept
        (originals → canonical for the merge step downstream)
      - ``surviving_scores``   dict[canonical → summed score] ready to display
    """
    lang_block = _language_blocklist()
    language_drops = {s for s in merged_skills if s.lower() in lang_block}

    cache_model_key = model_data.get("model", "unknown")
    cache = _load_cache(cache_path)
    model_cache = cache.setdefault(cache_model_key, {})

    candidates = [s for s in merged_skills if s not in language_drops]
    needs_query = [s for s in candidates if s not in model_cache]

    if needs_query:
        print(f"  Querying {model_data.get('model')} for canonical + relevance of "
              f"{len(needs_query)} skills (batch size {BATCH_SIZE})...", flush=True)
        total_batches = (len(needs_query) + BATCH_SIZE - 1) // BATCH_SIZE
        for i in range(0, len(needs_query), BATCH_SIZE):
            batch = needs_query[i:i + BATCH_SIZE]
            t0 = time.time()
            decisions = _ollama_filter_call(batch, model_data)
            for skill in batch:
                # Default: keep as-is on missing — permissive when the LLM stays silent.
                model_cache[skill] = decisions.get(skill, {"canonical": skill, "keep": True})
            print(f"    batch {i // BATCH_SIZE + 1}/{total_batches}  "
                  f"({len(batch)} skills, {time.time() - t0:.1f}s)", flush=True)
        _save_cache(cache_path, cache)

    llm_drops = set()
    canonical_map = {}
    surviving_scores = {}
    for s in candidates:
        decision = model_cache.get(s) or {"canonical": s, "keep": True}
        if not decision.get("keep", True):
            llm_drops.add(s)
            continue
        canonical = decision.get("canonical") or s
        canonical_map[s] = canonical
        surviving_scores[canonical] = surviving_scores.get(canonical, 0) + merged_skills[s]

    return language_drops, llm_drops, canonical_map, surviving_scores
