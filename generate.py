#!/usr/bin/env python3
"""
AI Daily Briefing - 主脚本
GitHub Actions 每日自动执行：抓新闻 → AI 写稿 → 生成音频+Markdown → 推送邮件
"""
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from config import Config
from news_sources import fetch_news
from script_writer import generate_script
from tts_engine import generate_audio
from email_sender import send_email, make_email_body


def save_markdown(script_text: str, news_items: list[dict], date_str: str) -> Path:
    """保存文字版早报为 Markdown"""
    md_dir = ROOT / "briefings"
    md_dir.mkdir(parents=True, exist_ok=True)
    filepath = md_dir / f"{date_str}.md"

    lines = [
        f"# 全球要闻 {date_str}",
        f"> 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## 播报稿",
        "",
        script_text,
        "",
        "## 新闻来源",
        "",
    ]
    for i, item in enumerate(news_items, 1):
        title = item.get("title", "")
        source = item.get("source", "")
        link = item.get("link", "")
        lines.append(f"{i}. **{title}** ({source})")
        if link:
            lines.append(f"   链接：{link}")
        lines.append("")

    filepath.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Markdown 已保存: {filepath}")
    return filepath


def main():
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    audio_file = ROOT / f"ai-daily-{date_str}.mp3"

    print(f"{'='*50}")
    print(f"AI Daily Briefing - {date_str}")
    print(f"{'='*50}")

    # 1. 抓取新闻
    print("\n[1/5] 抓取新闻...")
    news = fetch_news(Config.MAX_NEWS_PER_DAY)
    if not news:
        print("[WARN] 没有抓取到新闻，跳过")
        return False
    print(f"       抓取到 {len(news)} 条新闻")

    # 2. AI 生成播报稿（含每条新闻的中文标题）
    print("\n[2/5] AI 生成播报稿...")
    ai_result = generate_script(news)
    script_text = ai_result["script"]

    if not script_text:
        print("[ERROR] AI 播报稿生成失败，发送降级通知邮件")
        body = make_email_body(news, degraded=True)
        send_email(
            subject=f"AI 早报 [{date_str}] - ⚠️ AI 翻译服务异常，今日无音频",
            body_html=body,
        )
        return False

    titles_zh = ai_result.get("titles_zh") or []
    print(f"       播报稿 {len(script_text)} 字")

    # 3. 保存 Markdown 文字版
    print("\n[3/5] 保存 Markdown...")
    md_path = save_markdown(script_text, news, date_str)

    # 4. 生成音频
    print("\n[4/5] 生成音频...")
    success, result = generate_audio(script_text, audio_file)

    if not success:
        print(f"[ERROR] 音频生成失败: {result}")
        body = make_email_body(news, titles_zh=titles_zh)
        send_email(
            subject=f"AI 早报 [{date_str}] - 音频生成失败",
            body_html=body + f"<p style='color:red;'>音频生成失败：{result}</p>",
        )
        return False

    file_size_mb = audio_file.stat().st_size / (1024 * 1024)
    print(f"       音频大小: {file_size_mb:.2f} MB")

    # 5. 推送邮件
    print("\n[5/5] 发送邮件...")
    body = make_email_body(news, audio_file.name, titles_zh=titles_zh)
    email_success = send_email(
        subject=f"AI 早报 [{date_str}] - {len(news)} 条全球要闻",
        body_html=body,
        audio_path=audio_file,
    )

    if email_success:
        print("\n早报推送完成！")
        audio_file.unlink(missing_ok=True)
    else:
        print("\n邮件发送失败！")

    return email_success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
