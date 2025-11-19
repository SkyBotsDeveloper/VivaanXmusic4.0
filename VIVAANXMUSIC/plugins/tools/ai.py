"""
AI Chatbot Handler - Multiple AI Models Support
Supports: Jarvis (Felo AI), Ask (Ninja AI), Assis (Meta AI)
Part of VivaanXMusic Bot
"""

import httpx
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatAction
from VIVAANXMUSIC import app


# ────────────────────────────────────────────────────────────
# Helper Functions
# ────────────────────────────────────────────────────────────

def get_prompt(message: Message) -> str | None:
    """Extract prompt from message"""
    parts = message.text.split(' ', 1)
    return parts[1] if len(parts) > 1 else None


def format_response(model_name: str, content: str) -> str:
    """Format AI response with model name"""
    return f"**ᴍᴏᴅᴇʟ:** `{model_name}`\n\n**ʀᴇsᴘᴏɴsᴇ:**\n{content}"


# ────────────────────────────────────────────────────────────
# Yabes API Handler
# ────────────────────────────────────────────────────────────

YABES_API_BASE = "https://yabes-api.pages.dev"

async def handle_yabes_api(message: Message, endpoint: str, model_name: str):
    """Handle Yabes API-based models"""
    prompt = get_prompt(message)
    if not prompt:
        return await message.reply_text("❌ **Usage:** `command [your question]`\n\n**Example:** `jarvis What is AI?`")

    await message._client.send_chat_action(message.chat.id, ChatAction.TYPING)

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{YABES_API_BASE}{endpoint}",
                json={"prompt": prompt}
            )
            response.raise_for_status()
            data = response.json()

        # Extract response
        if data.get("status") and "result" in data:
            result = data["result"]
            await message.reply_text(format_response(model_name, result))
        else:
            await message.reply_text(f"⚠️ **{model_name}** returned no content. Try again.")

    except httpx.TimeoutException:
        await message.reply_text("❌ **Timeout Error!** The API took too long to respond. Please try again.")
    except httpx.HTTPStatusError as e:
        await message.reply_text(f"❌ **HTTP Error {e.response.status_code}!** API is currently unavailable.")
    except Exception as e:
        await message.reply_text(f"❌ **Error:** {str(e)[:200]}")


# ────────────────────────────────────────────────────────────
# AI Commands (Your Original Commands)
# ────────────────────────────────────────────────────────────

@app.on_message(filters.command("jarvis"))
async def jarvis_handler(client: Client, message: Message):
    """Jarvis AI - Your Personal Assistant (Felo AI)"""
    await handle_yabes_api(message, "/api/ai/chat/felo-ai", "Jarvis AI")


@app.on_message(filters.command("ask"))
async def ask_handler(client: Client, message: Message):
    """Ask AI - General Questions (Ninja AI)"""
    await handle_yabes_api(message, "/api/ai/chat/ninja-ai", "Ask AI")


@app.on_message(filters.command("assis"))
async def assis_handler(client: Client, message: Message):
    """Assistant AI - Your Helper (Meta AI)"""
    await handle_yabes_api(message, "/api/ai/chat/meta-ai", "Assistant AI")


@app.on_message(filters.command("gpt"))
async def gpt_handler(client: Client, message: Message):
    """ChatGPT AI - Alias for Felo AI"""
    await handle_yabes_api(message, "/api/ai/chat/felo-ai", "ChatGPT")


# ────────────────────────────────────────────────────────────
# Help Command
# ────────────────────────────────────────────────────────────

@app.on_message(filters.command(["aihelp", "ai"]))
async def ai_help(client: Client, message: Message):
    """Show all available AI commands"""
    help_text = """
🤖 **AI Chatbot Commands**

**Main Commands:**
• `jarvis [question]` - Your personal AI assistant
• `ask [question]` - Ask any question
• `assis [question]` - Get help from assistant
• `/gpt [question]` - ChatGPT alternative

**Usage Examples:**
`jarvis What is quantum computing?`
`ask How does blockchain work?`
`assis Write a poem about nature`
`/gpt Explain machine learning`

**Features:**
✅ Fast & accurate responses
✅ Multiple AI models
✅ No rate limits
✅ 24/7 availability

**Powered by:**
🔹 Felo AI (jarvis, /gpt)
🔹 Ninja AI (ask)
🔹 Meta AI (assis)

Need help? Contact support.
"""
    await message.reply_text(help_text)
