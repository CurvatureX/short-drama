# 使用前安装：pip install opencv-python
import math
import os
import logging
import cv2

logger = logging.getLogger(__name__)

FRAME_FACTOR = 2
# 对于Qwen3-VL、qwen-vl-max-0813以后及qwen-vl-plus-0710，IMAGE_FACTOR为32
# 对于其他模型，IMAGE_FACTOR为28
IMAGE_FACTOR = 32
# 视频帧的长宽比
MAX_RATIO = 200

# 视频帧的 Token 下限
VIDEO_MIN_PIXELS = 128 * 32 * 32
# 视频帧的 Token 上限
VIDEO_MAX_PIXELS = 768 * 32 * 32

# 用户未传入FPS参数，则fps使用默认值
FPS = 2.0
# 最少抽取帧数
FPS_MIN_FRAMES = 4
# 最大抽取帧数，使用Qwen3-VL和Qwen2.5-vl模型时，请FPS_MAX_FRAMES将设置为512，其他模型则设置为80
FPS_MAX_FRAMES = 512

# 视频输入的最大像素值，
# 使用Qwen3-VL和Qwen2.5-vl模型时，请将VIDEO_TOTAL_PIXELS设置为65536 * 32 * 32  和 65536 * 28 * 28，其他模型则设置为24576 * 28 * 28
VIDEO_TOTAL_PIXELS = int(float(os.environ.get("VIDEO_MAX_PIXELS", 65536 * 28 * 28)))


def round_by_factor(number: int, factor: int) -> int:
    """返回与”number“最接近的整数，该整数可被”factor“整除。"""
    return round(number / factor) * factor


def ceil_by_factor(number: int, factor: int) -> int:
    """返回大于或等于“number”且可被“factor”整除的最小整数。"""
    return math.ceil(number / factor) * factor


def floor_by_factor(number: int, factor: int) -> int:
    """返回小于或等于“number”且可被“factor”整除的最大整数。"""
    return math.floor(number / factor) * factor


def smart_nframes(ele, total_frames, video_fps):
    """用于计算抽取的视频帧数。

    Args:
        ele (dict): 包含视频配置的字典格式
            - fps: fps用于控制提取模型输入帧的数量。
        total_frames (int): 视频的原始总帧数。
        video_fps (int | float): 视频的原始帧率

    Raises:
        nframes应该在[FRAME_FACTOR，total_frames]间隔内，否则会报错

    Returns:
        用于模型输入的视频帧数。
    """
    assert not (
        "fps" in ele and "nframes" in ele
    ), "Only accept either `fps` or `nframes`"
    fps = ele.get("fps", FPS)
    min_frames = ceil_by_factor(ele.get("min_frames", FPS_MIN_FRAMES), FRAME_FACTOR)
    max_frames = floor_by_factor(
        ele.get("max_frames", min(FPS_MAX_FRAMES, total_frames)), FRAME_FACTOR
    )
    duration = total_frames / video_fps if video_fps != 0 else 0
    if duration - int(duration) > (1 / fps):
        total_frames = math.ceil(duration * video_fps)
    else:
        total_frames = math.ceil(int(duration) * video_fps)
    nframes = total_frames / video_fps * fps
    if nframes > total_frames:
        logger.warning(
            f"smart_nframes: nframes[{nframes}] > total_frames[{total_frames}]"
        )
    nframes = int(min(min(max(nframes, min_frames), max_frames), total_frames))
    if not (FRAME_FACTOR <= nframes and nframes <= total_frames):
        raise ValueError(
            f"nframes should in interval [{FRAME_FACTOR}, {total_frames}], but got {nframes}."
        )

    return nframes


def get_video(video_path):
    # 获取视频信息
    cap = cv2.VideoCapture(video_path)

    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    # 获取视频高度
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    video_fps = cap.get(cv2.CAP_PROP_FPS)
    return frame_height, frame_width, total_frames, video_fps


def smart_resize(ele, path, factor=IMAGE_FACTOR):
    # 获取原视频的宽和高
    height, width, total_frames, video_fps = get_video(path)
    # 视频帧的Token下限
    min_pixels = VIDEO_MIN_PIXELS
    total_pixels = VIDEO_TOTAL_PIXELS
    # 抽取的视频帧数
    nframes = smart_nframes(ele, total_frames, video_fps)
    max_pixels = max(
        min(VIDEO_MAX_PIXELS, total_pixels / nframes * FRAME_FACTOR),
        int(min_pixels * 1.05),
    )

    # 视频的长宽比不应超过200:1或1:200
    if max(height, width) / min(height, width) > MAX_RATIO:
        raise ValueError(
            f"absolute aspect ratio must be smaller than {MAX_RATIO}, got {max(height, width) / min(height, width)}"
        )

    h_bar = max(factor, round_by_factor(height, factor))
    w_bar = max(factor, round_by_factor(width, factor))
    if h_bar * w_bar > max_pixels:
        beta = math.sqrt((height * width) / max_pixels)
        h_bar = floor_by_factor(height / beta, factor)
        w_bar = floor_by_factor(width / beta, factor)
    elif h_bar * w_bar < min_pixels:
        beta = math.sqrt(min_pixels / (height * width))
        h_bar = ceil_by_factor(height * beta, factor)
        w_bar = ceil_by_factor(width * beta, factor)
    return h_bar, w_bar


def token_calculate(video_path, fps):
    # 传入视频路径和fps抽帧参数
    messages = [{"content": [{"video": video_path, "fps": fps}]}]
    vision_infos = extract_vision_info(messages)[0]

    resized_height, resized_width = smart_resize(vision_infos, video_path)

    height, width, total_frames, video_fps = get_video(video_path)
    num_frames = smart_nframes(vision_infos, total_frames, video_fps)
    print(
        f"原视频尺寸：{height}*{width}，输入模型的尺寸：{resized_height}*{resized_width}，视频总帧数:{total_frames}，fps等于{fps}时，抽取的总帧数：{num_frames}",
        end="，",
    )
    video_token = int(
        math.ceil(num_frames / 2) * resized_height / 28 * resized_width / 28
    )
    video_token += (
        2  # 系统会自动添加<|vision_bos|>和<|vision_eos|>视觉标记（各计1个Token）
    )
    return video_token


def extract_vision_info(conversations):
    vision_infos = []
    if isinstance(conversations[0], dict):
        conversations = [conversations]
    for conversation in conversations:
        for message in conversation:
            if isinstance(message["content"], list):
                for ele in message["content"]:
                    if (
                        "image" in ele
                        or "image_url" in ele
                        or "video" in ele
                        or ele.get("type", "") in ("image", "image_url", "video")
                    ):
                        vision_infos.append(ele)
    return vision_infos


video_token = token_calculate(
    "/Users/jingweizhang/Workspace/short-drama/playground/test1.mp4", 1
)
print("视频tokens:", video_token)
