# API key 信息
API_KEY = "your_api_key_here"

# 视频提取语音的FFMPEG路径
FFMPEG_PATH = "your_ffmpeg_path_here"

# 语言转srt文本的ASR模型
ASK_INFO = {
    
}


# 分析截图信息的VLM
VLM_INFO = {
    "model": "doubao-1.5-vision-pro-250328",
    "max_tokens": 4096,
    "temperature": 0.3,
    "base_url": "https://ark.cn-beijing.volces.com/api/v3",
    "api_key": "45001e86-62d6-4c59-9cc7-8df07deba9ce",
}

# 分析截图文字内容的OCR
OCR_INFO = {
    
}

# 具有长上下文的LLM
Long_LLM_INFO = {
    "model": "glm-4-long",
    "max_tokens": 128000,
    "temperature": 0.3,
    "base_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    "api_key": "130e0b22a84a4d2692cf926378a79ee7.BIwCMAVqw4S4D7Mp",
}

# 用于问答的深度思考模型
Reason_LLM_INFO = {
    "model": "qwq",
    "max_tokens": 64000,
    "temperature": 0.3,
    "base_url": "",
    "api_key": "",
}