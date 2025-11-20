import os
import json
import uuid
import time
import asyncio
import websocket
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Dict, Any, Optional, List, Literal
import boto3
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn
import requests

# Configuration
COMFYUI_HOST = "127.0.0.1"
COMFYUI_PORT = 8188
WORKFLOW_DIR = "/home/ubuntu/ComfyUI/user/default/workflows"
S3_BUCKET = os.getenv("S3_BUCKET", "short-drama-assets")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
CLOUDFRONT_DOMAIN = os.getenv("CLOUDFRONT_DOMAIN", "https://d3bg7alr1qwred.cloudfront.net")

# Initialize S3 client
s3_client = boto3.client("s3", region_name=AWS_REGION)

# Initialize FastAPI
app = FastAPI(
    title="ComfyUI Unified API",
    description="Unified API for ComfyUI workflows - Camera Angle & Qwen Image Edit",
    version="1.0.0",
)

# In-memory job storage
jobs = {}

# ==================== Models ====================


class CameraAngleRequest(BaseModel):
    image_url: str
    prompt: Optional[str] = None
    vertical: Literal[-2, -1, 0, 1, 2] = 0
    horizontal: Literal[-2, -1, 0, 1, 2] = 0
    zoom: Literal[-1, 0, 1] = 0
    seed: Optional[int] = None
    steps: Optional[int] = 8


class ImageEditRequest(BaseModel):
    image_url: str
    prompt: str
    image2_url: Optional[str] = None
    image3_url: Optional[str] = None
    seed: Optional[int] = None
    steps: Optional[int] = 4
    cfg: Optional[float] = 1.0
    sampler_name: Optional[str] = "sa_solver"
    scheduler: Optional[str] = "beta"
    denoise: Optional[float] = 1.0


class JobStatus(BaseModel):
    job_id: str
    status: str
    result_s3_uri: Optional[str] = None
    error: Optional[str] = None


# ==================== Utility Functions ====================


def parse_s3_uri(s3_uri: str) -> tuple:
    """Parse S3 URI into bucket and key"""
    if not s3_uri.startswith("s3://"):
        raise ValueError("Invalid S3 URI format")
    parts = s3_uri[5:].split("/", 1)
    return parts[0], parts[1] if len(parts) > 1 else ""


def download_from_s3(s3_uri: str, local_path: str):
    """Download file from S3"""
    bucket, key = parse_s3_uri(s3_uri)
    s3_client.download_file(bucket, key, local_path)


def download_from_url(url: str, local_path: str):
    """Download file from HTTP(S) URL"""
    response = requests.get(url, stream=True, timeout=30)
    response.raise_for_status()
    with open(local_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)


def download_image(image_url: str, local_path: str):
    """Download image from S3 or HTTP(S) URL"""
    if image_url.startswith("s3://"):
        download_from_s3(image_url, local_path)
    elif image_url.startswith(("http://", "https://")):
        download_from_url(image_url, local_path)
    else:
        raise ValueError(
            f"Unsupported image URL format: {image_url}. Must start with s3://, http:// or https://"
        )


def upload_to_s3(local_path: str, s3_key: str) -> str:
    """Upload file to S3 and return CloudFront URL"""
    s3_client.upload_file(local_path, S3_BUCKET, s3_key)
    # Return CloudFront URL instead of S3 URI for frontend access
    return f"{CLOUDFRONT_DOMAIN}/{s3_key}"


def queue_prompt(prompt_workflow: Dict, client_id: str) -> str:
    """Queue a prompt to ComfyUI"""
    p = {"prompt": prompt_workflow, "client_id": client_id}
    data = json.dumps(p).encode("utf-8")
    req = urllib.request.Request(
        f"http://{COMFYUI_HOST}:{COMFYUI_PORT}/prompt", data=data
    )
    response = urllib.request.urlopen(req)
    return json.loads(response.read())["prompt_id"]


def get_image(filename: str, subfolder: str, folder_type: str) -> bytes:
    """Get image from ComfyUI"""
    data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    url_values = urllib.parse.urlencode(data)
    url = f"http://{COMFYUI_HOST}:{COMFYUI_PORT}/view?{url_values}"
    with urllib.request.urlopen(url) as response:
        return response.read()


def get_history(prompt_id: str) -> Dict:
    """Get execution history from ComfyUI"""
    with urllib.request.urlopen(
        f"http://{COMFYUI_HOST}:{COMFYUI_PORT}/history/{prompt_id}"
    ) as response:
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
                if message["type"] == "executing":
                    data = message["data"]
                    if data["node"] is None and data["prompt_id"] == prompt_id:
                        break
        except Exception as e:
            print(f"WebSocket error: {e}")
            break

    ws.close()
    history = get_history(prompt_id)[prompt_id]
    return history


# ==================== Processing Functions ====================


async def process_camera_angle(job_id: str, request: CameraAngleRequest):
    """Background task to process camera angle transformation"""
    try:
        jobs[job_id]["status"] = "processing"

        # Download input image
        input_image_path = f"/tmp/{job_id}_input.jpg"
        download_image(request.image_url, input_image_path)

        # Copy to ComfyUI input directory
        comfyui_input_dir = "/home/ubuntu/ComfyUI/input"
        comfyui_input_filename = f"{job_id}_input.jpg"
        comfyui_input_path = os.path.join(comfyui_input_dir, comfyui_input_filename)
        os.system(f"cp {input_image_path} {comfyui_input_path}")

        # Load workflow (API format)
        workflow_path = os.path.join(WORKFLOW_DIR, "camera-angle-api.json")
        with open(workflow_path, "r") as f:
            workflow = json.load(f)

        # Generate prompt from parameters if not provided
        if request.prompt:
            final_prompt = request.prompt
        else:
            # Build prompt from vertical, horizontal, zoom parameters
            prompt_parts = []
            if request.vertical != 0:
                if request.vertical == -2:
                    prompt_parts.append(
                        "Use an extreme low-angle view shot from far below the subject, looking sharply upward. The camera is placed near ground level, creating a dramatic towering effect above the viewer."
                    )
                elif request.vertical == -1:
                    prompt_parts.append(
                        "把相机视角稍微降低 Use a subtle low-angle shot with the camera slightly below eye level"
                    )
                elif request.vertical == 1:
                    prompt_parts.append(
                        "把相机视角稍微提高 Use a slightly elevated high-angle view."
                    )
                elif request.vertical == 2:
                    prompt_parts.append(
                        "将相机转向俯拍鸟瞰视角，完全俯视图 Turn the camera to a bird's-eye view. "
                    )
            if request.horizontal != 0:
                if request.horizontal == -2:
                    prompt_parts.append("将镜头向左旋转45度")
                elif request.horizontal == -1:
                    prompt_parts.append("将镜头向左旋转90度")
                elif request.horizontal == 1:
                    prompt_parts.append("将镜头向右旋转45度")
                elif request.horizontal == 2:
                    prompt_parts.append("将镜头向右旋转90度")
            if request.zoom != 0:
                direction = (
                    "将镜头向前移动 Move the camera forward."
                    if request.zoom > 0
                    else "将镜头拉远 Pull the camera away from the object for a distance, and expose more surrounding area."
                )
                prompt_parts.append(f"镜头{direction}")
            final_prompt = "，and".join(prompt_parts) if prompt_parts else "保持原样"

        # Update workflow parameters (API format)
        # Update LoadImage node 31
        if "31" in workflow:
            workflow["31"]["inputs"]["image"] = comfyui_input_filename

        # Update TextEncodeQwenImageEditPlus node 11 (positive prompt)
        if "11" in workflow:
            workflow["11"]["inputs"]["prompt"] = final_prompt

        # Update KSampler node 14
        if "14" in workflow:
            if request.seed is not None:
                workflow["14"]["inputs"]["seed"] = request.seed
            if request.steps is not None:
                workflow["14"]["inputs"]["steps"] = request.steps

        # Execute workflow
        client_id = str(uuid.uuid4())
        prompt_id = queue_prompt(workflow, client_id)
        history = track_progress(prompt_id, client_id)

        # Get output images
        outputs = history["outputs"]
        output_images = []

        for node_id, node_output in outputs.items():
            if "images" in node_output:
                for image in node_output["images"]:
                    image_data = get_image(
                        image["filename"], image["subfolder"], image["type"]
                    )
                    output_path = f"/tmp/{job_id}_output_{len(output_images)}.png"
                    with open(output_path, "wb") as f:
                        f.write(image_data)
                    output_images.append(output_path)

        # Upload to S3
        if output_images:
            s3_key = f"comfyui-results/camera-angle/{job_id}/output.png"
            result_s3_uri = upload_to_s3(output_images[0], s3_key)
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["result_s3_uri"] = result_s3_uri
        else:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = "No output images generated"

        # Cleanup
        for img_path in output_images:
            if os.path.exists(img_path):
                os.remove(img_path)
        if os.path.exists(input_image_path):
            os.remove(input_image_path)
        if os.path.exists(comfyui_input_path):
            os.remove(comfyui_input_path)

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)
        print(f"Error processing camera angle job {job_id}: {e}")


async def process_image_edit(job_id: str, request: ImageEditRequest):
    """Background task to process image editing"""
    try:
        jobs[job_id]["status"] = "processing"

        # Download input images
        comfyui_input_dir = "/home/ubuntu/ComfyUI/input"
        input_files = []

        # Main image (required)
        main_image_filename = f"{job_id}_image1.jpg"
        main_image_path = os.path.join(comfyui_input_dir, main_image_filename)
        download_image(request.image_url, main_image_path)
        input_files.append(main_image_path)

        # Optional images
        image2_filename = None
        if request.image2_url:
            image2_filename = f"{job_id}_image2.jpg"
            image2_path = os.path.join(comfyui_input_dir, image2_filename)
            download_image(request.image2_url, image2_path)
            input_files.append(image2_path)

        image3_filename = None
        if request.image3_url:
            image3_filename = f"{job_id}_image3.jpg"
            image3_path = os.path.join(comfyui_input_dir, image3_filename)
            download_image(request.image3_url, image3_path)
            input_files.append(image3_path)

        # Load workflow (API format)
        workflow_path = os.path.join(WORKFLOW_DIR, "qwen-image-edit-api.json")
        with open(workflow_path, "r") as f:
            workflow = json.load(f)

        # Update workflow parameters (API format uses node IDs as keys)
        # Update LoadImage node 10 (main image)
        if "10" in workflow:
            workflow["10"]["inputs"]["image"] = main_image_filename

        # Update LoadImage node 8 (image2 - optional)
        if "8" in workflow:
            if image2_filename:
                workflow["8"]["inputs"]["image"] = image2_filename
            else:
                # Remove node 8 from workflow if no image2
                del workflow["8"]
                # Update node 3 to not reference node 8
                if "3" in workflow and "image2" in workflow["3"]["inputs"]:
                    workflow["3"]["inputs"]["image2"] = [
                        "10",
                        0,
                    ]  # Use main image as fallback

        # Update LoadImage node 11 (image3 - optional)
        if "11" in workflow:
            if image3_filename:
                workflow["11"]["inputs"]["image"] = image3_filename
            else:
                # Remove node 11 from workflow if no image3
                del workflow["11"]
                # Update node 3 to not reference node 11
                if "3" in workflow and "image3" in workflow["3"]["inputs"]:
                    workflow["3"]["inputs"]["image3"] = [
                        "10",
                        0,
                    ]  # Use main image as fallback

        # Update TextEncodeQwenImageEditPlus node 3 (positive prompt)
        if "3" in workflow:
            workflow["3"]["inputs"]["prompt"] = request.prompt

        # Update KSampler node 2
        if "2" in workflow:
            if request.seed is not None:
                workflow["2"]["inputs"]["seed"] = request.seed
            if request.steps is not None:
                workflow["2"]["inputs"]["steps"] = request.steps
            if request.cfg is not None:
                workflow["2"]["inputs"]["cfg"] = request.cfg
            if request.sampler_name is not None:
                workflow["2"]["inputs"]["sampler_name"] = request.sampler_name
            if request.scheduler is not None:
                workflow["2"]["inputs"]["scheduler"] = request.scheduler
            if request.denoise is not None:
                workflow["2"]["inputs"]["denoise"] = request.denoise

        # Execute workflow
        client_id = str(uuid.uuid4())
        prompt_id = queue_prompt(workflow, client_id)
        history = track_progress(prompt_id, client_id)

        # Get output images
        outputs = history["outputs"]
        output_images = []

        for node_id, node_output in outputs.items():
            if "images" in node_output:
                for image in node_output["images"]:
                    image_data = get_image(
                        image["filename"], image["subfolder"], image["type"]
                    )
                    output_path = f"/tmp/{job_id}_output_{len(output_images)}.png"
                    with open(output_path, "wb") as f:
                        f.write(image_data)
                    output_images.append(output_path)

        # Upload to S3
        if output_images:
            s3_key = f"comfyui-results/qwen-image-edit/{job_id}/output.png"
            result_s3_uri = upload_to_s3(output_images[0], s3_key)
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["result_s3_uri"] = result_s3_uri
        else:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = "No output images generated"

        # Cleanup
        for img_path in output_images:
            if os.path.exists(img_path):
                os.remove(img_path)
        for img_path in input_files:
            if os.path.exists(img_path):
                os.remove(img_path)

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)
        print(f"Error processing image edit job {job_id}: {e}")


# ==================== API Endpoints ====================


# Root endpoint
@app.get("/")
async def root():
    """API root with service info"""
    return {
        "service": "ComfyUI Unified API",
        "version": "1.0.0",
        "endpoints": {
            "camera_angle": "/api/v1/camera-angle",
            "qwen_image_edit": "/api/v1/qwen-image-edit",
            "health": "/health",
        },
    }


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        response = requests.get(
            f"http://{COMFYUI_HOST}:{COMFYUI_PORT}/system_stats", timeout=5
        )
        comfyui_status = "healthy" if response.status_code == 200 else "unhealthy"
    except:
        comfyui_status = "unhealthy"

    return {"status": "healthy", "comfyui_status": comfyui_status}


# ==================== Camera Angle API ====================


@app.post("/api/v1/camera-angle/jobs", response_model=JobStatus)
async def create_camera_angle_job(
    request: CameraAngleRequest, background_tasks: BackgroundTasks
):
    """Submit a camera angle transformation job"""
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "pending",
        "type": "camera-angle",
        "created_at": time.time(),
    }
    background_tasks.add_task(process_camera_angle, job_id, request)
    return JobStatus(job_id=job_id, status="pending")


@app.get("/api/v1/camera-angle/jobs/{job_id}", response_model=JobStatus)
async def get_camera_angle_job(job_id: str):
    """Get camera angle job status"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]
    return JobStatus(
        job_id=job_id,
        status=job["status"],
        result_s3_uri=job.get("result_s3_uri"),
        error=job.get("error"),
    )


# ==================== Qwen Image Edit API ====================


@app.post("/api/v1/qwen-image-edit/jobs", response_model=JobStatus)
async def create_qwen_image_edit_job(
    request: ImageEditRequest, background_tasks: BackgroundTasks
):
    """Submit a Qwen image editing job"""
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "pending",
        "type": "qwen-image-edit",
        "created_at": time.time(),
    }
    background_tasks.add_task(process_image_edit, job_id, request)
    return JobStatus(job_id=job_id, status="pending")


@app.get("/api/v1/qwen-image-edit/jobs/{job_id}", response_model=JobStatus)
async def get_qwen_image_edit_job(job_id: str):
    """Get Qwen image edit job status"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]
    return JobStatus(
        job_id=job_id,
        status=job["status"],
        result_s3_uri=job.get("result_s3_uri"),
        error=job.get("error"),
    )


# ==================== Unified Job Status ====================


@app.get("/api/v1/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """Get status of any job (camera-angle or image-edit)"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]
    return JobStatus(
        job_id=job_id,
        status=job["status"],
        result_s3_uri=job.get("result_s3_uri"),
        error=job.get("error"),
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
