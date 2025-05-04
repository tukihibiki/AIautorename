#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import logging
import sys
from pathlib import Path
import pytesseract
import fitz  # PyMuPDF
import tempfile
from PIL import Image
import re
import shutil
import random
import string
import requests
import json

# DeepSeek API配置
DEEPSEEK_API_KEY = "sk-          "  # 请替换为实际API密钥
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
PROMPT_TEMPLATE = """请根据以下PDF文档第一页内容，生成一个简洁、有意义的文件名。
要求：
1. 包含文档核心主题
2. 包含关键日期或编号(如有)
3. 使用中文
4. 长度不超过30个字符
5. 如果第一行内容可以体现文件内容，请直接使用第一行文字作为文件名
6. 如果前6行内容中出现判决书、裁定书、裁决书或类似字眼，你需要按照该方式生成文件名，具体案号在文本中会有显示：（2021）浙0110民初1234号民事判决书
7. 如果文本中出现核准开业登记通知书、个体户机读档案或类似字眼，你需要在文本中找到“企业名称：”字眼，并将“企业名称：”后属于企业名称的部分列为文件名，如：“企业名称:佛山市禅城区潮牌网红服装商行(个体工商户)”的文件名为“佛山市禅城区潮牌网红服装商行(个体工商户)”
8. 如果文本前三行内容包含材料清单字眼，则无需考虑后面出现的判决书、裁定书、裁决书、核准开业登记通知书、个体户机读档案或类似字眼

文档内容：
{content}

请直接返回文件名，不要包含其他说明。"""
# 设置日志
def setup_logging():
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"pdf_renamer_{time.strftime('%Y%m%d_%H%M%S')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file)
        ]
    )
    return logging.getLogger("PDFRenamer")

# 清理文件名，去除非法字符和所有空格，限制长度
def clean_filename(name):
    if not name:
        return "未命名文档"
    
    # 去除文件名中的非法字符
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    
    # 去除所有空格
    name = name.replace(' ', '')
    
    # 限制文件名长度
    if len(name) > 100:
        name = name[:100]
    
    # 如果文件名为空，则使用默认名称
    if not name:
        name = "未命名文档"
        
    return name

# 生成唯一的文件名
def get_unique_filename(folder_path, base_name, extension=".pdf"):
    counter = 0
    new_name = base_name
    
    while os.path.exists(os.path.join(folder_path, new_name + extension)):
        counter += 1
        new_name = f"{base_name}（{counter}）"
    
    return new_name + extension

# 生成临时文件路径
def get_temp_file_path(suffix='.png'):
    # 创建唯一随机文件名
    random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    timestamp = int(time.time())
    filename = f"temp_{timestamp}_{random_str}{suffix}"
    
    # 使用当前目录下的temp文件夹
    temp_dir = Path("temp")
    temp_dir.mkdir(exist_ok=True)
    
    return temp_dir / filename

# 备份原始文件
def backup_file(src_path):
    backup_dir = Path("backups")
    backup_dir.mkdir(exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    dest_path = backup_dir / f"{timestamp}_{Path(src_path).name}"
    shutil.copy2(src_path, dest_path)
    return dest_path

# 检查tesseract是否安装并配置正确
def check_tesseract_installed():
    try:
        # 检查tesseract是否安装
        pytesseract.get_tesseract_version()
        
        # 检查中文语言包是否存在
        tessdata_dir = os.getenv('TESSDATA_PREFIX', 'C:\\Program Files\\Tesseract-OCR')
        # 处理可能的路径格式问题
        if tessdata_dir.endswith('tessdata'):
            chi_sim_path = os.path.join(tessdata_dir, 'chi_sim.traineddata')
        else:
            chi_sim_path = os.path.join(tessdata_dir, 'tessdata', 'chi_sim.traineddata')
        if not os.path.exists(chi_sim_path):
            logger.error(f"中文语言包未找到: {chi_sim_path}")
            return False
            
        return True
    except Exception as e:
        logger.error(f"Tesseract检查失败: {e}")
        return False

# 使用OCR从图像中提取文本
def extract_text_from_image(image_path):
    if not check_tesseract_installed():
        logger.error("OCR功能不可用: 请先安装tesseract OCR引擎")
        return ""
    
    try:
        # 使用pytesseract进行OCR，指定语言为简体中文
        text = pytesseract.image_to_string(Image.open(image_path), lang='chi_sim')
        return text.strip()
    except Exception as e:
        logger.error(f"OCR识别失败: {e}")
        return ""

def call_deepseek_api(content):
    """调用DeepSeek API生成智能文件名"""
    try:
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "user", "content": PROMPT_TEMPLATE.format(content=content)}
            ],
            "temperature": 0.3
        }
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        return result['choices'][0]['message']['content'].strip()
    except Exception as e:
        logger.error(f"DeepSeek API调用失败: {e}")
        return None

# 从PDF的第一页提取文本并生成智能文件名
def extract_filename_from_pdf(pdf_path):
    try:
        # 打开PDF文件
        doc = fitz.open(pdf_path)
        if doc.page_count == 0:
            logger.warning(f"PDF文件 {pdf_path} 没有页面")
            return ""
        
        # 获取第一页
        page = doc[0]
        
        # 尝试直接提取文本
        text = page.get_text()
        
        # 如果没有文本（可能是图像PDF），则渲染为图像并使用OCR
        if not text.strip():
            logger.info(f"文件 {pdf_path} 可能是图像PDF，尝试OCR")
            
            # 将PDF页面渲染为图像
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            
            # 创建临时文件路径
            temp_image_path = get_temp_file_path('.png')
            
            try:
                # 保存图像到临时文件
                pix.save(str(temp_image_path))
                
                # 使用OCR识别图像
                text = extract_text_from_image(temp_image_path)
            finally:
                # 删除临时文件
                try:
                    if os.path.exists(temp_image_path):
                        os.remove(temp_image_path)
                except Exception as e:
                    logger.warning(f"无法删除临时文件 {temp_image_path}: {e}")
        
        # 获取完整文本内容
        full_text = text.strip()
        
        # 尝试使用DeepSeek生成智能文件名
        smart_name = call_deepseek_api(full_text)
        if smart_name:
            logger.info(f"DeepSeek生成的文件名: {smart_name}")
            return smart_name
        
        # 如果API调用失败，回退到第一行文本
        lines = text.splitlines()
        first_line = next((line.strip() for line in lines if line.strip()), "")
        logger.warning("使用第一行文本作为文件名")
        return first_line
    
    except Exception as e:
        logger.error(f"处理PDF文件 {pdf_path} 时出错: {e}")
        return ""
    finally:
        # 关闭文档
        if 'doc' in locals():
            doc.close()

# 记录已处理的文件
def load_processed_files(folder_path):
    processed_file = os.path.join(folder_path, "更名存档.txt")
    if os.path.exists(processed_file):
        with open(processed_file, 'r', encoding='utf-8') as f:
            return set(line.strip() for line in f)
    return set()

def save_processed_file(folder_path, filename):
    processed_file = os.path.join(folder_path, "更名存档.txt")
    with open(processed_file, 'a', encoding='utf-8') as f:
        f.write(f"{filename}\n")

# 主要处理函数
def process_folder(folder_path):
    # 确保目录存在
    Path("temp").mkdir(exist_ok=True)
    Path("backups").mkdir(exist_ok=True)
    
    # 获取已处理的文件列表
    processed_files = load_processed_files(folder_path)
    
    # 获取文件夹中的所有PDF文件
    pdf_files = [f for f in os.listdir(folder_path) 
                if f.lower().endswith('.pdf') and os.path.isfile(os.path.join(folder_path, f))
                and f not in processed_files]
    
    logger.info(f"找到 {len(pdf_files)} 个未处理的PDF文件")
    
    for pdf_file in pdf_files:
        pdf_path = os.path.join(folder_path, pdf_file)
        try:
            # 提取或生成文件名
            new_name_content = extract_filename_from_pdf(pdf_path)
            
            if new_name_content:
                # 清理并生成新的文件名
                new_name_base = clean_filename(new_name_content)
                new_name = get_unique_filename(folder_path, new_name_base)
                new_path = os.path.join(folder_path, new_name)
                
                # 直接重命名文件
                os.rename(pdf_path, new_path)
                logger.info(f"已重命名文件: {pdf_file} -> {new_name}")
                
                # 仅当重命名成功后才记录为已处理
                save_processed_file(folder_path, new_name)
            else:
                logger.warning(f"无法从 {pdf_file} 提取文本，保留原文件名")
                
        except Exception as e:
            logger.error(f"处理文件 {pdf_file} 时出错: {e}")


def main():
    # 默认处理脚本所在目录下的共享文件文件夹：default_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "共享文件")
    default_folder = "C:/Users/共享文件"  # 替换，指定文件夹
    
    # 如果提供了命令行参数则使用参数指定的文件夹
    if len(sys.argv) == 2:
        folder_path = sys.argv[1]
    else:
        folder_path = default_folder
    
    # 确保目标文件夹存在
    os.makedirs(folder_path, exist_ok=True)
    
    if not os.path.isdir(folder_path):
        print(f"错误: {folder_path} 不是有效的文件夹路径")
        sys.exit(1)
    
    logger.info(f"开始监控文件夹: {folder_path}")
    
    try:
        while True:
            process_folder(folder_path)
            logger.info("等待新文件...")
            time.sleep(10)
    except KeyboardInterrupt:
        logger.info("程序已终止")
    except Exception as e:
        logger.error(f"发生错误: {e}")

if __name__ == "__main__":
    logger = setup_logging()
    main()
