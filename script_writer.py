"""
AI 播报稿生成模块 - 全领域
调用 OpenAI 兼容 API（NVIDIA NIM），返回中文播报稿 + 各条新闻的中文标题
出站请求统一走 safe_http 校验（防 SSRF）
"""
import json
import re
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
直接给出最终结果，不要输出任何思考过程、解释或 markdown 代码块。回复必须严格遵循以下结构：

【中文标题】
第1条中文标题；第2条中文标题；第3条中文标题
【播报稿】
早上好，以下是今天的全球要闻。……（完整播报稿正文）

【中文标题】行用分号分隔，共 N 条，与输入顺序一致，每条不超过 25 个汉字；【播报稿】后面是完整播报稿全文。"""

_THINK_RE = re.compile(r"<think>.*?</think>", flags=re.S)
_OPENING = "早上好，以下是今天的全球要闻"


def _cjk_ratio(text: str) -> float:
    """文本中 CJK 字符占比，用于判断是否为中文成品稿"""
    if not text:
        return 0.0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return cjk / max(len(text), 1)


def _split_titles(raw: str, expected_count: int) -> list[str]:
    """把标题段按分号/换行拆开，去掉编号前缀，截到 expected_count 条"""
    raw = re.sub(r"^\s*\d+[\.、\)\)]\s*", "", raw, flags=re.M)
    return [t.strip(" .。") for t in re.split(r"[；;\n]+", raw) if t.strip()][:expected_count]


def _harvest_numbered_titles(head: str) -> str:
    """无标记时从导语里捞『编号+含中文的短句』，拼回分号分隔串"""
    frags = re.split(r"\d+\s*[\.、\)\)]\s*", head)
    kept = []
    for f in frags:
        f = f.strip().replace("\n", " ")
        if 2 <= len(f) <= 40 and any("\u4e00" <= ch <= "\u9fff" for ch in f):
            kept.append(f)
    return "；".join(kept)


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


def _parse_llm_output(text: str, expected_count: int) -> tuple[str, list[str]]:
    """解析标记分隔格式的 LLM 输出，返回 (播报稿, 中文标题列表)。

    兜底顺序：标准标记 → 从固定开头语锚定 → 整段文本直接当播报稿。
    """
    cleaned = _THINK_RE.sub("", text).strip()

    m_script = re.search(r"【播报稿】\s*", cleaned)
    script = cleaned[m_script.end():].strip() if m_script else ""

    titles: list[str] = []
    m_titles = re.search(r"【中文标题】\s*(.*?)\s*【播报稿】", cleaned, flags=re.S)
    if m_titles:
        titles = _split_titles(m_titles.group(1), expected_count)

    if not script:
        # 没有标记：优先从固定开头语锚定（推理模型常在正文前混入思考过程）
        idx = cleaned.find(_OPENING)
        if idx >= 0:
            script = cleaned[idx:].strip()
            # 开头语之前若存在标题段（标记形式或编号列表）则顺手提取
            if not titles and idx > 0:
                head = cleaned[:idx]
                hm = re.search(r"【中文标题】\s*(.*)", head, flags=re.S)
                src = hm.group(1) if hm else _harvest_numbered_titles(head)
                if src:
                    titles = _split_titles(src, expected_count)
        else:
            script = cleaned

    return script, titles


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
    with open_url(req, timeout=240) as resp:
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
        f"【中文标题】必须包含 {len(news_items)} 项（分号分隔）：\n\n{news_text}"
    )

    max_attempts = 3
    last_error = ""
    for attempt in range(1, max_attempts + 1):
        try:
            print(f"[AI] 尝试 {attempt}/{max_attempts}: {Config.LLM_API_BASE} 模型 {Config.LLM_MODEL}")
            text = _call_llm(user_prompt)
            script, titles = _parse_llm_output(text, len(news_items))
            # 成品稿必须是中文为主；否则视为推理污染，重试
            if not script or _cjk_ratio(script) < 0.3:
                last_error = "输出不是合格的中文播报稿"
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
