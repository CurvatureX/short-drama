import os
from dashscope import MultiModalConversation
from PIL import Image, ImageDraw
import json
import re
import numpy as np

def detect_head_segmentation_with_qwen(image_path, api_key):
    """
    使用 QWEN3-VL 进行头部分割检测
    """
    messages = [
        {
            "role": "user",
            "content": [
                {"image": f"file://{image_path}"},
                {
                    "text": """Detect and segment the person's head (including hair) in this image.
Return the segmentation mask or polygon points that outline the head region.
If you can provide polygon points, return them in this format:
{
  "head_polygon": [[x1, y1], [x2, y2], ...],
  "type": "polygon"
}

If you can only provide a bounding box, return:
{
  "head_bbox": [x1, y1, x2, y2],
  "type": "bbox"
}"""
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
    print("QWEN3-VL 分割响应:")
    print(result_text)
    print("-" * 80)

    return {"raw_response": result_text}

def detect_head_bbox_with_qwen(image_path, api_key):
    """
    使用 QWEN3-VL 检测头部边界框（更精确的提示）
    """
    messages = [
        {
            "role": "user",
            "content": [
                {"image": f"file://{image_path}"},
                {
                    "text": """Detect the person's head region (face + hair, but keep it tight) in the image.
Return the bounding box in format [x1, y1, x2, y2].
Make the box as tight as possible while still covering the entire head including hair."""
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
    print("QWEN3-VL 头部检测响应:")
    print(result_text)
    print("-" * 80)

    # 提取坐标
    try:
        result = json.loads(result_text.strip().strip('`').strip('json').strip())
        if isinstance(result, list) and len(result) == 4:
            return {"normalized_bbox": result}
    except:
        pass

    # 尝试直接提取数字数组
    array_match = re.search(r'\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]', result_text)
    if array_match:
        coords = [int(array_match.group(i)) for i in range(1, 5)]
        return {"normalized_bbox": coords}

    return {"normalized_bbox": None, "raw_response": result_text}

def convert_normalized_to_pixels(normalized_bbox, img_width, img_height, norm_range=1000):
    """将归一化坐标转换为像素坐标"""
    x1_norm, y1_norm, x2_norm, y2_norm = normalized_bbox

    x1 = int(x1_norm / norm_range * img_width)
    y1 = int(y1_norm / norm_range * img_height)
    x2 = int(x2_norm / norm_range * img_width)
    y2 = int(y2_norm / norm_range * img_height)

    return [x1, y1, x2, y2]

def create_elliptical_mask(bbox, img_width, img_height, expand_top=1.2, expand_sides=1.1, expand_bottom=1.0):
    """
    创建椭圆形遮罩，更自然地覆盖头部

    参数:
        bbox: [x1, y1, x2, y2]
        expand_top: 顶部扩展系数（覆盖头发）
        expand_sides: 左右扩展系数
        expand_bottom: 底部扩展系数
    """
    x1, y1, x2, y2 = bbox

    # 计算中心点
    center_x = (x1 + x2) / 2
    center_y = (y1 + y2) / 2

    # 计算宽度和高度
    width = x2 - x1
    height = y2 - y1

    # 扩展椭圆尺寸
    ellipse_width = width * expand_sides / 2
    ellipse_height_top = (center_y - y1) * expand_top
    ellipse_height_bottom = (y2 - center_y) * expand_bottom

    # 总高度
    ellipse_height = ellipse_height_top + ellipse_height_bottom

    # 调整中心点（因为顶部扩展更多）
    adjusted_center_y = y1 + ellipse_height_top

    # 椭圆边界框
    ellipse_bbox = [
        center_x - ellipse_width,
        adjusted_center_y - ellipse_height / 2,
        center_x + ellipse_width,
        adjusted_center_y + ellipse_height / 2
    ]

    return ellipse_bbox

def create_rounded_rect_mask(bbox, img_width, img_height, expand_ratio=0.15):
    """
    创建圆角矩形遮罩

    参数:
        bbox: [x1, y1, x2, y2]
        expand_ratio: 扩展比例
    """
    x1, y1, x2, y2 = bbox

    width = x2 - x1
    height = y2 - y1

    # 扩展（顶部多一些，底部少一些）
    expand_x = int(width * expand_ratio)
    expand_y_top = int(height * expand_ratio * 1.3)
    expand_y_bottom = int(height * expand_ratio * 0.5)

    x1_new = max(0, x1 - expand_x)
    y1_new = max(0, y1 - expand_y_top)
    x2_new = min(img_width, x2 + expand_x)
    y2_new = min(img_height, y2 + expand_y_bottom)

    return [x1_new, y1_new, x2_new, y2_new]

def mask_head_with_ellipse(image_path, detection_result, output_path):
    """使用椭圆形遮罩遮住头部"""
    img = Image.open(image_path)
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

    # 创建椭圆遮罩
    ellipse_bbox = create_elliptical_mask(pixel_bbox, img_width, img_height)
    print(f"椭圆遮罩边界: {ellipse_bbox}")

    # 创建一个遮罩图层
    mask = Image.new('L', (img_width, img_height), 0)
    mask_draw = ImageDraw.Draw(mask)

    # 画椭圆遮罩
    mask_draw.ellipse(ellipse_bbox, fill=255)

    # 创建黑色图层
    black_layer = Image.new('RGB', (img_width, img_height), 'black')

    # 将黑色图层通过遮罩合成到原图上
    img.paste(black_layer, mask=mask)

    # 保存结果
    img.save(output_path)
    print(f"\n已保存遮罩后的图片到: {output_path}")
    return output_path

def mask_head_with_rounded_rect(image_path, detection_result, output_path):
    """使用圆角矩形遮罩遮住头部"""
    img = Image.open(image_path)
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

    # 创建圆角矩形
    rect_bbox = create_rounded_rect_mask(pixel_bbox, img_width, img_height)
    print(f"圆角矩形边界: {rect_bbox}")

    # 创建遮罩图层
    mask = Image.new('L', (img_width, img_height), 0)
    mask_draw = ImageDraw.Draw(mask)

    # 计算圆角半径
    width = rect_bbox[2] - rect_bbox[0]
    height = rect_bbox[3] - rect_bbox[1]
    radius = min(width, height) // 4

    # 画圆角矩形
    mask_draw.rounded_rectangle(rect_bbox, radius=radius, fill=255)

    # 创建黑色图层
    black_layer = Image.new('RGB', (img_width, img_height), 'black')

    # 合成
    img.paste(black_layer, mask=mask)

    # 保存结果
    img.save(output_path)
    print(f"\n已保存遮罩后的图片到: {output_path}")
    return output_path

def main():
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError("请设置 DASHSCOPE_API_KEY")

    image_path = "/Users/jingweizhang/Workspace/short-drama/playground/qwen3-vl/jimeng-2025-11-15-5498-一名28岁的东亚男性的全身人像，端正站好。  发型是稍微有点凌乱的中短发，略微蓬....png"

    print("=" * 80)
    print("使用 QWEN3-VL 检测头部并创建精细遮罩")
    print("=" * 80)

    # 检测头部
    detection_result = detect_head_bbox_with_qwen(image_path, api_key)

    # 方法1: 椭圆形遮罩
    print("\n方法 1: 椭圆形遮罩")
    print("-" * 80)
    output_ellipse = "/Users/jingweizhang/Workspace/short-drama/playground/qwen3-vl/output_ellipse_mask.png"
    mask_head_with_ellipse(image_path, detection_result, output_ellipse)

    # 方法2: 圆角矩形遮罩
    print("\n方法 2: 圆角矩形遮罩")
    print("-" * 80)
    output_rounded = "/Users/jingweizhang/Workspace/short-drama/playground/qwen3-vl/output_rounded_mask.png"
    mask_head_with_rounded_rect(image_path, detection_result, output_rounded)

    print("\n" + "=" * 80)
    print("完成! 已生成两种遮罩效果:")
    print(f"  1. 椭圆形: {output_ellipse}")
    print(f"  2. 圆角矩形: {output_rounded}")
    print("=" * 80)

if __name__ == "__main__":
    main()
