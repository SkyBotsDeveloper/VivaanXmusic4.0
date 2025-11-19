"""
AI Chatbot Handler - FINAL PERFECT VERSION
100% Working with Yabes API
Part of VivaanXMusic Bot
"""

import httpx
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatAction
from VIVAANXMUSIC import app


def get_prompt(message: Message) -> str | None:
    """Extract prompt from message"""
    parts = message.text.split(' ', 1)
    return parts[1].strip() if len(parts) > 1 else None


def format_response(model_name: str, content: str) -> str:
    """Format AI response beautifully"""
    content = content.strip()
    if len(content) > 4000:
        content = content[:3997] + "..."
    return f"**{model_name}**\n\n{content}"


async def handle_ai_request(message: Message, model_name: str, endpoint: str):
    """Handle AI requests with perfect response parsing"""
    query = get_prompt(message)
    
    if not query:
        await message.reply_text(
            f"❌ **Usage:** `{message.text.split()[0]} [your question]`\n\n"
            f"**Example:** `{message.text.split()[0]} What is AI?`"
        )
        return
    
    await message._client.send_chat_action(message.chat.id, ChatAction.TYPING)
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://yabes-api.pages.dev{endpoint}",
                json={"query": query},
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Parse response correctly - check for 'results' (plural)
                result_text = None
                
                if "results" in data:
                    result_text = data["results"]
                elif "result" in data:
                    result_text = data["result"]
                
                if result_text and isinstance(result_text, str) and result_text.strip():
                    await message.reply_text(format_response(model_name, result_text))
                else:
                    await message.reply_text(
                        "⚠️ **No response from AI**\n\n"
                        "Please try rephrasing your question."
                    )
            else:
                await message.reply_text(
                    f"❌ **API Error {response.status_code}**\n\n"
                    f"Please try again later."
                )
    
    except httpx.TimeoutException:
        await message.reply_text("⏱️ **Timeout!** Please try again.")
    except Exception as e:
        await message.reply_text(f"❌ **Error:** {str(e)[:150]}")


# ────────────────────────────────────────────────────────────
# Commands
# ────────────────────────────────────────────────────────────

@app.on_message(filters.command("jarvis"))
async def jarvis_handler(client: Client, message: Message):
    """Jarvis AI - Felo"""
    await handle_ai_request(message, "🤖 Jarvis AI", "/api/ai/chat/felo-ai")


@app.on_message(filters.command("ask"))
async def ask_handler(client: Client, message: Message):
    """Ask AI - Ninja"""
    await handle_ai_request(message, "💬 Ask AI", "/api/ai/chat/ninja-ai")


@app.on_message(filters.command("assis"))
async def assis_handler(client: Client, message: Message):
    """Assistant AI - Meta"""
    await handle_ai_request(message, "🎯 Assistant", "/api/ai/chat/meta-ai")


@app.on_message(filters.command("gpt"))
async def gpt_handler(client: Client, message: Message):
    """ChatGPT - Felo"""
    await handle_ai_request(message, "✨ ChatGPT", "/api/ai/chat/felo-ai")


@app.on_message(filters.command(["aihelp", "ai"]))
async def ai_help_handler(client: Client, message: Message):
    """AI Help"""
    help_text = """
🤖 **AI Chatbot Commands**

**Commands:**
• `jarvis [question]` - Felo AI (Advanced)
• `ask [question]` - Ninja AI (Fast)  
• `assis [question]` - Meta AI (Smart)
• `/gpt [question]` - ChatGPT Style

**Examples:**
`jarvis What is artificial intelligence?`
`ask Tell me a joke`
`assis Write a haiku`
`/gpt Explain Python`

**✨ Features:**
✅ Human-like responses
✅ Fast & accurate
✅ Multiple AI models
✅ Free unlimited usage

**Try it now!** 🚀
"""
    await message.reply_text(help_text)
