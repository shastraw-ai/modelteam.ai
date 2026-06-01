"""Filter extracted skills: deduplicate, canonicalize, drop generics.

Four passes:

  1. Deterministic strip of programming-language names.
  2. Hierarchical canonicalization — iteratively merge variant skills
     into canonical forms until no new merges happen.
  3. Chunk-frequency analysis — compute how often each skill appears
     across code snippets (TF-IDF analog) to inform the generic filter.
  4. Generic filter — LLM drops skills too vague for a resume, using
     chunk-frequency context when available.

Generic filter decisions are cached per-skill on disk so re-runs are fast.
"""

import hashlib
import json
import math
import os
import time
from collections import defaultdict

import requests

from .utils import get_extension_to_language_map

CACHE_FILENAME = "skill_filter_cache.json"
CANON_BATCH_SIZE = 40
MIN_SCORE_PCT = 0.005  # drop skills below 0.5% of total lines

CANONICALIZE_PROMPT = """You merge duplicate and closely-related technical skills into canonical forms.

Given a list of skills extracted from code, identify groups that refer to the same
underlying technology and pick one canonical name for each group.

MERGE only true duplicates — different names for the SAME thing:
- Sub-features into their parent: "useState", "useEffect", "JSX" → "React"
- API wrappers into the library: "pd.DataFrame", "DataFrame Operations" → "pandas"
- Casing/spelling variants: "numpy" → "NumPy", "pytorch" → "PyTorch"
- Technique variants: "QLoRA", "LoRA adapters" → "LoRA"
- Synonyms: "JSON Web Token" → "JWT"

NEVER merge a named library/tool into a generic category:
- "SQLAlchemy" is NOT a duplicate of "SQL" or "Database" — it's a specific ORM library
- "NumPy" is NOT "Data Engineering" — it's a specific library
- "pytest" is NOT "Testing" — it's a specific test framework
- "requests" is NOT "HTTP Requests" — it's a specific library
- "FFmpeg" is NOT "Video Processing" — it's a specific tool
- "Flask" is NOT "Web Frameworks" — it's a specific framework

The canonical name should ALWAYS be the most specific named technology, never a category.
When in doubt, do NOT merge — leave them as separate single-member groups.

Use standard capitalization (e.g., "FastAPI", "NumPy", "PyTorch", "LangChain").

Return ONLY JSON: {"groups": [{"members": ["skill1", "skill2"], "canonical": "Name"}, ...]}
Every input skill must appear in exactly one group. A skill with no merge partner is a single-member group."""


GENERIC_FILTER_PROMPT = """You filter a software engineer's skill list for their public profile.

DECISION PRINCIPLE: KEEP a skill if a hiring manager would use it as a search term when
looking for candidates. DROP it if it describes what every programmer does regardless
of their specialization.

FREQUENCY DATA: Each skill may include chunk frequency (what % of code snippets returned
it) and language spread (how many file types). Use these as signal:
  - <5% freq, 1 language → specialized, lean KEEP
  - >20% freq, 3+ languages → likely a generic pattern, lean DROP
  - High freq in 1 language → core stack technology, KEEP (e.g. React in JSX)

EXAMPLES (apply the principle, not these specific lists):
  KEEP: "NetworkX" (named library), "Machine Learning" (hiring managers search for it),
        "Graph Theory" (domain expertise), "RAG" (specific technique), "Docker" (platform),
        "FastAPI" (framework), "LoRA" (ML technique), "Web Scraping" (searchable specialty)
  DROP: "Error Handling" (every codebase), "Data Processing" (too vague to search),
        "OOP" (universal pattern), "Async/Await" (language feature, not a skill),
        "Web Development" (vague umbrella), "JSON" (trivial data format),
        "Logging" (not a differentiator), "File I/O" (every programmer does this)

Return skill names only (without any frequency annotations).
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


def _filter_generics_batch(skills, model_data, chunk_stats=None):
    """Decide which skills are too generic. Returns set of skills to keep."""
    if chunk_stats:
        labeled = []
        for s in skills:
            cs = chunk_stats.get(s)
            if cs:
                freq_pct = f"{cs['freq']:.0%}"
                n_langs = cs['langs']
                labeled.append(f"{s} ({freq_pct} of chunks, {n_langs} lang{'s' if n_langs != 1 else ''})")
            else:
                labeled.append(s)
        user_content = f"Filter these skills:\n{json.dumps(labeled)}"
    else:
        user_content = f"Filter these skills:\n{json.dumps(skills)}"

    result = _llm_call(model_data, GENERIC_FILTER_PROMPT, user_content)
    keep = result.get("keep", [])
    if isinstance(keep, list) and keep:
        skill_set = set(skills)
        keep_set = set()
        for s in keep:
            if not isinstance(s, str):
                continue
            name = s.split(" (")[0].strip()
            if name in skill_set:
                keep_set.add(name)
        return keep_set if keep_set else set(skills)
    return set(skills)


def _case_insensitive_premerge(candidates):
    """Merge case variants (e.g. numpy→NumPy) before LLM canonicalization.

    Picks the variant with the most non-lowercase characters as canonical,
    preferring the higher-scored variant as tiebreaker.
    """
    groups = {}
    for skill, score in candidates.items():
        key = skill.lower()
        if key not in groups:
            groups[key] = []
        groups[key].append((skill, score))

    chain = {}
    merged = {}
    for key, variants in groups.items():
        if len(variants) == 1:
            skill, score = variants[0]
            chain[skill] = skill
            merged[skill] = score
            continue
        # Pick canonical: most uppercase chars, then highest score
        variants.sort(key=lambda x: (-sum(1 for c in x[0] if c.isupper()), -x[1]))
        canon = variants[0][0]
        total = 0
        for skill, score in variants:
            chain[skill] = canon
            total += score
        merged[canon] = total

    return chain, merged


def _hierarchical_canonicalize(candidates, model_data):
    """Iteratively canonicalize until stable.

    Returns (chain, merged_scores):
      - chain: {original_skill: final_canonical}
      - merged_scores: {canonical: summed_score}
    """
    # Pre-merge case variants in code (don't rely on LLM for numpy→NumPy)
    premerge_chain, premerged = _case_insensitive_premerge(candidates)
    if len(premerged) < len(candidates):
        print(f"  Pre-merged {len(candidates)} → {len(premerged)} (case variants)", flush=True)

    chain = dict(premerge_chain)
    current = dict(premerged)
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


# ── Chunk-frequency analysis (TF-IDF analog) ──────────────────────────────

def _compute_chunk_stats(profiles):
    """Compute per-skill chunk frequency from c2s data in profiles.

    Returns (total_chunks, skill_chunks, skill_langs) where:
      - total_chunks: int, total code snippets analyzed
      - skill_chunks: {skill: int}, how many chunks returned each skill
      - skill_langs: {skill: set}, which file extensions each skill appeared in
    """
    total_chunks = 0
    skill_chunks = defaultdict(int)
    skill_langs = defaultdict(set)

    for profile in profiles:
        stats = profile.get("stats", {}) or {}
        for ext, lang_block in (stats.get("langs", {}) or {}).items():
            yyyymm = (lang_block or {}).get("yyyymm", {}) or {}
            for month_data in yyyymm.values():
                if not isinstance(month_data, dict):
                    continue
                total_chunks += int(month_data.get("sig_cont", 0) or 0)
                for key, val in month_data.items():
                    if not key.startswith("c2s::") or not isinstance(val, dict):
                        continue
                    for skill, entry in val.items():
                        if isinstance(entry, (list, tuple)) and len(entry) >= 1:
                            skill_chunks[skill] += int(entry[0] or 0)
                            skill_langs[skill].add(ext)

    return total_chunks, dict(skill_chunks), {s: set(v) for s, v in skill_langs.items()}


def _remap_chunk_stats(total_chunks, raw_chunks, raw_langs, canonical_chain):
    """Remap chunk stats through canonical mapping, merging counts."""
    if not total_chunks or not raw_chunks:
        return None

    merged_chunks = defaultdict(int)
    merged_langs = defaultdict(set)

    for skill in raw_chunks:
        canon = canonical_chain.get(skill, skill)
        merged_chunks[canon] += raw_chunks[skill]
        merged_langs[canon].update(raw_langs.get(skill, set()))

    return {
        skill: {
            "chunks": merged_chunks[skill],
            "freq": merged_chunks[skill] / total_chunks,
            "langs": len(merged_langs[skill]),
            "idf": math.log(total_chunks / max(merged_chunks[skill], 1)),
        }
        for skill in merged_chunks
    }


def _looks_like_named_tool(name):
    """Heuristic: does this skill name look like a specific library/tool?

    Returns True for names like NumPy, SQLAlchemy, Three.js, scikit-learn,
    psycopg2, FastAPI — proper nouns that are almost certainly real packages.
    Returns False for plain English phrases like "Error Handling", "Logging".
    """
    # Contains a dot → likely a package (Three.js, Chart.js)
    if "." in name:
        return True
    # Contains a digit → likely a package/version (psycopg2, SAM2, h5py)
    if any(c.isdigit() for c in name):
        return True
    # Has medial uppercase (camelCase/PascalCase with lowercase): NumPy, SQLAlchemy, FastAPI, PyTorch
    # But not ALL-CAPS acronyms like "OOP", "SMTP" or plain "Title Case" like "Error Handling"
    stripped = name.replace(" ", "").replace("-", "")
    has_lower = any(c.islower() for c in stripped)
    has_upper_after_start = any(c.isupper() for c in stripped[1:])
    if has_lower and has_upper_after_start and " " not in name:
        return True
    # Hyphenated package names: scikit-learn, react-select
    if "-" in name and name[0].islower():
        return True
    return False


# ── Public API ───────────────────────────────────────────────────────────────

def filter_profile_skills(merged_skills, model_data, cache_path=None, profiles=None):
    """Filter + canonicalize skill dict for job-search relevance.

    Returns ``(language_drops, llm_drops, canonical_map, surviving_scores)``.
    """
    lang_block = _language_blocklist()
    language_drops = {s for s in merged_skills if s.lower() in lang_block}
    candidates = {s: v for s, v in merged_skills.items() if s not in language_drops}

    if not candidates:
        return language_drops, set(), {}, {}

    # Compute chunk stats from profiles (TF-IDF context for the filter)
    total_chunks, raw_chunks, raw_langs = (0, {}, {})
    if profiles:
        total_chunks, raw_chunks, raw_langs = _compute_chunk_stats(profiles)
        if total_chunks:
            print(f"  Chunk stats: {total_chunks} total snippets, "
                  f"{len(raw_chunks)} skills observed.", flush=True)

    cache_data = _load_cache(cache_path)
    model_key = model_data.get("model", "unknown")
    generic_cache = cache_data.setdefault("generic_filter", {}).setdefault(model_key, {})

    # Hierarchical canonicalize
    print(f"  Canonicalizing {len(candidates)} skills...", flush=True)
    chain, merged_scores = _hierarchical_canonicalize(candidates, model_data)

    # Remap chunk stats through canonical mapping
    chunk_stats = None
    if total_chunks and raw_chunks:
        chunk_stats = _remap_chunk_stats(total_chunks, raw_chunks, raw_langs, chain)

    # Filter generics (cached per-skill)
    auto_keep = set()
    canonical_skills = sorted(merged_scores.keys())
    needs_query = [s for s in canonical_skills if s not in generic_cache]

    if needs_query:
        print(f"  Filtering {len(needs_query)} skills for generic concepts...", flush=True)
        batches = [needs_query[i:i + CANON_BATCH_SIZE]
                   for i in range(0, len(needs_query), CANON_BATCH_SIZE)]
        for idx, batch in enumerate(batches):
            t0 = time.time()
            keep_set = _filter_generics_batch(batch, model_data, chunk_stats=chunk_stats)
            for s in batch:
                generic_cache[s] = s in keep_set
            print(f"    filter {idx + 1}/{len(batches)}  "
                  f"({len(batch)} skills, {time.time() - t0:.1f}s)", flush=True)
        _save_cache(cache_path, cache_data)

    keep_canonicals = {s for s in canonical_skills if generic_cache.get(s, True)}

    # Rescue named tools the LLM incorrectly dropped.
    # Heuristic: if the name looks like a proper noun / package name
    # (mixed case, dots, digits), it's likely a real tool, not a concept.
    rescued = set()
    for s in canonical_skills:
        if s in keep_canonicals:
            continue
        if _looks_like_named_tool(s):
            rescued.add(s)
            keep_canonicals.add(s)
    if rescued:
        print(f"  Rescued {len(rescued)} named tools the LLM dropped: "
              f"{', '.join(sorted(rescued))}", flush=True)

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

    # Drop skills below a minimum line-count threshold (0.2% of total lines)
    if surviving_scores:
        total_lines = sum(surviving_scores.values())
        min_lines = total_lines * MIN_SCORE_PCT
        before = len(surviving_scores)
        low_score = {s for s, v in surviving_scores.items() if v < min_lines}
        if low_score:
            for s in low_score:
                del surviving_scores[s]
            # Move their originals to llm_drops
            for orig, canon in canonical_map.items():
                if canon in low_score:
                    llm_drops.add(orig)
            canonical_map = {o: c for o, c in canonical_map.items() if c not in low_score}
            print(f"  Dropped {len(low_score)} skills below {min_lines:.0f} lines "
                  f"({MIN_SCORE_PCT:.1%} of {total_lines:.0f} total).", flush=True)

    kept = len(surviving_scores)
    dropped = len(merged_scores) - kept
    print(f"  Kept {kept} skills, dropped {dropped} total.", flush=True)

    return language_drops, llm_drops, canonical_map, surviving_scores
