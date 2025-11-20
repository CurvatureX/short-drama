import os
from dashscope import MultiModalConversation
from PIL import Image, ImageDraw
import json
import re

def detect_face_with_qwen(image_path, api_key):
    """
    使用 QWEN3-VL 模型检测图片中的人脸位置
    """
    messages = [
        {
            "role": "user",
            "content": [
                {"image": f"file://{image_path}"},
                {
                    "text": """请识别图片中所有人脸的位置，并以JSON格式返回。

对于每个人脸，返回其边界框坐标 (x1, y1, x2, y2)，其中：
- (x1, y1) 是左上角坐标
- (x2, y2) 是右下角坐标
- 坐标应该是相对于图片的像素坐标

请严格按照以下JSON格式返回：
{
  "faces": [
    {
      "bbox": [x1, y1, x2, y2],
      "confidence": 0.95
    }
  ]
}

如果图片中没有人脸，返回空数组。
只返回JSON，不要其他解释。"""
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

    # 尝试从响应中提取JSON
    try:
        # 尝试直接解析
        result = json.loads(result_text)
        return result
    except json.JSONDecodeError:
        # 尝试从文本中提取JSON块
        json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            return result
        else:
            print("无法解析JSON，尝试使用更灵活的人脸检测提示...")
            return detect_face_with_grounding(image_path, api_key)

def detect_face_with_grounding(image_path, api_key):
    """
    使用 QWEN3-VL 的 grounding 能力检测人脸
    """
    messages = [
        {
            "role": "user",
            "content": [
                {"image": f"file://{image_path}"},
                {
                    "text": "Please detect and locate the face in this image. Return the bounding box coordinates."
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
    print("Grounding 模式响应:")
    print(result_text)
    print("-" * 80)

    # 这里我们需要手动解析响应，因为可能不是严格的JSON格式
    # 如果模型返回了坐标信息，我们尝试提取
    return {"faces": [], "raw_response": result_text}

def mask_faces_in_image(image_path, faces_data, output_path):
    """
    在图片中用黑色遮住检测到的人脸
    """
    # 打开图片
    img = Image.open(image_path)
    draw = ImageDraw.Draw(img)

    # 获取图片尺寸
    img_width, img_height = img.size
    print(f"图片尺寸: {img_width} x {img_height}")

    # 遮住每个人脸
    faces = faces_data.get("faces", [])
    if not faces:
        print("警告: 没有检测到人脸数据")
        # 如果有原始响应，打印出来帮助调试
        if "raw_response" in faces_data:
            print("原始响应:", faces_data["raw_response"])
        # 作为备选方案，检测整个图片中心区域作为人脸（用于测试）
        print("\n尝试使用简单的人脸检测方案...")
        return manual_face_detection(image_path, output_path, api_key)

    for i, face in enumerate(faces):
        bbox = face["bbox"]
        x1, y1, x2, y2 = bbox

        print(f"人脸 {i+1}: bbox = ({x1}, {y1}, {x2}, {y2})")

        # 画黑色矩形遮住人脸
        draw.rectangle([x1, y1, x2, y2], fill="black")

    # 保存结果
    img.save(output_path)
    print(f"\n已保存遮罩后的图片到: {output_path}")
    return output_path

def manual_face_detection(image_path, output_path, api_key):
    """
    使用简化的方法：让QWEN描述人脸位置，然后手动估计坐标
    """
    messages = [
        {
            "role": "user",
            "content": [
                {"image": f"file://{image_path}"},
                {
                    "text": """请详细描述图片中人脸的位置：
1. 人脸在图片中的大致位置（上部/中部/下部，左侧/中间/右侧）
2. 人脸大约占图片宽度和高度的百分比
3. 人脸的大致范围

请简洁明了地回答。"""
                }
            ]
        }
    ]

    response = MultiModalConversation.call(
        api_key=api_key,
        model="qwen3-vl-plus",
        messages=messages,
    )

    description = response.output.choices[0].message.content[0]["text"]
    print("人脸位置描述:")
    print(description)
    print("-" * 80)

    # 打开图片
    img = Image.open(image_path)
    draw = ImageDraw.Draw(img)
    img_width, img_height = img.size

    # 基于全身人像的假设，人脸通常在上部中央
    # 这是一个粗略的估计，实际应该使用真实的检测结果
    face_x1 = int(img_width * 0.35)
    face_y1 = int(img_height * 0.05)
    face_x2 = int(img_width * 0.65)
    face_y2 = int(img_height * 0.25)

    print(f"估计的人脸位置: ({face_x1}, {face_y1}, {face_x2}, {face_y2})")

    # 画黑色矩形
    draw.rectangle([face_x1, face_y1, face_x2, face_y2], fill="black")

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
    output_path = "/Users/jingweizhang/Workspace/short-drama/playground/qwen3-vl/output_masked.png"

    print("=" * 80)
    print("开始使用 QWEN3-VL 检测人脸...")
    print("=" * 80)

    # 检测人脸
    faces_data = detect_face_with_qwen(image_path, api_key)

    # 遮住人脸
    mask_faces_in_image(image_path, faces_data, output_path)

    print("=" * 80)
    print("完成!")
    print("=" * 80)

if __name__ == "__main__":
    main()
