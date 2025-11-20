import os
from dashscope import MultiModalConversation
from PIL import Image, ImageDraw
import json
import re
import cv2
import numpy as np

def detect_face_with_opencv(image_path):
    """
    使用 OpenCV 的 Haar Cascade 检测人脸
    """
    # 读取图片
    img = cv2.imread(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 加载人脸检测器
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

    # 检测人脸
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))

    print(f"OpenCV 检测到 {len(faces)} 个人脸")

    result = {"faces": []}
    for (x, y, w, h) in faces:
        print(f"OpenCV 人脸: x={x}, y={y}, w={w}, h={h}")
        result["faces"].append({
            "bbox": [int(x), int(y), int(x + w), int(y + h)],
            "confidence": 0.9,
            "method": "opencv"
        })

    return result

def detect_face_with_qwen_detailed(image_path, api_key):
    """
    使用 QWEN3-VL 模型进行详细的人脸位置描述
    """
    messages = [
        {
            "role": "user",
            "content": [
                {"image": f"file://{image_path}"},
                {
                    "text": """请非常精确地标注出图片中人物脸部的位置。

图片尺寸是 1440x2560 像素。

请返回人脸区域（包括额头、眉毛、眼睛、鼻子、嘴巴、下巴）的边界框，格式为：
- 左上角坐标 (x1, y1)
- 右下角坐标 (x2, y2)

注意：
1. 只需要标注脸部，不包括头发
2. 坐标必须是像素坐标
3. x 是横坐标（0到1440），y 是纵坐标（0到2560）

请以JSON格式返回：
{
  "face_bbox": [x1, y1, x2, y2],
  "image_width": 1440,
  "image_height": 2560
}

只返回JSON，不要其他内容。"""
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
    print("QWEN3-VL 详细响应:")
    print(result_text)
    print("-" * 80)

    try:
        # 尝试直接解析
        result = json.loads(result_text)
        if "face_bbox" in result:
            bbox = result["face_bbox"]
            return {
                "faces": [{
                    "bbox": bbox,
                    "confidence": 0.95,
                    "method": "qwen"
                }]
            }
    except:
        pass

    # 尝试提取坐标
    json_match = re.search(r'\{[^}]*"face_bbox"[^}]*\}', result_text, re.DOTALL)
    if json_match:
        try:
            result = json.loads(json_match.group())
            bbox = result["face_bbox"]
            return {
                "faces": [{
                    "bbox": bbox,
                    "confidence": 0.95,
                    "method": "qwen"
                }]
            }
        except:
            pass

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
        if "raw_response" in faces_data:
            print("原始响应:", faces_data["raw_response"])
        return None

    for i, face in enumerate(faces):
        bbox = face["bbox"]
        x1, y1, x2, y2 = bbox
        method = face.get("method", "unknown")

        print(f"人脸 {i+1} (方法: {method}): bbox = ({x1}, {y1}, {x2}, {y2})")

        # 扩大一点范围以确保覆盖整个脸
        padding = 20
        x1 = max(0, x1 - padding)
        y1 = max(0, y1 - padding)
        x2 = min(img_width, x2 + padding)
        y2 = min(img_height, y2 + padding)

        print(f"加上边距后: bbox = ({x1}, {y1}, {x2}, {y2})")

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
        print("警告: 未设置 DASHSCOPE_API_KEY，将只使用 OpenCV 检测")

    # 输入图片路径
    image_path = "/Users/jingweizhang/Workspace/short-drama/playground/qwen3-vl/jimeng-2025-11-15-5498-一名28岁的东亚男性的全身人像，端正站好。  发型是稍微有点凌乱的中短发，略微蓬....png"

    # 输出图片路径
    output_path = "/Users/jingweizhang/Workspace/short-drama/playground/qwen3-vl/output_masked_v2.png"

    print("=" * 80)
    print("方法 1: 使用 OpenCV 检测人脸...")
    print("=" * 80)

    faces_data = detect_face_with_opencv(image_path)

    if not faces_data["faces"] and api_key:
        print("\nOpenCV 未检测到人脸，尝试使用 QWEN3-VL...")
        print("=" * 80)
        faces_data = detect_face_with_qwen_detailed(image_path, api_key)

    if faces_data["faces"]:
        mask_faces_in_image(image_path, faces_data, output_path)
    else:
        print("\n所有方法都未能检测到人脸")

    print("=" * 80)
    print("完成!")
    print("=" * 80)

if __name__ == "__main__":
    main()
