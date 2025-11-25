# -*- coding: utf-8 -*-
"""
This module manages the predefined TTS models, especially for Sherpa-ONNX.
It provides a centralized place to define model configurations, including
download URLs and file names.
"""

PREDEFINED_MODELS = {
    "sherpa-vits-zh-aishell3": {
        "id": "sherpa-vits-zh-aishell3",
        "engine": "sherpa-onnx",
        "download_url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-zh-aishell3.tar.bz2",
        "file_names": [
            "vits-aishell3.onnx",
            "tokens.txt",
            "lexicon.txt",
            "rule.fsts"
        ]
    }
    # Future models can be added here
}
