import os
from dashscope import MultiModalConversation
from PIL import Image, ImageDraw
import json
import re
import sys

def detect_face_with_qwen(image_path, api_key):
    """使用 QWEN3-VL 检测人脸位置"""
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
    print("QWEN3-VL 检测响应:")
    print(result_text)
    print("-" * 80)

    # 提取坐标
    try:
        result = json.loads(result_text.strip().strip('`').strip('json').strip())

        # 直接返回数组
        if isinstance(result, list) and len(result) == 4:
            return {"normalized_bbox": result}

        # 返回对象数组
        if isinstance(result, list) and len(result) > 0 and isinstance(result[0], dict):
            if "bbox_2d" in result[0]:
                return {"normalized_bbox": result[0]["bbox_2d"]}

        # 返回字典
        if isinstance(result, dict):
            for key in ["face_bbox", "bbox", "head_bbox"]:
                if key in result:
                    return {"normalized_bbox": result[key]}
    except:
        pass

    # 尝试提取 <box> 标签
    box_match = re.search(r'<box>\[\[([^\]]+)\]\]</box>', result_text)
    if box_match:
        coords_str = box_match.group(1)
        coords = [int(x.strip()) for x in coords_str.split(',')]
        return {"normalized_bbox": coords}

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

def create_elliptical_mask(bbox, img_width, img_height, expand_top=1.15, expand_sides=1.1, expand_bottom=1.05):
    """
    创建椭圆形遮罩

    参数:
        bbox: [x1, y1, x2, y2]
        expand_top: 顶部扩展系数
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

    # 调整中心点
    adjusted_center_y = y1 + ellipse_height_top

    # 椭圆边界框
    ellipse_bbox = [
        center_x - ellipse_width,
        adjusted_center_y - ellipse_height / 2,
        center_x + ellipse_width,
        adjusted_center_y + ellipse_height / 2
    ]

    return ellipse_bbox

def mask_face_with_ellipse(image_path, detection_result, output_path):
    """使用椭圆形遮罩遮住人脸"""
    img = Image.open(image_path)
    img_width, img_height = img.size

    print(f"图片尺寸: {img_width} x {img_height}")

    normalized_bbox = detection_result.get("normalized_bbox")
    if not normalized_bbox:
        print("错误: 没有检测到人脸")
        if "raw_response" in detection_result:
            print("原始响应:", detection_result["raw_response"])
        return None

    print(f"QWEN 归一化坐标: {normalized_bbox}")

    # 转换为像素坐标
    pixel_bbox = convert_normalized_to_pixels(normalized_bbox, img_width, img_height)
    print(f"转换为像素坐标: {pixel_bbox}")

    # 创建椭圆遮罩
    ellipse_bbox = create_elliptical_mask(pixel_bbox, img_width, img_height)
    print(f"椭圆遮罩边界: {ellipse_bbox}")

    # 创建遮罩图层
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

def main():
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError("请设置 DASHSCOPE_API_KEY")

    # 输入图片路径
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
    else:
        image_path = "/Users/jingweizhang/Workspace/short-drama/playground/qwen3-vl/jimeng-2025-11-19-6461-将近景改为中景.png"

    # 输出图片路径
    input_filename = os.path.basename(image_path)
    input_name, input_ext = os.path.splitext(input_filename)
    output_path = f"/Users/jingweizhang/Workspace/short-drama/playground/qwen3-vl/{input_name}_masked{input_ext}"

    print("=" * 80)
    print(f"处理图片: {image_path}")
    print("=" * 80)

    # 检测人脸
    detection_result = detect_face_with_qwen(image_path, api_key)

    # 使用椭圆形遮罩
    mask_face_with_ellipse(image_path, detection_result, output_path)

    print("=" * 80)
    print("完成!")
    print("=" * 80)

if __name__ == "__main__":
    main()
