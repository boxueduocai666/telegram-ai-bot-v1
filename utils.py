import html
import re

from config import (
    MAX_TELEGRAM_LENGTH,
)


# ============================================================
# 获取消息文字
# ============================================================
def get_message_text(message):
    if not message:
        return ""

    return message.text or message.caption or ""


# ============================================================
# 获取引用消息
# ============================================================
def get_quoted_message(message):
    if not message:
        return None

    replied = message.reply_to_message

    if not replied:
        return None

    quoted_text = get_message_text(replied)
    quoted_user = replied.from_user

    if quoted_user:
        quoted_name = (
            quoted_user.first_name
            or quoted_user.username
            or "未知用户"
        )

        if quoted_user.username:
            quoted_name += f" (@{quoted_user.username})"
    else:
        quoted_name = "未知用户"

    return {
        "user": quoted_name,
        "text": quoted_text,
        "message_id": replied.message_id,
        "has_photo": bool(replied.photo),
        "has_document": bool(replied.document),
        "has_video": bool(replied.video),
    }


# ============================================================
# 构造引用上下文
# ============================================================
def build_quote_context(message):
    quote = get_quoted_message(message)

    if not quote:
        return ""

    text = quote["text"].strip()

    if not text:
        if quote["has_photo"]:
            text = "[这是一条图片消息，图片本身未提供文字内容。]"
        elif quote["has_document"]:
            text = "[这是一条文件消息。]"
        elif quote["has_video"]:
            text = "[这是一条视频消息。]"
        else:
            text = "[该消息没有文字内容。]"

    return (
        "\n\n"
        "【用户引用的消息】\n"
        "--------------------\n"
        f"发送者：{quote['user']}\n"
        f"消息内容：{text}\n"
        "--------------------\n"
        "请结合这条被引用的消息理解用户的问题。\n"
    )


# ============================================================
# 联网搜索
# ============================================================
def search_web(query: str) -> str:
    if not isinstance(query, str) or not query.strip():
        return "搜索关键词不能为空。"

    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        results = []

        with DDGS() as ddgs:
            for result in ddgs.text(
                query.strip(),
                max_results=5,
            ):
                results.append(result)

        if not results:
            return "未找到相关联网信息。"

        output = []

        for result in results:
            title = result.get("title", "")
            body = result.get("body", "")
            href = result.get("href", "")

            output.append(
                f"- {title}\n"
                f"  {body}\n"
                f"  链接：{href}"
            )

        return "\n\n".join(output)

    except Exception as e:
        print("[SEARCH] 联网搜索失败：", repr(e))
        return f"联网搜索失败：{e}"


# ============================================================
# AI 回复排版
# ============================================================
def format_ai_reply(text):
    if not text:
        return "AI 没有返回内容。"

    text = str(text).strip()

    # --------------------------------------------------------
    # 先 Escape HTML
    # --------------------------------------------------------
    # --------------------------------------------------------
    # Markdown 链接先占位，再统一 Escape HTML。
    # 这样可以避免 URL 中的 & 被重复转义，
    # 同时确保 href 属性中的引号不会破坏 HTML。
    # --------------------------------------------------------
    markdown_links = {}

    def replace_markdown_link(match):
        index = len(markdown_links)
        placeholder = f"__MARKDOWN_LINK_{index}__"
        markdown_links[placeholder] = (
            html.escape(match.group(1), quote=False),
            html.escape(match.group(2), quote=True),
        )
        return placeholder

    text = re.sub(
        r"\[([^\]]+)\]"
        r"\((https?://[^\s)]+)\)",
        replace_markdown_link,
        text,
    )

    # --------------------------------------------------------
    # Escape HTML
    # --------------------------------------------------------
    text = html.escape(text, quote=False)

    # --------------------------------------------------------
    # 恢复安全的 Markdown 链接
    # --------------------------------------------------------
    for placeholder, (label, url) in markdown_links.items():
        text = text.replace(
            placeholder,
            f'<a href="{url}">{label}</a>',
        )

    # --------------------------------------------------------
    # 代码块
    # --------------------------------------------------------
    text = re.sub(
        r"```(?:\w+)?\n?(.*?)```",
        r"<pre>\1</pre>",
        text,
        flags=re.S,
    )

    # --------------------------------------------------------
    # 行内代码
    # --------------------------------------------------------
    text = re.sub(
        r"`([^`\n]+)`",
        r"<code>\1</code>",
        text,
    )

    # --------------------------------------------------------
    # 加粗
    # --------------------------------------------------------
    text = re.sub(
        r"\*\*(.+?)\*\*",
        r"<b>\1</b>",
        text,
    )

    # --------------------------------------------------------
    # 标题
    # --------------------------------------------------------
    text = re.sub(
        r"(?m)^#{1,6}\s*(.+)$",
        r"<b>\1</b>",
        text,
    )

    # --------------------------------------------------------
    # 斜体
    # --------------------------------------------------------
    text = re.sub(
        r"(?<!\*)\*([^*\n]+)\*(?!\*)",
        r"<i>\1</i>",
        text,
    )

    # --------------------------------------------------------
    # 无序列表
    # --------------------------------------------------------
    text = re.sub(
        r"(?m)^[ \t]*[-*]\s+",
        "• ",
        text,
    )

    # --------------------------------------------------------
    # 清理空行
    # --------------------------------------------------------
    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text,
    )

    # --------------------------------------------------------
    # Telegram 长度
    # --------------------------------------------------------
    if len(text) > MAX_TELEGRAM_LENGTH:
        text = (
            text[:3900]
            + "\n\n"
            + "……内容过长，已截断。"
        )

    return text


# ============================================================
# 安全编辑 AI 消息
# ============================================================
async def edit_ai_message(
    context,
    chat_id,
    message_id,
    text,
):
    formatted = format_ai_reply(text)

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=formatted,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    except Exception as e:
        print("[FORMAT] HTML 排版发送失败：", repr(e))

        plain_text = re.sub(
            r"<[^>]+>",
            "",
            formatted,
        )

        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=html.unescape(plain_text)[:MAX_TELEGRAM_LENGTH],
            disable_web_page_preview=True,
        )
