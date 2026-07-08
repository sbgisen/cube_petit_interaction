#!/usr/bin/env python

# Copyright (c) 2026 SoftBank Corp.
#
# <<licensetext>>

"""pytest 設定: パッケージをインストールせずソースから import できるようにする."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
