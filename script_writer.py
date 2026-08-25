"""
AI 播报稿生成模块 - 全领域
调用 OpenAI 兼容 API（NVIDIA NIM），返回中文播报稿 + 各条新闻的中文标题
出站请求统一走 safe_http 校验（防 SSRF）
"""
import json
import time
from config import Config
from safe_http import open_url


SYSTEM_PROMPT = """你是一位专业的中文新闻播音员。你的任务是把给定的全球新闻翻译并改写成一段自然流畅的中文语音播报稿，并为每条新闻生成简短的中文标题。

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
- 所有内容必须翻译成中文（公司名、人名、政策名可保留英文）
- 新闻之间用过渡句自然衔接
- 不要使用任何 Markdown 格式、特殊符号、emoji
- 英文公司名保留原文（如 OpenAI、Tesla、Federal Reserve）
- 语气轻松专业，像朋友给你读新闻
- 播报稿全文控制在 2000-3000 字

【输出格式】
必须输出如下 JSON，不要输出任何其他文字，不要用 markdown 代码块包裹：
{"script": "完整中文播报稿", "titles_zh": ["第1条的中文标题", "第2条的中文标题"]}
titles_zh 数组长度必须等于输入新闻条数，顺序与输入一致，每条不超过 25 个汉字。"""


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


def _parse_llm_json(text: str, expected_count: int) -> tuple[str, list[str]]:
    """解析 LLM 返回的 JSON；解析不出时把整段文本当作播报稿（标题留空）"""
    raw = text.strip()
    # 容错：剥掉可能存在的 markdown 代码块
    if raw.startswith("```"):
        chunks = raw.split("```")
        raw = chunks[1] if len(chunks) > 1 else raw.lstrip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        data = json.loads(raw[start:end])
        script = str(data.get("script", "")).strip()
        titles = [str(t).strip() for t in (data.get("titles_zh") or [])][:expected_count]
        if script:
            return script, [t for t in titles if t]
    except (ValueError, json.JSONDecodeError):
        pass
    return text.strip(), []


def _call_llm(user_prompt: str) -> str:
    """单次调用 LLM，返回响应文本"""
    import urllib.request

    api_base = Config.LLM_API_BASE.rstrip("/")
    url = f"{api_base}/chat/completions"
    payload = json.dumps({
        "model": Config.LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 6000,
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {Config.OPENAI_API_KEY}",
    }

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    with open_url(req, timeout=180) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        return _extract_response_text(result)


def generate_script(news_items: list[dict]) -> dict:
    """生成播报稿。

    返回 {"script": str, "titles_zh": list[str]}；
    全部尝试失败时 script 为空字符串，由调用方决定降级行为。
    """
    if not Config.OPENAI_API_KEY:
        print("[AI] 未配置 OPENAI_API_KEY")
        return {"script": "", "titles_zh": []}

    news_text = ""
    for i, item in enumerate(news_items, 1):
        title = item.get("title", "")
        summary = item.get("summary", "")[:300]
        source = item.get("source", "")
        news_text += f"{i}. [{source}] {title}\n   摘要：{summary}\n\n"

    user_prompt = (
        f"以下是今天的 {len(news_items)} 条全球新闻，请翻译并改写成中文播报稿，"
        f"titles_zh 必须包含 {len(news_items)} 项中文标题：\n\n{news_text}"
    )

    max_attempts = 3
    last_error = ""
    for attempt in range(1, max_attempts + 1):
        try:
            print(f"[AI] 尝试 {attempt}/{max_attempts}: {Config.LLM_API_BASE} 模型 {Config.LLM_MODEL}")
            text = _call_llm(user_prompt)
            script, titles = _parse_llm_json(text, len(news_items))
            if not script:
                last_error = "响应中没有文本"
                print(f"[AI] {last_error}")
                continue
            note = f"，中文标题 {len(titles)} 条" if titles else ""
            print(f"[AI] 播报稿生成成功，共 {len(script)} 字{note}")
            return {"script": script, "titles_zh": titles}
        except Exception as e:
            code = getattr(e, "code", None)
            body = ""
            if code is not None:
                try:
                    body = e.read().decode("utf-8", errors="replace")[:200]
                except Exception:
                    body = ""
            last_error = f"HTTP {code} {body}" if code else str(e)
            print(f"[AI] 第 {attempt} 次调用失败: {last_error.strip()}")
            if attempt < max_attempts:
                wait = 20 * attempt
                print(f"[AI] {wait} 秒后重试...")
                time.sleep(wait)

    print(f"[AI] 全部尝试失败: {last_error.strip()}")
    return {"script": "", "titles_zh": []}
