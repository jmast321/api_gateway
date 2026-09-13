import re
from typing import Any, Dict, List
from pydantic import BaseModel, Field


class HeuristicProfile(BaseModel):
    requires_vision: bool = False
    requires_audio: bool = False
    requires_video: bool = False
    requires_tools: bool = False
    is_coding: bool = False
    is_reasoning: bool = False
    estimated_tokens: int = 0
    detected_tags: List[str] = Field(default_factory=list)
    summary: str = "General query"


class HeuristicAnalyzer:
    # Code patterns
    CODE_FENCE_REGEX = re.compile(r"```[a-zA-Z0-9_\-\+]*\n[\s\S]*?```", re.MULTILINE)
    CODE_KEYWORDS_REGEX = re.compile(
        r"\b(def\s+\w+|class\s+\w+|import\s+\w+|from\s+\w+\s+import|function\s*\(|const\s+\w+\s*=|let\s+\w+\s*=|var\s+\w+\s*=|public\s+class|interface\s+\w+|package\s+\w+|SELECT\s+.*\s+FROM|Traceback \(most recent call last\):|TypeError:|ValueError:|SyntaxError:|docker run|npm install|git commit|pip install)\b",
        re.IGNORECASE
    )

    # Reasoning and logic patterns
    REASONING_REGEX = re.compile(
        r"\b(step by step|prove that|calculate|evaluate the integral|solve the equation|mathematical proof|deduce|logic puzzle|chain of thought|derive the formula|theorem)\b",
        re.IGNORECASE
    )
    LATEX_REGEX = re.compile(r"(\$\$[\s\S]*?\$\$|\$[^\$]+\$|\\frac\{|\\sum_\{|\\int_\{)", re.MULTILINE)

    # Media URL patterns
    IMAGE_EXT_REGEX = re.compile(r"\.(png|jpg|jpeg|gif|webp|svg)(\?.*)?$", re.IGNORECASE)
    AUDIO_EXT_REGEX = re.compile(r"\.(mp3|wav|ogg|m4a|flac)(\?.*)?$", re.IGNORECASE)
    VIDEO_EXT_REGEX = re.compile(r"\.(mp4|webm|mov|mkv)(\?.*)?$", re.IGNORECASE)

    @classmethod
    def analyze(cls, payload: Dict[str, Any]) -> HeuristicProfile:
        requires_vision = False
        requires_audio = False
        requires_video = False
        requires_tools = False
        is_coding = False
        is_reasoning = False
        total_text_length = 0
        detected_tags: List[str] = []

        # 1. Inspect Tools
        if payload.get("tools") or payload.get("functions"):
            requires_tools = True
            detected_tags.append("tools")

        # 2. Inspect Messages
        messages = payload.get("messages", [])
        combined_text_parts: List[str] = []

        for msg in messages:
            content = msg.get("content")
            if isinstance(content, str):
                combined_text_parts.append(content)
                total_text_length += len(content)

                # Base64 inline detection
                if "data:image/" in content:
                    requires_vision = True
                if "data:audio/" in content:
                    requires_audio = True
                if "data:video/" in content:
                    requires_video = True

            elif isinstance(content, list):
                # OpenAI multimodal parts
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    part_type = part.get("type", "")
                    if part_type == "text":
                        text_val = part.get("text", "")
                        combined_text_parts.append(text_val)
                        total_text_length += len(text_val)
                    elif part_type == "image_url":
                        requires_vision = True
                    elif part_type in ("input_audio", "audio"):
                        requires_audio = True
                    elif part_type in ("video", "video_url"):
                        requires_video = True

        full_text = " ".join(combined_text_parts)

        # 3. Code Detection
        code_fence_matches = cls.CODE_FENCE_REGEX.findall(full_text)
        code_kw_matches = cls.CODE_KEYWORDS_REGEX.findall(full_text)

        if code_fence_matches or len(code_kw_matches) >= 1:
            is_coding = True
            detected_tags.append("coding")

        # 4. Reasoning Detection
        reasoning_matches = cls.REASONING_REGEX.findall(full_text)
        latex_matches = cls.LATEX_REGEX.findall(full_text)

        if reasoning_matches or latex_matches:
            is_reasoning = True
            detected_tags.append("reasoning")

        # 5. Media Tags
        if requires_vision:
            detected_tags.append("vision")
        if requires_audio:
            detected_tags.append("audio")
        if requires_video:
            detected_tags.append("video")

        # Estimated tokens (standard approximation ~3.8 chars per token)
        estimated_tokens = max(1, int(total_text_length / 3.8))

        # Build Summary
        summary_tags = detected_tags if detected_tags else ["general"]
        summary = f"Identified intents: [{', '.join(summary_tags)}] (~{estimated_tokens} tokens)"

        return HeuristicProfile(
            requires_vision=requires_vision,
            requires_audio=requires_audio,
            requires_video=requires_video,
            requires_tools=requires_tools,
            is_coding=is_coding,
            is_reasoning=is_reasoning,
            estimated_tokens=estimated_tokens,
            detected_tags=detected_tags,
            summary=summary
        )


heuristic_analyzer = HeuristicAnalyzer()
