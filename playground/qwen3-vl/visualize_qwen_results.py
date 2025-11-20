from PIL import Image, ImageDraw, ImageFont
import os

def visualize_all_bboxes(image_path):
    """可视化所有QWEN3-VL返回的边界框"""

    # 所有测试结果
    results = [
        {
            "label": "Test 1 - Grounding",
            "bbox": [406, 81, 563, 179],
            "color": "red"
        },
        {
            "label": "Test 2 - Ref/Box tags",
            "bbox": [412, 83, 569, 177],
            "color": "blue"
        },
        {
            "label": "Test 3 - Percentage (错误-返回像素)",
            "bbox": [408, 79, 566, 179],
            "color": "green"
        },
        {
            "label": "Test 4 - Step by step",
            "bbox": [398, 74, 580, 180],
            "color": "yellow"
        },
        {
            "label": "Test 5 - qwen-vl-max",
            "bbox": [325, 86, 479, 271],
            "color": "purple"
        },
        {
            "label": "OpenCV (正确答案)",
            "bbox": [582, 209, 816, 443],
            "color": "orange"
        }
    ]

    # 为每个结果创建一个可视化
    for i, result in enumerate(results):
        img = Image.open(image_path).copy()
        draw = ImageDraw.Draw(img)

        bbox = result["bbox"]
        color = result["color"]
        label = result["label"]

        x1, y1, x2, y2 = bbox

        # 画边框
        draw.rectangle([x1, y1, x2, y2], outline=color, width=8)

        # 画标签
        draw.text((x1, y1 - 30), label, fill=color)

        output_path = f"/Users/jingweizhang/Workspace/short-drama/playground/qwen3-vl/viz_{i+1}_{label.split('-')[0].strip()}.png"
        img.save(output_path)
        print(f"保存: {output_path}")
        print(f"  {label}: bbox={bbox}")

    # 创建一个综合对比图
    img = Image.open(image_path).copy()
    draw = ImageDraw.Draw(img)

    for result in results:
        bbox = result["bbox"]
        color = result["color"]
        x1, y1, x2, y2 = bbox
        draw.rectangle([x1, y1, x2, y2], outline=color, width=3)

    output_path = "/Users/jingweizhang/Workspace/short-drama/playground/qwen3-vl/viz_all_combined.png"
    img.save(output_path)
    print(f"\n综合对比图: {output_path}")

    # 分析坐标范围
    print("\n" + "=" * 80)
    print("坐标分析:")
    print("=" * 80)
    print(f"图片尺寸: 1440 x 2560")
    print()

    for result in results:
        bbox = result["bbox"]
        x1, y1, x2, y2 = bbox
        width = x2 - x1
        height = y2 - y1
        center_x = (x1 + x2) / 2
        center_y = (y1 + y2) / 2

        print(f"{result['label']}:")
        print(f"  位置: ({x1}, {y1}) -> ({x2}, {y2})")
        print(f"  尺寸: {width} x {height}")
        print(f"  中心: ({center_x:.0f}, {center_y:.0f})")
        print(f"  中心占比: ({center_x/1440*100:.1f}%, {center_y/2560*100:.1f}%)")
        print()

if __name__ == "__main__":
    image_path = "/Users/jingweizhang/Workspace/short-drama/playground/qwen3-vl/jimeng-2025-11-15-5498-一名28岁的东亚男性的全身人像，端正站好。  发型是稍微有点凌乱的中短发，略微蓬....png"
    visualize_all_bboxes(image_path)
