# 安全公告

> 本仓库早期提交中曾出现真实邮箱配置样例；虽然后续已替换为占位符，但 Git 历史中仍可能保留敏感痕迹。请立即轮换曾用于本项目的邮箱及对应应用密码，并建议在 GitHub Settings 开启 Secret Scanning 与 Push Protection。
# AI 每日早报音频

每天自动抓取英文科技新闻 → AI 翻译成中文 → 生成中文语音播报 → 推送到邮箱。

## 架构

```
GitHub Actions (cron 每天 7:00 UTC+8)
  ├─ 爬取英文 RSS 新闻源（BBC、The Verge、Wired、Reuters 等）
  ├─ LLM 翻译+改写为中文播报稿（800-1200字）
  ├─ edge-tts (XiaoxiaoNeural) 生成中文 MP3
  └─ SMTP 邮件推送至邮箱
```

## 新闻源

| 源 | 内容方向 |
|---|---|
| BBC Technology | 全球科技新闻 |
| The Verge | 消费电子/互联网 |
| Wired | 深度科技报道 |
| Reuters Tech | 科技产业动态 |
| Hacker News | 全球开发者热点 |
| OpenAI Blog | AI 前沿动态 |

## 配置

1. 复制 `.env.example` → `.env`，填入 SMTP 凭据和 LLM API Key
2. `.env` 已在 `.gitignore`，真实配置请用 GitHub Secrets
3. 必须配置 `OPENAI_API_KEY`（用于英文→中文翻译+播报稿生成）