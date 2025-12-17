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

from typing import Optional

import cv2
from cv_bridge import CvBridge
import numpy as np
from phomemo_printer.ESCPOS_printer import Printer
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image as RosImage
from std_srvs.srv import Trigger


class M02Printer(Node):
    """
    ROS 2 node for Phomemo M02/M02S printing over Bluetooth SPP (RFCOMM).

    Params:
      mac_address (str): Bluetooth MAC (e.g., '24:70:06:1D:C4:8E')
      ch (int): RFCOMM channel (e.g., 1)
      paper_width_mm (int/float): 用紙幅（mm）。M02系は 53 を想定
      dpi (int): プリンタDPI。M02S/M02Proは 300dpi が多い
      dither (bool): 2値化時にFloyd–Steinbergディザを使うか
      margin_px (int): 左右マージン（ピクセル）
    """

    def __init__(self) -> None:
        super().__init__('m02_printer')

        # Declare parameters with default values
        self.declare_parameter('mac_address', '24:70:06:1D:C4:8E')
        self.declare_parameter('ch', 1)
        self.declare_parameter('paper_width_mm', 53.0)
        self.declare_parameter('dpi', 300)
        self.declare_parameter('dither', True)
        self.declare_parameter('margin_px', 0)

        # Get parameter values
        self.mac_address: str = self.get_parameter('mac_address').get_parameter_value().string_value
        self.ch: int = self.get_parameter('ch').get_parameter_value().integer_value
        self.paper_width_mm: float = float(
            self.get_parameter('paper_width_mm').get_parameter_value().double_value or 53.0)
        self.dpi: int = int(self.get_parameter('dpi').get_parameter_value().integer_value or 300)
        self.use_dither: bool = bool(self.get_parameter('dither').get_parameter_value().bool_value)
        self.margin_px: int = int(self.get_parameter('margin_px').get_parameter_value().integer_value)

        # Initialize CvBridge for ROS <-> OpenCV conversion
        self.bridge = CvBridge()
        self.printer: Optional[Printer] = None
        self.last_cv_bgr: Optional[np.ndarray] = None

        # Initialize printer instance (lazy connection: connects on first print)
        self.printer: Optional[Printer] = None

        self.sub = self.create_subscription(RosImage, 'm02_printer/print_image', self._on_image_msg, 10)
        self.srv = self.create_service(Trigger, 'm02_printer/print_last', self._on_print_last)

        self.get_logger().info(
            f'Initialized M02_Printer: MAC={self.mac_address}, CH={self.ch}, '
            f'paper={self.paper_width_mm}mm @ {self.dpi}dpi, dither={self.use_dither}, margin={self.margin_px}px')

    def _on_image_msg(self, msg: RosImage) -> None:
        """画像を受け取ったら前処理しておく."""
        try:
            cv_bgr: np.ndarray = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            self.last_cv_bgr = cv_bgr.copy()
            # self._print_cv_image(cv_bgr)
        except Exception as e:
            self.get_logger().error(f'_on_image_msg error: {e}')

    def _on_print_last(self, req: Trigger.Request, res: Trigger.Response) -> None:
        """最後に受け取った画像を再印刷（/m02/print_last）."""
        if self.last_cv_bgr is None:
            res.success = False
            res.message = '写真がありませんでした'
            return res
        try:
            self._print_cv_image(self.last_cv_bgr)
            res.success = True
            res.message = '写真を印刷しました'
        except Exception as e:
            res.success = False
            res.message = f'Failed: {e}'
        return res

    def _print_cv_image(self, cv_bgr: np.ndarray) -> None:
        """前処理（サイズ・2値化）→ 一時ファイル保存 → プリンタ印刷."""
        # 1) 前処理（幅フィット＋モノクロ）
        processed = self._preprocess_for_m02(cv_bgr)

        # 2) 一時ファイルへ保存
        tmp_path = '/tmp/m02_print_image.png'
        cv2.imwrite(tmp_path, processed)

        # 3) プリンタ接続（初回）
        if self.printer is None:
            self.printer = Printer(bluetooth_address=self.mac_address, channel=self.ch)

        # 4) 印刷
        self.printer.print_image(tmp_path)
        self.get_logger().info(f'Printed image to {self.mac_address} (CH={self.ch}) -> {tmp_path}')

    def _preprocess_for_m02(self, cv_bgr: np.ndarray) -> np.ndarray:
        """
        M02/M02S向け前処理.

          - 紙幅(ピクセル) = paper_width_mm * (dpi / 25.4)
          - 横幅を紙幅 - margin×2 にフィット（縦は等倍）
          - グレースケール→2値化（Floyd–Steinbergディザ選択可）
        Return: 8bit単チャネル(0/255)の2値画像
        """
        # 実効印字幅（px）
        paper_px = int(round(self.paper_width_mm * (self.dpi / 25.4)))
        target_w = max(1, paper_px - self.margin_px * 2)

        h, w = cv_bgr.shape[:2]
        scale = target_w / w
        new_w = target_w
        new_h = max(1, int(round(h * scale)))
        resized = cv2.resize(cv_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)

        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

        if self.use_dither:
            bw = self._floyd_steinberg_dither(gray)
        else:
            # 普通の2値化（閾値は自動: Otsu）
            _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

        # 左右マージン付与（白）
        if self.margin_px > 0:
            pad_left = self.margin_px
            pad_right = self.margin_px
            bw = cv2.copyMakeBorder(bw, 0, 0, pad_left, pad_right, cv2.BORDER_CONSTANT, value=255)

        return bw

    @staticmethod
    def _floyd_steinberg_dither(gray: np.ndarray) -> np.ndarray:
        """
        Floyd–Steinbergディザ（高速実装）.

        入力: 0..255 のグレー
        出力: 0 or 255 の2値
        """
        img = gray.astype(np.float32) / 255.0
        h, w = img.shape
        out = np.zeros_like(img, dtype=np.float32)

        for y in range(h):
            for x in range(w):
                old = img[y, x]
                new = 1.0 if old >= 0.5 else 0.0
                out[y, x] = new
                err = old - new
                if x + 1 < w:
                    img[y, x + 1] += err * 7 / 16
                if y + 1 < h and x > 0:
                    img[y + 1, x - 1] += err * 3 / 16
                if y + 1 < h:
                    img[y + 1, x] += err * 5 / 16
                if y + 1 < h and x + 1 < w:
                    img[y + 1, x + 1] += err * 1 / 16

        return (out * 255).astype(np.uint8)

    def easy_print(self, image: RosImage) -> bool:
        """
        Convert a ROS Image message to a format suitable for Phomemo printer
        and send it for printing.

        Parameters
        ----------
        image : sensor_msgs.msg.Image
            ROS Image message to be printed.

        Returns:
        -------
        bool
            True if printing succeeded, False otherwise.
        """  # noqa: D205
        try:
            # Convert ROS Image to OpenCV image
            cv_img: np.ndarray = self.bridge.imgmsg_to_cv2(image, desired_encoding='bgr8')

            # Save to temporary file (phomemo_printer expects a file path)
            tmp_path = '/tmp/m02_print_image.png'
            cv2.imwrite(tmp_path, cv_img)

            # Initialize printer connection if not already
            if self.printer is None:
                self.printer = Printer(bluetooth_address=self.mac_address, channel=self.ch)

            # Print the image
            self.printer.print_image(tmp_path)
            self.get_logger().info(f'Printed image to {self.mac_address} (CH={self.ch})')

            return True

        except Exception as e:
            self.get_logger().error(f'Failed to print: {e}')
            return False

    def destroy_node(self) -> None:
        """Cleanup printer connection on node shutdown."""
        if self.printer is not None:
            self.printer.close()
        super().destroy_node()


def main() -> None:
    """Entry point for the M02_Printer node."""
    rclpy.init()
    node = M02Printer()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
