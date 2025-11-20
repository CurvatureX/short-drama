import os
import json
import uuid
import time
import asyncio
import websocket
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Dict, Any, Optional, List
import boto3
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn
import requests

# Configuration
COMFYUI_HOST = "127.0.0.1"
COMFYUI_PORT = 8188
WORKFLOW_PATH = "/home/ubuntu/ComfyUI/user/default/workflows/AIO.json"
S3_BUCKET = os.getenv("S3_BUCKET", "your-bucket-name")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Initialize S3 client
s3_client = boto3.client('s3', region_name=AWS_REGION)

# Initialize FastAPI
app = FastAPI(title="ComfyUI Qwen Edit API")

# In-memory job storage
jobs = {}

class QwenEditRequest(BaseModel):
    image_url: str  # Main input image (s3://bucket/key or https://example.com/image.jpg)
    prompt: str
    image2_url: Optional[str] = None  # Optional second image
    image3_url: Optional[str] = None  # Optional third image
    seed: Optional[int] = None
    steps: Optional[int] = 4
    cfg: Optional[float] = 1.0
    sampler_name: Optional[str] = "sa_solver"
    scheduler: Optional[str] = "beta"
    denoise: Optional[float] = 1.0

class JobStatus(BaseModel):
    job_id: str
    status: str  # pending, processing, completed, failed
    result_s3_uri: Optional[str] = None
    error: Optional[str] = None

def parse_s3_uri(s3_uri: str) -> tuple:
    """Parse S3 URI into bucket and key"""
    if not s3_uri.startswith('s3://'):
        raise ValueError("Invalid S3 URI format")
    parts = s3_uri[5:].split('/', 1)
    return parts[0], parts[1] if len(parts) > 1 else ''

def download_from_s3(s3_uri: str, local_path: str):
    """Download file from S3"""
    bucket, key = parse_s3_uri(s3_uri)
    s3_client.download_file(bucket, key, local_path)

def download_from_url(url: str, local_path: str):
    """Download file from HTTP(S) URL"""
    response = requests.get(url, stream=True, timeout=30)
    response.raise_for_status()
    with open(local_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

def download_image(image_url: str, local_path: str):
    """Download image from S3 or HTTP(S) URL"""
    if image_url.startswith('s3://'):
        download_from_s3(image_url, local_path)
    elif image_url.startswith(('http://', 'https://')):
        download_from_url(image_url, local_path)
    else:
        raise ValueError(f"Unsupported image URL format: {image_url}. Must start with s3://, http:// or https://")

def upload_to_s3(local_path: str, s3_key: str) -> str:
    """Upload file to S3 and return S3 URI"""
    s3_client.upload_file(local_path, S3_BUCKET, s3_key)
    return f"s3://{S3_BUCKET}/{s3_key}"

def queue_prompt(prompt_workflow: Dict, client_id: str) -> str:
    """Queue a prompt to ComfyUI"""
    p = {"prompt": prompt_workflow, "client_id": client_id}
    data = json.dumps(p).encode('utf-8')
    req = urllib.request.Request(f"http://{COMFYUI_HOST}:{COMFYUI_PORT}/prompt", data=data)
    response = urllib.request.urlopen(req)
    return json.loads(response.read())['prompt_id']

def get_image(filename: str, subfolder: str, folder_type: str) -> bytes:
    """Get image from ComfyUI"""
    data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    url_values = urllib.parse.urlencode(data)
    url = f"http://{COMFYUI_HOST}:{COMFYUI_PORT}/view?{url_values}"
    with urllib.request.urlopen(url) as response:
        return response.read()

def get_history(prompt_id: str) -> Dict:
    """Get execution history from ComfyUI"""
    with urllib.request.urlopen(f"http://{COMFYUI_HOST}:{COMFYUI_PORT}/history/{prompt_id}") as response:
        return json.loads(response.read())

def track_progress(prompt_id: str, client_id: str) -> Dict[str, Any]:
    """Track progress via WebSocket"""
    ws = websocket.WebSocket()
    ws.connect(f"ws://{COMFYUI_HOST}:{COMFYUI_PORT}/ws?clientId={client_id}")

    while True:
        try:
            out = ws.recv()
            if isinstance(out, str):
                message = json.loads(out)
                if message['type'] == 'executing':
                    data = message['data']
                    if data['node'] is None and data['prompt_id'] == prompt_id:
                        break  # Execution is done
        except Exception as e:
            print(f"WebSocket error: {e}")
            break

    ws.close()

    # Get the results
    history = get_history(prompt_id)[prompt_id]
    return history

async def process_qwen_edit(job_id: str, request: QwenEditRequest):
    """Background task to process Qwen image editing"""
    try:
        jobs[job_id]['status'] = 'processing'

        # Download input images
        comfyui_input_dir = "/home/ubuntu/ComfyUI/input"
        input_files = []

        # Main image (required)
        main_image_filename = f"{job_id}_image1.jpg"
        main_image_path = os.path.join(comfyui_input_dir, main_image_filename)
        download_image(request.image_url, main_image_path)
        input_files.append(main_image_path)

        # Optional image 2
        image2_filename = None
        if request.image2_url:
            image2_filename = f"{job_id}_image2.jpg"
            image2_path = os.path.join(comfyui_input_dir, image2_filename)
            download_image(request.image2_url, image2_path)
            input_files.append(image2_path)

        # Optional image 3
        image3_filename = None
        if request.image3_url:
            image3_filename = f"{job_id}_image3.jpg"
            image3_path = os.path.join(comfyui_input_dir, image3_filename)
            download_image(request.image3_url, image3_path)
            input_files.append(image3_path)

        # Load workflow
        with open(WORKFLOW_PATH, 'r') as f:
            workflow = json.load(f)

        # Update workflow with parameters
        for node in workflow['nodes']:
            # Node 10: Main input image (required)
            if node['type'] == 'LoadImage' and node['id'] == 10:
                node['widgets_values'][0] = main_image_filename
                node['mode'] = 0  # Enable node

            # Node 8: Optional image 2
            if node['type'] == 'LoadImage' and node['id'] == 8:
                if image2_filename:
                    node['widgets_values'][0] = image2_filename
                    node['mode'] = 0  # Enable node
                else:
                    node['mode'] = 4  # Disable node

            # Node 11: Optional image 3
            if node['type'] == 'LoadImage' and node['id'] == 11:
                if image3_filename:
                    node['widgets_values'][0] = image3_filename
                    node['mode'] = 0  # Enable node
                else:
                    node['mode'] = 4  # Disable node

            # Node 3: Input prompt (TextEncodeQwenImageEditPlus)
            if node['type'] == 'TextEncodeQwenImageEditPlus' and node['id'] == 3:
                node['widgets_values'][0] = request.prompt

            # Node 2: KSampler parameters
            if node['type'] == 'KSampler' and node['id'] == 2:
                # widgets_values: [seed, control_after_generate, steps, cfg, sampler_name, scheduler, denoise]
                if request.seed is not None:
                    node['widgets_values'][0] = request.seed
                    node['widgets_values'][1] = "fixed"
                if request.steps is not None:
                    node['widgets_values'][2] = request.steps
                if request.cfg is not None:
                    node['widgets_values'][3] = request.cfg
                if request.sampler_name is not None:
                    node['widgets_values'][4] = request.sampler_name
                if request.scheduler is not None:
                    node['widgets_values'][5] = request.scheduler
                if request.denoise is not None:
                    node['widgets_values'][6] = request.denoise

        # Generate client ID and queue prompt
        client_id = str(uuid.uuid4())
        prompt_id = queue_prompt(workflow, client_id)

        # Track progress
        history = track_progress(prompt_id, client_id)

        # Get output images
        outputs = history['outputs']
        output_images = []

        for node_id, node_output in outputs.items():
            if 'images' in node_output:
                for image in node_output['images']:
                    image_data = get_image(image['filename'], image['subfolder'], image['type'])
                    output_path = f"/tmp/{job_id}_output_{len(output_images)}.png"
                    with open(output_path, 'wb') as f:
                        f.write(image_data)
                    output_images.append(output_path)

        # Upload results to S3
        if output_images:
            s3_key = f"comfyui-results/{job_id}/output.png"
            result_s3_uri = upload_to_s3(output_images[0], s3_key)

            jobs[job_id]['status'] = 'completed'
            jobs[job_id]['result_s3_uri'] = result_s3_uri
        else:
            jobs[job_id]['status'] = 'failed'
            jobs[job_id]['error'] = 'No output images generated'

        # Cleanup
        for img_path in output_images:
            if os.path.exists(img_path):
                os.remove(img_path)
        for img_path in input_files:
            if os.path.exists(img_path):
                os.remove(img_path)

    except Exception as e:
        jobs[job_id]['status'] = 'failed'
        jobs[job_id]['error'] = str(e)
        print(f"Error processing job {job_id}: {e}")

@app.post("/qwen-edit/edit", response_model=JobStatus)
async def create_qwen_edit(request: QwenEditRequest, background_tasks: BackgroundTasks):
    """Submit a Qwen image editing job"""
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        'status': 'pending',
        'created_at': time.time()
    }

    background_tasks.add_task(process_qwen_edit, job_id, request)

    return JobStatus(job_id=job_id, status='pending')

@app.get("/qwen-edit/status/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """Get status of a job"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    return JobStatus(
        job_id=job_id,
        status=job['status'],
        result_s3_uri=job.get('result_s3_uri'),
        error=job.get('error')
    )

@app.get("/qwen-edit/health")
async def health_check():
    """Health check endpoint"""
    try:
        response = requests.get(f"http://{COMFYUI_HOST}:{COMFYUI_PORT}/system_stats", timeout=5)
        comfyui_status = "healthy" if response.status_code == 200 else "unhealthy"
    except:
        comfyui_status = "unhealthy"

    return {
        "status": "healthy",
        "comfyui_status": comfyui_status
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
