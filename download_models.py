import argparse
import subprocess
import sys
from configparser import ConfigParser

from modelteam_utils.ai_utils import check_ollama_ready, init_ollama, extract_skills_from_snippet
from modelteam_utils.constants import OLLAMA_DEFAULT_MODEL

arg_parser = argparse.ArgumentParser(description="Setup Ollama models")
arg_parser.add_argument("--config", type=str, help="config file")
args = arg_parser.parse_args()
config = ConfigParser()
config.read(args.config)
model = config.get("ollama", "model", fallback=OLLAMA_DEFAULT_MODEL)

print("Checking Ollama installation...", flush=True)
try:
    subprocess.run(["ollama", "pull", model], check=True)
except FileNotFoundError:
    print("ERROR: Ollama is not installed. Please install from https://ollama.com")
    sys.exit(1)
except subprocess.CalledProcessError as e:
    print(f"ERROR: Failed to pull model '{model}': {e}")
    sys.exit(1)

if check_ollama_ready(config):
    print(f"Ollama model '{model}' is ready.", flush=True)
    model_data = init_ollama(config)
    test_code = 'def hello_world():\n    print("Hello World!")\n'
    skills = extract_skills_from_snippet(model_data, test_code)
    print(f"Test inference successful. Detected skills: {skills}")
else:
    print(f"ERROR: Ollama is running but model '{model}' not available. Try: ollama pull {model}")
    sys.exit(1)
