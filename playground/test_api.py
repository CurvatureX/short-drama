#!/usr/bin/env python3
"""
Simple test script to debug CosyVoice API
"""

import os
import traceback
import dashscope
from dotenv import load_dotenv
from dashscope.audio.tts_v2 import SpeechSynthesizer, AudioFormat

# Load environment
load_dotenv()

print(f"API Key set: {'DASHSCOPE_API_KEY' in os.environ}")
print(f"API Key (first 10 chars): {os.environ.get('DASHSCOPE_API_KEY', '')[:10]}...")

# Set dashscope API key
if 'DASHSCOPE_API_KEY' in os.environ:
    dashscope.api_key = os.environ['DASHSCOPE_API_KEY']
    print(f"DashScope API key set: {dashscope.api_key[:10]}...")

try:
    print("\nCreating synthesizer...")
    synthesizer = SpeechSynthesizer(
        model="cosyvoice-v3",
        voice="longhuhu_v3",
        format=AudioFormat.MP3_22050HZ_MONO_256KBPS,
        speech_rate=1.0,
        volume=50
    )

    print("Calling synthesizer...")
    text = "你好，这是一个测试。"
    audio = synthesizer.call(text=text)

    print(f"Audio type: {type(audio)}")
    print(f"Audio is None: {audio is None}")
    if audio:
        print(f"Audio length: {len(audio)} bytes")

        with open('test_output.mp3', 'wb') as f:
            f.write(audio)
        print("Success! Audio saved to test_output.mp3")
    else:
        print("ERROR: Audio is None!")

except Exception as e:
    print(f"\nError occurred: {type(e).__name__}: {e}")
    traceback.print_exc()
