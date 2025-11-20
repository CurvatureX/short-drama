import os
from dashscope import MultiModalConversation
from PIL import Image, ImageDraw
import json
import re

def detect_face_with_qwen(image_path, api_key):
    """
    使用 QWEN3-VL 模型检测图片中的人脸位置

    重要发现：QWEN3-VL 返回的是归一化坐标（0-1000范围），需要转换为像素坐标
    """
    messages = [
        {
            "role": "user",
            "content": [
                {"image": f"file://{image_path}"},
                {
                    "text": "Detect the person's face in the image and return its bounding box coordinates in the format [x1, y1, x2, y2] where (x1,y1) is top-left and (x2,y2) is bottom-right."
                }
            ]
        }
    ]

    response = MultiModalConversation.call(
        api_key=api_key,
        model="qwen3-vl-plus",
        messages=messages,
    )

    result_text = response.output.choices[0].message.content[0]["text"]
    print("QWEN3-VL 响应:")
    print(result_text)
    print("-" * 80)

    # 尝试从响应中提取坐标
    # 格式可能是: [{"bbox_2d": [x1, y1, x2, y2], "label": "person's face"}]
    try:
        # 尝试解析 JSON
        result = json.loads(result_text.strip().strip('`').strip('json').strip())

        if isinstance(result, list) and len(result) > 0:
            # 格式 1: [{"bbox_2d": [...], ...}]
            if "bbox_2d" in result[0]:
                normalized_bbox = result[0]["bbox_2d"]
                return {"normalized_bbox": normalized_bbox, "format": "bbox_2d"}
        elif isinstance(result, dict):
            # 格式 2: {"face_bbox": [...]}
            if "face_bbox" in result:
                normalized_bbox = result["face_bbox"]
                return {"normalized_bbox": normalized_bbox, "format": "face_bbox"}

    except json.JSONDecodeError:
        pass

    # 尝试提取 <box>[[...]]</box> 格式
    box_match = re.search(r'<box>\[\[([^\]]+)\]\]</box>', result_text)
    if box_match:
        coords_str = box_match.group(1)
        coords = [int(x.strip()) for x in coords_str.split(',')]
        return {"normalized_bbox": coords, "format": "box_tag"}

    # 尝试直接提取数字数组
    array_match = re.search(r'\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]', result_text)
    if array_match:
        coords = [int(array_match.group(i)) for i in range(1, 5)]
        return {"normalized_bbox": coords, "format": "direct_array"}

    print("警告: 无法解析 QWEN 响应")
    return {"normalized_bbox": None, "raw_response": result_text}

def convert_normalized_to_pixels(normalized_bbox, img_width, img_height, norm_range=1000):
    """
    将 QWEN 的归一化坐标（0-1000）转换为实际像素坐标

    参数:
        normalized_bbox: [x1, y1, x2, y2] 归一化坐标（0-1000范围）
        img_width: 图片宽度（像素）
        img_height: 图片高度（像素）
        norm_range: 归一化范围（默认1000）

    返回:
        [x1, y1, x2, y2] 像素坐标
    """
    x1_norm, y1_norm, x2_norm, y2_norm = normalized_bbox

    x1 = int(x1_norm / norm_range * img_width)
    y1 = int(y1_norm / norm_range * img_height)
    x2 = int(x2_norm / norm_range * img_width)
    y2 = int(y2_norm / norm_range * img_height)

    return [x1, y1, x2, y2]

def mask_faces_in_image(image_path, detection_result, output_path):
    """
    在图片中用黑色遮住检测到的人脸
    """
    # 打开图片
    img = Image.open(image_path)
    draw = ImageDraw.Draw(img)

    # 获取图片尺寸
    img_width, img_height = img.size
    print(f"图片尺寸: {img_width} x {img_height}")

    normalized_bbox = detection_result.get("normalized_bbox")
    if not normalized_bbox:
        print("错误: 没有检测到人脸")
        return None

    print(f"QWEN 归一化坐标: {normalized_bbox}")

    # 转换为像素坐标
    pixel_bbox = convert_normalized_to_pixels(normalized_bbox, img_width, img_height)
    print(f"转换为像素坐标: {pixel_bbox}")

    x1, y1, x2, y2 = pixel_bbox

    # 可选：扩大一点边距
    padding = 20
    x1 = max(0, x1 - padding)
    y1 = max(0, y1 - padding)
    x2 = min(img_width, x2 + padding)
    y2 = min(img_height, y2 + padding)

    print(f"加上边距后: ({x1}, {y1}, {x2}, {y2})")

    # 画黑色矩形遮住人脸
    draw.rectangle([x1, y1, x2, y2], fill="black")

    # 保存结果
    img.save(output_path)
    print(f"\n已保存遮罩后的图片到: {output_path}")
    return output_path

def main():
    # 配置
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError("请设置环境变量 DASHSCOPE_API_KEY")

    # 输入图片路径
    image_path = "/Users/jingweizhang/Workspace/short-drama/playground/qwen3-vl/jimeng-2025-11-15-5498-一名28岁的东亚男性的全身人像，端正站好。  发型是稍微有点凌乱的中短发，略微蓬....png"

    # 输出图片路径
    output_path = "/Users/jingweizhang/Workspace/short-drama/playground/qwen3-vl/output_qwen_fixed.png"

    print("=" * 80)
    print("使用 QWEN3-VL 检测人脸（修正版 - 坐标转换）")
    print("=" * 80)

    # 检测人脸
    detection_result = detect_face_with_qwen(image_path, api_key)

    # 遮住人脸
    mask_faces_in_image(image_path, detection_result, output_path)

    print("=" * 80)
    print("完成!")
    print("=" * 80)
    print("\n关键发现:")
    print("  QWEN3-VL 返回的是归一化坐标（0-1000范围）")
    print("  需要使用公式转换: pixel = (normalized / 1000) * image_dimension")

if __name__ == "__main__":
    main()
