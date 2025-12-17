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

weather_code_map = {
    0: '快晴',
    1: 'ほぼ快晴',
    2: '晴れ時々曇り',
    3: '曇り',
    45: '霧',
    48: '氷霧',
    51: '弱い霧雨',
    53: '霧雨',
    55: '強い霧雨',
    56: '弱い着氷性の霧雨',
    57: '着氷性の霧雨',
    61: '弱い雨',
    63: '雨',
    65: '強い雨',
    66: '弱い着氷性の雨',
    67: '着氷性の雨',
    71: '弱い雪',
    73: '雪',
    75: '強い雪',
    77: '雪あられ',
    80: '弱いにわか雨',
    81: 'にわか雨',
    82: '強いにわか雨',
    85: '弱いにわか雪',
    86: 'にわか雪',
    95: '雷雨',
    96: 'ひょうを伴う弱い雷雨',
    99: 'ひょうを伴う雷雨'
}


async def get_weather_from_api(location: str) -> dict:
    """Get current weather data for a given location."""
    try:
        if location in ['東京', 'tokyo']:
            lat, lon = 35.6895, 139.6917
        elif location in ['名古屋', 'nagoya']:
            lat, lon = 35.1815, 136.9066
        else:
            print(f'Unknown location: {location}, defaulting to Tokyo')
            lat, lon = 35.6895, 139.6917

        url = (f'https://api.open-meteo.com/v1/forecast?'
               f'latitude={lat}&longitude={lon}&current_weather=true')

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            if response.status_code != 200:
                print(f'Weather API request failed with status {response.status_code}')
                return {'error': f'Weather API request failed with status {response.status_code}'}

            data = response.json()
            weather = data.get('current_weather', {})
            return {
                'location': location,
                'temperature': weather.get('temperature'),
                'windspeed': weather.get('windspeed'),
                'weathercode': weather.get('weathercode'),
                'time': weather.get('time'),
            }

    except Exception as e:
        print(f'Error getting weather: {e}')
        return {'error': str(e)}


async def weather(arguments: dict) -> str:
    """Call Horoscope API and return formatted text."""
    try:
        args = json.loads(arguments)
        location = args.get('location', '東京')
        if location == 'tokyo':
            location = '東京'
        if location == 'nagoya':
            location = '名古屋'

        weather_data = await get_weather_from_api(location)
        temperature_text = weather_data.get('temperature')
        temperature_text = f'{temperature_text:g}'.replace('.', 'てん')
        wathercode_text = weather_data.get('weathercode')
        weather_desc = weather_code_map.get(wathercode_text, f'不明({wathercode_text})')
        weather_text = f'{location}の天気は {temperature_text}度の{weather_desc}です'
        return f'{weather_text}'

    except Exception as e:
        return f'Failed to handle sample_horoscope call: {e}'
