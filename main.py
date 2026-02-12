import time
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import json
import uvicorn
from config import MODEL_CONFIG, MIN_REQUEST_INTERVAL
from database import init_database, store_message_with_usage, get_session_stats, delete_session, count_messages, get_cached_summary,estimate_tokens,get_all_sessions
from context import build_context, generate_summary_incremental
from llm_utils import call_llm
import os

app = FastAPI()

# Rate limiting
last_request_time = 0
#uvicorn port
port = 9000
# Initialize database on startup
init_database()


@app.get("/")
def root():
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
    store_message_with_usage(body.session_id, "user", body.prompt, input_tokens=0, output_tokens=0)
    
    # Build context
    context = build_context(body.session_id, body.prompt)
    
    # Add current prompt
    context.append({"role": "user", "content": body.prompt})
    
    try:
        print(f"🚀 Sending request to {body.model}...")
        
        # Call LLM
        assistant_response,usage = call_llm(context, max_tokens=body.max_tokens)
        
        last_request_time = time.time()

        # Extract actual token counts
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)
        
        print(f"📊 Tokens - Input: {prompt_tokens}, Output: {completion_tokens}, Total: {total_tokens}")
        
        # Store AI response with ACTUAL token count
        store_message_with_usage(
            body.session_id, 
            "assistant", 
            assistant_response,
            input_tokens=prompt_tokens,      # ← Real numbers!
            output_tokens=completion_tokens
        )
        
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
            ],
            "usage": usage  # ← Include usage in response
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

    # Calculate REAL costs
    input_cost = (stats['input_tokens'] / 1_000_000) * MODEL_CONFIG['input_cost_per_1m']
    output_cost = (stats['output_tokens'] / 1_000_000) * MODEL_CONFIG['output_cost_per_1m']
    total_cost = input_cost + output_cost
    
    return {
        "session_id": session_id,
        **stats,
        "costs": {
            "input": f"${input_cost:.6f}",
            "output": f"${output_cost:.6f}",
            "total": f"${total_cost:.6f}"
        }
    }


@app.delete("/api/session/{session_id}")
def delete_session_endpoint(session_id: str):
    """Delete a session and all its data"""
    deleted = delete_session(session_id)
    
    return {"session_id": session_id, "deleted_messages": deleted}


@app.post("/api/chat/stream")
async def chat_stream(body: PromptIn):
    """Streaming chat endpoint"""
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
    print(f"📨 Streaming request from session: {body.session_id}")
    print(f"💬 User prompt: {body.prompt[:100]}...")
    
    # Store user message
    store_message_with_usage(body.session_id, "user", body.prompt, input_tokens=0, output_tokens=0)
    
    # Build context
    context = build_context(body.session_id, body.prompt)
    context.append({"role": "user", "content": body.prompt})
    
    # Generator function for streaming
    async def generate():
        from llm_utils import call_llm_stream
        
        full_response = ""
        total_input_tokens = 0
        total_output_tokens = 0
        
        try:
            print(f"🚀 Starting stream to {body.model}...")
            last_request_time = time.time()
            
            # Stream chunks
            for chunk in call_llm_stream(context, max_tokens=body.max_tokens):
                full_response += chunk
                yield f"data: {json.dumps({'content': chunk})}\n\n"
            
            # After streaming completes, call once more to get usage stats
            # (OpenRouter doesn't provide usage in streaming mode, so we estimate)

            # Estimate input tokens from context
            total_input_tokens = sum(estimate_tokens(msg['content']) for msg in context)

            # Estimate output tokens from response
            total_output_tokens = estimate_tokens(full_response)
            
            # Signal completion with token info
            yield "data: " + json.dumps({
                    'done': True,
                    'usage': {
                        'prompt_tokens': total_input_tokens,
                        'completion_tokens': total_output_tokens
                    }
            }) + "\n\n"
            
            # Store with token usage
            store_message_with_usage(
                body.session_id, 
                "assistant", 
                full_response,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens
            )
            
            print(f"✅ Stream complete: {len(full_response)} chars")
            print(f"📊 Tokens - Input: {total_input_tokens}, Output: {total_output_tokens}")
            
        except Exception as e:
            print(f"❌ Streaming error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/api/sessions")
def get_sessions():
    """Get all saved story sessions"""
    sessions = get_all_sessions()
    return {"sessions": sessions, "total": len(sessions)}

if __name__ == "__main__":
    print(f"🚀 Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)