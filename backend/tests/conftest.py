import os

os.environ.setdefault("APP_SECRET", "test-secret-with-at-least-32-characters")
os.environ.setdefault("MYSQL_HOST", "localhost")
os.environ.setdefault("MYSQL_DATABASE", "test")
os.environ.setdefault("MYSQL_USERNAME", "test")
os.environ.setdefault("MYSQL_PASSWORD", "test")
os.environ.setdefault("LLM_PROVIDER", "openai-compatible")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_MODEL", "test-model")
