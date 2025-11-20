import os
from dashscope import MultiModalConversation
from PIL import Image, ImageDraw
import json

def test_prompt_1(image_path, api_key):
    """测试提示词 1: 使用 grounding 格式"""
    print("\n" + "=" * 80)
    print("测试 1: 使用 grounding 格式请求坐标")
    print("=" * 80)

    messages = [
        {
            "role": "user",
            "content": [
                {"image": f"file://{image_path}"},
                {
                    "text": "Detect the person's face in the image and return its bounding box coordinates in the format [x1, y1, x2, y2] where (x1,y1) is top-left and (x2,y2) is bottom-right in pixels."
                }
            ]
        }
    ]

    response = MultiModalConversation.call(
        api_key=api_key,
        model="qwen3-vl-plus",
        messages=messages,
    )

    result = response.output.choices[0].message.content[0]["text"]
    print("响应:")
    print(result)
    return result

def test_prompt_2(image_path, api_key):
    """测试提示词 2: 使用 <ref> 和 <box> 标签"""
    print("\n" + "=" * 80)
    print("测试 2: 使用 <ref> 和 <box> 标签")
    print("=" * 80)

    messages = [
        {
            "role": "user",
            "content": [
                {"image": f"file://{image_path}"},
                {
                    "text": "Please detect <ref>the face</ref><box> in this image."
                }
            ]
        }
    ]

    response = MultiModalConversation.call(
        api_key=api_key,
        model="qwen3-vl-plus",
        messages=messages,
    )

    result = response.output.choices[0].message.content[0]["text"]
    print("响应:")
    print(result)
    return result

def test_prompt_3(image_path, api_key):
    """测试提示词 3: 询问相对位置"""
    print("\n" + "=" * 80)
    print("测试 3: 询问相对位置（百分比）")
    print("=" * 80)

    messages = [
        {
            "role": "user",
            "content": [
                {"image": f"file://{image_path}"},
                {
                    "text": """分析图片中人脸的位置，并返回边界框。

图片尺寸: 1440 x 2560 像素

请返回人脸的边界框坐标，以百分比形式表示（相对于图片宽高的比例，0-100）：
{
  "face_bbox_percent": {
    "x1_percent": 数字,
    "y1_percent": 数字,
    "x2_percent": 数字,
    "y2_percent": 数字
  }
}

只返回JSON。"""
                }
            ]
        }
    ]

    response = MultiModalConversation.call(
        api_key=api_key,
        model="qwen3-vl-plus",
        messages=messages,
    )

    result = response.output.choices[0].message.content[0]["text"]
    print("响应:")
    print(result)
    return result

def test_prompt_4(image_path, api_key):
    """测试提示词 4: 分步骤描述再给坐标"""
    print("\n" + "=" * 80)
    print("测试 4: 分步骤 - 先描述人脸位置特征")
    print("=" * 80)

    messages = [
        {
            "role": "user",
            "content": [
                {"image": f"file://{image_path}"},
                {
                    "text": """请详细分析这张图片中人脸的位置：

1. 首先描述人脸在图片中的位置（上/中/下，左/中/右）
2. 人脸的大小（相对于整张图）
3. 然后给出人脸区域的精确像素坐标 [x1, y1, x2, y2]

图片尺寸是 1440x2560。

请用JSON格式返回：
{
  "description": "人脸位置描述",
  "bbox_pixels": [x1, y1, x2, y2]
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

    result = response.output.choices[0].message.content[0]["text"]
    print("响应:")
    print(result)
    return result

def test_prompt_5(image_path, api_key):
    """测试提示词 5: 使用 qwen-vl-max 模型"""
    print("\n" + "=" * 80)
    print("测试 5: 使用 qwen-vl-max 模型（更强）")
    print("=" * 80)

    messages = [
        {
            "role": "user",
            "content": [
                {"image": f"file://{image_path}"},
                {
                    "text": """Detect the person's face and return the bounding box.

Image dimensions: 1440 x 2560 pixels

Return only JSON:
{
  "face_bbox": [x1, y1, x2, y2]
}

Where (x1,y1) is top-left corner and (x2,y2) is bottom-right corner in pixel coordinates."""
                }
            ]
        }
    ]

    try:
        response = MultiModalConversation.call(
            api_key=api_key,
            model="qwen-vl-max",
            messages=messages,
        )

        result = response.output.choices[0].message.content[0]["text"]
        print("响应:")
        print(result)
        return result
    except Exception as e:
        print(f"错误: {e}")
        return None

def visualize_bbox(image_path, bbox, output_path, label="Test"):
    """可视化边界框"""
    img = Image.open(image_path)
    draw = ImageDraw.Draw(img)

    if bbox and len(bbox) == 4:
        x1, y1, x2, y2 = bbox
        # 画红色边框
        draw.rectangle([x1, y1, x2, y2], outline="red", width=5)
        # 画黑色填充
        draw.rectangle([x1, y1, x2, y2], fill="black")

    img.save(output_path)
    print(f"已保存到: {output_path}")

def main():
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError("请设置 DASHSCOPE_API_KEY")

    image_path = "/Users/jingweizhang/Workspace/short-drama/playground/qwen3-vl/jimeng-2025-11-15-5498-一名28岁的东亚男性的全身人像，端正站好。  发型是稍微有点凌乱的中短发，略微蓬....png"

    print("开始测试不同的 QWEN3-VL 提示词...")

    # 测试所有提示词
    test_prompt_1(image_path, api_key)
    test_prompt_2(image_path, api_key)
    test_prompt_3(image_path, api_key)
    test_prompt_4(image_path, api_key)
    test_prompt_5(image_path, api_key)

    print("\n" + "=" * 80)
    print("所有测试完成！")
    print("=" * 80)

if __name__ == "__main__":
    main()
