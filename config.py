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
RECENT_MESSAGE_COUNT = 15           # Keep last 10 messages in full
SUMMARIZE_THRESHOLD = 15            # Start summarizing after 10 messages
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

SUMMARY_PROMPT = """Analyze the conversation and produce a rich, accurate, and comprehensive story summary that:

Tells the story exactly as it unfolds, without adding speculation or deviating from established events, motivations, or tone. Captures all main characters, their development arcs, psychological shifts, relationships, motivations, conflicts, and present status, including how they have changed from their introduction to the current moment. Includes all major plot developments, key events, turning points, causal chains, and consequences that have shaped the story so far. Clearly describes the current setting, environment, timeline, and situation, including the characters’ emotional and strategic positions in the present moment. Preserves all important world details, story mechanics, and narrative rules that matter for understanding the plot. Identifies unresolved threads, unanswered questions, open conflicts, missing pieces, risks, and narrative tension points that are still active. Summarizes the story in flowing prose only, not in bullet points, while remaining concise but fully informative, ensuring no key detail is omitted.

Write the summary like a well-formed narrative that feels like a faithful story recap or story-so-far, explaining what has happened, why it happened, how characters reacted, how dynamics evolved, and how the story is progressing toward its next phase."""

COMPRESS_PROMPT = """Summarize the following story segment concisely while preserving key plot points, character actions, and important details. Keep it under 2000 words:"""