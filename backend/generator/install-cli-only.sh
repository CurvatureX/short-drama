#!/bin/bash
set -e

# Image Generation CLI-Only Installation Script
# For AWS EC2 instances (when API server is running elsewhere)
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/.../install-cli-only.sh | bash
#   or
#   chmod +x install-cli-only.sh && ./install-cli-only.sh

echo "🚀 Image Generation CLI Installation"
echo "====================================="

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Check Python version
echo ""
echo "🐍 Checking Python..."
if ! command -v python3 &> /dev/null; then
    echo "Installing Python 3.11..."
    sudo apt-get update -qq
    sudo apt-get install -y python3.11 python3.11-venv python3-pip
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
print_status "Python $PYTHON_VERSION detected"

# Create temporary directory
TEMP_DIR=$(mktemp -d)
cd "$TEMP_DIR"
print_status "Working in: $TEMP_DIR"

# Download or copy project files
echo ""
echo "📥 Getting project files..."

# For local installation (update this section for remote installation)
cat > cli.py << 'CLI_EOF'
#!/usr/bin/env python3
"""Image Generation CLI Tool"""
import argparse
import sys
import time
import requests
from typing import Optional
from pathlib import Path
import json


class ImageGenerateCLI:
    """CLI for image generation API"""

    def __init__(self, api_base_url: str = "http://localhost:8000"):
        self.api_base_url = api_base_url.rstrip("/")

    def change_angle(
        self,
        image_url: str,
        prompt: str,
        negative_prompt: str = "",
        num_inference_steps: int = 8,
        guidance_scale: float = 1.0,
        true_cfg_scale: float = 1.0,
        seed: Optional[int] = None,
        scale_to_megapixels: float = 1.0,
        use_cfg_norm: bool = True,
        scheduler_shift: float = 3.0,
        output: Optional[str] = None,
        wait: bool = True,
        verbose: bool = False,
    ) -> Optional[str]:
        endpoint = f"{self.api_base_url}/api/qwen-multi-angle/i2i"
        data = {
            "image_url": image_url,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "true_cfg_scale": true_cfg_scale,
            "scale_to_megapixels": scale_to_megapixels,
            "use_cfg_norm": use_cfg_norm,
            "scheduler_shift": scheduler_shift,
        }
        if seed is not None:
            data["seed"] = seed

        if verbose:
            print(f"🚀 Submitting to: {endpoint}")
            print(f"📊 Params: {json.dumps(data, indent=2, ensure_ascii=False)}")

        try:
            response = requests.post(endpoint, data=data, timeout=30)
            response.raise_for_status()
            result = response.json()
            session_id = result.get("session_id")

            if not session_id:
                print(f"❌ Error: No session_id returned")
                return None

            print(f"✅ Task submitted! Session ID: {session_id}")

            if not wait:
                print(f"ℹ️  Check status: image-generate status {session_id}")
                return session_id

            result_url = self._wait_for_completion(session_id, verbose=verbose)
            if result_url and output:
                return self._download_result(result_url, Path(output), verbose=verbose)
            return result_url

        except Exception as e:
            print(f"❌ Error: {e}")
            return None

    def check_status(self, session_id: str, verbose: bool = False):
        endpoint = f"{self.api_base_url}/api/{session_id}/status"
        try:
            response = requests.get(endpoint, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"❌ Error: {e}")
            return None

    def _wait_for_completion(self, session_id: str, timeout: int = 300, verbose: bool = False):
        print(f"⏳ Waiting for completion (timeout: {timeout}s)...")
        start_time = time.time()
        last_progress = -1

        while time.time() - start_time < timeout:
            status = self.check_status(session_id, verbose=False)
            if not status:
                return None

            task_status = status.get("status")
            progress = status.get("progress", 0)
            message = status.get("message", "")

            if progress != last_progress:
                print(f"📈 Progress: {progress}% - {message}")
                last_progress = progress

            if task_status == "completed":
                result_url = status.get("result_url")
                print(f"✅ Task completed!\n🔗 Result: {result_url}")
                return result_url
            elif task_status == "failed":
                print(f"❌ Task failed: {status.get('error', 'Unknown')}")
                return None

            time.sleep(2)

        print(f"⏰ Timeout after {timeout}s")
        return None

    def _download_result(self, url: str, output_path: Path, verbose: bool = False):
        try:
            response = requests.get(url, timeout=60, stream=True)
            response.raise_for_status()
            output_path.parent.mkdir(parents=True, exist_ok=True)

            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0

            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            progress = (downloaded / total_size) * 100
                            print(f"\r📥 Downloading: {progress:.1f}%", end="", flush=True)

            print(f"\n💾 Saved to: {output_path.absolute()}")
            return str(output_path.absolute())
        except Exception as e:
            print(f"❌ Download failed: {e}")
            return None

    def get_model_info(self, verbose: bool = False):
        endpoint = f"{self.api_base_url}/api/qwen-multi-angle/info"
        try:
            response = requests.get(endpoint, timeout=10)
            response.raise_for_status()
            info = response.json()

            print("🤖 Qwen Multi-Angle Model Info:")
            print("=" * 60)

            if "models" in info:
                print("\n📦 Models:")
                for key, value in info["models"].items():
                    print(f"  - {key}: {value}")

            if "loras" in info:
                print("\n🎨 LoRAs:")
                for key, value in info["loras"].items():
                    print(f"  - {key}: {value}")

            return info
        except Exception as e:
            print(f"❌ Error: {e}")
            return None


def main():
    parser = argparse.ArgumentParser(description="Image Generation CLI")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("-v", "--verbose", action="store_true")
    subparsers = parser.add_subparsers(dest="command")

    # change_angle
    change = subparsers.add_parser("change_angle")
    change.add_argument("-i", "--image-url", required=True)
    change.add_argument("-p", "--prompt", required=True)
    change.add_argument("-n", "--negative-prompt", default="")
    change.add_argument("--num_inference_steps", type=int, default=8)
    change.add_argument("--guidance_scale", type=float, default=1.0)
    change.add_argument("--true_cfg_scale", type=float, default=1.0)
    change.add_argument("--seed", type=int)
    change.add_argument("--scale_to_megapixels", type=float, default=1.0)
    change.add_argument("--no-cfg-norm", action="store_true")
    change.add_argument("--scheduler_shift", type=float, default=3.0)
    change.add_argument("-o", "--output")
    change.add_argument("--no-wait", action="store_true")

    # status
    status = subparsers.add_parser("status")
    status.add_argument("session_id")

    # info
    subparsers.add_parser("info")

    args = parser.parse_args()
    cli = ImageGenerateCLI(api_base_url=args.api_url)

    if args.command == "change_angle":
        result = cli.change_angle(
            image_url=args.image_url,
            prompt=args.prompt,
            negative_prompt=args.negative_prompt,
            num_inference_steps=args.num_inference_steps,
            guidance_scale=args.guidance_scale,
            true_cfg_scale=args.true_cfg_scale,
            seed=args.seed,
            scale_to_megapixels=args.scale_to_megapixels,
            use_cfg_norm=not args.no_cfg_norm,
            scheduler_shift=args.scheduler_shift,
            output=args.output,
            wait=not args.no_wait,
            verbose=args.verbose,
        )
        sys.exit(0 if result else 1)
    elif args.command == "status":
        status = cli.check_status(args.session_id, verbose=args.verbose)
        if status:
            print(f"\n📊 Status: {status.get('status')}")
            print(f"  Progress: {status.get('progress')}%")
            print(f"  Message: {status.get('message')}")
            if status.get("result_url"):
                print(f"  Result: {status.get('result_url')}")
            sys.exit(0)
        sys.exit(1)
    elif args.command == "info":
        cli.get_model_info(verbose=args.verbose)
        sys.exit(0)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
CLI_EOF

chmod +x cli.py
print_status "CLI script created"

# Install dependencies
echo ""
echo "📦 Installing dependencies..."
pip3 install requests --quiet
print_status "Dependencies installed"

# Install CLI globally
echo ""
echo "🔗 Installing CLI globally..."
sudo cp cli.py /usr/local/bin/image-generate
sudo chmod +x /usr/local/bin/image-generate
print_status "CLI installed to: /usr/local/bin/image-generate"

# Cleanup
cd /
rm -rf "$TEMP_DIR"

# Installation complete
echo ""
echo "=============================================="
echo -e "${GREEN}✅ CLI Installation Complete!${NC}"
echo "=============================================="
echo ""
echo "📋 Usage:"
echo ""
echo "  # Basic usage"
echo "  image-generate change_angle \\"
echo "    -i https://short-drama-assets.s3.us-east-1.amazonaws.com/images/test.png \\"
echo "    -p \"将镜头向左旋转45度\" \\"
echo "    -o output.png"
echo ""
echo "  # With custom API URL"
echo "  image-generate --api-url http://api-server:8000 change_angle \\"
echo "    -i <image_url> \\"
echo "    -p \"将镜头转为俯视\""
echo ""
echo "  # Check status"
echo "  image-generate status <session_id>"
echo ""
echo "  # Get model info"
echo "  image-generate info"
echo ""
echo "  # Help"
echo "  image-generate --help"
echo ""
echo "⚠️  Note: Make sure the API server is running and accessible"
echo ""
