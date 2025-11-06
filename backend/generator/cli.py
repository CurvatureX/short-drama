#!/usr/bin/env python3
"""
Image Generation CLI Tool
Provides command-line interface for the image generation API
"""

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
        """
        Change camera angle of an image using Qwen Multi-Angle model

        Args:
            image_url: S3 URL or HTTP(S) URL of input image
            prompt: Camera angle instruction (Chinese)
            negative_prompt: Negative prompt
            num_inference_steps: Number of inference steps (default: 8)
            guidance_scale: CFG scale (default: 1.0)
            true_cfg_scale: True CFG scale (default: 1.0)
            seed: Random seed for reproducibility
            scale_to_megapixels: Scale image to megapixels (default: 1.0)
            use_cfg_norm: Enable CFG normalization (default: True)
            scheduler_shift: ModelSamplingAuraFlow shift (default: 3.0)
            output: Output file path (optional)
            wait: Wait for completion and download result
            verbose: Print detailed logs

        Returns:
            Result URL or local file path if output is specified
        """
        endpoint = f"{self.api_base_url}/api/qwen-multi-angle/i2i"

        # Prepare form data
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
            print(f"🚀 Submitting request to: {endpoint}")
            print(f"📊 Parameters: {json.dumps(data, indent=2, ensure_ascii=False)}")

        try:
            # Submit task
            response = requests.post(endpoint, data=data, timeout=30)
            response.raise_for_status()
            result = response.json()

            session_id = result.get("session_id")
            if not session_id:
                print(f"❌ Error: No session_id returned")
                return None

            print(f"✅ Task submitted successfully!")
            print(f"📝 Session ID: {session_id}")

            if not wait:
                print(f"ℹ️  Use 'image-generate status {session_id}' to check progress")
                return session_id

            # Wait for completion
            result_url = self._wait_for_completion(session_id, verbose=verbose)

            if not result_url:
                return None

            # Download result if output path is specified
            if output:
                output_path = Path(output)
                return self._download_result(result_url, output_path, verbose=verbose)

            return result_url

        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
            return None
        except Exception as e:
            print(f"❌ Error: {e}")
            return None

    def check_status(self, session_id: str, verbose: bool = False) -> Optional[dict]:
        """
        Check status of a generation task

        Args:
            session_id: Session ID from task submission
            verbose: Print detailed logs

        Returns:
            Status dictionary or None
        """
        endpoint = f"{self.api_base_url}/api/{session_id}/status"

        try:
            response = requests.get(endpoint, timeout=10)
            response.raise_for_status()
            status = response.json()

            if verbose:
                print(f"📊 Status: {json.dumps(status, indent=2, ensure_ascii=False)}")

            return status

        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
            return None

    def _wait_for_completion(
        self, session_id: str, timeout: int = 300, verbose: bool = False
    ) -> Optional[str]:
        """
        Wait for task completion and return result URL

        Args:
            session_id: Session ID
            timeout: Maximum wait time in seconds
            verbose: Print detailed logs

        Returns:
            Result URL or None
        """
        print(f"⏳ Waiting for completion (timeout: {timeout}s)...")

        start_time = time.time()
        last_progress = -1

        while time.time() - start_time < timeout:
            status = self.check_status(session_id, verbose=False)

            if not status:
                print(f"❌ Failed to get status")
                return None

            task_status = status.get("status")
            progress = status.get("progress", 0)
            message = status.get("message", "")

            # Show progress if changed
            if progress != last_progress:
                print(f"📈 Progress: {progress}% - {message}")
                last_progress = progress

            if task_status == "completed":
                result_url = status.get("result_url")
                print(f"✅ Task completed!")
                print(f"🔗 Result URL: {result_url}")
                return result_url

            elif task_status == "failed":
                error = status.get("error", "Unknown error")
                print(f"❌ Task failed: {error}")
                return None

            # Wait before next check
            time.sleep(2)

        print(f"⏰ Timeout reached after {timeout}s")
        return None

    def _download_result(
        self, url: str, output_path: Path, verbose: bool = False
    ) -> Optional[str]:
        """
        Download result from URL to local file

        Args:
            url: URL to download from
            output_path: Output file path
            verbose: Print detailed logs

        Returns:
            Local file path or None
        """
        try:
            if verbose:
                print(f"📥 Downloading from: {url}")

            response = requests.get(url, timeout=60, stream=True)
            response.raise_for_status()

            # Ensure parent directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Download with progress
            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0

            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        if total_size > 0 and not verbose:
                            progress = (downloaded / total_size) * 100
                            print(
                                f"\r📥 Downloading: {progress:.1f}%", end="", flush=True
                            )

            print()  # New line after progress
            print(f"💾 Saved to: {output_path.absolute()}")
            return str(output_path.absolute())

        except Exception as e:
            print(f"❌ Download failed: {e}")
            return None

    def remove_watermark_image(
        self,
        image_url: str,
        auto_detect_mask: bool = True,
        num_inference_steps: int = 10,
        guidance_scale: float = 3.0,
        seed: Optional[int] = None,
        output: Optional[str] = None,
        wait: bool = True,
        verbose: bool = False,
    ) -> Optional[str]:
        """
        Remove watermark from an image

        Args:
            image_url: S3 URL or HTTP(S) URL of input image
            auto_detect_mask: Automatically detect watermark regions
            num_inference_steps: Number of denoising steps (default: 10)
            guidance_scale: Guidance scale (default: 3.0)
            seed: Random seed for reproducibility
            output: Output file path (optional)
            wait: Wait for completion and download result
            verbose: Print detailed logs

        Returns:
            Result URL or local file path if output is specified
        """
        endpoint = f"{self.api_base_url}/api/watermark-removal/image"

        data = {
            "image_url": image_url,
            "auto_detect_mask": auto_detect_mask,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
        }

        if seed is not None:
            data["seed"] = seed

        if verbose:
            print(f"🚀 Submitting request to: {endpoint}")
            print(f"📊 Parameters: {json.dumps(data, indent=2, ensure_ascii=False)}")

        try:
            # Submit task
            response = requests.post(endpoint, data=data, timeout=30)
            response.raise_for_status()
            result = response.json()

            session_id = result.get("session_id")
            if not session_id:
                print(f"❌ Error: No session_id returned")
                return None

            print(f"✅ Watermark removal task submitted!")
            print(f"📝 Session ID: {session_id}")

            if not wait:
                print(f"ℹ️  Use 'edit_image status {session_id}' to check progress")
                return session_id

            # Wait for completion
            result_url = self._wait_for_completion(session_id, verbose=verbose)

            if not result_url:
                return None

            # Download result if output path is specified
            if output:
                output_path = Path(output)
                return self._download_result(result_url, output_path, verbose=verbose)

            return result_url

        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
            return None
        except Exception as e:
            print(f"❌ Error: {e}")
            return None

    def remove_watermark_video(
        self,
        video_url: str,
        auto_detect_mask: bool = True,
        num_inference_steps: int = 10,
        guidance_scale: float = 3.0,
        seed: Optional[int] = None,
        preserve_audio: bool = True,
        output: Optional[str] = None,
        wait: bool = True,
        verbose: bool = False,
    ) -> Optional[str]:
        """
        Remove watermark from a video

        Args:
            video_url: S3 URL or HTTP(S) URL of input video
            auto_detect_mask: Automatically detect watermark regions
            num_inference_steps: Number of denoising steps (default: 10)
            guidance_scale: Guidance scale (default: 3.0)
            seed: Random seed for reproducibility
            preserve_audio: Preserve original audio track
            output: Output file path (optional)
            wait: Wait for completion and download result
            verbose: Print detailed logs

        Returns:
            Result URL or local file path if output is specified
        """
        endpoint = f"{self.api_base_url}/api/watermark-removal/video"

        data = {
            "video_url": video_url,
            "auto_detect_mask": auto_detect_mask,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "preserve_audio": preserve_audio,
        }

        if seed is not None:
            data["seed"] = seed

        if verbose:
            print(f"🚀 Submitting request to: {endpoint}")
            print(f"📊 Parameters: {json.dumps(data, indent=2, ensure_ascii=False)}")

        try:
            # Submit task
            response = requests.post(endpoint, data=data, timeout=30)
            response.raise_for_status()
            result = response.json()

            session_id = result.get("session_id")
            if not session_id:
                print(f"❌ Error: No session_id returned")
                return None

            print(f"✅ Video watermark removal task submitted!")
            print(f"📝 Session ID: {session_id}")
            print(f"⏰ Note: Video processing may take several minutes...")

            if not wait:
                print(f"ℹ️  Use 'edit_video status {session_id}' to check progress")
                return session_id

            # Wait for completion with longer timeout
            result_url = self._wait_for_completion(session_id, timeout=1800, verbose=verbose)

            if not result_url:
                return None

            # Download result if output path is specified
            if output:
                output_path = Path(output)
                return self._download_result(result_url, output_path, verbose=verbose)

            return result_url

        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
            return None
        except Exception as e:
            print(f"❌ Error: {e}")
            return None

    def get_model_info(self, verbose: bool = False) -> Optional[dict]:
        """
        Get information about loaded models and system status

        Args:
            verbose: Print detailed logs

        Returns:
            Model info dictionary or None
        """
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

            if "workflow_features" in info:
                print("\n⚙️  Workflow Features:")
                for key, value in info["workflow_features"].items():
                    print(f"  - {key}: {value}")

            if "vram_stats" in info:
                print("\n💾 VRAM Stats:")
                vram = info["vram_stats"]
                print(f"  - State: {vram.get('state', 'unknown')}")
                print(f"  - Utilization: {vram.get('utilization', 0) * 100:.1f}%")

            if verbose:
                print(f"\n📊 Full Info: {json.dumps(info, indent=2, ensure_ascii=False)}")

            return info

        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
            return None


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Image Generation CLI - Control image generation with AI models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Remove watermark from image
  image-generate remove_watermark_image \\
    -i https://short-drama-assets.s3.us-east-1.amazonaws.com/images/watermarked.png \\
    -o clean.png

  # Remove watermark from video
  image-generate remove_watermark_video \\
    -i https://short-drama-assets.s3.us-east-1.amazonaws.com/videos/watermarked.mp4 \\
    -o clean.mp4

  # Change camera angle
  image-generate change_angle \\
    -i https://short-drama-assets.s3.us-east-1.amazonaws.com/images/input.png \\
    -p "将镜头向左旋转45度" \\
    -o output.png

  # Check status
  image-generate status <session_id>

  # Get model info
  image-generate info
        """,
    )

    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="API base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # remove_watermark_image command
    remove_wm_img_parser = subparsers.add_parser(
        "remove_watermark_image",
        aliases=["rm-wm-img"],
        help="Remove watermark from an image",
        description="Remove watermark from an image using AI-powered inpainting"
    )
    remove_wm_img_parser.add_argument(
        "-i", "--image-url", required=True, help="S3 URL or HTTP(S) URL of input image"
    )
    remove_wm_img_parser.add_argument(
        "--auto-detect",
        action="store_true",
        default=True,
        help="Automatically detect watermark regions (default: True)"
    )
    remove_wm_img_parser.add_argument(
        "--num_inference_steps",
        type=int,
        default=10,
        help="Number of denoising steps (default: 10)"
    )
    remove_wm_img_parser.add_argument(
        "--guidance_scale",
        type=float,
        default=3.0,
        help="Guidance scale (default: 3.0)"
    )
    remove_wm_img_parser.add_argument(
        "--seed", type=int, help="Random seed for reproducibility"
    )
    remove_wm_img_parser.add_argument(
        "-o", "--output", help="Output file path (optional)"
    )
    remove_wm_img_parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Don't wait for completion"
    )

    # remove_watermark_video command
    remove_wm_vid_parser = subparsers.add_parser(
        "remove_watermark_video",
        aliases=["rm-wm-vid"],
        help="Remove watermark from a video",
        description="Remove watermark from a video using AI-powered inpainting"
    )
    remove_wm_vid_parser.add_argument(
        "-i", "--video-url", required=True, help="S3 URL or HTTP(S) URL of input video"
    )
    remove_wm_vid_parser.add_argument(
        "--auto-detect",
        action="store_true",
        default=True,
        help="Automatically detect watermark regions (default: True)"
    )
    remove_wm_vid_parser.add_argument(
        "--num_inference_steps",
        type=int,
        default=10,
        help="Number of denoising steps (default: 10)"
    )
    remove_wm_vid_parser.add_argument(
        "--guidance_scale",
        type=float,
        default=3.0,
        help="Guidance scale (default: 3.0)"
    )
    remove_wm_vid_parser.add_argument(
        "--seed", type=int, help="Random seed for reproducibility"
    )
    remove_wm_vid_parser.add_argument(
        "--no-audio",
        action="store_true",
        help="Don't preserve original audio"
    )
    remove_wm_vid_parser.add_argument(
        "-o", "--output", help="Output file path (optional)"
    )
    remove_wm_vid_parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Don't wait for completion"
    )

    # change_angle command
    change_angle_parser = subparsers.add_parser(
        "change_angle",
        help="Change camera angle of an image",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
Change camera angle using Qwen Multi-Angle model

Supported camera angle instructions (Chinese):
  - "将镜头向前移动" (Move the camera forward)
  - "将镜头向左移动" (Move the camera left)
  - "将镜头向右移动" (Move the camera right)
  - "将镜头向下移动" (Move the camera down)
  - "将镜头向左旋转45度" (Rotate 45° left)
  - "将镜头向右旋转45度" (Rotate 45° right)
  - "将镜头转为俯视" (Top-down view)
  - "将镜头转为广角镜头" (Wide-angle lens)
  - "将镜头转为特写镜头" (Close-up)
        """,
    )
    change_angle_parser.add_argument(
        "-i", "--image-url", required=True, help="S3 URL or HTTP(S) URL of input image"
    )
    change_angle_parser.add_argument(
        "-p", "--prompt", required=True, help="Camera angle instruction (Chinese)"
    )
    change_angle_parser.add_argument(
        "-n", "--negative-prompt", default="", help="Negative prompt"
    )
    change_angle_parser.add_argument(
        "--num_inference_steps",
        type=int,
        default=8,
        help="Number of inference steps (default: 8)",
    )
    change_angle_parser.add_argument(
        "--guidance_scale", type=float, default=1.0, help="CFG scale (default: 1.0)"
    )
    change_angle_parser.add_argument(
        "--true_cfg_scale",
        type=float,
        default=1.0,
        help="True CFG scale (default: 1.0)",
    )
    change_angle_parser.add_argument(
        "--seed", type=int, help="Random seed for reproducibility"
    )
    change_angle_parser.add_argument(
        "--scale_to_megapixels",
        type=float,
        default=1.0,
        help="Scale image to megapixels (default: 1.0)",
    )
    change_angle_parser.add_argument(
        "--no-cfg-norm",
        action="store_true",
        help="Disable CFG normalization (enabled by default)",
    )
    change_angle_parser.add_argument(
        "--scheduler_shift",
        type=float,
        default=3.0,
        help="ModelSamplingAuraFlow shift (default: 3.0)",
    )
    change_angle_parser.add_argument(
        "-o", "--output", help="Output file path (optional, downloads result if set)"
    )
    change_angle_parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Don't wait for completion, just return session_id",
    )

    # status command
    status_parser = subparsers.add_parser(
        "status", help="Check status of a generation task"
    )
    status_parser.add_argument("session_id", help="Session ID from task submission")

    # info command
    info_parser = subparsers.add_parser(
        "info", help="Get model and system information"
    )

    args = parser.parse_args()

    # Create CLI instance
    cli = ImageGenerateCLI(api_base_url=args.api_url)

    # Execute command
    if args.command in ("remove_watermark_image", "rm-wm-img"):
        result = cli.remove_watermark_image(
            image_url=args.image_url,
            auto_detect_mask=args.auto_detect,
            num_inference_steps=args.num_inference_steps,
            guidance_scale=args.guidance_scale,
            seed=args.seed,
            output=args.output,
            wait=not args.no_wait,
            verbose=args.verbose,
        )

        if result:
            sys.exit(0)
        else:
            sys.exit(1)

    elif args.command in ("remove_watermark_video", "rm-wm-vid"):
        result = cli.remove_watermark_video(
            video_url=args.video_url,
            auto_detect_mask=args.auto_detect,
            num_inference_steps=args.num_inference_steps,
            guidance_scale=args.guidance_scale,
            seed=args.seed,
            preserve_audio=not args.no_audio,
            output=args.output,
            wait=not args.no_wait,
            verbose=args.verbose,
        )

        if result:
            sys.exit(0)
        else:
            sys.exit(1)

    elif args.command == "change_angle":
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

        if result:
            sys.exit(0)
        else:
            sys.exit(1)

    elif args.command == "status":
        status = cli.check_status(args.session_id, verbose=args.verbose)

        if status:
            print(f"\n📊 Task Status:")
            print(f"  Status: {status.get('status')}")
            print(f"  Progress: {status.get('progress')}%")
            print(f"  Message: {status.get('message')}")

            if status.get("result_url"):
                print(f"  Result URL: {status.get('result_url')}")

            if status.get("error"):
                print(f"  Error: {status.get('error')}")

            sys.exit(0)
        else:
            sys.exit(1)

    elif args.command == "info":
        info = cli.get_model_info(verbose=args.verbose)
        sys.exit(0 if info else 1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
