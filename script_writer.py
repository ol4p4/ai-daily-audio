"""
AI 播报稿生成模块 - 全领域
调用 OpenAI 兼容 API（NVIDIA NIM）：
- 主调用：英文新闻 → 中文语音播报稿（纯文本，不带结构标记）
- 副调用：每条新闻的中文标题（供邮件列表展示）
拆成两次轻量调用是为了避免单次长输出被 max_tokens 截断。
出站请求统一走 safe_http 校验（防 SSRF）。
"""
import json
import re
import time
from config import Config
from safe_http import open_url


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
- 所有内容必须翻译成中文（公司名、人名、政策名可保留英文）
- 新闻之间用过渡句自然衔接
- 不要使用任何 Markdown 格式、特殊符号、emoji
- 英文公司名保留原文（如 OpenAI、Tesla、Federal Reserve）
- 语气轻松专业，像朋友给你读新闻
- 全文控制在 2000-3000 字

【输出要求】
直接输出播报稿正文，第一句必须是"早上好，以下是今天的全球要闻"。
不要输出任何思考过程、解释、标记符号或 markdown 代码块。"""

_TITLES_PROMPT = """你是新闻编辑。为输入的每条新闻生成一个不超过 20 个汉字的简体中文标题。
严格按输入顺序，把全部标题用分号（；）连成一段输出。
只输出标题本身：不要编号、不要解释、不要输出任何其他内容。"""

_THINK_RE = re.compile(r"<think>.*?</think>", flags=re.S)
_OPENING = "早上好，以下是今天的全球要闻"
_MIN_SCRIPT_LEN = 500


def _cjk_ratio(text: str) -> float:
    """文本中 CJK 字符占比，用于判断是否为中文成品稿"""
    if not text:
        return 0.0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return cjk / max(len(text), 1)


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


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


def _parse_script(text: str) -> str:
    """从响应中提取播报稿正文。

    优先级：【播报稿】标记之后 → 固定开头语锚定 → 整段文本。
    """
    cleaned = _THINK_RE.sub("", text).strip()
    m = re.search(r"【播报稿】\s*", cleaned)
    if m:
        return cleaned[m.end():].strip()
    idx = cleaned.find(_OPENING)
    if idx >= 0:
        return cleaned[idx:].strip()
    return cleaned


def _split_titles(raw: str, expected_count: int) -> list[str]:
    """把标题段按分号/换行拆开，去掉编号前缀，过滤非中文与超长项"""
    raw = re.sub(r"^\s*\d+[\.、\)\)]\s*", "", raw, flags=re.M)
    parts = [t.strip(" .。") for t in re.split(r"[；;\n]+", raw) if t.strip()]
    return [p for p in parts if _has_cjk(p) and len(p) <= 30][:expected_count]


def _call_llm(system: str, user: str, max_tokens: int, label: str) -> str:
    """单次调用 LLM，返回响应文本"""
    import urllib.request

    api_base = Config.LLM_API_BASE.rstrip("/")
    url = f"{api_base}/chat/completions"
    payload = json.dumps({
        "model": Config.LLM_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.7,
        "max_tokens": max_tokens,
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {Config.OPENAI_API_KEY}",
    }

    print(f"[AI] {label}: {Config.LLM_API_BASE} 模型 {Config.LLM_MODEL}")
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    with open_url(req, timeout=240) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        return _extract_response_text(result)


def _retry_call(system: str, user: str, max_tokens: int, label: str) -> str:
    """带重试的调用；全部失败抛出最后一次异常"""
    last_err: Exception = RuntimeError("未执行")
    for attempt in range(1, 4):
        try:
            return _call_llm(system, user, max_tokens, f"{label} [尝试 {attempt}/3]")
        except Exception as e:
            last_err = e
            code = getattr(e, "code", None)
            body = ""
            if code is not None:
                try:
                    body = e.read().decode("utf-8", errors="replace")[:200]
                except Exception:
                    body = ""
            detail = f"HTTP {code} {body}" if code else str(e)
            print(f"[AI] 第 {attempt} 次调用失败: {detail.strip()}")
            if attempt < 3:
                wait = 20 * attempt
                print(f"[AI] {wait} 秒后重试...")
                time.sleep(wait)
    raise last_err


def generate_titles_zh(news_items: list[dict]) -> list[str]:
    """为每条新闻生成中文标题；失败时返回空列表（邮件回退英文标题）"""
    lines = []
    for i, item in enumerate(news_items, 1):
        title = item.get("title", "")
        summary = item.get("summary", "")[:80]
        source = item.get("source", "")
        lines.append(f"{i}. [{source}] {title}：{summary}")
    user_prompt = "\n".join(lines)

    try:
        text = _retry_call(_TITLES_PROMPT, user_prompt, 2000, "生成中文标题")
        cleaned = _THINK_RE.sub("", text).strip()
        m = re.search(r"【中文标题】\s*(.*)", cleaned, flags=re.S)
        src = m.group(1) if m else cleaned
        titles = _split_titles(src, len(news_items))
        if titles:
            print(f"[AI] 中文标题生成成功，共 {len(titles)} 条")
        else:
            print("[AI] 中文标题解析结果为空")
        return titles
    except Exception as e:
        print(f"[AI] 中文标题生成失败（邮件将回退英文标题）: {e}")
        return []


def generate_script(news_items: list[dict]) -> dict:
    """生成播报稿。

    返回 {"script": str, "titles_zh": list[str]}；
    播报稿全部尝试失败时 script 为空字符串，由调用方决定降级行为。
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

    user_prompt = f"请把以下 {len(news_items)} 条全球新闻翻译并改写成中文播报稿：\n\n{news_text}"

    script = ""
    try:
        for attempt in range(1, 4):
            text = _call_llm(SYSTEM_PROMPT, user_prompt, 8000, f"生成播报稿 [尝试 {attempt}/3]")
            script = _parse_script(text)
            # 质量门禁：中文为主且达到最低长度，否则视为推理污染或截断，重试
            if script and len(script) >= _MIN_SCRIPT_LEN and _cjk_ratio(script) >= 0.3:
                break
            print(f"[AI] 第 {attempt} 次输出不合格（长度 {len(script)}，CJK 占比 {_cjk_ratio(script):.0%}）")
            script = ""
            if attempt < 3:
                time.sleep(10)
    except Exception as e:
        code = getattr(e, "code", None)
        body = ""
        if code is not None:
            try:
                body = e.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                body = ""
        print(f"[AI] 播报稿调用失败: {(f'HTTP {code} ' + body) if code else e}")

    if not script:
        print("[AI] 播报稿生成最终失败")
        return {"script": "", "titles_zh": []}

    print(f"[AI] 播报稿生成成功，共 {len(script)} 字")

    titles = generate_titles_zh(news_items)
    return {"script": script, "titles_zh": titles}
