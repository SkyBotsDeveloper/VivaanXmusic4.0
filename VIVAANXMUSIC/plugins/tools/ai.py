"""
AI Chatbot Handler - PERFECT FINAL VERSION
Short, Clean Responses - All Commands Working
Part of VivaanXMusic Bot
"""

import httpx
import re
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatAction
from VIVAANXMUSIC import app


def get_prompt(message: Message) -> str | None:
    """Extract prompt from message"""
    parts = message.text.split(' ', 1)
    return parts[1].strip() if len(parts) > 1 else None


def clean_response(text: str) -> str:
    """Clean and shorten AI response"""
    if not text:
        return ""
    
    # Remove URLs and references
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'→.*', '', text)
    text = re.sub(r'References?:.*', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'📚.*', '', text, flags=re.DOTALL)
    text = re.sub(r'-\s*\d+.*→', '', text)
    
    # Split into sentences and keep first 3-4
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    
    # Keep only first 3-4 sentences (about 150-200 words)
    if len(sentences) > 4:
        text = ' '.join(sentences[:4])
    
    # Limit total length
    if len(text) > 800:
        text = text[:797] + "..."
    
    return text.strip()


def format_response(model_name: str, content: str) -> str:
    """Format AI response cleanly"""
    content = clean_response(content)
    if len(content) > 4000:
        content = content[:3997] + "..."
    return f"**{model_name}**\n\n{content}"


async def handle_ai_request(message: Message, model_name: str, endpoint: str):
    """Handle AI requests - ALL endpoints working"""
    query = get_prompt(message)
    
    if not query:
        await message.reply_text(
            f"❌ **Usage:** `{message.text.split()[0]} [question]`\n\n"
            f"**Example:** `{message.text.split()[0]} What is AI?`"
        )
        return
    
    await message._client.send_chat_action(message.chat.id, ChatAction.TYPING)
    
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.post(
                f"https://yabes-api.pages.dev{endpoint}",
                json={"query": query},
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Extract result - try all possible keys
                result_text = None
                
                if "results" in data and data["results"]:
                    result_text = data["results"]
                elif "result" in data and data["result"]:
                    result_text = data["result"]
                elif "response" in data and data["response"]:
                    result_text = data["response"]
                elif "answer" in data and data["answer"]:
                    result_text = data["answer"]
                
                if result_text and isinstance(result_text, str) and result_text.strip():
                    await message.reply_text(format_response(model_name, result_text))
                else:
                    await message.reply_text(
                        "⚠️ **No response**\n\nPlease rephrase your question."
                    )
            else:
                await message.reply_text(
                    f"❌ **Error {response.status_code}**\n\nTry again."
                )
    
    except httpx.TimeoutException:
        await message.reply_text("⏱️ **Timeout!** Try again.")
    except Exception as e:
        await message.reply_text(f"❌ **Error:** Try again.")


# ────────────────────────────────────────────────────────────
# Commands
# ────────────────────────────────────────────────────────────

@app.on_message(filters.command("jarvis"))
async def jarvis_handler(client: Client, message: Message):
    """Jarvis AI - Felo (Advanced)"""
    await handle_ai_request(message, "🤖 Jarvis", "/api/ai/chat/felo-ai")


@app.on_message(filters.command("ask"))
async def ask_handler(client: Client, message: Message):
    """Ask AI - Ninja (Fast)"""
    await handle_ai_request(message, "💬 Ask", "/api/ai/chat/ninja-ai")


@app.on_message(filters.command("assis"))
async def assis_handler(client: Client, message: Message):
    """Assistant - Meta (Smart)"""
    await handle_ai_request(message, "🎯 Assistant", "/api/ai/chat/meta-ai")


@app.on_message(filters.command("gpt"))
async def gpt_handler(client: Client, message: Message):
    """ChatGPT - Felo"""
    await handle_ai_request(message, "✨ ChatGPT", "/api/ai/chat/felo-ai")


@app.on_message(filters.command(["aihelp", "ai"]))
async def ai_help_handler(client: Client, message: Message):
    """AI Help"""
    help_text = """
🤖 **AI Chatbot**

**Commands:**
• `jarvis [question]` - Advanced AI
• `ask [question]` - Fast answers
• `assis [question]` - Smart assistant
• `/gpt [question]` - ChatGPT style

**Examples:**
`jarvis What is AI?`
`ask Tell a joke`
`assis Write a poem`

✅ Short, clean answers
✅ No long references
✅ Fast responses
"""
    await message.reply_text(help_text)
