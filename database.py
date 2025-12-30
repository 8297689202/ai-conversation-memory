import sqlite3
from typing import List, Dict, Optional
from datetime import datetime
from config import DB_NAME


def init_database():
    """Initialize SQLite database"""
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    cursor = conn.cursor()
    
    # Messages table - stores all messages in full
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            token_count INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Summaries table - caches summaries for old messages
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS summaries (
            session_id TEXT NOT NULL,
            messages_covered INTEGER NOT NULL,
            summary_text TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (session_id, messages_covered)
        )
    ''')
    
    # Create indexes
    cursor.execute('''CREATE INDEX IF NOT EXISTS idx_session_timestamp 
                     ON messages(session_id, timestamp DESC)''')
    cursor.execute('''CREATE INDEX IF NOT EXISTS idx_summary_session 
                     ON summaries(session_id, messages_covered DESC)''')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized successfully")


def estimate_tokens(text: str) -> int:
    """Estimate token count (roughly 4 chars per token)"""
    return len(text) // 4


def store_message(session_id: str, role: str, content: str):
    """Store a message in database"""
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    cursor = conn.cursor()
    
    token_count = estimate_tokens(content)
    
    cursor.execute('''
        INSERT INTO messages (session_id, role, content, token_count)
        VALUES (?, ?, ?, ?)
    ''', (session_id, role, content, token_count))
    
    conn.commit()
    conn.close()


def count_messages(session_id: str) -> int:
    """Count total messages for a session"""
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT COUNT(*) FROM messages WHERE session_id = ?
    ''', (session_id,))
    
    count = cursor.fetchone()[0]
    conn.close()
    
    return count


def get_all_messages(session_id: str) -> List[Dict]:
    """Get all messages for a session"""
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT role, content FROM messages 
        WHERE session_id = ? 
        ORDER BY timestamp ASC
    ''', (session_id,))
    
    messages = [{"role": row[0], "content": row[1]} for row in cursor.fetchall()]
    conn.close()
    
    return messages


def get_last_n_messages(session_id: str, n: int) -> List[Dict]:
    """Get last N messages for a session"""
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT role, content FROM messages 
        WHERE session_id = ? 
        ORDER BY timestamp DESC 
        LIMIT ?
    ''', (session_id, n))
    
    messages = [{"role": row[0], "content": row[1]} for row in cursor.fetchall()]
    conn.close()
    
    # Reverse to get chronological order
    return list(reversed(messages))


def get_messages_range(session_id: str, start: int, end: int) -> List[Dict]:
    """Get messages in a range (1-indexed, inclusive)"""
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT role, content FROM messages 
        WHERE session_id = ? 
        ORDER BY timestamp ASC 
        LIMIT ? OFFSET ?
    ''', (session_id, end - start + 1, start - 1))
    
    messages = [{"role": row[0], "content": row[1]} for row in cursor.fetchall()]
    conn.close()
    
    return messages


def get_cached_summary(session_id: str, messages_covered: int) -> Optional[str]:
    """Get cached summary for specific message count"""
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT summary_text FROM summaries 
        WHERE session_id = ? AND messages_covered = ?
    ''', (session_id, messages_covered))
    
    result = cursor.fetchone()
    conn.close()
    
    return result[0] if result else None


def get_latest_cached_summary(session_id: str) -> Optional[tuple]:
    """Get the most recent cached summary and its coverage"""
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT messages_covered, summary_text FROM summaries 
        WHERE session_id = ? 
        ORDER BY messages_covered DESC 
        LIMIT 1
    ''', (session_id,))
    
    result = cursor.fetchone()
    conn.close()
    
    return result if result else None


def cache_summary(session_id: str, messages_covered: int, summary: str):
    """Cache a summary"""
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO summaries (session_id, messages_covered, summary_text)
        VALUES (?, ?, ?)
    ''', (session_id, messages_covered, summary))
    
    conn.commit()
    conn.close()


def get_session_stats(session_id: str) -> Dict:
    """Get statistics for a session"""
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    cursor = conn.cursor()
    
    # Total messages
    cursor.execute('''
        SELECT COUNT(*) FROM messages WHERE session_id = ?
    ''', (session_id,))
    total_messages = cursor.fetchone()[0]
    
    # Cached summaries
    cursor.execute('''
        SELECT COUNT(*) FROM summaries WHERE session_id = ?
    ''', (session_id,))
    summary_count = cursor.fetchone()[0]
    
    # Total tokens
    cursor.execute('''
        SELECT SUM(token_count) FROM messages WHERE session_id = ?
    ''', (session_id,))
    total_tokens = cursor.fetchone()[0] or 0
    
    conn.close()
    
    return {
        "total_messages": total_messages,
        "cached_summaries": summary_count,
        "total_tokens": total_tokens
    }


def delete_session(session_id: str) -> int:
    """Delete a session and all its data"""
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM messages WHERE session_id = ?', (session_id,))
    messages_deleted = cursor.rowcount
    
    cursor.execute('DELETE FROM summaries WHERE session_id = ?', (session_id,))
    
    conn.commit()
    conn.close()
    
    return messages_deleted