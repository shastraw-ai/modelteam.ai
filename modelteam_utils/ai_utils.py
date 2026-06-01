import json

import requests

from .constants import OLLAMA_DEFAULT_ENDPOINT, OLLAMA_DEFAULT_MODEL, SKILL_PREDICTION_LIMIT, CHUNK_CHAR_LIMIT

SYSTEM_PROMPT = (
    "You are a code skill extractor. Given code snippets with file metadata, identify the "
    "specific technical skills demonstrated.\n\n"
    "RULES:\n"
    "1. Return specific, named technologies: frameworks, libraries, platforms, tools, "
    "protocols, concrete engineering disciplines.\n"
    "   GOOD: \"React\", \"FastAPI\", \"Docker\", \"PostgreSQL\", \"pandas\", \"PyTorch\", "
    "\"Hugging Face Transformers\", \"LangChain\", \"RAG\", \"LoRA\", \"ONNX\", \"vLLM\", "
    "\"Vector Database\", \"Prompt Engineering\", \"Function Calling\", \"GraphQL\", "
    "\"WebSocket\", \"Kubernetes\", \"Terraform\", \"Redis\", \"Celery\", \"OAuth\"\n"
    "   BAD: \"Error Handling\", \"Data Processing\", \"Web Development\", \"API Design\", "
    "\"Object-Oriented Programming\", \"Code Quality\", \"Asynchronous Programming\", "
    "\"String Manipulation\", \"Logging\"\n\n"
    "2. Map imports and usage patterns to the framework/library/technique name:\n"
    "   - \"from transformers import ...\" -> \"Hugging Face Transformers\"\n"
    "   - \"from peft import LoraConfig\" -> \"LoRA\", \"PEFT\"\n"
    "   - \"from langchain import ...\" -> \"LangChain\"\n"
    "   - \"import chromadb\" -> \"ChromaDB\"\n"
    "   - \"from openai import OpenAI\" -> \"OpenAI API\"\n"
    "   - \"import torch\", \"nn.Module\" -> \"PyTorch\"\n"
    "   - \"from diffusers import ...\" -> \"Diffusers\"\n"
    "   - \"import pandas\", \"pd.DataFrame\" -> \"pandas\"\n"
    "   - \"useEffect\", \"useState\" -> \"React\"\n"
    "   - \"app = FastAPI()\" -> \"FastAPI\"\n\n"
    "3. Recognize AI/ML patterns and name them specifically:\n"
    "   - Fine-tuning with adapters (QLoRA, LoRA, PEFT) -> \"Fine-Tuning\", \"LoRA\", \"PEFT\"\n"
    "   - Retrieval-augmented generation -> \"RAG\"\n"
    "   - Embedding generation + vector search -> \"Vector Database\", \"Embeddings\"\n"
    "   - Tool/function calling with LLMs -> \"Function Calling\"\n"
    "   - Prompt templates, chat completions -> \"Prompt Engineering\"\n"
    "   - Model quantization (GPTQ, AWQ, bitsandbytes) -> \"Model Quantization\"\n"
    "   - Model serving (vLLM, TGI, Triton) -> name the specific server\n"
    "   - Agents, planning, multi-step reasoning -> \"AI Agents\"\n\n"
    "4. Do NOT return the programming language itself as a skill.\n"
    "5. Use standard capitalization (e.g., \"FastAPI\" not \"fastapi\", \"NumPy\" not \"numpy\", "
    "\"PyTorch\" not \"pytorch\", \"LangChain\" not \"langchain\").\n"
    "6. Return at most {limit} skills.\n"
    "7. Return ONLY JSON: {{\"skills\": [\"Skill1\", \"Skill2\"]}}"
)

FEW_SHOT_EXAMPLES = [
    {
        "user": (
            "Language: Python\nFile: train_lora.py\n"
            "Imports: transformers, peft, torch, datasets, bitsandbytes, trl\n\n"
            "Code:\n```\n"
            "model = AutoModelForCausalLM.from_pretrained(\n"
            "    base_model, quantization_config=BitsAndBytesConfig(load_in_4bit=True),\n"
            "    device_map=\"auto\"\n"
            ")\n"
            "lora_config = LoraConfig(r=16, lora_alpha=32, target_modules=[\"q_proj\", \"v_proj\"])\n"
            "model = get_peft_model(model, lora_config)\n"
            "trainer = SFTTrainer(\n"
            "    model=model, train_dataset=dataset,\n"
            "    tokenizer=tokenizer, args=training_args\n"
            ")\n"
            "trainer.train()\n"
            "model.push_to_hub(\"my-org/fine-tuned-model\")\n"
            "```"
        ),
        "assistant": '{"skills": ["Hugging Face Transformers", "LoRA", "PEFT", "QLoRA", "PyTorch", "Fine-Tuning", "Hugging Face Hub"]}'
    },
    {
        "user": (
            "Language: Python\nFile: rag_pipeline.py\n"
            "Imports: langchain, chromadb, openai, tiktoken\n\n"
            "Code:\n```\n"
            "embeddings = OpenAIEmbeddings(model=\"text-embedding-3-small\")\n"
            "vectorstore = Chroma.from_documents(chunks, embeddings, persist_directory=\"./db\")\n"
            "retriever = vectorstore.as_retriever(search_kwargs={\"k\": 5})\n"
            "llm = ChatOpenAI(model=\"gpt-4\", temperature=0)\n"
            "chain = RetrievalQA.from_chain_type(llm=llm, retriever=retriever)\n"
            "response = chain.invoke({\"query\": user_question})\n"
            "```"
        ),
        "assistant": '{"skills": ["LangChain", "ChromaDB", "OpenAI API", "RAG", "Embeddings", "Vector Database"]}'
    },
    {
        "user": (
            "Language: TypeScript\nFile: api/routes/users.ts\n"
            "Imports: express, prisma, zod, jsonwebtoken, bcrypt\n\n"
            "Code:\n```\n"
            "const schema = z.object({ email: z.string().email(), password: z.string().min(8) });\n"
            "router.post('/register', async (req, res) => {\n"
            "  const { email, password } = schema.parse(req.body);\n"
            "  const hashed = await bcrypt.hash(password, 12);\n"
            "  const user = await prisma.user.create({ data: { email, password: hashed } });\n"
            "  const token = jwt.sign({ sub: user.id }, process.env.JWT_SECRET);\n"
            "  res.json({ token });\n"
            "});\n"
            "```"
        ),
        "assistant": '{"skills": ["Express", "Prisma", "Zod", "JWT", "Authentication", "bcrypt"]}'
    },
]


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
    chunk_char_limit = int(config.get("ollama", "chunk_char_limit", fallback=str(CHUNK_CHAR_LIMIT)))
    num_predict = int(config.get("ollama", "num_predict", fallback="1024"))
    system_prompt = SYSTEM_PROMPT.format(limit=SKILL_PREDICTION_LIMIT)
    return {
        "endpoint": endpoint,
        "model": model,
        "model_tag": f"c2s::{model}",
        "chunk_char_limit": chunk_char_limit,
        "num_predict": num_predict,
        "system_prompt": system_prompt,
    }


def extract_skills_from_snippet(model_data, code_snippet, file_name="", lang="", imports=None):
    url = f"{model_data['endpoint']}/api/chat"

    context_parts = []
    if lang:
        context_parts.append(f"Language: {lang}")
    if file_name:
        context_parts.append(f"File: {file_name}")
    if imports:
        context_parts.append(f"Imports: {', '.join(imports[:30])}")

    context_header = "\n".join(context_parts)
    if context_header:
        user_content = f"{context_header}\n\nCode:\n```\n{code_snippet}\n```"
    else:
        user_content = f"Code:\n```\n{code_snippet}\n```"

    messages = [{"role": "system", "content": model_data["system_prompt"]}]
    for ex in FEW_SHOT_EXAMPLES:
        messages.append({"role": "user", "content": ex["user"]})
        messages.append({"role": "assistant", "content": ex["assistant"]})
    messages.append({"role": "user", "content": user_content})

    payload = {
        "model": model_data["model"],
        "messages": messages,
        "stream": False,
        "format": "json",
        "think": False,
        "options": {
            "temperature": 0.1,
            "num_predict": model_data.get("num_predict", 1024)
        }
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
        return normalize_skill_names(raw_skills)[:SKILL_PREDICTION_LIMIT]
    except Exception as e:
        print(f"Ollama inference error: {e}", flush=True)
        return []


REFACTOR_CHECK_PROMPT = (
    "You classify code changes. Given a description of a large code change, "
    "determine if it is primarily:\n"
    "- REFACTOR: code reformatting, style/lint fixes, auto-formatter output, "
    "whitespace cleanup, renaming, moving code between files, import reordering, "
    "generated/vendored file updates\n"
    "- CONTRIBUTION: new features, bug fixes, new APIs, significant logic changes, "
    "new tests, new modules, meaningful refactors that change architecture\n\n"
    "Return ONLY JSON: {\"classification\": \"REFACTOR\" or \"CONTRIBUTION\"}"
)


def check_if_refactor(model_data, description):
    """Ask the LLM whether a large code change is a refactor.

    Returns True if the change appears to be a refactor/reformatting.
    Defaults to False (not a refactor) on error — err on the side of processing.
    """
    url = f"{model_data['endpoint']}/api/chat"
    payload = {
        "model": model_data["model"],
        "messages": [
            {"role": "system", "content": REFACTOR_CHECK_PROMPT},
            {"role": "user", "content": description},
        ],
        "stream": False,
        "format": "json",
        "think": False,
        "options": {"temperature": 0.0, "num_predict": 64},
    }
    try:
        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        parsed = json.loads(content)
        classification = parsed.get("classification", "").upper()
        return classification == "REFACTOR"
    except Exception:
        return False


def normalize_skill_names(raw_skills):
    normalized = []
    seen = set()
    for skill in raw_skills:
        if not isinstance(skill, str) or not skill.strip():
            continue
        s = skill.strip()
        key = s.lower()
        if key not in seen:
            normalized.append(s)
            seen.add(key)
    return normalized


_KEYWORD_CATEGORIES = [
    ("AI / ML", ["pytorch", "tensorflow", "keras", "scikit-learn", "numpy", "pandas",
                 "feature engineering", "time series", "lightgbm", "xgboost", "catboost",
                 "neural network", "deep learning", "machine learning", "computer vision",
                 "hugging face", "transformers", "fine-tuning", "lora", "peft",
                 "model quantization", "onnx", "diffusers", "reinforcement learning",
                 "model evaluation", "model training", "hyperparameter",
                 "scipy", "matplotlib", "seaborn", "data visualization",
                 "regression", "classification", "clustering", "video processing",
                 "image processing", "opencv", "networkx", "graph analysis",
                 "graph construction"]),
    ("GenAI", ["prompt engineering", "langchain", "llamaindex", "rag",
               "vector database", "embeddings", "openai api", "ai agents",
               "function calling", "chromadb", "weaviate", "pinecone", "milvus",
               "ollama", "vllm", "text generation", "llm", "chatbot",
               "gemini api", "claude api"]),
    ("Frontend", ["react", "angular", "vue", "svelte", "next.js", "nuxt",
                  "html", "css", "sass", "tailwind", "bootstrap", "webpack",
                  "vite", "redux", "zustand", "material ui", "chakra",
                  "framer motion", "three.js", "d3.js", "chart.js",
                  "web scraping"]),
    ("Backend", ["rest api", "graphql", "express", "fastapi", "flask", "django",
                 "spring", "node.js", "websocket", "grpc", "api integration",
                 "authentication", "jwt", "oauth", "celery", "rabbitmq",
                 "kafka", "microservices", "nginx", "api gateway",
                 "pydantic", "middleware", "batch processing"]),
    ("Databases", ["sqlite", "postgresql", "mysql", "mongodb", "redis",
                   "sqlalchemy", "orm", "prisma", "dynamodb", "cassandra",
                   "elasticsearch", "neo4j", "firestore", "supabase",
                   "data modeling"]),
    ("DevOps / Cloud", ["docker", "kubernetes", "terraform", "ansible", "jenkins",
                        "github actions", "ci/cd", "aws", "azure", "gcp",
                        "google cloud", "cloudformation", "helm", "prometheus",
                        "grafana", "linux", "monitoring", "pytest"]),
    ("Data", ["spark", "airflow", "dbt", "snowflake", "bigquery",
              "data pipeline", "etl", "data warehouse", "hadoop",
              "databricks", "redshift", "tableau", "power bi",
              "data engineering", "streaming", "backtesting"]),
    ("Mobile", ["react native", "flutter", "swift", "swiftui", "kotlin",
                "android", "ios", "expo", "capacitor"]),
    ("APIs", ["alpaca api", "youtube api", "stripe api", "twilio",
              "slack api", "twitter api", "github api", "spotify api"]),
]


def group_skills_by_keyword(skill_names):
    """Group skills into categories using keyword matching (no LLM needed)."""
    if not skill_names:
        return []

    groups = {}
    for skill in skill_names:
        skill_lower = skill.lower()
        matched = False
        for cat_name, keywords in _KEYWORD_CATEGORIES:
            for kw in keywords:
                if len(kw) <= 3 or len(skill_lower) <= 3:
                    hit = (kw == skill_lower)
                else:
                    hit = (kw in skill_lower or skill_lower in kw)
                if hit:
                    groups.setdefault(cat_name, []).append(skill)
                    matched = True
                    break
            if matched:
                break
        if not matched:
            groups.setdefault("Other", []).append(skill)

    cat_order = [c[0] for c in _KEYWORD_CATEGORIES] + ["Other"]
    result = []
    for cat in cat_order:
        if cat in groups:
            result.append({"name": cat, "skills": groups[cat]})
    return result


GROUP_SKILLS_PROMPT = (
    "Group these technical skills into 3-5 categories for a developer profile chart.\n\n"
    "Use short domain-based category names like:\n"
    "  \"AI / ML\", \"Frontend\", \"Backend\", \"Data\", \"DevOps\", \"Databases\", \"Cloud\"\n\n"
    "RULES:\n"
    "1. Each group should have 1-5 skills. Merge tiny groups into the nearest fit.\n"
    "2. Every input skill must appear in exactly one group.\n"
    "3. Order groups by total importance (most important group first).\n"
    "4. Return ONLY JSON: {\"groups\": [{\"name\": \"Category\", \"skills\": [\"Skill1\"]}, ...]}"
)


def group_skills_for_report(model_data, skills):
    """Group skills into categories for charting. Returns list of {name, skills} dicts."""
    if not skills:
        return []
    url = f"{model_data['endpoint']}/api/chat"
    payload = {
        "model": model_data["model"],
        "messages": [
            {"role": "system", "content": GROUP_SKILLS_PROMPT},
            {"role": "user", "content": f"Group these skills:\n{json.dumps(skills)}"},
        ],
        "stream": False,
        "format": "json",
        "think": False,
        "options": {"temperature": 0.0, "num_predict": 1024},
    }
    try:
        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        parsed = json.loads(resp.json()["message"]["content"])
        groups = parsed.get("groups", [])
        if isinstance(groups, list) and groups:
            valid = []
            for g in groups:
                if isinstance(g, dict) and g.get("name") and g.get("skills"):
                    valid.append({"name": g["name"], "skills": list(g["skills"])})
            if valid:
                return valid
    except Exception as e:
        print(f"  Skill grouping error: {e}", flush=True)
    return [{"name": "Skills", "skills": skills}]


PROFILE_RANK_PROMPT = (
    "You curate a software engineer's public profile. Given their programming languages "
    "and extracted skill list, decide which skills should appear on the profile.\n\n"
    "GUIDELINES:\n"
    "1. RELEVANT: specific, distinctive skills that showcase real expertise — named "
    "frameworks, libraries, platforms, tools, concrete disciplines. A skill mentioned "
    "rarely can still be highly relevant (e.g. Kubernetes from a few config files).\n"
    "2. NOT RELEVANT: skills that are too generic, too expected given their stack, "
    "redundant with another skill already marked relevant, or add noise.\n"
    "3. Aim for 15-30 relevant skills. Fewer is better than padding with filler.\n"
    "4. Consider the developer's apparent specialization from their language mix.\n"
    "5. Frequency scores are provided but should NOT dominate — a low-frequency skill "
    "can be more profile-worthy than a high-frequency generic one.\n\n"
    "Return ONLY JSON: {\"relevant\": [\"Skill1\", \"Skill2\", ...], "
    "\"not_relevant\": [\"Skill3\", \"Skill4\", ...]}\n"
    "Every input skill must appear in exactly one list."
)


def rank_skills_for_profile(model_data, skills_with_scores, languages):
    """Ask the LLM which skills should default to RELEVANT on the profile.

    Returns a set of skill names deemed relevant.
    Falls back to all-relevant on error.
    """
    url = f"{model_data['endpoint']}/api/chat"

    skill_entries = [f"{s} (score: {v:.1f})" for s, v in
                     sorted(skills_with_scores.items(), key=lambda x: -x[1])]
    user_content = (
        f"Languages: {', '.join(sorted(languages))}\n\n"
        f"Skills:\n{json.dumps(skill_entries)}"
    )

    payload = {
        "model": model_data["model"],
        "messages": [
            {"role": "system", "content": PROFILE_RANK_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "format": "json",
        "think": False,
        "options": {"temperature": 0.0, "num_predict": 2048},
    }
    try:
        resp = requests.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        parsed = json.loads(content)
        relevant = parsed.get("relevant", [])
        if isinstance(relevant, list) and relevant:
            return set(relevant)
        return set(skills_with_scores.keys())
    except Exception as e:
        print(f"  Profile ranking error: {e}", flush=True)
        return set(skills_with_scores.keys())
