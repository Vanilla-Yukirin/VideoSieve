import sys

def main():
    # 检查命令行参数
    if len(sys.argv) > 1:
        # 处理参数
        print(f"参数: {sys.argv[1:]}")
    else:
        # 进入交互模式
        print("没有参数，进入交互模式")
        # 这里可以添加交互逻辑

if __name__ == "__main__":
    main()
