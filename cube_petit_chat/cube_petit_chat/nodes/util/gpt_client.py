#!/usr/bin/env python

# Copyright (c) 2026 SoftBank Corp.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import pathlib
from typing import Callable, Dict, List, Optional

from cube_petit_chat.nodes.util import history_logic
import cv2
import numpy as np
from openai import OpenAI
from vision_msgs.msg import BoundingBox2D


class GPTClient:

    def __init__(
        self,
        api_key: str,
        model_name: str = 'gpt-4o',
        max_tokens: int = 4000,
        instructions_file: Optional[pathlib.Path] = None,
        enable_web_search: bool = False,
        detail: str = 'auto',
    ) -> None:

        self.client = OpenAI(api_key=api_key)
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.enable_web_search = enable_web_search
        self.detail = detail

        self.system_prompt = ''
        if instructions_file and instructions_file.exists():
            self.system_prompt = instructions_file.read_text(encoding='utf-8')

        self._history: List[Dict] = []
        self._response_id: Optional[str] = None

    # ==========================================================
    # Utility
    # ==========================================================
    def _create_bbox(self, det: dict) -> BoundingBox2D:
        bbox = BoundingBox2D()
        bbox.center.position.x = float(det['x'])
        bbox.center.position.y = float(det['y'])
        bbox.size_x = float(det['width'])
        bbox.size_y = float(det['height'])
        return bbox

    def _encode_image(self, image: np.ndarray) -> str:
        _, buffer = cv2.imencode('.jpg', image)
        return base64.b64encode(buffer).decode('utf-8')

    def _approx_token_count(self, messages: List[Dict]) -> int:
        return history_logic.approx_token_count(messages)

    def _trim_history(self) -> None:
        history_logic.trim_history(self._history, self.system_prompt, self.max_tokens)

    def _build_input(self) -> List[Dict]:
        return history_logic.build_input(self.system_prompt, self._history)

    # ==========================================================
    # Public API
    # ==========================================================

    def add_context(
        self,
        role: str,
        text: Optional[str] = None,
        images: Optional[List[np.ndarray]] = None,
    ) -> None:

        image_data_urls = None
        if images:
            image_data_urls = [f'data:image/jpeg;base64,{self._encode_image(img)}' for img in images]

        self._history.append(
            history_logic.make_context_entry(
                role,
                text=text,
                image_data_urls=image_data_urls,
                detail=self.detail,
            ))

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
            tools.append({'type': 'web_search'})

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
            self._history.append({'role': 'assistant', 'content': response.output_text})
            return response.output_text

        # ======================================================
        # Function Call Handling
        # ======================================================

        if function_map and response.output:
            for item in response.output:
                if item.type == 'tool_call':
                    fn_name = item.name
                    arguments = item.arguments or {}

                    if fn_name in function_map:
                        result = function_map[fn_name](**arguments)

                        followup = self.client.responses.create(
                            model=self.model_name,
                            previous_response_id=response.id,
                            input=[{
                                'type': 'tool_result',
                                'tool_call_id': item.id,
                                'content': str(result)
                            }],
                        )

                        self._response_id = followup.id

                        if followup.output_text:
                            self._history.append({'role': 'assistant', 'content': followup.output_text})
                            return followup.output_text

        return ''
