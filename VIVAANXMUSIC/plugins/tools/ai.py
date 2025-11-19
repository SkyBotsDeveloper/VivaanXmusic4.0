"""
AI Chatbot Handler - Yabes API (Perfect Implementation)
Production-Ready Code with Complete Error Handling
Author: Elite Developer
Part of VivaanXMusic Bot
"""

import httpx
import logging
from typing import Optional, Dict, Any
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatAction
from VIVAANXMUSIC import app

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API Configuration
API_BASE_URL = "https://yabes-api.pages.dev"
API_TIMEOUT = 30.0

# API Endpoints
ENDPOINTS = {
    "felo": "/api/ai/chat/felo-ai",
    "ninja": "/api/ai/chat/ninja-ai",
    "meta": "/api/ai/chat/meta-ai"
}


# ────────────────────────────────────────────────────────────
# Helper Functions
# ────────────────────────────────────────────────────────────

def get_prompt(message: Message) -> Optional[str]:
    """
    Extract prompt from message
    
    Args:
        message: Pyrogram Message object
        
    Returns:
        str: User's prompt or None
    """
    try:
        parts = message.text.split(' ', 1)
        return parts[1].strip() if len(parts) > 1 else None
    except Exception as e:
        logger.error(f"Error extracting prompt: {e}")
        return None


def format_response(model_name: str, content: str) -> str:
    """
    Format AI response for Telegram
    
    Args:
        model_name: Name of AI model
        content: AI response content
        
    Returns:
        str: Formatted response
    """
    content = content.strip()
    
    # Telegram message limit
    if len(content) > 4000:
        content = content[:3997] + "..."
    
    return f"**{model_name}:**\n\n{content}"


async def call_yabes_api(endpoint: str, query: str) -> Dict[str, Any]:
    """
    Call Yabes AI API
    
    Args:
        endpoint: API endpoint path
        query: User's question
        
    Returns:
        dict: API response data
        
    Raises:
        httpx.HTTPError: On HTTP errors
    """
    async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
        response = await client.post(
            f"{API_BASE_URL}{endpoint}",
            json={"query": query},  # CORRECT parameter name
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
        )
        response.raise_for_status()
        return response.json()


async def handle_ai_request(
    message: Message,
    model_name: str,
    endpoint: str
) -> None:
    """
    Handle AI request with complete error handling
    
    Args:
        message: Pyrogram Message object
        model_name: Display name of AI model
        endpoint: API endpoint to use
    """
    # Extract user prompt
    query = get_prompt(message)
    
    if not query:
        await message.reply_text(
            f"❌ **Usage Error**\n\n"
            f"**Correct usage:**\n"
            f"`{message.text.split()[0]} [your question]`\n\n"
            f"**Example:**\n"
            f"`{message.text.split()[0]} What is artificial intelligence?`"
        )
        return
    
    # Show typing indicator
    await message._client.send_chat_action(message.chat.id, ChatAction.TYPING)
    
    try:
        # Call API
        logger.info(f"API Request - Endpoint: {endpoint}, Query: {query[:50]}...")
        data = await call_yabes_api(endpoint, query)
        
        # Parse response
        if data.get("status") and "result" in data:
            result = data["result"]
            
            if result:
                await message.reply_text(format_response(model_name, result))
                logger.info(f"Success - Model: {model_name}, Response length: {len(result)}")
            else:
                await message.reply_text(
                    "⚠️ **Empty Response**\n\n"
                    "The AI returned an empty response. Please try rephrasing your question."
                )
        else:
            # Unexpected response format
            await message.reply_text(
                "⚠️ **Unexpected Response**\n\n"
                f"API returned: `{str(data)[:200]}`"
            )
            logger.warning(f"Unexpected API response: {data}")
    
    except httpx.TimeoutException:
        await message.reply_text(
            "⏱️ **Timeout Error**\n\n"
            "The AI service took too long to respond. Please try again with a shorter question."
        )
        logger.error(f"Timeout - Endpoint: {endpoint}")
    
    except httpx.HTTPStatusError as e:
        error_msg = f"HTTP {e.response.status_code}"
        try:
            error_data = e.response.json()
            error_detail = error_data.get("message", str(error_data))
        except:
            error_detail = e.response.text[:200]
        
        await message.reply_text(
            f"❌ **API Error**\n\n"
            f"**Status:** {error_msg}\n"
            f"**Details:** {error_detail}"
        )
        logger.error(f"HTTP Error - {error_msg}: {error_detail}")
    
    except Exception as e:
        await message.reply_text(
            f"❌ **Unexpected Error**\n\n"
            f"Error: `{str(e)[:200]}`\n\n"
            f"Please try again or contact support."
        )
        logger.exception(f"Unexpected error in handle_ai_request: {e}")


# ────────────────────────────────────────────────────────────
# Command Handlers
# ────────────────────────────────────────────────────────────

@app.on_message(filters.command("jarvis"))
async def jarvis_handler(client: Client, message: Message):
    """
    Jarvis AI - Advanced AI powered by Felo
    Best for: Complex questions, research, detailed explanations
    """
    await handle_ai_request(
        message,
        "🤖 Jarvis AI (Felo)",
        ENDPOINTS["felo"]
    )


@app.on_message(filters.command("ask"))
async def ask_handler(client: Client, message: Message):
    """
    Ask AI - Fast AI powered by Ninja
    Best for: Quick questions, general knowledge, simple tasks
    """
    await handle_ai_request(
        message,
        "💬 Ask AI (Ninja)",
        ENDPOINTS["ninja"]
    )


@app.on_message(filters.command("assis"))
async def assis_handler(client: Client, message: Message):
    """
    Assistant AI - Smart AI powered by Meta
    Best for: Conversations, creative writing, assistance
    """
    await handle_ai_request(
        message,
        "🎯 Assistant (Meta AI)",
        ENDPOINTS["meta"]
    )


@app.on_message(filters.command("gpt"))
async def gpt_handler(client: Client, message: Message):
    """
    ChatGPT Style - Powered by Felo AI
    Best for: ChatGPT-like interactions
    """
    await handle_ai_request(
        message,
        "✨ ChatGPT (Felo)",
        ENDPOINTS["felo"]
    )


@app.on_message(filters.command(["aihelp", "ai"]))
async def ai_help_handler(client: Client, message: Message):
    """Display comprehensive AI help information"""
    help_text = """
🤖 **AI Chatbot - Production Ready**

**Available Commands:**

• `jarvis [question]` - Advanced AI (Felo)
  _Best for complex questions & research_

• `ask [question]` - Fast AI (Ninja)
  _Best for quick answers & facts_

• `assis [question]` - Smart AI (Meta)
  _Best for conversations & creativity_

• `/gpt [question]` - ChatGPT Style
  _Best for GPT-like interactions_

**📚 Usage Examples:**

`jarvis Explain quantum computing in simple terms`
`ask What is the capital of France?`
`assis Write a short poem about the ocean`
`/gpt How does machine learning work?`

**✨ Features:**

✅ Multiple AI models (Felo, Ninja, Meta)
✅ Fast & accurate responses
✅ Production-grade error handling
✅ 24/7 availability
✅ No rate limits

**⚡ Powered By:**
Yabes API - Free AI Services

**💡 Tips:**
• Be specific in your questions
• Keep questions under 200 words
• Try different models for best results

Need more help? Contact support!
"""
    await message.reply_text(help_text)


# ────────────────────────────────────────────────────────────
# Module Info
# ────────────────────────────────────────────────────────────

__MODULE__ = "AI Chat"
__DESCRIPTION__ = "Production-ready AI chatbot with multiple models"
__VERSION__ = "2.0.0"
__AUTHOR__ = "Elite Developer"
