import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
from dotenv import load_dotenv
from fastapi.responses import FileResponse
import time
import json
import sqlite3
from datetime import datetime, timedelta
import threading
from typing import List, Dict

load_dotenv()

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_KEY:
    raise RuntimeError("Set OPENROUTER_API_KEY env var")

app = FastAPI()

# Rate limiting
last_request_time = 0
MIN_REQUEST_INTERVAL = 2
open_router_url = "https://openrouter.ai/api/v1/chat/completions"

# Database setup
DB_NAME = "story_conversations.db"

# Enhanced system prompt for story writing
SYSTEM_PROMPT = """
"""

# Comprehensive summary prompt for story context
SUMMARY_PROMPT = """Create a comprehensive story summary that captures:

1. **Current Scene**: Where exactly the story left off, current location, immediate situation
2. **Main Characters**: Names, personalities, relationships, current status/condition
3. **Plot Status**: Major ongoing storylines, recent developments, unresolved conflicts
4. **World/Setting**: Important locations, rules, atmosphere, time period
5. **Tone/Style**: Writing style, genre elements, narrative voice
6. **Key Details**: Important objects, secrets, or plot devices mentioned

Format as a detailed but organized summary that would allow someone to continue the story seamlessly. Focus on actionable details that inform the next scene."""

def init_database():
    """Initialize SQLite database with enhanced story tracking"""
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    cursor = conn.cursor()
    
    # Messages table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Story context table for better tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS story_context (
            session_id TEXT PRIMARY KEY,
            comprehensive_summary TEXT,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
            message_count INTEGER DEFAULT 0
        )
    ''')
    
    # Create indexes
    cursor.execute('''CREATE INDEX IF NOT EXISTS idx_session_timestamp ON messages(session_id, timestamp DESC)''')
    cursor.execute('''CREATE INDEX IF NOT EXISTS idx_context_session ON story_context(session_id)''')
    
    conn.commit()
    conn.close()
    print("Enhanced database initialized successfully")

def store_message(session_id: str, role: str, content: str):
    """Store message and update context tracking"""
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)''', 
                      (session_id, role, content))
        
        # Update message count in story_context
        cursor.execute('''
            INSERT OR REPLACE INTO story_context (session_id, message_count, last_updated)
            VALUES (?, COALESCE((SELECT message_count FROM story_context WHERE session_id = ?), 0) + 1, ?)
        ''', (session_id, session_id, datetime.now()))
        
        conn.commit()
    finally:
        conn.close()

def get_story_messages(session_id: str, limit: int = 30) -> List[Dict]:
    """Get recent story messages with larger context window"""
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT role, content FROM messages 
            WHERE session_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (session_id, limit))
        
        messages = cursor.fetchall()
        return [{"role": role, "content": content} for role, content in reversed(messages)]
    finally:
        conn.close()

def generate_comprehensive_summary(session_id: str) -> str:
    """Generate comprehensive story summary using grok"""
    # Get more messages for better context
    messages = get_story_messages(session_id, limit=50)
    
    if not messages:
        return ""
    
    # Format conversation for analysis
    conversation_text = ""
    for msg in messages:
        conversation_text += f"{msg['role']}: {msg['content']}\n\n"
    
    summary_payload = {
        "model": "x-ai/grok-4-fast",  # Better model for analysis
        "messages": [
            {"role": "system", "content": SUMMARY_PROMPT},
            {"role": "user", "content": f"Analyze and summarize this story conversation for perfect continuation:\n\n{conversation_text}"}
        ],
        "max_tokens": 2000
    }
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        r = requests.post(url=open_router_url, json=summary_payload, headers=headers, timeout=60)
        if r.status_code == 200:
            summary = r.json()["choices"][0]["message"]["content"]
            
            # Store the summary
            conn = sqlite3.connect(DB_NAME, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE story_context 
                SET comprehensive_summary = ?, last_updated = ?
                WHERE session_id = ?
            ''', (summary, datetime.now(), session_id))
            conn.commit()
            conn.close()
            
            return summary
    except Exception as e:
        print(f"Summary generation failed: {e}")
    
    return "Story context available for continuation."

def get_cached_summary(session_id: str) -> str:
    """Get cached summary or generate new one if needed"""
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT comprehensive_summary, message_count, last_updated 
            FROM story_context 
            WHERE session_id = ?
        ''', (session_id,))
        
        result = cursor.fetchone()
        
        if result:
            summary, old_count, last_updated = result
            
            # Check current message count
            cursor.execute('''SELECT COUNT(*) FROM messages WHERE session_id = ?''', (session_id,))
            current_count = cursor.fetchone()[0]
            
            # Regenerate summary if more than 10 new messages or older than 1 hour
            time_diff = datetime.now() - datetime.fromisoformat(last_updated.replace('Z', '+00:00') if 'Z' in last_updated else last_updated)
            
            if (current_count - old_count) > 10 or time_diff > timedelta(hours=1):
                return generate_comprehensive_summary(session_id)
            
            return summary if summary else generate_comprehensive_summary(session_id)
        else:
            return generate_comprehensive_summary(session_id)
    finally:
        conn.close()

def cleanup_old_messages():
    """Clean up messages older than 30 days (extended for stories)"""
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    cursor = conn.cursor()
    
    cutoff_date = datetime.now() - timedelta(days=30)
    
    cursor.execute('''DELETE FROM messages WHERE timestamp < ?''', (cutoff_date,))
    cursor.execute('''DELETE FROM story_context WHERE last_updated < ?''', (cutoff_date,))
    
    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()
    
    print(f"Cleaned up {deleted_count} old records")

def start_cleanup_scheduler():
    """Start background cleanup every 7 days"""
    def cleanup_loop():
        while True:
            time.sleep(7 * 24 * 60 * 60)  # 7 days
            cleanup_old_messages()
    
    cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
    cleanup_thread.start()
    print("Cleanup scheduler started")

# Initialize on startup
init_database()
start_cleanup_scheduler()

@app.get("/")
def root():
    return FileResponse("index.html")

class PromptIn(BaseModel):
    prompt: str
    model: str = "x-ai/grok-4-fast"  # Better default model
    session_id: str = "default"
    max_tokens: int = 4000

@app.post("/api/chat")
def chat(body: PromptIn):
    global last_request_time
    
    # Rate limiting
    current_time = time.time()
    time_since_last = current_time - last_request_time
    
    if time_since_last < MIN_REQUEST_INTERVAL:
        wait_time = MIN_REQUEST_INTERVAL - time_since_last
        raise HTTPException(status_code=429, detail=f"Please wait {wait_time:.1f} seconds")
    
    # Store user message
    store_message(body.session_id, "user", body.prompt)
    
    # Get comprehensive story context
    story_context = get_cached_summary(body.session_id)
    
    # Get recent messages for immediate context (last 6 exchanges)
    recent_messages = get_story_messages(body.session_id, limit=12)
    
    # Build context-aware system prompt
    enhanced_system_prompt = f"""{SYSTEM_PROMPT}

CURRENT STORY CONTEXT:
{story_context}

Instructions: Use the above context to continue the story seamlessly. The user's input should guide the next development in the narrative. Maintain all established elements while responding to their direction."""

    # Prepare messages with recent context
    messages = [{"role": "system", "content": enhanced_system_prompt}]
    
    # Add recent conversation for immediate context
    if len(recent_messages) > 1:
        messages.extend(recent_messages[-6:])  # Last 3 exchanges
    else:
        messages.append({"role": "user", "content": body.prompt})
    
    payload = {
        "model": body.model,
        "messages": messages,
        "max_tokens": body.max_tokens,
        "temperature": 0.8,  # Good balance for creative writing
        "top_p": 0.9
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }

    try:
        r = requests.post(url=open_router_url, json=payload, headers=headers, timeout=60)
        last_request_time = time.time()
        
        r.raise_for_status()
        
        # Store AI response
        response_data = r.json()
        assistant_response = response_data["choices"][0]["message"]["content"]
        store_message(body.session_id, "assistant", assistant_response)
        
        return response_data
        
    except requests.HTTPError:
        if r.status_code == 401:
            raise HTTPException(status_code=401, detail="Authentication failed")
        elif r.status_code == 429:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        raise HTTPException(status_code=r.status_code, detail=r.text)

@app.get("/api/summary/{session_id}")
def get_story_summary(session_id: str):
    """Get current story summary"""
    summary = get_cached_summary(session_id)
    return {"session_id": session_id, "summary": summary}

@app.post("/api/regenerate-summary/{session_id}")
def regenerate_summary(session_id: str):
    """Force regenerate story summary"""
    summary = generate_comprehensive_summary(session_id)
    return {"session_id": session_id, "new_summary": summary}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 9000))
    uvicorn.run(app, host="0.0.0.0", port=port)