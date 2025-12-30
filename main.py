import time
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config import MODEL_CONFIG, MIN_REQUEST_INTERVAL
from database import init_database, store_message, get_session_stats, delete_session, count_messages, get_cached_summary
from context import build_context, generate_summary_incremental
from llm_utils import call_llm

app = FastAPI()

# Rate limiting
last_request_time = 0

# Initialize database on startup
init_database()


@app.get("/")
def root():
    # return {"message": "Story API is running", "model": MODEL_CONFIG["name"]}
    return FileResponse("index.html")


class PromptIn(BaseModel):
    prompt: str
    model: str = MODEL_CONFIG["name"]
    session_id: str = "default"
    max_tokens: int = MODEL_CONFIG["max_output"]


@app.post("/api/chat")
def chat(body: PromptIn):
    global last_request_time
    
    # Rate limiting
    current_time = time.time()
    time_since_last = current_time - last_request_time
    
    if time_since_last < MIN_REQUEST_INTERVAL:
        wait_time = MIN_REQUEST_INTERVAL - time_since_last
        raise HTTPException(
            status_code=429, 
            detail=f"Please wait {wait_time:.1f} seconds"
        )
    
    print(f"\n{'='*60}")
    print(f"📨 New request from session: {body.session_id}")
    print(f"💬 User prompt: {body.prompt[:100]}...")
    
    # Store user message
    store_message(body.session_id, "user", body.prompt)
    
    # Build context
    context = build_context(body.session_id, body.prompt)
    
    # Add current prompt
    context.append({"role": "user", "content": body.prompt})
    
    try:
        print(f"🚀 Sending request to {body.model}...")
        
        # Call LLM
        assistant_response = call_llm(context, max_tokens=body.max_tokens)
        
        last_request_time = time.time()
        
        # Store AI response (FULL, no compression)
        store_message(body.session_id, "assistant", assistant_response)
        
        print(f"✅ Response generated: {len(assistant_response)} chars")
        print(f"{'='*60}\n")
        
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": assistant_response
                    }
                }
            ]
        }
        
    except Exception as e:
        print(f"❌ Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/summary/{session_id}")
def get_summary_endpoint(session_id: str):
    """Get current summary for a session"""
    total_messages = count_messages(session_id)
    
    if total_messages == 0:
        return {"session_id": session_id, "summary": "No messages yet", "messages": 0}
    
    from config import RECENT_MESSAGE_COUNT
    
    if total_messages <= RECENT_MESSAGE_COUNT:
        return {
            "session_id": session_id, 
            "summary": "Conversation too short for summary",
            "messages": total_messages
        }
    
    old_count = total_messages - RECENT_MESSAGE_COUNT
    summary = get_cached_summary(session_id, old_count)
    
    if not summary:
        from database import cache_summary
        summary = generate_summary_incremental(session_id, old_count)
        cache_summary(session_id, old_count, summary)
    
    return {
        "session_id": session_id,
        "summary": summary,
        "messages": total_messages,
        "summary_covers": old_count
    }


@app.get("/api/stats/{session_id}")
def get_stats(session_id: str):
    """Get statistics for a session"""
    stats = get_session_stats(session_id)
    
    return {
        "session_id": session_id,
        **stats,
        "estimated_cost": f"${(stats['total_tokens'] / 1_000_000) * MODEL_CONFIG['input_cost_per_1m']:.4f}"
    }


@app.delete("/api/session/{session_id}")
def delete_session_endpoint(session_id: str):
    """Delete a session and all its data"""
    deleted = delete_session(session_id)
    
    return {"session_id": session_id, "deleted_messages": deleted}


if __name__ == "__main__":
    import uvicorn
    port = 9000
    print(f"🚀 Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)