"""CLI 输出清洗与交互提示识别。"""

import re

ANSI_RE = re.compile(
    r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1B\\))"
)


class StreamSanitizer:
    """清理终端控制序列，把 TUI 输出降级为纯文本。"""

    @staticmethod
    def clean(text: str) -> str:
        text = ANSI_RE.sub("", text)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        return "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)


class PromptInterceptor:
    """用滑动窗口识别 y/n 类阻塞式交互提示。"""

    PATTERNS = [
        re.compile(r"do you want to (?:run|proceed|continue).*?\(y/n\)", re.I | re.S),
        re.compile(r"proceed\?\s*\[[yY]/[nN]\]", re.I),
        re.compile(r"create file .*\?", re.I),
        re.compile(r"apply (?:these )?changes\?", re.I),
        re.compile(r"continue\?", re.I),
    ]

    def __init__(self, window_chars: int = 800):
        self.window_chars = window_chars
        self._window = ""
        self._last_prompt: str | None = None

    def detect(self, chunk: str) -> str | None:
        self._window = (self._window + chunk)[-self.window_chars :]
        for pattern in self.PATTERNS:
            match = pattern.search(self._window)
            if match:
                prompt = match.group(0).strip()
                if prompt == self._last_prompt:
                    return None
                self._last_prompt = prompt
                return prompt
        return None
