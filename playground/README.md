# CosyVoice 3.0 Voice Generation

This directory contains scripts for generating voice using Aliyun's CosyVoice 3.0 Text-to-Speech service.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up your API key:
```bash
export DASHSCOPE_API_KEY='your-api-key-here'
```

## Usage

### Command Line Interface

Basic usage:
```bash
python cosyvoice_tts.py "你好，这是一个测试" -o output.mp3
```

With options:
```bash
python cosyvoice_tts.py "你的文本内容" \
  -o output.mp3 \
  -m v3 \
  -v longyingxiao \
  -f mp3_24000 \
  -r 1.2 \
  --volume 60
```

For long text (streaming mode):
```bash
python cosyvoice_tts.py "很长的文本..." -o output.mp3 --streaming
```

### Python API

```python
from cosyvoice_tts import CosyVoiceTTS

# Create TTS instance
tts = CosyVoiceTTS(
    model='v3',              # Model version
    voice='longyingxiao'     # Voice character
)

# Generate speech
tts.synthesize(
    text="你的文本内容",
    output_path="output.mp3",
    speech_rate=1.0,         # Speed (0.5-2.0)
    volume=50                # Volume (0-100)
)
```

## Available Models

- `v3-plus`: Highest quality (2 yuan/10K chars)
- `v3`: Balanced quality and cost (0.4 yuan/10K chars) - **Recommended**
- `v2`: Legacy version (2 yuan/10K chars)
- `v1`: Legacy version (2 yuan/10K chars)

## Audio Formats

- MP3: `mp3_22050`, `mp3_24000`
- WAV: `wav_16000`, `wav_22050`, `wav_24000`
- PCM: `pcm_16000`, `pcm_22050`, `pcm_24000`

## Examples

Run the example script:
```bash
python example_cosyvoice.py
```

This will generate multiple audio files demonstrating different features:
- Basic synthesis
- Custom speech rate and volume
- Different audio formats
- Reading from text file
- Streaming mode (commented out by default)

## Parameters

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `model` | str | v3-plus, v3, v2, v1 | v3 | Model version |
| `voice` | str | - | longyingxiao | Voice character |
| `format` | str | See above | mp3_22050 | Audio format |
| `speech_rate` | float | 0.5-2.0 | 1.0 | Speech speed |
| `volume` | int | 0-100 | 50 | Audio volume |

## Limitations

- Single call: Max 2000 characters
- Streaming mode: Max 200K characters total
- Text must be UTF-8 encoded
- Character counting: Chinese = 2 chars, English/punctuation = 1 char

## Free Tier

Each account includes 2000 free characters per month across all models.

## Support

For issues or questions, refer to the [official documentation](https://help.aliyun.com/zh/model-studio/cosyvoice-python-sdk).
