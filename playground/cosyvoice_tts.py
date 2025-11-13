#!/usr/bin/env python3
"""
CosyVoice 3.0 Voice Generation Script
Uses Aliyun DashScope SDK for text-to-speech generation
"""

import os
import sys
from pathlib import Path
import dashscope
from dashscope.audio.tts_v2 import SpeechSynthesizer, AudioFormat

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, skip

# Set dashscope API key from environment
if 'DASHSCOPE_API_KEY' in os.environ:
    dashscope.api_key = os.environ['DASHSCOPE_API_KEY']


class CosyVoiceTTS:
    """CosyVoice Text-to-Speech Generator"""

    # Available models
    MODELS = {
        'v3-plus': 'cosyvoice-v3-plus',  # Highest quality, 2 yuan/10K chars
        'v3': 'cosyvoice-v3',             # Balanced, 0.4 yuan/10K chars
        'v2': 'cosyvoice-v2',             # Legacy, 2 yuan/10K chars
        'v1': 'cosyvoice-v1',             # Legacy, 2 yuan/10K chars
    }

    # Available audio formats
    FORMATS = {
        'mp3_22050': AudioFormat.MP3_22050HZ_MONO_256KBPS,
        'mp3_24000': AudioFormat.MP3_24000HZ_MONO_256KBPS,
        'wav_16000': AudioFormat.WAV_16000HZ_MONO_16BIT,
        'wav_22050': AudioFormat.WAV_22050HZ_MONO_16BIT,
        'wav_24000': AudioFormat.WAV_24000HZ_MONO_16BIT,
        'pcm_16000': AudioFormat.PCM_16000HZ_MONO_16BIT,
        'pcm_22050': AudioFormat.PCM_22050HZ_MONO_16BIT,
        'pcm_24000': AudioFormat.PCM_24000HZ_MONO_16BIT,
    }

    def __init__(self, model='v3', voice='longyingxiao', api_key=None):
        """
        Initialize CosyVoice TTS

        Args:
            model: Model version ('v3-plus', 'v3', 'v2', 'v1')
            voice: Voice character name
            api_key: DashScope API key (if not set in environment)
        """
        if api_key:
            dashscope.api_key = api_key
            os.environ['DASHSCOPE_API_KEY'] = api_key
        elif 'DASHSCOPE_API_KEY' in os.environ:
            dashscope.api_key = os.environ['DASHSCOPE_API_KEY']
        else:
            raise ValueError(
                "API key not found. Please set DASHSCOPE_API_KEY environment variable "
                "or pass api_key parameter"
            )

        self.model = self.MODELS.get(model, model)
        self.voice = voice

    def synthesize(
        self,
        text,
        output_path=None,
        format='mp3_22050',
        speech_rate=1.0,
        volume=50
    ):
        """
        Synthesize speech from text (synchronous)

        Args:
            text: Text to synthesize (max 2000 characters)
            output_path: Output file path (optional)
            format: Audio format (default: mp3_22050)
            speech_rate: Speech rate 0.5-2.0 (default: 1.0)
            volume: Volume 0-100 (default: 50)

        Returns:
            Audio bytes data
        """
        # Validate parameters
        if len(text) > 2000:
            raise ValueError("Text length exceeds 2000 characters limit")

        if not 0.5 <= speech_rate <= 2.0:
            raise ValueError("Speech rate must be between 0.5 and 2.0")

        if not 0 <= volume <= 100:
            raise ValueError("Volume must be between 0 and 100")

        # Get audio format
        audio_format = self.FORMATS.get(format, AudioFormat.MP3_22050HZ_MONO_256KBPS)

        # Create synthesizer with configuration
        synthesizer = SpeechSynthesizer(
            model=self.model,
            voice=self.voice,
            format=audio_format,
            speech_rate=speech_rate,
            volume=volume
        )

        # Generate speech
        print(f"Generating speech with model: {self.model}, voice: {self.voice}")
        try:
            audio_data = synthesizer.call(text=text)
        except Exception as e:
            raise RuntimeError(f"Failed to generate speech: {str(e)}") from e

        # Check if audio_data is valid
        if audio_data is None:
            raise RuntimeError("Speech synthesis returned None - check API credentials and model/voice compatibility")

        # Save to file if output path provided
        if output_path:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, 'wb') as f:
                f.write(audio_data)
            print(f"Audio saved to: {output_file}")

        return audio_data

    def synthesize_streaming(
        self,
        text,
        output_path,
        format='mp3_22050',
        speech_rate=1.0,
        volume=50,
        chunk_size=1800
    ):
        """
        Synthesize long text using streaming mode

        Args:
            text: Text to synthesize (max 200K characters)
            output_path: Output file path
            format: Audio format (default: mp3_22050)
            speech_rate: Speech rate 0.5-2.0 (default: 1.0)
            volume: Volume 0-100 (default: 50)
            chunk_size: Size of text chunks (max 2000)
        """
        if len(text) > 200000:
            raise ValueError("Text length exceeds 200K characters limit")

        if chunk_size > 2000:
            raise ValueError("Chunk size must not exceed 2000 characters")

        # Get audio format
        audio_format = self.FORMATS.get(format, AudioFormat.MP3_22050HZ_MONO_256KBPS)

        # Prepare output file
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        print(f"Streaming synthesis with model: {self.model}, voice: {self.voice}")
        print(f"Text length: {len(text)} characters")

        # Split text into chunks and stream
        with open(output_file, 'wb') as f:
            for i in range(0, len(text), chunk_size):
                chunk = text[i:i + chunk_size]
                print(f"Processing chunk {i//chunk_size + 1}...")

                # Create new synthesizer for each chunk (as per documentation)
                synthesizer = SpeechSynthesizer(
                    model=self.model,
                    voice=self.voice,
                    format=audio_format,
                    speech_rate=speech_rate,
                    volume=volume
                )

                audio_chunk = synthesizer.call(text=chunk)
                f.write(audio_chunk)

        print(f"Audio saved to: {output_file}")


def main():
    """Example usage"""
    import argparse

    parser = argparse.ArgumentParser(
        description='CosyVoice 3.0 Text-to-Speech Generator'
    )
    parser.add_argument(
        'text',
        help='Text to synthesize'
    )
    parser.add_argument(
        '-o', '--output',
        default='output.mp3',
        help='Output file path (default: output.mp3)'
    )
    parser.add_argument(
        '-m', '--model',
        choices=['v3-plus', 'v3', 'v2', 'v1'],
        default='v3',
        help='Model version (default: v3)'
    )
    parser.add_argument(
        '-v', '--voice',
        default='longyingxiao',
        help='Voice character (default: longyingxiao)'
    )
    parser.add_argument(
        '-f', '--format',
        choices=list(CosyVoiceTTS.FORMATS.keys()),
        default='mp3_22050',
        help='Audio format (default: mp3_22050)'
    )
    parser.add_argument(
        '-r', '--rate',
        type=float,
        default=1.0,
        help='Speech rate 0.5-2.0 (default: 1.0)'
    )
    parser.add_argument(
        '--volume',
        type=int,
        default=50,
        help='Volume 0-100 (default: 50)'
    )
    parser.add_argument(
        '--streaming',
        action='store_true',
        help='Use streaming mode for long text'
    )
    parser.add_argument(
        '--api-key',
        help='DashScope API key (or set DASHSCOPE_API_KEY env var)'
    )

    args = parser.parse_args()

    try:
        # Create TTS instance
        tts = CosyVoiceTTS(
            model=args.model,
            voice=args.voice,
            api_key=args.api_key
        )

        # Generate speech
        if args.streaming or len(args.text) > 2000:
            tts.synthesize_streaming(
                text=args.text,
                output_path=args.output,
                format=args.format,
                speech_rate=args.rate,
                volume=args.volume
            )
        else:
            tts.synthesize(
                text=args.text,
                output_path=args.output,
                format=args.format,
                speech_rate=args.rate,
                volume=args.volume
            )

        print("Done!")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
