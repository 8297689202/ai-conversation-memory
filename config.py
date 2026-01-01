import os
from dotenv import load_dotenv

load_dotenv()

# API Configuration
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_KEY:
    raise RuntimeError("Set OPENROUTER_API_KEY env var")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Model Configuration
MODEL_CONFIG = {
    "name": "x-ai/grok-4-fast",
    "max_output": 4000,
    "input_cost_per_1m": 0.20,
    "output_cost_per_1m": 0.50
}

# Strategy Settings
RECENT_MESSAGE_COUNT = 10           # Keep last 10 messages in full
SUMMARIZE_THRESHOLD = 10            # Start summarizing after 10 messages
SUMMARY_MAX_TOKENS = 2000           # Max tokens for summary
MESSAGE_COMPRESS_THRESHOLD = 2500   # Compress messages longer than this
MESSAGE_COMPRESSED_SIZE = 800       # Compress to this size
TARGET_INPUT_TOKENS = 20000         # Target input size
MAX_INPUT_TOKENS = 50000            # Safety limit

# Rate Limiting
MIN_REQUEST_INTERVAL = 2  # seconds

# Database
DB_NAME = "story_conversations.db"

# Prompts
STORY_SYSTEM_PROMPT = """
"""

SUMMARY_PROMPT = """Analyze this conversation and create a comprehensive story summary that captures:

1. Main characters and their current status
2. Key plot developments and events
3. Current setting and situation
4. Important details and unresolved threads

Keep it concise but informative. Format as flowing prose, not bullet points."""

COMPRESS_PROMPT = """Summarize the following story segment concisely while preserving key plot points, character actions, and important details. Keep it under 200 words:"""