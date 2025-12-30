from typing import List, Dict
from database import (
    count_messages,
    get_all_messages,
    get_last_n_messages,
    get_messages_range,
    get_cached_summary,
    get_latest_cached_summary,
    cache_summary,
    estimate_tokens
)
from llm_utils import generate_summary, compress_message
from config import (
    RECENT_MESSAGE_COUNT,
    SUMMARY_MAX_TOKENS,
    MESSAGE_COMPRESS_THRESHOLD,
    MESSAGE_COMPRESSED_SIZE,
    MAX_INPUT_TOKENS,
    STORY_SYSTEM_PROMPT
)

def compress_if_needed(message: Dict) -> Dict:
    """Compress a message if it's too long"""
    token_count = estimate_tokens(message['content'])
    
    if token_count > MESSAGE_COMPRESS_THRESHOLD:
        print(f"🔧 Compressing message: {token_count} tokens → {MESSAGE_COMPRESSED_SIZE} tokens")
        compressed_content = compress_message(message['content'], MESSAGE_COMPRESSED_SIZE)
        return {
            "role": message['role'],
            "content": f"[Previous scene, compressed]: {compressed_content}"
        }
    
    return message


def generate_summary_incremental(session_id: str, target_coverage: int) -> str:
    """Generate summary incrementally"""
    # Check if we have a previous summary to build on
    latest = get_latest_cached_summary(session_id)
    
    if latest:
        prev_coverage, prev_summary = latest
        
        # If we already have summary for this coverage, return it
        if prev_coverage >= target_coverage:
            return prev_summary
        
        # Generate incremental summary for new messages
        new_messages = get_messages_range(session_id, prev_coverage + 1, target_coverage)
        
        if new_messages:
            print(f"📝 Generating incremental summary for messages {prev_coverage + 1}-{target_coverage}")
            new_summary_part = generate_summary(new_messages, max_tokens=1000)
            
            # Combine summaries
            combined = f"{prev_summary}\n\nRecent developments: {new_summary_part}"
            
            # If combined is too long, re-summarize
            if estimate_tokens(combined) > SUMMARY_MAX_TOKENS:
                print("🔄 Combined summary too long, re-summarizing...")
                all_messages = get_messages_range(session_id, 1, target_coverage)
                combined = generate_summary(all_messages, SUMMARY_MAX_TOKENS)
            
            return combined
        else:
            return prev_summary
    else:
        # No previous summary, generate from scratch
        print(f"📝 Generating summary for messages 1-{target_coverage}")
        messages = get_messages_range(session_id, 1, target_coverage)
        summary = generate_summary(messages, SUMMARY_MAX_TOKENS)
        return summary


def build_context(session_id: str, current_prompt: str) -> List[Dict]:
    """Build context for the LLM request"""
    total_messages = count_messages(session_id)
    
    print(f"\n📊 Building context: {total_messages} total messages")
    
    # PHASE 1: Short conversations - send everything
    if total_messages <= RECENT_MESSAGE_COUNT:
        print(f"✅ Short conversation, sending all {total_messages} messages")
        messages = get_all_messages(session_id)
        
        # Compress any long messages
        messages = [compress_if_needed(msg) for msg in messages]
        
        return messages
    
    # PHASE 2: Long conversations - summarize old, keep recent
    old_message_count = total_messages - RECENT_MESSAGE_COUNT
    print(f"📦 Long conversation: {old_message_count} old + {RECENT_MESSAGE_COUNT} recent")
    
    # Get or create summary for old messages
    summary = get_cached_summary(session_id, old_message_count)
    
    if not summary:
        print(f"🔨 Generating new summary for {old_message_count} messages...")
        summary = generate_summary_incremental(session_id, old_message_count)
        cache_summary(session_id, old_message_count, summary)
        print("✅ Summary cached")
    else:
        print(f"♻️  Using cached summary for {old_message_count} messages")
    
    # Get recent messages
    recent_messages = get_last_n_messages(session_id, RECENT_MESSAGE_COUNT)
    
    # Compress long recent messages
    recent_messages = [compress_if_needed(msg) for msg in recent_messages]
    
    # Build final context
    context = [
        {"role": "system", "content": f"{STORY_SYSTEM_PROMPT}\n\nStory so far: {summary}"}
    ]
    context.extend(recent_messages)
    
    # Estimate total tokens
    total_tokens = sum(estimate_tokens(msg['content']) for msg in context)
    print(f"📏 Total context tokens: ~{total_tokens}")
    
    # Safety check
    if total_tokens > MAX_INPUT_TOKENS:
        print("⚠️  Context exceeds limit! Applying emergency truncation...")
        # Emergency: keep only last 10 messages + summary
        context = [
            {"role": "system", "content": f"{STORY_SYSTEM_PROMPT}\n\nStory so far: {summary}"}
        ]
        context.extend(recent_messages[-10:])
    
    return context