import platform
import shutil
import subprocess
import sys
from platform import python_version

from setup_utils import get_python_bin, run_command_stream

OLLAMA_INSTALL_URL = "https://ollama.com/download"
OLLAMA_LINUX_INSTALLER = "curl -fsSL https://ollama.com/install.sh | sh"


def ensure_ollama_installed():
    if shutil.which("ollama"):
        return

    print("Ollama not found. Installing...", flush=True)
    system = platform.system()
    if system == "Linux":
        try:
            subprocess.run(OLLAMA_LINUX_INSTALLER, shell=True, check=True)
        except subprocess.CalledProcessError:
            print(f"Ollama install failed. Install manually from {OLLAMA_INSTALL_URL} and re-run setup.")
            sys.exit(1)
    elif system == "Darwin":
        if not shutil.which("brew"):
            print(f"Homebrew not found. Install Ollama manually from {OLLAMA_INSTALL_URL} and re-run setup.")
            sys.exit(1)
        try:
            subprocess.run(["brew", "install", "ollama"], check=True)
        except subprocess.CalledProcessError:
            print(f"`brew install ollama` failed. Install manually from {OLLAMA_INSTALL_URL} and re-run setup.")
            sys.exit(1)
    else:
        print(f"Auto-install not supported on {system}. Install Ollama from {OLLAMA_INSTALL_URL} and re-run setup.")
        sys.exit(1)

    if not shutil.which("ollama"):
        print("Ollama install completed but `ollama` is not on PATH. Restart your shell and re-run setup.")
        sys.exit(1)
    print("Ollama installed.", flush=True)


def main():
    pv = python_version()
    if int(pv.split(".")[0]) < 3 or int(pv.split(".")[1]) < 9 or int(pv.split(".")[1]) > 12:
        print("Please install python version >= 3.9 and <= 3.12")
        exit(1)

    print("Getting latest modelteam code")
    run_command_stream(["git", "pull"])

    print("Setting Virtual Environment and installing dependencies", flush=True)
    python_bin = get_python_bin(create_venv=True)

    run_command_stream([python_bin, "-m", "pip", "install", "--upgrade", "pip"])
    run_command_stream([python_bin, "-m", "pip", "install", "-r", "requirements.txt"])

    ensure_ollama_installed()

    print("Pulling Ollama model...", flush=True)
    run_command_stream([python_bin, "download_models.py", "--config", "config.ini"])

    print("modelteam setup complete")


if __name__ == "__main__":
    main()
