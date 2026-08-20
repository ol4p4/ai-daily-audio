"""
新闻源管理 - 全球源（通讯社/财经/政策/科技/就业）
"""
import feedparser
from datetime import datetime, timedelta
from config import Config


def fetch_news(max_items: int = None) -> list[dict]:
    """从所有 RSS 源抓取新闻，返回按时间排序的前 N 条"""
    max_items = max_items or Config.MAX_NEWS_PER_DAY
    all_items = []

    for url in Config.NEWS_SOURCES:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    published = datetime(*entry.updated_parsed[:6])

                if published and published < datetime.utcnow() - timedelta(hours=30):
                    continue

                title = entry.get("title", "无标题")
                summary = entry.get("summary", entry.get("description", ""))
                summary = summary.replace("<br/>", " ").replace("<br>", " ")
                summary = summary.replace("<p>", " ").replace("</p>", " ")
                summary = summary.replace("<b>", "").replace("</b>", "")
                summary = summary.strip()[:500]

                link = entry.get("link", "")

                all_items.append({
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "published": published.isoformat() if published else "",
                    "source": feed.feed.get("title", url),
                })
        except Exception as e:
            print(f"[WARN] 抓取 {url} 失败: {e}")

    all_items.sort(key=lambda x: x["published"] or "", reverse=True)

    seen_titles = set()
    unique_items = []
    for item in all_items:
        title_key = item["title"][:30]
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_items.append(item)

    return unique_items[:max_items]


def format_news_for_tts(news_items: list[dict]) -> str:
    """格式化新闻为 TTS 可读的文本"""
    lines = []
    for i, item in enumerate(news_items, 1):
        title = item["title"].replace("【", "").replace("】", "")
        title = title.replace(":", " -").replace("：", " - ")
        lines.append(f"第{i}条：{title}")
    return "，".join(lines)


if __name__ == "__main__":
    items = fetch_news(5)
    for item in items:
        print(f"[{item['source']}] {item['title'][:80]}")
