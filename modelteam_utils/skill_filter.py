"""Filter extracted skills: deduplicate, canonicalize, drop generics.

Three passes:

  1. Deterministic strip of programming-language names.
  2. Hierarchical canonicalization — iteratively merge variant skills
     into canonical forms until no new merges happen.
  3. Generic filter — LLM drops skills too vague for a resume.

Generic filter decisions are cached per-skill on disk so re-runs are fast.
"""

import hashlib
import json
import os
import time

import requests

from .utils import get_extension_to_language_map

CACHE_FILENAME = "skill_filter_cache.json"
CANON_BATCH_SIZE = 40

CANONICALIZE_PROMPT = """You merge duplicate and closely-related technical skills into canonical forms.

Given a list of skills extracted from code, identify groups that refer to the same underlying technology and pick one canonical name for each group.

MERGE these kinds of duplicates:
- Sub-features into their parent: "useState", "useEffect", "React Hooks", "JSX" -> "React"
- API wrappers into the library: "pd.DataFrame", "DataFrame Operations" -> "pandas"
- Technique variants: "QLoRA", "LoRA adapters" -> "LoRA"
- Synonyms: "Containerization" -> "Docker" (if Docker is in the list)
- Partial overlaps: "JWT", "JSON Web Token" -> "JWT"

DO NOT MERGE genuinely different technologies:
- "React" and "Vue" — different frameworks
- "Docker" and "Kubernetes" — related but distinct
- "pandas" and "NumPy" — different libraries
- "FastAPI" and "Flask" — different frameworks
- "PostgreSQL" and "Redis" — different databases
- "LoRA" and "RAG" — different AI techniques

Use standard capitalization (e.g., "FastAPI", "NumPy", "PyTorch", "LangChain").

Return ONLY JSON: {"groups": [{"members": ["skill1", "skill2"], "canonical": "Name"}, ...]}
Every input skill must appear in exactly one group. A skill with no merge partner is a single-member group."""


GENERIC_FILTER_PROMPT = """You filter a software engineer's skill list for their public profile.

KEEP skills specific enough for a recruiter to search for:
- Named frameworks/libraries: "React", "FastAPI", "pandas", "LangChain", "PyTorch"
- Named platforms/infrastructure: "Docker", "Kubernetes", "Redis", "PostgreSQL", "AWS S3"
- Specific techniques: "RAG", "LoRA", "Fine-Tuning", "Function Calling", "OAuth"
- Concrete disciplines: "Machine Learning", "Computer Vision", "Web Scraping", "Authentication"

DROP skills that are too generic or trivially expected:
- Generic programming concepts: "Error Handling", "Data Processing", "OOP"
- Vague umbrellas: "Web Development", "Backend Development", "API Design", "Code Quality"
- Language features as skills: "List Comprehension", "Async/Await", "Type Hinting", "Decorators"
- Trivially common: "Logging", "Configuration", "Environment Variables", "JSON"
- Overly broad: "Data Structures", "Algorithms", "String Manipulation", "File I/O"

When uncertain, DROP. A shorter, sharper profile is better.

Return ONLY JSON: {"keep": ["Skill1", ...], "drop": ["Skill3", ...]}
Every input skill must appear in exactly one list."""

PROMPT_HASH = hashlib.sha256(
    (CANONICALIZE_PROMPT + GENERIC_FILTER_PROMPT).encode("utf-8")
).hexdigest()[:16]


def _language_blocklist():
    """Lower-cased set of programming-language names that should never appear as skills."""
    langs = set(get_extension_to_language_map().values())
    langs.update({"python", "javascript", "typescript", "java", "go", "golang",
                  "c", "c++", "cpp", "c#", "csharp", "php", "ruby", "rust",
                  "scala", "swift", "kotlin", "lua", "dart", "elixir",
                  "shell", "bash", "html", "css", "scss", "sass", "json", "yaml", "xml"})
    return {name.lower() for name in langs}


def _load_cache(cache_path):
    if not cache_path or not os.path.exists(cache_path):
        return {}
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("prompt_hash") != PROMPT_HASH:
            return {}
        return data
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache_path, data):
    if not cache_path:
        return
    data["prompt_hash"] = PROMPT_HASH
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
    except OSError:
        pass


def _llm_call(model_data, system_prompt, user_content, num_predict=2048):
    url = f"{model_data['endpoint']}/api/chat"
    payload = {
        "model": model_data["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "format": "json",
        "think": False,
        "options": {"temperature": 0.0, "num_predict": num_predict},
    }
    try:
        resp = requests.post(url, json=payload, timeout=180)
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else {}
    except Exception as e:
        print(f"    LLM call failed: {e}", flush=True)
        return {}


def _canonicalize_batch(skills, model_data):
    """Merge variant skills in one batch. Returns {input_skill: canonical}."""
    result = _llm_call(
        model_data, CANONICALIZE_PROMPT,
        f"Merge these skills:\n{json.dumps(skills)}",
        num_predict=4096,
    )
    skill_set = set(skills)
    mapping = {}
    for group in result.get("groups", []):
        if not isinstance(group, dict):
            continue
        canonical = group.get("canonical", "")
        members = group.get("members", [])
        if not canonical or not isinstance(members, list):
            continue
        for m in members:
            if isinstance(m, str) and m in skill_set:
                mapping[m] = canonical.strip()
    for s in skills:
        if s not in mapping:
            mapping[s] = s
    return mapping


def _filter_generics_batch(skills, model_data):
    """Decide which skills are too generic. Returns set of skills to keep."""
    result = _llm_call(
        model_data, GENERIC_FILTER_PROMPT,
        f"Filter these skills:\n{json.dumps(skills)}",
    )
    keep = result.get("keep", [])
    if isinstance(keep, list) and keep:
        return {s for s in keep if isinstance(s, str)}
    return set(skills)


def _hierarchical_canonicalize(candidates, model_data):
    """Iteratively canonicalize until stable.

    Returns (chain, merged_scores):
      - chain: {original_skill: final_canonical}
      - merged_scores: {canonical: summed_score}
    """
    chain = {s: s for s in candidates}
    current = dict(candidates)
    max_rounds = 5

    for round_num in range(max_rounds):
        skill_list = sorted(current.keys())
        batches = [skill_list[i:i + CANON_BATCH_SIZE]
                   for i in range(0, len(skill_list), CANON_BATCH_SIZE)]

        merge_map = {}
        for idx, batch in enumerate(batches):
            t0 = time.time()
            batch_map = _canonicalize_batch(batch, model_data)
            merge_map.update(batch_map)
            print(f"    canonicalize {idx + 1}/{len(batches)}  "
                  f"({len(batch)} skills, {time.time() - t0:.1f}s)", flush=True)

        new_current = {}
        for s, score in current.items():
            canon = merge_map.get(s, s)
            new_current[canon] = new_current.get(canon, 0) + score

        for orig in chain:
            old_canon = chain[orig]
            chain[orig] = merge_map.get(old_canon, old_canon)

        if len(new_current) == len(current):
            break

        print(f"  Round {round_num + 1}: {len(current)} → {len(new_current)} skills", flush=True)
        current = new_current

    return chain, current


def filter_profile_skills(merged_skills, model_data, cache_path=None):
    """Filter + canonicalize skill dict for job-search relevance.

    Returns ``(language_drops, llm_drops, canonical_map, surviving_scores)``.
    """
    lang_block = _language_blocklist()
    language_drops = {s for s in merged_skills if s.lower() in lang_block}
    candidates = {s: v for s, v in merged_skills.items() if s not in language_drops}

    if not candidates:
        return language_drops, set(), {}, {}

    cache_data = _load_cache(cache_path)
    model_key = model_data.get("model", "unknown")
    generic_cache = cache_data.setdefault("generic_filter", {}).setdefault(model_key, {})

    # Hierarchical canonicalize
    print(f"  Canonicalizing {len(candidates)} skills...", flush=True)
    chain, merged_scores = _hierarchical_canonicalize(candidates, model_data)

    # Filter generics (cached per-skill)
    canonical_skills = sorted(merged_scores.keys())
    needs_query = [s for s in canonical_skills if s not in generic_cache]

    if needs_query:
        print(f"  Filtering {len(needs_query)} skills for generic concepts...", flush=True)
        batches = [needs_query[i:i + CANON_BATCH_SIZE]
                   for i in range(0, len(needs_query), CANON_BATCH_SIZE)]
        for idx, batch in enumerate(batches):
            t0 = time.time()
            keep_set = _filter_generics_batch(batch, model_data)
            for s in batch:
                generic_cache[s] = s in keep_set
            print(f"    filter {idx + 1}/{len(batches)}  "
                  f"({len(batch)} skills, {time.time() - t0:.1f}s)", flush=True)
        _save_cache(cache_path, cache_data)

    keep_canonicals = {s for s in canonical_skills if generic_cache.get(s, True)}

    llm_drops = set()
    canonical_map = {}
    surviving_scores = {}

    for orig, canon in chain.items():
        if orig not in candidates:
            continue
        if canon not in keep_canonicals:
            llm_drops.add(orig)
            continue
        canonical_map[orig] = canon
        surviving_scores[canon] = surviving_scores.get(canon, 0) + candidates[orig]

    kept = len(surviving_scores)
    dropped = len(merged_scores) - kept
    print(f"  Kept {kept} skills, dropped {dropped} generic concepts.", flush=True)

    return language_drops, llm_drops, canonical_map, surviving_scores
