# backend/routes/chatbot.py

from typing import List, Optional, Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

router = APIRouter()


# ---------- Pydantic models ----------

class ChatTurn(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(..., min_length=1, max_length=5000, description="Message content")


class ChatbotRequest(BaseModel):
    """
    Request body for the chatbot.

    - message: the latest user message
    - itinerary_context: OPTIONAL – the itinerary JSON you got back
      from /itinerary/itinerary/generate. You can just paste it in
      when testing from Swagger.
    - history: OPTIONAL – previous turns of the conversation
    """
    message: str = Field(..., min_length=1, max_length=2000, description="Latest user message")
    itinerary_context: Optional[dict] = Field(
        default=None,
        description="Itinerary JSON returned by /itinerary/itinerary/generate",
    )
    history: List[ChatTurn] = Field(
        default_factory=list,
        description="Previous messages in the conversation (max 50 messages)",
    )


class ChatbotResponse(BaseModel):
    reply: str
    used_llm: bool = False


# ---------- LLM helper ----------

def _build_system_prompt(itinerary_context: Optional[dict], language: str = "en") -> str:
    language_instruction = "Answer in clear, friendly English." if language == "en" else "Answer in clear, friendly Urdu (اردو). Use proper Urdu script."
    
    base = (
        "You are the Smart Itinerary Planner assistant. "
        "You help the user understand and refine their travel itinerary for Pakistan. "
        f"{language_instruction} "
        "If they ask to change the plan, you can propose a revised plan in text, "
        "but you do NOT need to return raw JSON – just a well-formatted explanation.\n\n"
    )

    if itinerary_context:
        base += (
            "Here is the current itinerary and meta-data as JSON. "
            "Use it as ground truth when answering questions or making adjustments:\n"
            f"{itinerary_context}\n\n"
        )
    else:
        base += (
            "Currently no itinerary JSON was provided, so answer in a general way "
            "based on the user's message and common sense about travel in Pakistan.\n\n"
        )

    base += (
        "Always keep answers concise but helpful. "
        "If the user asks something unrelated to travel, you can still reply helpfully."
    )
    return base


def _call_llm_chat(message: str,
                   itinerary_context: Optional[dict],
                   history: List[ChatTurn],
                   language: str = "en") -> ChatbotResponse:
    """
    Try Groq first (if GROQ_API_KEY is set), then OpenAI (if OPENAI_API_KEY is set).
    If both fail or libraries are missing, fall back to a simple rule-based reply.
    """
    # Detect language from message if it contains Urdu request
    if "respond in urdu" in message.lower() or "اردو" in message or "please respond in urdu" in message.lower():
        language = "ur"
        # Remove the language instruction from message for cleaner context
        import re
        message = re.sub(r'Please respond in Urdu \(اردو\):\s*', '', message, flags=re.IGNORECASE).strip()
        message = re.sub(r'respond in urdu[:\s]*', '', message, flags=re.IGNORECASE).strip()
    
    system_prompt = _build_system_prompt(itinerary_context, language)

    messages = [{"role": "system", "content": system_prompt}]
    for turn in history:
        messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": message})

    # ---------- Try Groq ----------
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key:
        try:
            from groq import Groq  # type: ignore
            client = Groq(api_key=groq_key)
            resp = client.chat.completions.create(
                model="llama-3.1-8b-instant",  # or any Groq chat model you like
                messages=messages,
                temperature=0.6,
                max_tokens=600,
            )
            reply = resp.choices[0].message.content
            return ChatbotResponse(reply=reply, used_llm=True)
        except Exception as e:
            print(f"[Chatbot] Groq call failed, will try OpenAI. Error: {e}")

    # ---------- Try OpenAI ----------
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        try:
            from openai import OpenAI  # type: ignore
            client = OpenAI(api_key=openai_key)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",  # cheap + good enough
                messages=messages,
                temperature=0.6,
                max_tokens=600,
            )
            reply = resp.choices[0].message.content
            return ChatbotResponse(reply=reply, used_llm=True)
        except Exception as e:
            print(f"[Chatbot] OpenAI call failed, will fall back. Error: {e}")

    # ---------- Fallback: simple rule-based reply ----------
    # This makes the endpoint usable even without any keys or extra libraries.
    fallback_reply = (
        "I'm currently running in demo mode without an LLM.\n\n"
        "Here is what I understood:\n"
        f"- Your latest message: '{message}'.\n"
    )
    if itinerary_context:
        fallback_reply += (
            "- An itinerary JSON was provided; I would normally use it to answer "
            "questions and suggest changes.\n\n"
            "For now, please explain what you want to change in your plan, "
            "and I will describe it in simple text."
        )
    else:
        fallback_reply += (
            "- No itinerary JSON was provided yet. You can first generate one using "
            "the itinerary endpoint, then paste it here in `itinerary_context` "
            "to chat about specific days/places."
        )

    return ChatbotResponse(reply=fallback_reply, used_llm=False)


# ---------- FastAPI route ----------

@router.post("/chat", response_model=ChatbotResponse)
def chat_with_itinerary(req: ChatbotRequest) -> ChatbotResponse:
    """
    Main chatbot endpoint.

    From Swagger (/docs):
    1. First call /itinerary/itinerary/generate to get a full itinerary.
    2. Copy the JSON you get in the response.
    3. Call /chatbot/chat, paste that JSON into `itinerary_context`,
       and write your question in `message`.
    """
    try:
        # Additional validation
        if not req.message or not req.message.strip():
            raise HTTPException(
                status_code=400,
                detail="Message cannot be empty"
            )
        
        if len(req.message) > 2000:
            raise HTTPException(
                status_code=400,
                detail="Message is too long (max 2000 characters)"
            )
        
        if len(req.history) > 50:
            raise HTTPException(
                status_code=400,
                detail="History is too long (max 50 messages)"
            )
        
        # Clean message
        message_clean = req.message.strip()
        
        response = _call_llm_chat(
            message=message_clean,
            itinerary_context=req.itinerary_context,
            history=req.history,
            language="en"  # Can be extended to accept language from request
        )
        return response
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Chatbot] Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Chatbot error")

