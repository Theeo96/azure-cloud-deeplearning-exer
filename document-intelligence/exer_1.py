import os
import requests
import time
import platform
import random
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

api_endpoint = os.getenv("DOCUMENT_INTELLIGENCE_ENDPOINT")
api_key = os.getenv("DOCUMENT_INTELLIGENCE_API_KEY")

def request_document_intelligence(img_pth):
    """
    Azure Document Intelligence API에 이미지를 전송하고 결과를 반환합니다.
    """
    # 1. Endpoint
    endpoint = api_endpoint
    
    # 2. METHOD : POST

    # 3. Header
    headers = {
        "Content-Type" : "image/*",
        "Ocp-Apim-Subscription-Key" : api_key
    }

    # 4. Body
    with open(img_pth, "rb") as img_file:
        img_data = img_file.read()

    body = img_data

    response = requests.post(endpoint, headers=headers, data=body)

    if response.status_code != 202:
        print("Error : ", response.status_code, response.text)
        return None
    
    url = response.headers['Operation-Location']

    while True:
        result_response = requests.get(url, headers=headers)

        if result_response.status_code != 200:
            print("Error : ", result_response.status_code, result_response.text)
            return None
        
        result_json = result_response.json()
        current_status = result_json.get('status')

        if current_status == 'running':
            print('current status :', current_status)
            time.sleep(1)
            continue

        else:
            break

    print('current status :', current_status)

    if current_status != 'succeeded':
        return None

    return result_response.json()

def random_color():
    """
    시각화를 위해 랜덤한 RGB 색상 튜플 (R, G, B)을 반환합니다.
    """
    return (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))

def get_font():
    """
    운영체제(OS)에 따라 한글이 지원되는 적절한 폰트 객체를 반환합니다.
    이미지에 텍스트를 그릴 때 깨짐을 방지하기 위함입니다.
    """
    font_size = 20
    
    try:
        if platform.system() == "Windows":
            # 윈도우: 맑은 고딕
            return ImageFont.truetype("malgun.ttf", font_size)
        elif platform.system() == "Darwin":  # macOS
            # 맥: 애플 고딕
            return ImageFont.truetype("AppleGothic.ttf", font_size)
        else:  # Linux 등
            # 기본 폰트 (한글 지원 안 될 수 있음)
            return ImageFont.load_default(size=font_size)
    except IOError:
        # 지정한 폰트 파일이 없을 경우 PIL 기본 폰트 사용
        return ImageFont.load_default()

def draw_image(img_pth, response_data):
    """
    이미지에 분석 결과를 그립니다.
    """
    img = Image.open(img_pth)
    draw = ImageDraw.Draw(img)

    block_list = response_data.get("analyzeResult").get("paragraphs")

    for block in block_list:
        color = random_color()
        content = block.get("content")
        polygon = block.get("boundingRegions")[0].get("polygon")
        pairs = list(zip(polygon[::2], polygon[1::2]))
        draw.polygon(pairs, outline=color)
        draw.text((pairs[0][0], pairs[0][1] - 20), content, fill=color, font=get_font())

    return img

def change_img(img_pth):
    """
    이미지 경로를 받아 분석 요청 후 결과를 그린 이미지를 반환합니다.
    """
    response_data = request_document_intelligence(img_pth)
    if response_data:
        img = draw_image(img_pth, response_data)
        return img
    return None

import gradio as gr

def run_ui():
    """
    Gradio UI를 실행합니다.
    """
    with gr.Blocks() as demo:
        gr.Markdown("# Azure Document Intelligence")

        with gr.Row():
            input_img = gr.Image(label="이미지 선택", type="filepath", width=500)
            output_img = gr.Image(label="결과 이미지", type="pil", interactive=False, width=500)

        input_img.change(fn=change_img, inputs=[input_img], outputs=[output_img])

    demo.launch()

if __name__ == "__main__":
    run_ui()
