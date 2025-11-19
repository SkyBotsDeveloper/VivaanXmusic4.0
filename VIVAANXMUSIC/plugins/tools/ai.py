"""
AI Chatbot Handler - Yabes API (Properly Implemented)
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
    content = content.strip()
    if len(content) > 4000:
        content = content[:3997] + "..."
    return f"**{model_name}:**\n\n{content}"


async def handle_ai_request(message: Message, model_name: str, api_endpoint: str):
    """Handle AI requests using Yabes API"""
    prompt = get_prompt(message)
    if not prompt:
        return await message.reply_text(
            f"❌ **Usage:** `{message.text.split()[0]} [your question]`\n\n"
            f"**Example:** `{message.text.split()[0]} What is AI?`"
        )

    await message._client.send_chat_action(message.chat.id, ChatAction.TYPING)

    try:
        # Yabes API - Correct implementation
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://yabes-api.pages.dev{api_endpoint}",
                json={"prompt": prompt},
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Extract result based on API response structure
                if data.get("status") == True and "result" in data:
                    result = data["result"]
                    await message.reply_text(format_response(model_name, result))
                    return
                elif "result" in data:
                    result = data["result"]
                    await message.reply_text(format_response(model_name, result))
                    return
            
            # Error response
            await message.reply_text(
                f"❌ **API Error**\n\n"
                f"Status: {response.status_code}\n"
                f"Response: {response.text[:200]}"
            )

    except httpx.TimeoutException:
        await message.reply_text("❌ **Timeout!** Please try again.")
    except Exception as e:
        await message.reply_text(f"❌ **Error:** {str(e)[:200]}")


# ────────────────────────────────────────────────────────────
# Commands - Each uses different AI model
# ────────────────────────────────────────────────────────────

@app.on_message(filters.command("jarvis"))
async def jarvis_handler(client: Client, message: Message):
    """Jarvis AI - Felo AI"""
    await handle_ai_request(message, "🤖 Jarvis AI", "/api/ai/chat/felo-ai")


@app.on_message(filters.command("ask"))
async def ask_handler(client: Client, message: Message):
    """Ask AI - Ninja AI"""
    await handle_ai_request(message, "💬 Ask AI", "/api/ai/chat/ninja-ai")


@app.on_message(filters.command("assis"))
async def assis_handler(client: Client, message: Message):
    """Assistant AI - Meta AI"""
    await handle_ai_request(message, "🎯 Assistant", "/api/ai/chat/meta-ai")


@app.on_message(filters.command("gpt"))
async def gpt_handler(client: Client, message: Message):
    """ChatGPT - Felo AI"""
    await handle_ai_request(message, "✨ ChatGPT", "/api/ai/chat/felo-ai")


@app.on_message(filters.command(["aihelp", "ai"]))
async def ai_help(client: Client, message: Message):
    """AI Help"""
    help_text = """
🤖 **AI Chatbot - Yabes API**

**Commands:**
• `jarvis [question]` - Felo AI (Advanced)
• `ask [question]` - Ninja AI (Fast)
• `assis [question]` - Meta AI (Smart)
• `/gpt [question]` - ChatGPT style

**Examples:**
`jarvis What is quantum computing?`
`ask Tell me a joke`
`assis Write a poem`
`/gpt Explain AI`

**✅ Powered by:**
🔹 Felo AI (jarvis, /gpt)
🔹 Ninja AI (ask)
🔹 Meta AI (assis)

**Try it now!** 🚀
"""
    await message.reply_text(help_text)
