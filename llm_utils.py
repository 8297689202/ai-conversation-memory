# llm_utils.py

import requests
from typing import List, Dict
from config import (
    OPENROUTER_KEY, 
    OPENROUTER_URL, 
    MODEL_CONFIG,
    SUMMARY_PROMPT,
    COMPRESS_PROMPT
)


def call_llm(messages: List[Dict], max_tokens: int = 4000, temperature: float = 0.8) -> str:
    """Call OpenRouter API"""
    payload = {
        "model": MODEL_CONFIG["name"],
        "messages": messages
    }
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        r = requests.post(url=OPENROUTER_URL, json=payload, headers=headers, timeout=120)
        r.raise_for_status()
        
        response = r.json()["choices"][0]["message"]["content"]
        return response
    except Exception as e:
        print(f"❌ LLM call failed: {e}")
        raise


def generate_summary(messages: List[Dict], max_tokens: int = 2000) -> str:
    """Generate summary using LLM"""
    # Format messages for summary
    conversation_text = ""
    for msg in messages:
        conversation_text += f"{msg['role']}: {msg['content']}\n\n"
    
    summary_messages = [
        {"role": "system", "content": SUMMARY_PROMPT},
        {"role": "user", "content": f"Summarize this story conversation:\n\n{conversation_text}"}
    ]
    
    try:
        summary = call_llm(summary_messages, max_tokens=max_tokens, temperature=0.5)
        return summary
    except Exception as e:
        print(f"❌ Summary generation failed: {e}")
        return "Story context available."


def compress_message(content: str, target_tokens: int = 800) -> str:
    """Compress a single long message"""
    compress_messages = [
        {"role": "system", "content": COMPRESS_PROMPT},
        {"role": "user", "content": content}
    ]
    
    try:
        compressed = call_llm(compress_messages, max_tokens=target_tokens, temperature=0.8)
        return compressed
    except Exception as e:
        print(f"❌ Message compression failed: {e}")
        # Fallback: truncate
        return content[:target_tokens * 4]