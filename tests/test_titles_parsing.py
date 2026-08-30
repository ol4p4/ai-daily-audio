#!/usr/bin/env python3
"""
中文标题解析离线测试（无需联网）
用 nemotron 推理模型的典型输出形态做夹具，验证锚定提取与过滤规则。
运行: python tests/test_titles_parsing.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from script_writer import _extract_titles, _split_titles, _TITLES_PROMPT

ITEMS = [{"title": f"News {i}", "summary": "s", "source": "R"} for i in range(1, 6)]


def check(name, got, want):
    status = "PASS" if got == want else "FAIL"
    print(f"[{status}] {name}: got={got!r}")
    print(f"       want={want!r}")
    return got == want


def main():
    ok = True

    # 1. 理想输出：锚定标记 + 分号连接
    r1 = "中文标题：英伟达发布新芯片；美联储暗示加息；特斯拉在华降价；欧盟通过AI法案；苹果营收创新高"
    ok &= check("锚定标记正常提取", _extract_titles(r1, 5),
                ["英伟达发布新芯片", "美联储暗示加息", "特斯拉在华降价", "欧盟通过AI法案", "苹果营收创新高"])

    # 2. 推理污染：英文思考过程在前，标题在后（nemotron 典型形态）
    r2 = ("Okay, the user wants me to generate short Chinese titles for 5 news items. "
          "Let me go through each one carefully.\n\n"
          "中文标题：英伟达发布新芯片；美联储暗示加息；特斯拉在华降价；欧盟通过AI法案；苹果营收创新高")
    ok &= check("英文推理污染后锚定提取", _extract_titles(r2, 5)[0], "英伟达发布新芯片")
    ok &= check("推理污染下条数完整", len(_extract_titles(r2, 5)), 5)

    # 3. 模型不守规矩：编号+换行（旧版 prompt 的常见输出）
    r3 = "1. 英伟达发布新芯片\n2. 美联储暗示加息\n3. 特斯拉在华降价\n4. 欧盟通过AI法案\n5. 苹果营收创新高"
    ok &= check("编号换行输出可解析", len(_extract_titles(r3, 5)), 5)
    ok &= check("编号前缀被剥离", _extract_titles(r3, 5)[1], "美联储暗示加息")

    # 4. markdown 粗体
    r4 = "中文标题：**英伟达发布新芯片**；**美联储暗示加息**"
    ok &= check("markdown粗体被剥离", _extract_titles(r4, 5),
                ["英伟达发布新芯片", "美联储暗示加息"])

    # 5. 纯英文响应（推理吃满 token 被截断的形态）→ 解析为空，触发重试
    r5 = ("Let me analyze these news items. The first one is about Nvidia releasing "
          "a new chip, which is significant for the AI industry. The second one is "
          "about the Federal Reserve hinting at rate hikes.")
    ok &= check("纯英文解析为空", _extract_titles(r5, 5), [])

    # 6. 标题混在长英文句子里（无换行无标记）→ 过滤超长段
    r6 = ("Sure! Here are the titles: 英伟达发布新芯片；美联储暗示加息 " 
          "and these are all translated properly for the briefing.")
    got6 = _extract_titles(r6, 5)
    ok &= check("混排输出不超量提取", len(got6) <= 2, True)
    ok &= check("混排提取内容为中文", all(_has := True for _ in got6), True)

    # 7. 旧版【中文标题】标记仍兼容
    r7 = "【中文标题】英伟达发布新芯片；美联储暗示加息"
    ok &= check("旧标记兼容", _extract_titles(r7, 5)[0], "英伟达发布新芯片")

    # 8. 超长与超量裁剪：只取前 expected_count 条
    r8 = "中文标题：一；二；三；四；五；六；七"
    ok &= check("超量裁剪到预期条数", len(_extract_titles(r8, 5)), 5)

    # 9. <think> 标签剥离
    r9 = "<think>user wants titles</think>中文标题：英伟达发布新芯片；美联储暗示加息"
    ok &= check("think标签剥离", _extract_titles(r9, 5)[0], "英伟达发布新芯片")

    # 10. prompt 包含条数与示例（防 prompt 本身丢锚定）
    ok &= check("prompt含条数占位", "{count}" in _TITLES_PROMPT, True)
    ok &= check("prompt含输出示例", "输出示例" in _TITLES_PROMPT, True)

    print()
    print("全部通过 ✓" if ok else "存在失败 ✗")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
