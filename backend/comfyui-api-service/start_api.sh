#!/bin/bash
cd ~/ComfyUI
source venv/bin/activate
export S3_BUCKET="${S3_BUCKET:-your-bucket-name}"
export AWS_REGION="${AWS_REGION:-us-east-1}"
python ~/comfyui_api_service/api_service.py
