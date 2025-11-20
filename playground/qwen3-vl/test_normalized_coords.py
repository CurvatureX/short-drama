from PIL import Image, ImageDraw

def convert_normalized_to_pixels(normalized_bbox, img_width, img_height, norm_range=1000):
    """
    将归一化坐标转换为像素坐标

    QWEN 可能使用 0-1000 的归一化坐标系统
    """
    x1_norm, y1_norm, x2_norm, y2_norm = normalized_bbox

    x1 = int(x1_norm / norm_range * img_width)
    y1 = int(y1_norm / norm_range * img_height)
    x2 = int(x2_norm / norm_range * img_width)
    y2 = int(y2_norm / norm_range * img_height)

    return [x1, y1, x2, y2]

def test_normalization_hypothesis():
    """测试归一化坐标假设"""

    image_path = "/Users/jingweizhang/Workspace/short-drama/playground/qwen3-vl/jimeng-2025-11-15-5498-一名28岁的东亚男性的全身人像，端正站好。  发型是稍微有点凌乱的中短发，略微蓬....png"

    img = Image.open(image_path)
    img_width, img_height = img.size

    print(f"图片尺寸: {img_width} x {img_height}")
    print("\n" + "=" * 80)
    print("假设: QWEN 使用 0-1000 归一化坐标系统")
    print("=" * 80)

    # QWEN 返回的坐标
    qwen_results = [
        ("Test 1 - Grounding", [406, 81, 563, 179]),
        ("Test 2 - Ref/Box", [412, 83, 569, 177]),
        ("Test 4 - Step by step", [398, 74, 580, 180]),
        ("Test 5 - qwen-vl-max", [325, 86, 479, 271]),
    ]

    opencv_bbox = [582, 209, 816, 443]
    print(f"\nOpenCV 正确答案: {opencv_bbox}")
    print()

    for label, qwen_bbox in qwen_results:
        print(f"\n{label}:")
        print(f"  QWEN 原始坐标: {qwen_bbox}")

        # 转换为像素坐标
        pixel_bbox = convert_normalized_to_pixels(qwen_bbox, img_width, img_height)
        print(f"  转换后像素坐标: {pixel_bbox}")

        # 计算与 OpenCV 的差距
        diff = [abs(pixel_bbox[i] - opencv_bbox[i]) for i in range(4)]
        print(f"  与 OpenCV 的差距: {diff}")

        # 可视化
        img_copy = Image.open(image_path).copy()
        draw = ImageDraw.Draw(img_copy)

        # 画 QWEN 转换后的框（红色）
        draw.rectangle(pixel_bbox, outline="red", width=8)

        # 画 OpenCV 的框（绿色）
        draw.rectangle(opencv_bbox, outline="green", width=4)

        output_path = f"/Users/jingweizhang/Workspace/short-drama/playground/qwen3-vl/normalized_{label.split('-')[0].strip()}.png"
        img_copy.save(output_path)
        print(f"  保存到: {output_path}")

if __name__ == "__main__":
    test_normalization_hypothesis()
