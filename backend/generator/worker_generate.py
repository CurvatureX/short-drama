#!/usr/bin/env python3
"""
Isolated worker process for image generation
This runs in a separate process and exits after completion,
automatically freeing all GPU memory
"""

import sys
import json
import gc
import torch
from PIL import Image
import io

# Add parent directory to path
sys.path.insert(0, '/opt/image-generator')

from services.qwen_service import qwen_model_service


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: worker_generate.py <operation> <params_json>"}))
        sys.exit(1)

    operation = sys.argv[1]
    params_json = sys.argv[2]

    try:
        params = json.loads(params_json)

        if operation == "edit_image":
            # Download image from URL
            from services.s3_service import s3_service
            image_url = params["image_url"]
            input_image = s3_service.download_image_from_url(image_url)

            if input_image is None:
                print(json.dumps({"error": f"Failed to download image from {image_url}"}))
                sys.exit(1)

            # Edit image
            edited_image = qwen_model_service.edit_image(
                image=input_image,
                prompt=params["prompt"],
                negative_prompt=params.get("negative_prompt", ""),
                num_inference_steps=params.get("num_inference_steps", 8),
                guidance_scale=params.get("guidance_scale", 1.0),
                true_cfg_scale=params.get("true_cfg_scale", 1.0),
                seed=params.get("seed"),
                scale_to_megapixels=params.get("scale_to_megapixels", 1.0),
                use_cfg_norm=params.get("use_cfg_norm", True),
                scheduler_shift=params.get("scheduler_shift", 3.0),
            )

            # Convert to bytes
            img_bytes = io.BytesIO()
            edited_image.save(img_bytes, format="PNG")
            img_bytes.seek(0)

            # Write to stdout as base64
            import base64
            img_b64 = base64.b64encode(img_bytes.getvalue()).decode()
            print(json.dumps({"success": True, "image_base64": img_b64}))

        else:
            print(json.dumps({"error": f"Unknown operation: {operation}"}))
            sys.exit(1)

    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
    finally:
        # Cleanup
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
