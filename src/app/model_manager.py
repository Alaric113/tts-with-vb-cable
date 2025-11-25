# -*- coding: utf-8 -*-
"""
This module manages the predefined TTS models, especially for Sherpa-ONNX.
It provides a centralized place to define model configurations, including
download URLs and file names.
"""

PREDEFINED_MODELS = {
    # Original model in our project
    "sherpa-vits-zh-aishell3": {
        "id": "sherpa-vits-zh-aishell3",
        "engine": "sherpa-vits-zh-aishell3",
        "download_url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-zh-aishell3.tar.bz2",
        "language": "Chinese",
        "speakers": 174, # aishell3 (Chinese, multi-speaker, 174 speakers) from webpage
        "filesize_mb": 116, # from webpage
        "default_rate": 1.0,
        "default_volume": 1.0,
        "file_names": [
            "vits-aishell3.onnx",
            "lexicon.txt",
            "tokens.txt",
            "date.fst",
            "new_heteronym.fst",
            "number.fst",
            "phone.fst",
            "rule.far" # Added rule.far based on parsing
        ]
    },
    # Glados model
    "vits-piper-en_US-glados": {
        "id": "vits-piper-en_US-glados",
        "engine": "vits-piper-en_US-glados",
        "download_url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-en_US-glados.tar.bz2",
        "language": "English",
        "speakers": 1,
        "filesize_mb": 61,
        "default_rate": 1.0,
        "default_volume": 1.0,
        "file_names": [
            "en_US-glados.onnx",
            "tokens.txt",
            "espeak-ng-data"
        ]
    },
    # vits-melo-tts-zh_en
    "vits-melo-tts-zh_en": {
        "id": "vits-melo-tts-zh_en",
        "engine": "vits-melo-tts-zh-en",
        "download_url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-melo-tts-zh_en.tar.bz2",
        "language": "Chinese + English",
        "speakers": 1,
        "filesize_mb": 163,
        "default_rate": 1.0,
        "default_volume": 1.0,
        "file_names": [
            "model.onnx",
            "lexicon.txt",
            "tokens.txt",
            "date.fst",
            "number.fst",
            "phone.fst"
        ]
    },
    # sherpa-onnx-vits-zh-ll
    "sherpa-onnx-vits-zh-ll": {
        "id": "sherpa-onnx-vits-zh-ll",
        "engine": "sherpa-onnx-vits-zh-ll",
        "download_url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/sherpa-onnx-vits-zh-ll.tar.bz2",
        "language": "Chinese",
        "speakers": 5,
        "filesize_mb": 115,
        "default_rate": 1.0,
        "default_volume": 1.0,
        "file_names": [
            "model.onnx",
            "lexicon.txt",
            "tokens.txt",
            "date.fst",
            "new_heteronym.fst",
            "number.fst",
            "phone.fst"
        ]
    },
    # vits-zh-hf-fanchen-C
    "vits-zh-hf-fanchen-C": {
        "id": "vits-zh-hf-fanchen-C",
        "engine": "vits-zh-hf-fanchen-C",
        "download_url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-zh-hf-fanchen-C.tar.bz2",
        "language": "Chinese",
        "speakers": 187,
        "filesize_mb": 116,
        "default_rate": 1.0,
        "default_volume": 1.0,
        "file_names": [
            "vits-zh-hf-fanchen-C.onnx",
            "lexicon.txt",
            "tokens.txt",
            "date.fst",
            "new_heteronym.fst",
            "number.fst",
            "phone.fst"
        ]
    },
    # vits-zh-hf-fanchen-wnj
    "vits-zh-hf-fanchen-wnj": {
        "id": "vits-zh-hf-fanchen-wnj",
        "engine": "vits-zh-hf-fanchen-wnj",
        "download_url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-zh-hf-fanchen-wnj.tar.bz2",
        "language": "Chinese",
        "speakers": 1,
        "filesize_mb": 116,
        "default_rate": 1.0,
        "default_volume": 1.0,
        "file_names": [
            "vits-zh-hf-fanchen-wnj.onnx",
            "lexicon.txt",
            "tokens.txt",
            "date.fst",
            "new_heteronym.fst",
            "number.fst",
            "phone.fst",
            "rule.far"
        ]
    },
    # vits-zh-hf-theresa
    "vits-zh-hf-theresa": {
        "id": "vits-zh-hf-theresa",
        "engine": "vits-zh-hf-theresa",
        "download_url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-zh-hf-theresa.tar.bz2",
        "language": "Chinese",
        "speakers": 804,
        "filesize_mb": 116, # approx
        "default_rate": 1.0,
        "default_volume": 1.0,
        "file_names": [
            "theresa.onnx",
            "lexicon.txt",
            "tokens.txt",
            "date.fst",
            "new_heteronym.fst",
            "number.fst",
            "phone.fst"
        ]
    },
    # vits-ljspeech
    "vits-ljspeech": {
        "id": "vits-ljspeech",
        "engine": "vits-ljspeech",
        "download_url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-ljs.tar.bz2",
        "language": "English (US)",
        "speakers": 1,
        "filesize_mb": 109,
        "default_rate": 1.0,
        "default_volume": 1.0,
        "file_names": [
            "vits-ljs.onnx"
        ]
    },
    # vits-model-vits-vctk
    "vits-vctk": {
        "id": "vits-vctk",
        "engine": "vits-vctk",
        "download_url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-vctk.tar.bz2",
        "language": "English",
        "speakers": 109,
        "filesize_mb": 116,
        "default_rate": 1.0,
        "default_volume": 1.0,
        "file_names": [
            "vits-vctk.onnx",
            "lexicon.txt",
            "tokens.txt"
        ]
    },
    # vits-piper-en_US-libritts_r-medium (multi-speaker)
    "vits-piper-en_US-libritts_r-medium": {
        "id": "vits-piper-en_US-libritts_r-medium",
        "engine": "vits-piper-en_US-libritts_r-medium",
        "download_url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-en_US-libritts_r-medium.tar.bz2",
        "language": "English",
        "speakers": 904,
        "filesize_mb": 75,
        "default_rate": 1.0,
        "default_volume": 1.0,
        "file_names": [
            "en_US-libritts_r-medium.onnx",
            "tokens.txt",
            "espeak-ng-data"
        ]
    }
}