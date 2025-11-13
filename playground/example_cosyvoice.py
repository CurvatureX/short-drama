#!/usr/bin/env python3
"""
Example usage of CosyVoice TTS
"""

import os
from cosyvoice_tts import CosyVoiceTTS

# Load environment variables from .env file
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # dotenv not installed, skip


def example_basic():
    """Basic synchronous synthesis example"""
    print("=== Basic Synthesis Example ===\n")

    tts = CosyVoiceTTS(
        model="v3",  # Use v3 model (balanced quality and cost)
        voice="longanhuan_v3",  # Voice character
    )

    text = "你好，欢迎使用CosyVoice语音合成服务。这是一个简单的示例。"

    # Generate and save audio
    tts.synthesize(
        text=text,
        output_path="output/basic_example1.mp3",
        speech_rate=1.0,  # Normal speed
        volume=50,  # Medium volume
    )


def example_with_options():
    """Example with different voice options"""
    print("\n=== Synthesis with Custom Options ===\n")

    # Use v3 model with custom speed and volume
    tts = CosyVoiceTTS(
        model="v3", voice="longhuhu_v3"  # v3 model with known compatible voice
    )

    text = "这是一个快速语音示例，音量更大。"

    # Generate with faster speed and higher volume
    tts.synthesize(
        text=text,
        output_path="output/fast_loud.mp3",
        format="mp3_24000",  # Higher quality MP3
        speech_rate=1.5,  # 1.5x speed
        volume=80,  # Louder
    )


def example_streaming():
    """Example for long text using streaming mode"""
    print("\n=== Streaming Synthesis Example ===\n")

    tts = CosyVoiceTTS(model="v3", voice="longhuhu_v3")

    # Long text example
    long_text = (
        """
    在遥远的未来，人类已经能够在星际间自由穿梭。
    太空探索不再是梦想，而是日常生活的一部分。
    每个人都有机会去探索宇宙的奥秘，发现新的世界。
    科技的进步让不可能变成可能，让梦想照进现实。
    """
        * 10
    )  # Repeat to make it longer

    # Use streaming for long text
    tts.synthesize_streaming(
        text=long_text,
        output_path="output/long_text.mp3",
        speech_rate=1.0,
        volume=50,
        chunk_size=1800,  # Process in chunks
    )


def example_different_formats():
    """Example generating different audio formats"""
    print("\n=== Different Format Examples ===\n")

    tts = CosyVoiceTTS(model="v3", voice="longhuhu_v3")

    text = "测试不同的音频格式。"

    # Generate different formats
    formats = {
        "mp3_22050": "output/format_mp3.mp3",
        "wav_24000": "output/format_wav.wav",
        "pcm_16000": "output/format_pcm.pcm",
    }

    for format_name, output_file in formats.items():
        print(f"Generating {format_name}...")
        tts.synthesize(text=text, output_path=output_file, format=format_name)


def example_from_file():
    """Example reading text from file"""
    print("\n=== Synthesis from Text File ===\n")

    # Create a sample text file
    sample_text = """
    欢迎使用CosyVoice语音合成系统。
    本系统支持多种语音合成模式。
    您可以选择不同的声音和参数。
    """

    with open("input_text.txt", "w", encoding="utf-8") as f:
        f.write(sample_text)

    # Read and synthesize
    with open("input_text.txt", "r", encoding="utf-8") as f:
        text = f.read()

    tts = CosyVoiceTTS(model="v3", voice="longhuhu_v3")
    tts.synthesize(text=text, output_path="output/from_file.mp3")


def main():
    """Run all examples"""
    # Check for API key
    if "DASHSCOPE_API_KEY" not in os.environ:
        print("Error: DASHSCOPE_API_KEY environment variable not set")
        print("Please set it with: export DASHSCOPE_API_KEY='your-api-key'")
        return

    try:
        # Run examples
        example_basic()
        # example_with_options()
        # example_different_formats()
        # example_from_file()

        # Uncomment to test streaming (generates longer audio)
        # example_streaming()

        print("\n=== All examples completed! ===")
        print("Check the 'output/' directory for generated audio files.")

    except Exception as e:
        print(f"Error running examples: {e}")


if __name__ == "__main__":
    main()
