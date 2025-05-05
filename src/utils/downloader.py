'''
视频下载模块
使用you-get下载视频
'''
import sys
import os
def download_bilibili(url: str, task_path: str):
    # 下载b站视频
    os.system('you-get ' + url + ' -O ' + os.path.join(task_path,'1'))
    # 查找后缀为 "日.cmt.xml" 的文件
    xml_path = None
    for filename in os.listdir(task_path):
        if filename.endswith('日.cmt.xml'):
            xml_path = os.path.join(task_path, filename)
            break
    # 返回下载后的视频路径和弹幕路径
    return os.path.join(task_path, "1[00].mp4"), xml_path
if __name__ == '__main__':
    download_bilibili(sys.argv[1], sys.argv[2])
