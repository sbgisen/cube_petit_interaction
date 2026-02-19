#!/usr/bin/env python3
import io
import json
import wave
import numpy as np
import requests

import rclpy
from rclpy.node import Node

from std_msgs.msg import String
from std_srvs.srv import SetBool
from audio_common_msgs.msg import AudioDataStamped


class VoiceEmotionNode(Node):

    def __init__(self):
        super().__init__("voice_emotion_node")

        # Parameters
        self.declare_parameter("api_key", "")
        self.declare_parameter(
            "endpoint",
            "https://api.webempath.net/v2/analyzeWav"
        )
        self.declare_parameter("start_enable", False)

        self.api_key = self.get_parameter("api_key").get_parameter_value().string_value
        self.endpoint = self.get_parameter("endpoint").value
        self.enabled = self.get_parameter("start_enable").get_parameter_value().bool_value

        # Publisher
        self.pub = self.create_publisher(
            String,
            "voice_emotion_json",
            10
        )

        # Subscriber
        self.sub = self.create_subscription(
            AudioDataStamped,
            "human_voice_stamped",
            self.audio_callback,
            10
        )

        # Service
        self.srv = self.create_service(
            SetBool,
            "enable_voice_emotion",
            self.enable_callback
        )

        self.session = requests.Session()

        self.get_logger().info("Voice Emotion Node (v2) started")

    # ---------------------------
    # Service
    # ---------------------------
    def enable_callback(self, request, response):
        self.enabled = request.data
        response.success = True
        response.message = f"enable_voice_emotion = {self.enabled}"
        self.get_logger().info(response.message)
        return response

    # ---------------------------
    # Audio Callback
    # ---------------------------
    def audio_callback(self, msg):

        if not self.enabled:
            return

        if not self.api_key:
            self.get_logger().warn("API key not set")
            return

        raw_bytes = bytes(msg.audio.data)

        try:
            wav_bytes = self.convert_to_11025_mono_wav(raw_bytes)
        except Exception as e:
            self.get_logger().error(f"Audio conversion failed: {e}")
            return

        result = self.call_empath(wav_bytes)
        if result:
            out = String()
            out.data = json.dumps(result, ensure_ascii=False)
            self.pub.publish(out)

    # ---------------------------
    # Convert to 11025Hz mono 5sec WAV
    # ---------------------------
    def convert_to_11025_mono_wav(self, audio_bytes):

        # ---- ここを自分のマイク設定に合わせる ----
        input_sample_rate = 24000   # ← ここ重要（確認してください）
        sample_width = 2            # 16bit = 2 bytes
        # ------------------------------------------

        # PCM → numpy int16
        data = np.frombuffer(audio_bytes, dtype=np.int16)

        # 5秒制限
        max_samples = input_sample_rate * 5
        data = data[:max_samples]

        # float化
        data = data.astype(np.float32) / 32768.0

        # リサンプリング
        if input_sample_rate != 11025:
            duration = len(data) / input_sample_rate
            new_length = int(duration * 11025)

            data = np.interp(
                np.linspace(0.0, duration, new_length),
                np.linspace(0.0, duration, len(data)),
                data
            )

        # int16へ戻す
        data = (data * 32767).astype(np.int16)

        # WAV化
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(11025)
            wf.writeframes(data.tobytes())

        return buffer.getvalue()

    def resample(self, data, orig_sr, target_sr):
        duration = len(data) / orig_sr
        new_length = int(duration * target_sr)
        return np.interp(
            np.linspace(0.0, duration, new_length),
            np.linspace(0.0, duration, len(data)),
            data
        )

    # ---------------------------
    # Call Empath v2 API
    # ---------------------------
    def call_empath(self, wav_bytes):

        files = {
            "wav": ("audio.wav", wav_bytes, "audio/wav")
        }
        data = {
            "apikey": self.api_key
        }

        try:
            r = self.session.post(
                self.endpoint,
                data=data,
                files=files,
                timeout=10
            )

            return r.json()

        except Exception as e:
            self.get_logger().error(f"API call failed: {e}")
            return None


def main():
    rclpy.init()
    node = VoiceEmotionNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
