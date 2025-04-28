'''
视频下载模块
使用you-get下载视频
'''

import sys
import you_get

def download(url: str, path: str) -> None:
    """下载视频到指定的路径

    参数:
        url: 视频链接地址，必须是完整的URL
        path: 视频保存的目标路径，必须是有效的目录路径
    
    返回:
        None: 该函数不返回任何值
    
    示例:
        >>> download("https://www.example.com/video", "/downloads")
    """
    you_get.main([url, '-o', path, 'videos'])

if __name__ == '__main__':
    download(sys.argv[1],sys.argv[2])