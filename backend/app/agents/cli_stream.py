"""CLI 输出清洗与交互提示识别。"""

import re

ANSI_RE = re.compile(
    r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1B\\))"
)
PLAIN_SGR_RE = re.compile(r"\[(?:\d{1,3};?){1,8}m")
OPENTUI_RESIDUAL_RE = re.compile(
    r"(?:\??\d{1,4};)*"
    r"(?:i=opentui-[^\s]*|p=\?|1337;Capabilities[^\s]*|66;[a-z]=\d+;?|"
    r"tab agents\s+ctrl\+p commands\s*/?workspace\s+\d+\.\d+\.\d+)"
    r"[^\n]*",
    re.IGNORECASE,
)
TUI_NOISE_LINE_RE = re.compile(
    r"(?:Update Available|Would you like to update now|Ask anything|"
    r"Skip Confirm|Build ·|OpenCode\s+\[[0-9;]*m)",
    re.IGNORECASE,
)


class StreamSanitizer:
    """清理终端控制序列，把 TUI 输出降级为纯文本。"""

    def __init__(self):
        self._pending_escape = ""

    @staticmethod
    def clean(text: str) -> str:
        return StreamSanitizer().clean_chunk(text)

    def clean_chunk(self, text: str) -> str:
        text = self._pending_escape + text
        self._pending_escape = ""
        cleaned = self._strip_escape_sequences(text)
        cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
        cleaned = "".join(
            ch for ch in cleaned
            if ch == "\n" or ch == "\t" or ord(ch) >= 32
        )
        return self._strip_tui_residue(cleaned)

    def _strip_escape_sequences(self, text: str) -> str:
        result: list[str] = []
        index = 0
        length = len(text)
        while index < length:
            char = text[index]
            if char != "\x1b":
                result.append(char)
                index += 1
                continue

            if index + 1 >= length:
                self._pending_escape = text[index:]
                break

            kind = text[index + 1]
            if kind == "[":
                end = _find_csi_end(text, index + 2)
                if end is None:
                    self._pending_escape = text[index:]
                    break
                index = end + 1
                continue
            if kind in {"]", "P", "^", "_", "X"}:
                end = _find_string_control_end(text, index + 2)
                if end is None:
                    self._pending_escape = text[index:]
                    break
                index = end
                continue
            index += 2
        if len(self._pending_escape) > 4096:
            self._pending_escape = ""
        return "".join(result)

    @staticmethod
    def _strip_tui_residue(text: str) -> str:
        text = PLAIN_SGR_RE.sub("", text)
        text = OPENTUI_RESIDUAL_RE.sub("", text)
        lines = []
        for line in text.split("\n"):
            if TUI_NOISE_LINE_RE.search(line):
                continue
            lines.append(line)
        return "\n".join(lines)


def _find_csi_end(text: str, start: int) -> int | None:
    for index in range(start, len(text)):
        if "@" <= text[index] <= "~":
            return index
    return None


def _find_string_control_end(text: str, start: int) -> int | None:
    bel = text.find("\x07", start)
    st = text.find("\x1b\\", start)
    if bel == -1 and st == -1:
        return None
    if bel != -1 and (st == -1 or bel < st):
        return bel + 1
    return st + 2


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
