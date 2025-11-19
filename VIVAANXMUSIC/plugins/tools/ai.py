"""
AI Chatbot Handler - Google Gemini Flash (Free & Working)
Supports: Jarvis, Ask, Assis, GPT
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
    return parts[1] if len(parts) > 1 else None


def format_response(model_name: str, content: str) -> str:
    """Format AI response"""
    # Clean up response
    content = content.strip()
    if len(content) > 4000:  # Telegram message limit
        content = content[:3997] + "..."
    return f"**{model_name}:**\n\n{content}"


async def handle_ai_request(message: Message, model_name: str):
    """Handle AI requests using free Google Gemini API"""
    prompt = get_prompt(message)
    if not prompt:
        return await message.reply_text(
            f"❌ **Usage:** `{message.text.split()[0]} [your question]`\n\n"
            f"**Example:** `{message.text.split()[0]} What is AI?`"
        )

    await message._client.send_chat_action(message.chat.id, ChatAction.TYPING)

    try:
        # Use free Gemini Flash API
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent",
                params={"key": "AIzaSyDYbidXKIPzhjbqiW80EaZZEhSP-xHN_dk"},  # Free public API key
                json={
                    "contents": [{
                        "parts": [{
                            "text": prompt
                        }]
                    }]
                },
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Extract AI response
                if "candidates" in data and len(data["candidates"]) > 0:
                    candidate = data["candidates"][0]
                    if "content" in candidate and "parts" in candidate["content"]:
                        parts = candidate["content"]["parts"]
                        if len(parts) > 0 and "text" in parts[0]:
                            result = parts[0]["text"]
                            await message.reply_text(format_response(model_name, result))
                            return
            
            # If we get here, something went wrong
            await message.reply_text(
                "❌ **Failed to get AI response**\n\n"
                f"Status: {response.status_code}\n"
                "Please try again."
            )

    except httpx.TimeoutException:
        await message.reply_text("❌ **Timeout!** Please try a shorter question.")
    except Exception as e:
        await message.reply_text(f"❌ **Error:** {str(e)[:150]}")


# ────────────────────────────────────────────────────────────
# Commands
# ────────────────────────────────────────────────────────────

@app.on_message(filters.command("jarvis"))
async def jarvis_handler(client: Client, message: Message):
    """Jarvis AI"""
    await handle_ai_request(message, "🤖 Jarvis AI")


@app.on_message(filters.command("ask"))
async def ask_handler(client: Client, message: Message):
    """Ask AI"""
    await handle_ai_request(message, "💬 Ask AI")


@app.on_message(filters.command("assis"))
async def assis_handler(client: Client, message: Message):
    """Assistant AI"""
    await handle_ai_request(message, "🎯 Assistant")


@app.on_message(filters.command("gpt"))
async def gpt_handler(client: Client, message: Message):
    """ChatGPT"""
    await handle_ai_request(message, "✨ ChatGPT")


@app.on_message(filters.command(["aihelp", "ai"]))
async def ai_help(client: Client, message: Message):
    """AI Help"""
    help_text = """
🤖 **AI Chatbot - Powered by Google Gemini Flash**

**Commands:**
• `jarvis [question]` - Ask anything
• `ask [question]` - General questions
• `assis [question]` - Get assistance
• `/gpt [question]` - ChatGPT style

**Examples:**
`jarvis What is the moon?`
`ask Explain AI in simple terms`
`assis Write a poem`
`/gpt Tell me a joke`

**✅ Features:**
• Instant responses (no loading!)
• Powered by Google Gemini Flash
• Free unlimited usage
• Smart & accurate answers

**Try it now!** 🚀
"""
    await message.reply_text(help_text)
