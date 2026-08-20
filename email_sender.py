"""
邮件发送模块
使用 SMTP 协议推送音频到邮箱
"""
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from config import Config


def send_email(subject: str, body_html: str, audio_path: Path = None) -> bool:
    """发送带附件的邮件"""
    context = ssl.create_default_context()

    try:
        # 465端口用SSL直连，587端口用STARTTLS
        if Config.SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(Config.SMTP_SERVER, Config.SMTP_PORT, context=context)
        else:
            server = smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT)
            server.starttls(context=context)

        with server:
            server.login(Config.EMAIL_USER, Config.EMAIL_PASSWORD)

            msg = MIMEMultipart()
            msg["From"] = Config.EMAIL_FROM
            msg["To"] = Config.EMAIL_TO
            msg["Subject"] = subject

            # HTML 正文
            msg.attach(MIMEText(body_html, "html", "utf-8"))

            # 音频附件
            if audio_path and Path(audio_path).exists():
                part = MIMEBase("application", "octet-stream")
                part.set_payload(Path(audio_path).read_bytes())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f'attachment; filename="{Path(audio_path).name}"',
                )
                msg.attach(part)

            server.send_message(msg)
            print(f"[邮件] 发送成功: {Config.EMAIL_TO}")
            return True

    except smtplib.SMTPAuthenticationError as e:
        print(f"[邮件] 认证失败: {e}")
        return False
    except smtplib.SMTPException as e:
        print(f"[邮件] SMTP 错误: {e}")
        return False
    except Exception as e:
        print(f"[邮件] 错误: {e}")
        return False


def make_email_body(news_items: list[dict], audio_filename: str = "") -> str:
    """生成 HTML 邮件正文"""
    items_html = ""
    for i, item in enumerate(news_items, 1):
        items_html += f"""
        <div style="margin:8px 0;padding:8px;border-left:3px solid #4A90D9;">
            <strong>{i}. {item.get('title', '')[:100]}</strong>
            <p style="font-size:12px;color:#666;">{item.get('source', '')}</p>
        </div>
        """

    return f"""<!DOCTYPE html>
<html>
<body style="font-family:system-ui;max-width:600px;margin:0 auto;padding:20px;">
    <h2 style="color:#1a1a2e;">🤖 AI Daily Audio</h2>
    <p>今天早报已完成生成，包含 {len(news_items)} 条资讯：</p>
    {items_html}
    <hr>
    <p style="font-size:12px;color:#999;">
        📧 由 GitHub Actions 自动推送 | {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}
    </p>
</body>
</html>"""


if __name__ == "__main__":
    print("email_sender 模块已加载")
