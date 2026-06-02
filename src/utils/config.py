import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
# Walk up to find the root folder
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

# Base Settings
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# Path configurations (resolving relative to project root)
DATA_DIR = BASE_DIR / os.getenv("DATA_DIR", "data")
MODELS_DIR = BASE_DIR / os.getenv("MODELS_DIR", "models")
DATABASE_PATH = BASE_DIR / os.getenv("DATABASE_PATH", "sql/credit_risk.db")

# Create folders if they don't exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

# Print verification of configuration
if __name__ == "__main__":
    print(f"BASE_DIR: {BASE_DIR}")
    print(f"DATA_DIR: {DATA_DIR}")
    print(f"MODELS_DIR: {MODELS_DIR}")
    print(f"DATABASE_PATH: {DATABASE_PATH}")
    print(f"GEMINI_API_KEY configured: {'Yes' if GEMINI_API_KEY else 'No'}")
