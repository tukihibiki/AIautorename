这是一个能够指定监控文件夹内PDF文件并实现自动重命名的脚本

该脚本使用了tesseract-OCR，请在使用前确保你的电脑已安装该库并存有chi_sim.traineddata文件

使用方法：
打开pdf_renamer.py文件，在DEEPSEEK_API_KEY = "sk- "内替换你的deepseekAPI

确保PROMPT_TEMPLATE中对文件重命名的规则适用于你的要求，如不适用请直接修改

default_folder = "C:/Users/共享文件" 指定了被监控目录是C:/Users/共享文件，请自行修改所要监控的文件夹路径

time.sleep(10) 指定了程序自动刷新文件夹的时间，请按需修改

完成修改后保存退出，打开run_pdf_renamer.bat，该脚本将在后台启动pdf_renamer.py脚本，自动完成实时监控、改名
