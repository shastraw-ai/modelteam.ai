import json

import requests

from .constants import OLLAMA_DEFAULT_ENDPOINT, OLLAMA_DEFAULT_MODEL, SKILL_PREDICTION_LIMIT
from .utils import load_skill_config, get_edit_distance

SYSTEM_PROMPT = (
    "You are a code analysis expert. Given a code snippet, identify the technical skills, "
    "frameworks, libraries, and concepts demonstrated. Return ONLY a JSON object with a single key "
    "'skills' containing an array of skill name strings. Each skill should be a concise, "
    "specific technical term (e.g., 'React', 'API Development', 'Unit Testing'). "
    "Return at most 10 skills. No explanations."
)


def check_ollama_ready(config):
    endpoint = config.get("ollama", "endpoint", fallback=OLLAMA_DEFAULT_ENDPOINT)
    model = config.get("ollama", "model", fallback=OLLAMA_DEFAULT_MODEL)
    try:
        resp = requests.get(f"{endpoint}/api/tags", timeout=5)
        if resp.status_code != 200:
            return False
        models = resp.json().get("models", [])
        model_names = [m.get("name", "") for m in models]
        return any(model in name for name in model_names)
    except requests.ConnectionError:
        return False


def init_ollama(config):
    endpoint = config.get("ollama", "endpoint", fallback=OLLAMA_DEFAULT_ENDPOINT)
    model = config.get("ollama", "model", fallback=OLLAMA_DEFAULT_MODEL)
    skill_list_file = config["modelteam.ai"]["skill_list"]
    canonical_skills = load_skill_config(skill_list_file, only_keys=True, return_set=False)
    canonical_skills_lower = {}
    for s in canonical_skills:
        canonical_skills_lower[s.lower()] = s
    return {
        "endpoint": endpoint,
        "model": model,
        "model_tag": f"c2s::{model}",
        "canonical_skills": canonical_skills,
        "canonical_skills_lower": canonical_skills_lower,
    }


def extract_skills_from_snippet(model_data, code_snippet):
    url = f"{model_data['endpoint']}/api/chat"
    payload = {
        "model": model_data["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Analyze this code and extract skills:\n```\n{code_snippet}\n```"}
        ],
        "stream": False,
        "format": "json",
        "think": False,
        "options": {"temperature": 0.1, "num_predict": 256}
    }
    try:
        resp = requests.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        parsed = json.loads(content)
        if isinstance(parsed, dict) and "skills" in parsed:
            raw_skills = parsed["skills"]
        elif isinstance(parsed, list):
            raw_skills = parsed
        else:
            return []
        return normalize_skill_names(raw_skills, model_data)[:SKILL_PREDICTION_LIMIT]
    except Exception as e:
        print(f"Ollama inference error: {e}", flush=True)
        return []


def normalize_skill_names(raw_skills, model_data):
    normalized = []
    seen = set()
    canonical_lower = model_data["canonical_skills_lower"]

    for skill in raw_skills:
        if not isinstance(skill, str) or not skill.strip():
            continue
        s = skill.strip().lower()
        # exact match to canonical
        if s in canonical_lower:
            canon = canonical_lower[s]
            if canon not in seen:
                normalized.append(canon)
                seen.add(canon)
            continue
        # fuzzy match — edit distance <= 1 for most strings, <= 2 only for long ones
        best_match = None
        max_dist = 2 if len(s) > 15 else 1
        best_dist = max_dist + 1
        if len(s) > 4:
            for canon_lower, canon in canonical_lower.items():
                if abs(len(s) - len(canon_lower)) > max_dist:
                    continue
                dist = get_edit_distance(s, canon_lower)
                if dist < best_dist:
                    best_dist = dist
                    best_match = canon
        if best_match and best_match not in seen:
            normalized.append(best_match)
            seen.add(best_match)
        elif s not in seen:
            normalized.append(skill.strip())
            seen.add(s)
    return normalized
