"""
AI 播报稿生成模块 - 全领域
直接调用 OpenCode Zen API（伪造客户端请求头）
"""
import json
import uuid
from config import Config


SYSTEM_PROMPT = """你是一位专业的中文新闻播音员。你的任务是把给定的全球新闻翻译并改写成一段自然流畅的中文语音播报稿。

【重要性分层规则】
- 头条新闻（前 3-5 条）：用 2-3 句话详细说明背景、影响和意义
- 重要新闻（第 6-15 条）：用 1-2 句话说明核心内容和关键影响
- 简讯（第 16 条以后）：用 1 句话快速带过

【播报格式】
1. 开头："早上好，以下是今天的全球要闻。今天重点关注：[头条标题]"
2. 头条区：详细播报前 3-5 条重要新闻，说明背景和影响
3. 要闻区：播报中间部分的重要新闻
4. 快讯区：快速播报剩余新闻，每条一句话
5. 结尾："以上就是今天的全球要闻，祝你今天顺利。"

【翻译规则】
- 所有英文内容必须翻译成中文（公司名、人名、政策名可保留英文）
- 新闻之间用过渡句自然衔接
- 不要使用任何 Markdown 格式、特殊符号、emoji
- 英文公司名保留原文（如 OpenAI、Tesla、Federal Reserve）
- 语气轻松专业，像朋友给你读新闻
- 全文控制在 2000-3000 字"""


def _extract_response_text(result: dict) -> str:
    msg = result["choices"][0]["message"]
    if msg.get("content"):
        return msg["content"].strip()
    for key in ("reasoning", "reasoning_content", "output"):
        if msg.get(key):
            return msg[key].strip()
    for key, val in msg.items():
        if isinstance(val, str) and len(val) > 50:
            return val.strip()
    return ""


def generate_script(news_items: list[dict]) -> str:
    api_key = Config.OPENAI_API_KEY
    if not api_key:
        print("[AI] 未配置 OPENAI_API_KEY，降级为简单拼接模式")
        return _fallback_script(news_items)

    news_text = ""
    for i, item in enumerate(news_items, 1):
        title = item.get("title", "")
        summary = item.get("summary", "")[:300]
        source = item.get("source", "")
        news_text += f"{i}. [{source}] {title}\n   摘要：{summary}\n\n"

    user_prompt = f"以下是今天的 {len(news_items)} 条全球新闻，请翻译并改写成中文播报稿：\n\n{news_text}"

    try:
        import urllib.request
        import urllib.error

        api_base = Config.LLM_API_BASE.rstrip("/")
        model = Config.LLM_MODEL
        url = f"{api_base}/chat/completions"

        print(f"[AI] 请求: {url}")
        print(f"[AI] 模型: {model}")

        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 4000,
        }).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "opencode/latest/1.3.15/cli",
            "x-opencode-client": "cli",
            "x-opencode-session": uuid.uuid4().hex,
            "x-opencode-project": uuid.uuid4().hex[:8],
            "x-opencode-request": uuid.uuid4().hex,
        }

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            script = _extract_response_text(result)
            if script:
                print(f"[AI] 播报稿生成成功，共 {len(script)} 字")
                return script
            else:
                print(f"[AI] 响应中没有找到文本")
                return _fallback_script(news_items)

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        print(f"[AI] API 返回 HTTP {e.code}: {body}")
        return _fallback_script(news_items)
    except Exception as e:
        print(f"[AI] 调用失败: {e}")
        return _fallback_script(news_items)


def _fallback_script(news_items: list[dict]) -> str:
    lines = ["早上好，以下是今天的全球要闻。"]
    for i, item in enumerate(news_items, 1):
        title = item.get("title", "").replace("【", "").replace("】", "")
        if i < len(news_items):
            transitions = ["接下来", "另外", "还有一条", "下面", "再来看看"]
            transition = transitions[(i - 1) % len(transitions)]
            lines.append(f"{transition}，第{i}条：{title}。")
        else:
            lines.append(f"最后，第{i}条：{title}。")
    lines.append("以上就是今天的全球要闻，祝你今天顺利。")
    return "。".join(lines)
