import os
from dashscope import MultiModalConversation
from PIL import Image, ImageDraw
import json
import re
import sys

def detect_head_with_qwen(image_path, api_key):
    """使用 QWEN3-VL 检测人物头部（包括头发）"""
    messages = [
        {
            "role": "user",
            "content": [
                {"image": f"file://{image_path}"},
                {
                    "text": """Detect all people's heads (including hair) in the image.
For each person, return the bounding box that covers the entire head including all hair.
Return in JSON format:
[
  {"bbox": [x1, y1, x2, y2], "gender": "male/female"}
]"""
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

        # 返回对象数组
        if isinstance(result, list) and len(result) > 0:
            heads = []
            for item in result:
                if isinstance(item, dict):
                    # 尝试多个可能的键名
                    bbox = None
                    for key in ["bbox_2d", "bbox", "head_bbox", "face_bbox"]:
                        if key in item:
                            bbox = item[key]
                            break

                    if bbox:
                        heads.append({
                            "normalized_bbox": bbox,
                            "label": item.get("label", ""),
                            "gender": item.get("gender", "unknown")
                        })

            if heads:
                return {"heads": heads}

    except Exception as e:
        print(f"JSON 解析错误: {e}")

    # 如果解析失败，尝试提取所有坐标
    arrays = re.findall(r'\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]', result_text)
    if arrays:
        heads = []
        for arr in arrays:
            coords = [int(x) for x in arr]
            heads.append({"normalized_bbox": coords, "label": "", "gender": "unknown"})
        return {"heads": heads}

    return {"heads": [], "raw_response": result_text}

def convert_normalized_to_pixels(normalized_bbox, img_width, img_height, norm_range=1000):
    """将归一化坐标转换为像素坐标"""
    x1_norm, y1_norm, x2_norm, y2_norm = normalized_bbox

    x1 = int(x1_norm / norm_range * img_width)
    y1 = int(y1_norm / norm_range * img_height)
    x2 = int(x2_norm / norm_range * img_width)
    y2 = int(y2_norm / norm_range * img_height)

    return [x1, y1, x2, y2]

def create_elliptical_mask_for_head(bbox, img_width, img_height,
                                     expand_top=1.4, expand_sides=1.3, expand_bottom=1.1):
    """
    创建椭圆形遮罩覆盖整个头部（包括头发）

    参数:
        bbox: [x1, y1, x2, y2] - 人脸边界框
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

    # 扩展椭圆尺寸以覆盖头发
    ellipse_width = width * expand_sides / 2
    ellipse_height_top = (center_y - y1) * expand_top
    ellipse_height_bottom = (y2 - center_y) * expand_bottom

    # 总高度
    ellipse_height = ellipse_height_top + ellipse_height_bottom

    # 调整中心点（因为顶部扩展更多）
    adjusted_center_y = y1 + ellipse_height_top

    # 椭圆边界框
    ellipse_bbox = [
        max(0, center_x - ellipse_width),
        max(0, adjusted_center_y - ellipse_height / 2),
        min(img_width, center_x + ellipse_width),
        min(img_height, adjusted_center_y + ellipse_height / 2)
    ]

    return ellipse_bbox

def mask_heads_with_ellipse(image_path, detection_result, output_path, target_gender="male"):
    """使用椭圆形遮罩遮住指定性别的头部"""
    img = Image.open(image_path)
    img_width, img_height = img.size

    print(f"图片尺寸: {img_width} x {img_height}")

    heads = detection_result.get("heads", [])
    if not heads:
        print("错误: 没有检测到头部")
        if "raw_response" in detection_result:
            print("原始响应:", detection_result["raw_response"])
        return None

    print(f"检测到 {len(heads)} 个头部")

    # 创建遮罩图层
    mask = Image.new('L', (img_width, img_height), 0)
    mask_draw = ImageDraw.Draw(mask)

    masked_count = 0
    for i, head in enumerate(heads):
        normalized_bbox = head.get("normalized_bbox")
        if not normalized_bbox:
            continue

        label = head.get("label", "")
        gender = head.get("gender", "unknown")

        # 判断是否是男性（根据标签或性别）
        is_male = "male" in label.lower() or "man" in label.lower() or gender == "male"

        # 如果只遮住男性，且当前不是男性，跳过
        # 由于检测结果中第一个通常是左侧的人，我们遮住第一个
        if target_gender == "male" and i == 0:
            print(f"\n头部 {i+1} (遮住):")
        elif target_gender == "male" and i > 0:
            print(f"\n头部 {i+1} (跳过):")
            continue
        else:
            print(f"\n头部 {i+1}:")

        print(f"  QWEN 归一化坐标: {normalized_bbox}")

        # 转换为像素坐标
        pixel_bbox = convert_normalized_to_pixels(normalized_bbox, img_width, img_height)
        print(f"  转换为像素坐标: {pixel_bbox}")

        # 创建椭圆遮罩
        ellipse_bbox = create_elliptical_mask_for_head(pixel_bbox, img_width, img_height)
        print(f"  椭圆遮罩边界: {ellipse_bbox}")

        # 画椭圆到遮罩上
        mask_draw.ellipse(ellipse_bbox, fill=255)
        masked_count += 1

    if masked_count == 0:
        print("警告: 没有遮住任何头部")
        return None

    # 创建黑色图层
    black_layer = Image.new('RGB', (img_width, img_height), 'black')

    # 将黑色图层通过遮罩合成到原图上
    img.paste(black_layer, mask=mask)

    # 保存结果
    img.save(output_path)
    print(f"\n已保存遮罩后的图片到: {output_path}")
    print(f"共遮住 {masked_count} 个头部")
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
    output_path = f"/Users/jingweizhang/Workspace/short-drama/playground/qwen3-vl/{input_name}_head_masked{input_ext}"

    print("=" * 80)
    print(f"处理图片: {image_path}")
    print("使用椭圆形遮罩遮住男人的整个头部（包括头发）")
    print("=" * 80)

    # 检测头部
    detection_result = detect_head_with_qwen(image_path, api_key)

    # 使用椭圆形遮罩遮住男性的头部
    mask_heads_with_ellipse(image_path, detection_result, output_path, target_gender="male")

    print("=" * 80)
    print("完成!")
    print("=" * 80)

if __name__ == "__main__":
    main()
