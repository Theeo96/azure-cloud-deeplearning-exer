import gradio as gr
import os
import requests
import time
import json
import datetime
from dotenv import load_dotenv
from openai import AzureOpenAI
from PIL import Image, ImageDraw, ImageFont, ImageOps
import io
import random
import platform

# Load environment variables
load_dotenv()

# Configuration
STT_ENDPOINT = os.getenv("STT_KR_ENDPOINT")
TTS_ENDPOINT = os.getenv("TTS_KR_ENDPOINT")
SPEECH_API_KEY = os.getenv("SPEECH_STUDIO_API_KEY")
DOC_INT_ENDPOINT = os.getenv("DOCUMENT_INTELLIGENCE_ENDPOINT")
DOC_INT_API_KEY = os.getenv("DOCUMENT_INTELLIGENCE_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")

# Initialize Azure OpenAI Client
client = AzureOpenAI(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_API_KEY,
    api_version="2024-05-01-preview"
)

# --- Helper Functions ---

def request_stt(audio_path):
    if not audio_path:
        return None
    
    headers = {
        "Content-Type": "audio/wav",
        "Ocp-Apim-Subscription-Key": SPEECH_API_KEY
    }
    
    try:
        with open(audio_path, "rb") as audio_file:
            audio_data = audio_file.read()
            
        response = requests.post(STT_ENDPOINT, headers=headers, data=audio_data)
        if response.status_code != 200:
            print(f"STT Error: {response.status_code} {response.text}")
            return None
            
        return response.json().get('DisplayText')
    except Exception as e:
        print(f"STT Exception: {e}")
        return None

def request_tts(text):
    if not text:
        return None
        
    headers = {
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": "audio-16khz-128kbitrate-mono-mp3",
        "Ocp-Apim-Subscription-Key": SPEECH_API_KEY
    }
    
    body = f"""
    <speak version='1.0' xml:lang='ko-KR'>
        <voice xml:lang='ko-KR' xml:gender='Male' name='ko-KR-InJoonNeural'>
            {text}
        </voice>
    </speak>
    """
    
    try:
        response = requests.post(TTS_ENDPOINT, headers=headers, data=body.strip().encode('utf-8'))
        if response.status_code != 200:
            print(f"TTS Error: {response.status_code} {response.text}")
            return None
            
        now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"tts_{now}.mp3" # Changed to mp3 based on header, though previous code used wav extension for mp3 content
        
        with open(file_name, "wb") as result_file:
            result_file.write(response.content)
            
        return file_name
    except Exception as e:
        print(f"TTS Exception: {e}")
        return None

def request_document_intelligence(img_path):
    if not img_path:
        return None

    headers = {
        "Content-Type": "image/*",
        "Ocp-Apim-Subscription-Key": DOC_INT_API_KEY
    }
    
    try:
        with open(img_path, "rb") as img_file:
            img_data = img_file.read()
            
        response = requests.post(DOC_INT_ENDPOINT, headers=headers, data=img_data)
        
        if response.status_code != 202:
            print(f"DocInt Error: {response.status_code} {response.text}")
            return None
            
        url = response.headers['Operation-Location']
        
        while True:
            result_response = requests.get(url, headers={"Ocp-Apim-Subscription-Key": DOC_INT_API_KEY})
            if result_response.status_code != 200:
                print(f"DocInt Polling Error: {result_response.status_code}")
                return None
                
            result_json = result_response.json()
            status = result_json.get('status')
            
            if status == 'running':
                time.sleep(1)
                continue
            elif status == 'succeeded':
                return result_json
            else:
                print(f"DocInt Failed: {status}")
                return None
    except Exception as e:
        print(f"DocInt Exception: {e}")
        return None

# --- Visualization Helpers ---
def random_color():
    return (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))

def get_font():
    font_size = 20
    try:
        if platform.system() == "Windows":
            return ImageFont.truetype("malgun.ttf", font_size)
        elif platform.system() == "Darwin":
            return ImageFont.truetype("AppleGothic.ttf", font_size)
        else:
            return ImageFont.load_default()
    except IOError:
        return ImageFont.load_default()

def draw_analysis_on_image(img_path, analysis_result):
    if not analysis_result:
        return img_path
        
    try:
        img = Image.open(img_path)
        draw = ImageDraw.Draw(img)
        
        # Draw paragraphs
        if "analyzeResult" in analysis_result and "paragraphs" in analysis_result["analyzeResult"]:
            for block in analysis_result["analyzeResult"]["paragraphs"]:
                color = random_color()
                content = block.get("content")
                if "boundingRegions" in block:
                    polygon = block["boundingRegions"][0].get("polygon")
                    if polygon:
                        pairs = list(zip(polygon[::2], polygon[1::2]))
                        draw.polygon(pairs, outline=color, width=3)
                        # Optional: Draw text (might be cluttered)
                        # draw.text((pairs[0][0], pairs[0][1] - 20), content, fill=color, font=get_font())
        return img
    except Exception as e:
        print(f"Drawing Error: {e}")
        return img_path

# --- Main Logic ---

def get_stt_result(audio_path):
    if not audio_path:
        return ""
    text = request_stt(audio_path)
    return text if text else "(음성 인식 실패)"

def process_interaction(audio_path, image_path, history, stt_text):
    print(f"DEBUG: process_interaction started. Audio: {audio_path}, Image: {image_path}, STT: {stt_text}")
    
    # Flip image if it exists to match the CSS un-mirrored view
    if image_path:
        try:
            img = Image.open(image_path)
            img = ImageOps.mirror(img)
            # Save with a suffix to distinguish
            base, ext = os.path.splitext(image_path)
            flipped_image_path = f"{base}_flipped{ext}"
            img.save(flipped_image_path)
            image_path = flipped_image_path
            print(f"DEBUG: Image flipped and saved to {image_path}")
        except Exception as e:
            print(f"DEBUG: Failed to flip image: {e}")

    if history is None:
        history = []
        
    # 1. STT
    user_text = ""
    if stt_text and stt_text.strip() and stt_text != "(음성 인식 실패)":
        user_text = stt_text
    elif audio_path:
        user_text = request_stt(audio_path)
        if not user_text:
            user_text = "(음성 인식 실패)"
    else:
        # No audio and no text
        return history, history, None, image_path, ""

    # Add user message to history
    history.append({"role": "user", "content": user_text})
    
    # 2. LLM Setup
    tools = [
        {
            "type": "function",
            "function": {
                "name": "analyze_document",
                "description": "Analyze the document in the current view/image to extract text and data.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }
    ]
    
    # Prepare messages for LLM
    messages = [{"role": "system", "content": "You are a helpful assistant for a HoloLens user. The user is looking at a document. If the user asks about the document content, use the 'analyze_document' tool. Summarize the document content in Korean."}]
    for msg in history:
        messages.append(msg)
        
    try:
        # First Call
        print(f"DEBUG: Calling LLM (First Call)... Endpoint: {AZURE_OPENAI_ENDPOINT}")
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini", 
                messages=messages,
                tools=tools,
                tool_choice="auto"
            )
        except Exception as e:
            print(f"DEBUG: LLM First Call Failed: {e}")
            raise e
            
        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls
        
        final_content = ""
        
        if tool_calls:
            print("DEBUG: Tool calls detected.")
            messages.append(response_message)
            
            for tool_call in tool_calls:
                if tool_call.function.name == "analyze_document":
                    if image_path:
                        print(f"DEBUG: Analyzing document image: {image_path}")
                        # Call Document Intelligence
                        doc_result = request_document_intelligence(image_path)
                        
                        # Visualize
                        annotated_img = draw_analysis_on_image(image_path, doc_result)
                        # Save annotated image to update UI
                        annotated_img_path = f"annotated_{int(time.time())}.png"
                        annotated_img.save(annotated_img_path)
                        image_path = annotated_img_path # Update image path to show annotated version
                        
                        # Extract text for LLM
                        doc_content = ""
                        if doc_result and "analyzeResult" in doc_result:
                            doc_content = doc_result["analyzeResult"].get("content", "")
                        
                        function_response = json.dumps({"content": doc_content}, ensure_ascii=False)
                    else:
                        print("DEBUG: No image path provided for analysis.")
                        function_response = json.dumps({"error": "No image available to analyze."})
                        
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": "analyze_document",
                        "content": function_response
                    })
            
            # Second Call
            print("DEBUG: Calling LLM (Second Call)...")
            try:
                second_response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages
                )
                final_content = second_response.choices[0].message.content
            except Exception as e:
                print(f"DEBUG: LLM Second Call Failed: {e}")
                raise e
        else:
            final_content = response_message.content
            
        history.append({"role": "assistant", "content": final_content})
        
        # 3. TTS
        print("DEBUG: Requesting TTS...")
        audio_response_path = request_tts(final_content)
        
        # Debugging: Print history to check format
        print(f"DEBUG: history before return: {history}")
        
        # Return history directly (list of dicts) as Chatbot in this version expects messages
        return history, history, audio_response_path, image_path, user_text
        
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        print(f"DEBUG: Exception occurred: {error_msg}")
        history.append({"role": "assistant", "content": error_msg})
        return history, history, None, image_path, user_text

# --- Gradio UI ---

custom_css = """
#webcam_input video {
    transform: scaleX(1) !important;
}
"""

with gr.Blocks(title="HoloLens Doc Assistant") as demo:
    gr.HTML(f"<style>{custom_css}</style>")
    gr.Markdown("# 🥽 HoloLens Document Assistant")
    gr.Markdown("문서를 카메라에 비추고 음성으로 질문하세요. (예: '이 문서 내용 요약해줘')")
    
    with gr.Row():
        with gr.Column(scale=1):
            # Input Area
            # Removed mirror_webcam argument as it caused TypeError. 
            # Added elem_id="webcam_input" and CSS to handle mirroring.
            img_input = gr.Image(sources=["webcam", "upload"], type="filepath", label="HoloLens View (Webcam)", elem_id="webcam_input")
            audio_input = gr.Audio(sources=["microphone"], type="filepath", label="Voice Command")
            stt_output = gr.Textbox(label="Recognized Text", interactive=False) # Added STT output
            btn_submit = gr.Button("Send Command", variant="primary")
            
        with gr.Column(scale=1):
            # Output Area
            chatbot = gr.Chatbot(label="Conversation History")
            audio_output = gr.Audio(label="Assistant Voice", autoplay=True)
    
    # State for history (List of dicts for LLM context)
    state_history = gr.State([])
    
    # Real-time STT trigger
    audio_input.stop_recording(fn=get_stt_result, inputs=audio_input, outputs=stt_output)
    audio_input.upload(fn=get_stt_result, inputs=audio_input, outputs=stt_output)
    
    btn_submit.click(
        fn=process_interaction,
        inputs=[audio_input, img_input, state_history, stt_output],
        outputs=[chatbot, state_history, audio_output, img_input, stt_output]
    )

from pyngrok import ngrok
import os
import sys

# ... (existing imports)

# ... (existing code)

if __name__ == "__main__":
    # ngrok setup
    ngrok_auth_token = os.getenv("NGROK_AUTH_TOKEN")
    if ngrok_auth_token:
        ngrok.set_auth_token(ngrok_auth_token)
    else:
        print("Warning: NGROK_AUTH_TOKEN not found in .env. Ngrok may fail if not authenticated.")

    port = 7860
    public_url = ngrok.connect(port).public_url
    print(f" * ngrok tunnel \"{public_url}\" -> \"http://127.0.0.1:{port}\"")
    
    demo.launch(server_port=port)
