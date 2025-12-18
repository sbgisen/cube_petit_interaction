#!/usr/bin/env python

# Copyright (c) 2025 SoftBank Corp.
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
#

import json

import httpx


async def get_horoscope_from_api(sign: str, day: str) -> str:
    """Fetch daily horoscope text for the given sign and day from Horoscope App API."""
    url = 'https://horoscope-app-api.vercel.app/api/v1/get-horoscope/daily'
    params = {'sign': sign, 'day': day.upper()}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10.0)
            if response.status_code != 200:
                return f'{sign} の占い取得に失敗しました (HTTP {response.status_code})'
            data = response.json()
            horoscope_data = (data.get('data', {}).get('horoscope_data', '').strip())
            if not horoscope_data:
                return f'{sign} の占い結果が取得できませんでした。'
            return horoscope_data
    except Exception as e:
        return f'{sign} の占い取得エラー: {e}'


async def horoscope(arguments: dict) -> str:
    """Call Horoscope API and return formatted text."""
    try:
        args = {}
        if isinstance(arguments, str):
            try:
                args = json.loads(arguments)
            except json.JSONDecodeError:
                args = {}
        elif isinstance(arguments, dict):
            args = arguments

        sign = args.get('sign', 'Aries')
        day = args.get('day', 'TODAY')

        horoscope_text = await get_horoscope_from_api(sign, day)
        return f'{sign} の {day} の運勢: {horoscope_text}'

    except Exception as e:
        return f'Failed to handle sample_horoscope call: {e}'
