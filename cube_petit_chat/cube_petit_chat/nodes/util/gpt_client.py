#!/usr/bin/env python

from openai import OpenAI
import pathlib
import base64
from typing import Optional
import numpy as np
import cv2
from typing import List
from vision_msgs.msg import BoundingBox2D
from typing import Dict, Callable



class GPTClient:

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-4o",
        max_tokens: int = 4000,
        instructions_file: Optional[pathlib.Path] = None,
        enable_web_search: bool = False,
        detail: str = "auto",
    ) -> None:

        self.client = OpenAI(api_key=api_key)
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.enable_web_search = enable_web_search
        self.detail = detail

        self.system_prompt = ""
        if instructions_file and instructions_file.exists():
            self.system_prompt = instructions_file.read_text(encoding="utf-8")

        self._history: List[Dict] = []
        self._response_id: Optional[str] = None

    # ==========================================================
    # Utility
    # ==========================================================
    def _create_bbox(self, det: dict) -> BoundingBox2D:
        bbox = BoundingBox2D()
        bbox.center.position.x = float(det["x"])
        bbox.center.position.y = float(det["y"])
        bbox.size_x = float(det["width"])
        bbox.size_y = float(det["height"])
        return bbox

    def _encode_image(self, image: np.ndarray) -> str:
        _, buffer = cv2.imencode(".jpg", image)
        return base64.b64encode(buffer).decode("utf-8")

    def _approx_token_count(self, messages: List[Dict]) -> int:
        total = 0
        for msg in messages:
            content = msg["content"]
            if isinstance(content, list):
                for block in content:
                    if block["type"] == "input_text":
                        total += len(block["text"]) // 4
            else:
                total += len(str(content)) // 4
        return total

    def _trim_history(self):
        messages = self._build_input()
        while self._approx_token_count(messages) > self.max_tokens and len(self._history) > 1:
            self._history.pop(0)
            messages = self._build_input()

    def _build_input(self) -> List[Dict]:
        messages = []
        if self.system_prompt:
            messages.append({
                "role": "system",
                "content": self.system_prompt
            })
        messages.extend(self._history)
        return messages

    # ==========================================================
    # Public API
    # ==========================================================

    def add_context(
        self,
        role: str,
        text: Optional[str] = None,
        images: Optional[List[np.ndarray]] = None,
    ) -> None:

        content_blocks = []

        if text:
            if pathlib.Path(text).is_file():
                text = pathlib.Path(text).read_text(encoding="utf-8")

            content_blocks.append({
                "type": "input_text",
                "text": text
            })

        if images:
            for img in images:
                content_blocks.append({
                    "type": "input_image",
                    "image_url": f"data:image/jpeg;base64,{self._encode_image(img)}",
                    "detail": self.detail,
                })

        self._history.append({
            "role": role,
            "content": content_blocks if content_blocks else text
        })

    def clear_context(self) -> None:
        self._history = []
        self._response_id = None

    # ==========================================================
    # Main Chat Function
    # ==========================================================

    def chat(
        self,
        functions: Optional[List[Dict]] = None,
        function_map: Optional[Dict[str, Callable]] = None,
    ) -> str:

        self._trim_history()

        tools = []

        if self.enable_web_search:
            tools.append({"type": "web_search"})

        if functions:
            tools.extend(functions)

        response = self.client.responses.create(
            model=self.model_name,
            input=self._build_input(),
            tools=tools if tools else None,
            previous_response_id=self._response_id,
            max_output_tokens=self.max_tokens,
        )

        self._response_id = response.id

        # Assistant通常応答
        if response.output_text:
            self._history.append({
                "role": "assistant",
                "content": response.output_text
            })
            return response.output_text

        # ======================================================
        # Function Call Handling
        # ======================================================

        if function_map and response.output:
            for item in response.output:
                if item.type == "tool_call":
                    fn_name = item.name
                    arguments = item.arguments or {}

                    if fn_name in function_map:
                        result = function_map[fn_name](**arguments)

                        followup = self.client.responses.create(
                            model=self.model_name,
                            previous_response_id=response.id,
                            input=[
                                {
                                    "type": "tool_result",
                                    "tool_call_id": item.id,
                                    "content": str(result)
                                }
                            ],
                        )

                        self._response_id = followup.id

                        if followup.output_text:
                            self._history.append({
                                "role": "assistant",
                                "content": followup.output_text
                            })
                            return followup.output_text

        return ""
