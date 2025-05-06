'''
视频下载模块
使用you-get下载视频
'''
import sys
import os
def download_bilibili(url: str, task_path: str, coockie=None):
    # 下载b站视频
    order_str='you-get -i ' + url + ' -O ' + os.path.join(task_path,'1') + ' --no-caption'
    if coockie != None:
        order_str += ' --cookies ' + coockie
        pass
    print(order_str)
    os.system(order_str)
    return os.path.join(task_path, "1[00].mp4")
if __name__ == '__main__':
    if len(sys.argv) < 3:
        download_bilibili(sys.argv[1], sys.argv[2])
    else:
        download_bilibili(sys.argv[1], sys.argv[2], sys.argv[3])
