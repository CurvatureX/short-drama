import os
from scenedetect import detect, ContentDetector, split_video_ffmpeg
from scenedetect.video_splitter import split_video_ffmpeg

def split_video_scenes(video_path, output_dir=None, threshold=27.0):
    """
    使用 PySceneDetect 将视频拆分成多个场景

    Args:
        video_path: 输入视频路径
        output_dir: 输出目录，默认为视频同目录下的 scenes 文件夹
        threshold: 场景检测阈值，默认27.0（越低越敏感）
    """
    # 检查视频文件是否存在
    if not os.path.exists(video_path):
        print(f"错误: 视频文件不存在: {video_path}")
        return

    # 设置输出目录
    if output_dir is None:
        video_dir = os.path.dirname(video_path)
        video_name = os.path.splitext(os.path.basename(video_path))[0]
        output_dir = os.path.join(video_dir, f"{video_name}_scenes")

    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)

    print(f"开始检测视频场景: {video_path}")
    print(f"检测阈值: {threshold}")
    print(f"输出目录: {output_dir}")
    print("-" * 50)

    # 使用 ContentDetector 检测场景
    scene_list = detect(video_path, ContentDetector(threshold=threshold))

    print(f"\n检测到 {len(scene_list)} 个场景:")
    print("-" * 50)

    # 打印每个场景的时间信息
    for i, scene in enumerate(scene_list):
        start_time = scene[0].get_timecode()
        end_time = scene[1].get_timecode()
        duration = (scene[1] - scene[0]).get_seconds()
        print(f"场景 {i+1}: {start_time} -> {end_time} (时长: {duration:.2f}秒)")

    print("-" * 50)
    print("\n开始拆分视频...")

    # 拆分视频
    split_video_ffmpeg(
        video_path,
        scene_list,
        output_dir=output_dir,
        show_progress=True,
        show_output=False
    )

    print(f"\n✓ 视频拆分完成! 输出目录: {output_dir}")
    print(f"✓ 共生成 {len(scene_list)} 个场景视频")

    return scene_list, output_dir


if __name__ == "__main__":
    # 视频路径
    video_path = "/Users/jingweizhang/Workspace/short-drama/playground/test1.mp4"

    # 拆分场景
    # threshold 参数说明:
    # - 默认值是 27.0
    # - 值越小，检测越敏感，会检测到更多场景
    # - 值越大，检测越不敏感，只会检测到明显的场景变化
    # 常用范围: 15.0-40.0

    scene_list, output_dir = split_video_scenes(
        video_path=video_path,
        threshold=40.0  # 可以调整这个值来改变检测敏感度
    )
