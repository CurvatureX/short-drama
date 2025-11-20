import os
from dashscope import MultiModalConversation
from PIL import Image, ImageDraw
import json
import re

def detect_head_with_qwen(image_path, api_key):
    """
    使用 QWEN3-VL 模型检测图片中整个头部的位置（包括头发）
    """
    messages = [
        {
            "role": "user",
            "content": [
                {"image": f"file://{image_path}"},
                {
                    "text": "Detect the person's entire head (including all hair) in the image and return its bounding box coordinates in the format [x1, y1, x2, y2] where (x1,y1) is top-left and (x2,y2) is bottom-right. Make sure to include all the hair at the top and sides."
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
    print("QWEN3-VL 响应（检测整个头部）:")
    print(result_text)
    print("-" * 80)

    # 尝试从响应中提取坐标
    try:
        result = json.loads(result_text.strip().strip('`').strip('json').strip())

        # 如果直接返回坐标数组
        if isinstance(result, list) and len(result) == 4 and all(isinstance(x, int) for x in result):
            return {"normalized_bbox": result, "format": "direct_list"}

        # 如果返回对象数组
        if isinstance(result, list) and len(result) > 0 and isinstance(result[0], dict):
            if "bbox_2d" in result[0]:
                normalized_bbox = result[0]["bbox_2d"]
                return {"normalized_bbox": normalized_bbox, "format": "bbox_2d"}

        # 如果返回字典
        elif isinstance(result, dict):
            if "face_bbox" in result:
                normalized_bbox = result["face_bbox"]
                return {"normalized_bbox": normalized_bbox, "format": "face_bbox"}
            elif "head_bbox" in result:
                normalized_bbox = result["head_bbox"]
                return {"normalized_bbox": normalized_bbox, "format": "head_bbox"}

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
    """
    x1_norm, y1_norm, x2_norm, y2_norm = normalized_bbox

    x1 = int(x1_norm / norm_range * img_width)
    y1 = int(y1_norm / norm_range * img_height)
    x2 = int(x2_norm / norm_range * img_width)
    y2 = int(y2_norm / norm_range * img_height)

    return [x1, y1, x2, y2]

def expand_bbox_for_full_head(bbox, img_width, img_height, expand_ratio=0.3):
    """
    扩展边界框以确保覆盖整个头部（包括所有头发）

    参数:
        bbox: [x1, y1, x2, y2] 原始边界框
        img_width: 图片宽度
        img_height: 图片高度
        expand_ratio: 扩展比例（默认0.3，即扩大30%）
    """
    x1, y1, x2, y2 = bbox

    width = x2 - x1
    height = y2 - y1

    # 计算扩展量
    expand_x = int(width * expand_ratio)
    expand_y_top = int(height * expand_ratio * 1.5)  # 顶部多扩展一些（头发）
    expand_y_bottom = int(height * expand_ratio * 0.3)  # 底部少扩展

    # 应用扩展
    x1_new = max(0, x1 - expand_x)
    y1_new = max(0, y1 - expand_y_top)
    x2_new = min(img_width, x2 + expand_x)
    y2_new = min(img_height, y2 + expand_y_bottom)

    return [x1_new, y1_new, x2_new, y2_new]

def mask_head_in_image(image_path, detection_result, output_path):
    """
    在图片中用黑色遮住整个头部
    """
    # 打开图片
    img = Image.open(image_path)
    draw = ImageDraw.Draw(img)

    # 获取图片尺寸
    img_width, img_height = img.size
    print(f"图片尺寸: {img_width} x {img_height}")

    normalized_bbox = detection_result.get("normalized_bbox")
    if not normalized_bbox:
        print("错误: 没有检测到头部")
        return None

    print(f"QWEN 归一化坐标: {normalized_bbox}")

    # 转换为像素坐标
    pixel_bbox = convert_normalized_to_pixels(normalized_bbox, img_width, img_height)
    print(f"转换为像素坐标: {pixel_bbox}")

    # 扩展边界框以覆盖整个头部
    expanded_bbox = expand_bbox_for_full_head(pixel_bbox, img_width, img_height)
    print(f"扩展后（覆盖整个头部）: {expanded_bbox}")

    x1, y1, x2, y2 = expanded_bbox

    # 画黑色矩形遮住整个头部
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
    output_path = "/Users/jingweizhang/Workspace/short-drama/playground/qwen3-vl/output_full_head_masked.png"

    print("=" * 80)
    print("使用 QWEN3-VL 检测并遮住整个头部（包括头发）")
    print("=" * 80)

    # 检测头部
    detection_result = detect_head_with_qwen(image_path, api_key)

    # 遮住整个头部
    mask_head_in_image(image_path, detection_result, output_path)

    print("=" * 80)
    print("完成!")
    print("=" * 80)

if __name__ == "__main__":
    main()
