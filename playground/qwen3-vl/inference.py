import os
from dashscope import MultiModalConversation
import dashscope

# 若使用新加坡地域的模型，请取消下列注释
# dashscope.base_http_api_url = "https://dashscope-intl.aliyuncs.com/api/v1"

# 将xxxx/test.mp4替换为你本地视频的绝对路径
local_path = "/Users/jingweizhang/Workspace/short-drama/playground/part1.mp4"
video_path = f"file://{local_path}"
messages = [
    {
        "role": "user",
        # fps参数控制视频抽帧数量，表示每隔1/fps 秒抽取一帧
        "content": [
            {"video": video_path, "fps": 2},
            {
                "text": """
请作为一名专业电影导演与镜头语言分析师，对我提供的整段视频进行全面分析，并输出一个包含完整镜头语言字段的 JSON。请基于你对画面、人物、运动、光影、叙事的理解，补全分镜知识库所需的所有字段。

你需要输出的信息包括：

============================================================
1. 剧情总结（Plot Summary）
============================================================
用 1–3 句话概括整个视频讲了什么。

============================================================
2. 镜头列表（Shots）
============================================================
对视频按镜头切分（shot），按时间顺序输出每个镜头的完整信息。每个镜头需包含以下字段：

{
  "start_time": "HH:mm:ss",
  "end_time": "HH:mm:ss",
  "shot_duration": 0.0,   // 秒数

  "shot_type": "...",     // 全景 / 中景 / 近景 / 特写 / 反打 / OTS / 双人镜头等
  "camera_motion": "...", // 推 / 拉 / 摇 / 移 / 环绕 / 手持 / 静止 + 方向

  "composition": {
    "framing": "...",             // 三分法 / 中心构图 / 对称 / 侧脸 / 背影 / OTS 等
    "subject_positions": "...",   // 男主左前、女主右中、背景在中后等
    "depth_layers": "...",        // 前景 / 中景 / 后景 分层
    "axis": "...",                // 摄影机位于 180 度轴线的哪一侧
    "camera_side": "left / right / centered"
  },

  "character_state": {
    "male": {
      "pose": "...",
      "action": "...",
      "emotion": "...",
      "face_direction": "..."
    },
    "female": {
      "pose": "...",
      "action": "...",
      "emotion": "...",
      "face_direction": "..."
    }
  },

  "action_beat": "...",     // 该镜头中的关键动作变化

  "emotional_arc": {
    "trend": "...",          // 情绪上升/下降
    "explanation": "..."     // 为什么
  },

  "narrative_intention": "...",  // 导演为什么拍这个镜头

  "shot_grammar_tags": [
      // 镜头语法标签，例如：
      "reaction shot",
      "romantic beat",
      "establishing shot",
      "intimate close-up",
      "conflict setup",
      "reveal shot",
      "walk-and-talk",
      ...
  ],

  "visual_style": {
    "lighting_style": "...",   // 侧光 / 逆光 / 环境光 / 暗部主导
    "color_palette": "...",    // 暖黄 / 冷蓝 / 低饱和 / 胶片色
    "contrast_level": "...",
    "aesthetic": "...",        // 例如 王家卫、古风、韩剧风
    "texture": "...",          // 例如 film grain, softness, sharp digital
  },

  "spatial_layout": {
    "actor_positions": "...",
    "camera_depth": "...",   // 近、中、远
    "scene_type": "interior / exterior"
  },

  "continuity": {
    "is_continuation": true / false,    // 是否与前镜头连续
    "camera_angle_change": "...",       // 角度变化幅度
    "position_consistency": "...",      // 人物位置是否保持
    "light_consistency": "..."          // 光影方向是否一致
  },

  "environmental_details": {
    "background_elements": "...",       // 桌子 / 桥 / 烛光 / 床铺 / 草地等
    "props": "...",                     // 道具
    "weather_or_light": "..."
  },

  "keyframes": [
      {
        "time": "HH:mm:ss",
        "description": "该关键帧的重要性说明"
      }
  ]
}

============================================================
3. 片段总结（Segments）
============================================================
按叙事片段（story beats）输出每个段落的：

{
  "start_time": "HH:mm:ss",
  "end_time": "HH:mm:ss",
  "event": "...",
  "emotion": "...",
  "intention": "...",
  "summary": "..."
}

============================================================
请务必严格使用 JSON 输出，不要添加任何额外解释。
                            """
            },
        ],
    }
]
response = MultiModalConversation.call(
    # 若没有配置环境变量，请用百炼API Key将下行替换为：api_key="sk-xxx"
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    model="qwen3-vl-plus",
    messages=messages,
)
print(response.output.choices[0].message.content[0]["text"])
