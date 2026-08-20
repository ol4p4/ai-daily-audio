"""
TTS 引擎封装
使用 edge-tts 生成中文语音，句间加停顿符号
"""
import os
import re
import subprocess
import tempfile
from pathlib import Path
from config import Config


def _add_pauses(text: str, pause_char: str = "...") -> str:
    """在句间加入停顿符号，让 TTS 自然停顿"""
    # 按句号、问号、叹号分句
    sentences = re.split(r'(?<=[。！？!?])\s*', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    parts = []
    for i, sent in enumerate(sentences):
        parts.append(sent)
        if i < len(sentences) - 1:
            parts.append(pause_char)

    return " ".join(parts)


def generate_audio_edge_tts(text: str, output_path: Path) -> bool:
    """用 edge-tts 生成 MP3"""
    # 加停顿符号
    text = _add_pauses(text)

    rate = Config.TTS_RATE

    # 写入临时文件避免命令行参数长度限制
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(text)
        tmp_file = f.name

    try:
        cmd = [
            "edge-tts",
            "--voice", Config.TTS_VOICE,
            f"--rate={rate}",
            "--file", tmp_file,
            "--write-media", str(output_path),
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            env={**os.environ, "PATH": os.environ.get("PATH", "")},
        )
        if result.returncode == 0 and output_path.exists():
            return True
        print(f"[edge-tts stderr] {result.stderr[:500]}")
        print(f"[edge-tts stdout] {result.stdout[:500]}")
        return False
    except subprocess.TimeoutExpired:
        print("[edge-tts] 超时")
        return False
    except FileNotFoundError:
        print("[edge-tts] 命令未找到，需 pip install edge-tts")
        return False
    except Exception as e:
        print(f"[edge-tts] 错误: {e}")
        return False
    finally:
        os.unlink(tmp_file)


def generate_audio(text: str, output_path: Path) -> tuple[bool, str]:
    """主入口：尝试 edge-tts，返回 (成功, 文件路径或错误信息)"""
    if generate_audio_edge_tts(text, output_path):
        size_kb = output_path.stat().st_size / 1024
        print(f"[TTS] edge-tts 成功: {output_path} ({size_kb:.1f} KB)")
        return True, str(output_path)
    return False, "TTS 引擎失败"
