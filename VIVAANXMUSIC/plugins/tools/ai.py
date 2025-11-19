"""
AI Chatbot Handler - Actually Working AI
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
    return f"**ᴍᴏᴅᴇʟ:** `{model_name}`\n\n**ʀᴇsᴘᴏɴsᴇ:**\n{content}"


async def handle_ai_request(message: Message, model_name: str):
    """Handle AI requests using Hugging Face Inference API"""
    prompt = get_prompt(message)
    if not prompt:
        return await message.reply_text(
            f"❌ **Usage:** `{message.text.split()[0]} [your question]`\n\n"
            f"**Example:** `{message.text.split()[0]} What is AI?`"
        )

    await message._client.send_chat_action(message.chat.id, ChatAction.TYPING)

    try:
        # Use Hugging Face Inference API (free, no API key needed)
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api-inference.huggingface.co/models/facebook/blenderbot-400M-distill",
                json={"inputs": prompt},
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Extract response
                if isinstance(data, list) and len(data) > 0:
                    result = data[0].get("generated_text", "")
                    if result:
                        await message.reply_text(format_response(model_name, result))
                        return
                elif isinstance(data, dict) and "generated_text" in data:
                    result = data["generated_text"]
                    await message.reply_text(format_response(model_name, result))
                    return
        
        # Fallback message
        await message.reply_text(
            "⚠️ **AI is warming up...**\n\n"
            "The AI model needs a moment to load. Please try again in 10 seconds."
        )

    except httpx.TimeoutException:
        await message.reply_text(
            "❌ **Timeout!** The AI took too long to respond. Try a shorter question."
        )
    except Exception as e:
        await message.reply_text(
            f"❌ **Error:** {str(e)[:150]}\n\n"
            f"Please try again in a moment."
        )


# ────────────────────────────────────────────────────────────
# Commands
# ────────────────────────────────────────────────────────────

@app.on_message(filters.command("jarvis"))
async def jarvis_handler(client: Client, message: Message):
    """Jarvis AI - Your Personal Assistant"""
    await handle_ai_request(message, "Jarvis AI")


@app.on_message(filters.command("ask"))
async def ask_handler(client: Client, message: Message):
    """Ask AI - General Questions"""
    await handle_ai_request(message, "Ask AI")


@app.on_message(filters.command("assis"))
async def assis_handler(client: Client, message: Message):
    """Assistant AI - Your Helper"""
    await handle_ai_request(message, "Assistant AI")


@app.on_message(filters.command("gpt"))
async def gpt_handler(client: Client, message: Message):
    """ChatGPT AI"""
    await handle_ai_request(message, "ChatGPT")


@app.on_message(filters.command(["aihelp", "ai"]))
async def ai_help(client: Client, message: Message):
    """Show AI commands"""
    help_text = """
🤖 **AI Chatbot Commands**

**Available Commands:**
• `jarvis [question]` - Your personal AI assistant
• `ask [question]` - Ask any question
• `assis [question]` - Get help from assistant
• `/gpt [question]` - ChatGPT alternative

**Usage:**
`jarvis What is artificial intelligence?`
`ask How does Python work?`
`assis Tell me a joke`
`/gpt Explain quantum physics`

**Powered by:**
🔹 Hugging Face BlenderBot
🔹 Free & Open Source AI
🔹 No API keys required

**Note:**
First request may take 10-20 seconds to warm up the model.
"""
    await message.reply_text(help_text)
