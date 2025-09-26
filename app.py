
from flask import Flask, request, jsonify, make_response, send_from_directory
from PIL import Image
import pytesseract
import pdf2image
import os
import re
from pathlib import Path
from flask_cors import CORS
import uuid
import pandas as pd
import logging
import json
import google.generativeai as genai
import requests
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO

app = Flask(__name__, static_folder='static')
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": "*"
    }
})

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configure Tesseract/Poppler
tesseract_cmd = os.getenv("TESSERACT_CMD")
if tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

poppler_path_env = os.getenv("POPPLER_PATH")
if poppler_path_env:
    os.environ['PATH'] += os.pathsep + poppler_path_env

# ElevenLabs configuration
ELEVENLABS_API_KEY = 'sk_eb003f5946468161b119115a09c2396fa2f8a4b387892aef'
ELEVENLABS_VOICE_ID = '6JsmTroalVewG1gA6Jmw'

# Blacklist and titles
BLACKLIST = {'I', 'me', 'you', 'he', 'she', 'it', 'we', 'they', 'the', 'a', 'an', 'and', 'or', 'but', 'good', 'great', 'bad', 'nice', 'big', 'small', 'new', 'old'}
TITLES = {'Mr', 'Mrs', 'Ms', 'Miss', 'Dr', 'Prof', 'Sir'}
ALLOWED_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png'}

def allowed_file(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS

def extract_name_from_text(text, df):
    try:
        for title in TITLES:
            text = re.sub(rf'\b{title}\b\.?\s*', '', text, flags=re.IGNORECASE)
        name_match = re.search(r'(?:Name|Full Name|Cardholder)\s*[:\-]\s*([A-Z][a-z]+(?:\s[A-Z][a-z]+){0,2})', text, re.IGNORECASE)
        if name_match:
            name = name_match.group(1).split()[0]
            logger.info(f"Extracted name via regex: {name}")
            return name
        name_candidates = []
        for i, candidate in enumerate(df['text']):
            for title in TITLES:
                candidate = re.sub(rf'\b{title}\b\.?\s*', '', candidate, flags=re.IGNORECASE)
            match = re.match(r'\b[A-Z][a-z]+(?:\s[A-Z][a-z]+){0,2}\b', candidate)
            if match:
                candidate = match.group(0)
                words = candidate.split()
                if all(word not in BLACKLIST for word in words):
                    name_candidates.append({
                        'name': words[0],
                        'height': df['height'].iloc[i],
                        'full_name': candidate
                    })
        if name_candidates:
            largest = max(name_candidates, key=lambda x: x['height'])
            logger.info(f"Detected name: {largest['name']} (height: {largest['height']}, full: {largest['full_name']})")
            return largest['name']
        logger.warning("No valid name found, using default: User")
        return 'User'
    except Exception as e:
        logger.error(f"Error in extract_name_from_text: {str(e)}")
        raise

def save_to_json(data):
    json_file = 'user.json'
    try:
        existing_data = []
        if os.path.exists(json_file):
            with open(json_file, 'r', encoding='utf-8') as f:
                try:
                    existing_data = json.load(f)
                    if not isinstance(existing_data, list):
                        existing_data = [existing_data]
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON in user.json, starting with empty list")
        existing_data.append(data)
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, indent=2)
        logger.info(f"Successfully saved data to {json_file}")
    except Exception as e:
        logger.error(f"Failed to save data to {json_file}: {str(e)}")
        raise

@app.route('/submit_user_data', methods=['POST', 'OPTIONS'])
def submit_user_data():
    logger.debug(f"Received {request.method} request for /submit_user_data from {request.remote_addr}")
    logger.debug(f"Request headers: {request.headers}")
    logger.debug(f"Form data: {request.form}")
    logger.debug(f"Files: {request.files}")

    if request.method == 'OPTIONS':
        response = make_response()
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = '*'
        response.headers['Access-Control-Max-Age'] = '86400'
        logger.debug("Returning 204 for OPTIONS request with headers: %s", response.headers)
        return response, 204

    if 'resume' not in request.files or not all(key in request.form for key in ['name', 'phone', 'email', 'jobDesc', 'company']):
        logger.error("Missing required fields")
        response = make_response(jsonify({'error': 'Missing required fields', 'status': 'error'}), 400)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Content-Type'] = 'application/json'
        logger.debug("Response headers: %s", response.headers)
        return response

    file = request.files['resume']
    name = request.form['name'].strip()
    phone = request.form['phone'].strip()
    email = request.form['email'].strip()
    company = request.form['company'].strip()
    job_description = request.form['jobDesc'].strip()
    company_details = f"{company}, a leader in AR/VR innovation, focused on immersive experiences."

    if file.filename == '':
        logger.error("No selected file")
        response = make_response(jsonify({'error': 'No selected file', 'status': 'error'}), 400)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Content-Type'] = 'application/json'
        logger.debug("Response headers: %s", response.headers)
        return response
    if not allowed_file(file.filename):
        logger.error(f"Invalid file type: {file.filename}")
        response = make_response(jsonify({'error': 'Invalid file type. Only PDF, JPG, JPEG, and PNG are allowed', 'status': 'error'}), 400)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Content-Type'] = 'application/json'
        logger.debug("Response headers: %s", response.headers)
        return response

    try:
        unique_id = str(uuid.uuid4())
        file_path = f"temp_{unique_id}_{file.filename}"
        file.save(file_path)
        logger.info(f"Saved file: {file_path}")

        if file.filename.lower().endswith('.pdf'):
            poppler_dir = os.getenv("POPPLER_PATH")
            if poppler_dir and os.path.isdir(poppler_dir):
                images = pdf2image.convert_from_path(file_path, poppler_path=poppler_dir)
            else:
                images = pdf2image.convert_from_path(file_path)
            if not images:
                raise ValueError("No images extracted from PDF")
            image = images[0]
        else:
            image = Image.open(file_path)
        logger.info("Image loaded successfully")

        image = image.convert('L')
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT, config='--psm 6')
        df = pd.DataFrame(data)
        df = df[df['text'].str.strip().astype(bool)]
        df['text'] = df['text'].str.strip()
        df['height'] = df['height'].astype(float)
        text = pytesseract.image_to_string(image, config='--psm 6')
        logger.info(f"Extracted text: {text[:200]}...")

        detected_name = extract_name_from_text(text, df)
        final_name = name if name else detected_name

        user_data = {
            'name': final_name,
            'phone': phone,
            'email': email,
            'company': company,
            'job_description': job_description,
            'company_details': company_details,
            'resume_text': text
        }
        save_to_json(user_data)

        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info("Temporary file removed")

        response_data = {
            'name': final_name,
            'phone': phone,
            'email': email,
            'company': company,
            'job_description': job_description,
            'company_details': company_details,
            'resume_text': text,
            'status': 'success'
        }
        logger.debug(f"Preparing response: {response_data}")
        response = make_response(jsonify(response_data), 200)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Content-Type'] = 'application/json'
        logger.debug("Response headers: %s", response.headers)
        return response

    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        response = make_response(jsonify({'error': str(e), 'status': 'error'}), 500)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Content-Type'] = 'application/json'
        logger.debug("Response headers: %s", response.headers)
        return response

@app.route('/get_user_data', methods=['GET'])
def get_user_data():
    logger.debug(f"Received {request.method} request for /get_user_data from {request.remote_addr}")
    json_file = 'user.json'
    try:
        if os.path.exists(json_file):
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info("Retrieved user.json data")
            response = make_response(jsonify({'status': 'success', 'data': data}), 200)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Content-Type'] = 'application/json'
            logger.debug("Response headers: %s", response.headers)
            return response
        logger.warning("user.json not found")
        response = make_response(jsonify({'status': 'error', 'error': 'No user data found'}), 404)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Content-Type'] = 'application/json'
        logger.debug("Response headers: %s", response.headers)
        return response
    except Exception as e:
        logger.error(f"Error reading user.json: {str(e)}")
        response = make_response(jsonify({'error': str(e), 'status': 'error'}), 500)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Content-Type'] = 'application/json'
        logger.debug("Response headers: %s", response.headers)
        return response

@app.route('/tts', methods=['POST'])
def text_to_speech():
    logger.debug(f"Received {request.method} request for /tts from {request.remote_addr}")
    try:
        data = request.get_json()
        text = data.get("text", "")
        if not text:
            logger.error("No text provided for TTS")
            response = make_response(jsonify({"status": "error", "error": "Text is required"}), 400)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Content-Type'] = 'application/json'
            return response

        headers = {
            'accept': 'audio/mpeg',
            'xi-api-key': ELEVENLABS_API_KEY,
            'Content-Type': 'application/json'
        }
        payload = {
            'text': text,
            'model_id': 'eleven_monolingual_v1',
            'voice_settings': {
                'stability': 0.5,
                'similarity_boost': 0.5
            }
        }
        logger.debug(f"Sending request to ElevenLabs: {text[:50]}...")
        response = requests.post(
            f'https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}',
            headers=headers,
            json=payload
        )
        
        if response.status_code != 200:
            logger.error(f"ElevenLabs API error: {response.status_code} - {response.text}")
            response = make_response(jsonify({"status": "error", "error": f"ElevenLabs API error: {response.status_code} - {response.text}"}), response.status_code)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Content-Type'] = 'application/json'
            return response

        response = make_response(response.content)
        response.headers['Content-Type'] = 'audio/mpeg'
        response.headers['Access-Control-Allow-Origin'] = '*'
        logger.debug("Successfully generated TTS audio")
        return response
    except Exception as e:
        logger.error(f"Error in TTS endpoint: {str(e)}")
        response = make_response(jsonify({"status": "error", "error": str(e)}), 500)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Content-Type'] = 'application/json'
        return response

@app.route('/generate_questions', methods=['POST'])
def generate_questions():
    logger.debug(f"Received {request.method} request for /generate_questions from {request.remote_addr}")
    logger.debug(f"Headers: {request.headers}")
    logger.debug(f"Body: {request.get_json()}")
    try:
        data = request.get_json()
        job_description = data.get("job_description", "")
        previous_answer = data.get("previous_answer", "")
        num_questions = data.get("num_questions", 5)
        is_follow_up = data.get("is_follow_up", False)
        if not job_description:
            response = make_response(jsonify({"status": "error", "error": "Job description is required"}), 400)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Content-Type'] = 'application/json'
            logger.debug("Response headers: %s", response.headers)
            return response

        json_file = 'user.json'
        if not os.path.exists(json_file):
            response = make_response(jsonify({"status": "error", "error": "No user data found"}), 404)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Content-Type'] = 'application/json'
            logger.debug("Response headers: %s", response.headers)
            return response

        with open(json_file, 'r', encoding='utf-8') as f:
            user_data = json.load(f)

        if not isinstance(user_data, list) or len(user_data) == 0:
            response = make_response(jsonify({"status": "error", "error": "No valid resume data found"}), 404)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Content-Type'] = 'application/json'
            logger.debug("Response headers: %s", response.headers)
            return response

        resume_text = user_data[-1].get("resume_text", "")
        company_details = user_data[-1].get("company_details", "TechCorp, a leader in AR/VR innovation.")
        if not resume_text:
            response = make_response(jsonify({"status": "error", "error": "No resume text found"}), 404)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Content-Type'] = 'application/json'
            logger.debug("Response headers: %s", response.headers)
            return response

        base_prompt = (
            f"Generate {num_questions} short and direct interview questions for a candidate whose resume is:\n"
            f"{resume_text}\n\n"
            f"For a job with this description:\n"
            f"{job_description}\n\n"
            f"And for a company described as:\n"
            f"{company_details}\n\n"
            f"Questions must be tailored to specific details from the candidate's resume, such as skills, experiences, or projects mentioned, and how they relate to the job description.\n"
            f"Make the questions realistic like a human interviewer: include a mix of technical, behavioral, scenario-based (e.g., 'What would you do if...'), experience-based, and 1-2 company/role-interest questions (e.g., 'Why do you want to work at this company?', 'Why are you excited about this role?'). Ensure variety, progression in difficulty, and relevance to the resume, job, and company. Avoid repetitions and make them engaging.\n"
            f"Each question must be numbered (e.g., '1. Why are you excited about this role?').\n"
        )
        if not is_follow_up:
            base_prompt += (
                f"The first question must be about the candidate's interest in the role or company (e.g., '1. Why are you excited about this {job_description} role at our company?').\n"
            )
        else:
            base_prompt += (
                f"These are follow-up questions based on the previous answer. Avoid repeating introductory, background, or company-interest questions. Probe deeper into the previous answer with specific, relevant questions, including scenario-based follow-ups if applicable. Incorporate resume details where relevant to the previous answer.\n"
            )
        
        if previous_answer:
            base_prompt += f"The candidate's previous answer was:\n{previous_answer}\n\nGenerate follow-ups that probe deeper, ask for examples, or address gaps. Include scenario-based questions related to the answer.\n"
        
        base_prompt += f"Provide the questions in plain text, numbered 1 to {num_questions}, each question under 15 words. Ensure no duplicates and high variety."

        api_key = "AIzaSyDov9DCp1LBEIeIFDNc-KtWEnfp1GoBNqQ"
        if not api_key:
            logger.error("GEMINI_API_KEY not set")
            response = make_response(jsonify({"status": "error", "error": "API key not configured"}), 500)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Content-Type'] = 'application/json'
            logger.debug("Response headers: %s", response.headers)
            return response
        genai.configure(api_key=api_key)
        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
        except Exception as e:
            logger.error(f"Failed to load model: {str(e)}")
            response = make_response(jsonify({"status": "error", "error": str(e)}), 400)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Content-Type'] = 'application/json'
            logger.debug("Response headers: %s", response.headers)
            return response
        response = model.generate_content(base_prompt)

        questions_text = response.text if hasattr(response, "text") else None
        logger.info(f"Gemini raw output: {questions_text}")

        if not questions_text:
            raise Exception("No valid response from Gemini")

        lines = questions_text.strip().split('\n')
        questions_list = []
        for line in lines:
            line = line.strip()
            if line and re.match(r'^\d+\.\s*.+', line):  # Ensure line starts with a number and question
                questions_list.append(line)

        logger.info(f"Parsed questions: {questions_list}")
        if not questions_list or len(questions_list) < num_questions:
            raise Exception("Gemini returned insufficient or malformed questions")

        response = make_response(jsonify({
            "status": "success",
            "questions": questions_list
        }), 200)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Content-Type'] = 'application/json'
        logger.debug("Response headers: %s", response.headers)
        return response
    except Exception as e:
        logger.warning(f"Fallback due to error: {str(e)}")
        response = make_response(jsonify({
            "status": "fallback",
            "questions": [
                "1. Why are you interested in this role?",
                "2. What are your key strengths for this role?",
                "3. How do you handle tight deadlines?",
                "4. Why do you want to work at our company?",
                "5. Describe a time you worked in a team."
            ][0:num_questions],
            "error": str(e)
        }), 200)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Content-Type'] = 'application/json'
        logger.debug("Response headers: %s", response.headers)
        return response

@app.route('/generate_response', methods=['POST'])
def generate_response():
    logger.debug(f"Received {request.method} request for /generate_response from {request.remote_addr}")
    try:
        data = request.get_json()
        prompt = data.get("prompt", "")
        if not prompt:
            response = make_response(jsonify({"status": "error", "error": "Prompt is required"}), 400)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Content-Type'] = 'application/json'
            logger.debug("Response headers: %s", response.headers)
            return response

        api_key = "AIzaSyDov9DCp1LBEIeIFDNc-KtWEnfp1GoBNqQ"
        if not api_key:
            logger.error("GEMINI_API_KEY not set")
            response = make_response(jsonify({"status": "error", "error": "API key not configured"}), 500)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Content-Type'] = 'application/json'
            logger.debug("Response headers: %s", response.headers)
            return response
        genai.configure(api_key=api_key)
        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
        except Exception as e:
            logger.error(f"Failed to load model: {str(e)}")
            response = make_response(jsonify({"status": "error", "error": str(e)}), 500)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Content-Type'] = 'application/json'
            logger.debug("Response headers: %s", response.headers)
            return response
        response = model.generate_content(prompt)

        response_text = response.text if hasattr(response, "text") else None
        if not response_text:
            raise Exception("No valid response from Gemini")

        response = make_response(jsonify({
            "status": "success",
            "response": response_text
        }), 200)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Content-Type'] = 'application/json'
        logger.debug("Response headers: %s", response.headers)
        return response
    except Exception as e:
        logger.error(f"Error generating response: {str(e)}")
        response = make_response(jsonify({"status": "error", "error": str(e)}), 500)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Content-Type'] = 'application/json'
        logger.debug("Response headers: %s", response.headers)
        return response

@app.route('/store_answers', methods=['POST'])
def store_answers():
    logger.debug(f"Received {request.method} request for /store_answers from {request.remote_addr}")
    try:
        data = request.get_json()
        answers = data.get("answers", [])
        if not answers:
            response = make_response(jsonify({"status": "error", "error": "No answers provided"}), 400)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Content-Type'] = 'application/json'
            logger.debug("Response headers: %s", response.headers)
            return response
        
        answers_file = 'answers.json'
        existing = []
        if os.path.exists(answers_file):
            with open(answers_file, 'r', encoding='utf-8') as f:
                existing = json.load(f)
                if not isinstance(existing, list):
                    existing = []
        
        existing.append({
            "timestamp": pd.Timestamp.now().isoformat(),
            "answers": answers
        })

        with open(answers_file, 'w', encoding='utf-8') as f:
            json.dump(existing, f, indent=2)

        logger.info(f"Saved answers: {answers}")
        response = make_response(jsonify({"status": "success"}), 200)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Content-Type'] = 'application/json'
        logger.debug("Response headers: %s", response.headers)
        return response
    except Exception as e:
        logger.error(f"Error storing answers: {str(e)}")
        response = make_response(jsonify({"status": "error", "error": str(e)}), 500)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Content-Type'] = 'application/json'
        logger.debug("Response headers: %s", response.headers)
        return response

@app.route('/confirm_user_data', methods=['POST'])
def confirm_user_data():
    logger.debug(f"Received {request.method} request for /confirm_user_data from {request.remote_addr}")
    try:
        data = request.get_json()
        with open('user.json', 'w', encoding='utf-8') as f:
            json.dump({
                "name": data.get("name"),
                "email": data.get("email"),
                "phone": data.get("phone"),
                "company_details": data.get("company_details")
            }, f)
        response = make_response(jsonify({"status": "success"}), 200)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Content-Type'] = 'application/json'
        logger.debug("Response headers: %s", response.headers)
        return response
    except Exception as e:
        logger.error(f"Error confirming user data: {str(e)}")
        response = make_response(jsonify({"status": "error", "error": str(e)}), 500)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Content-Type'] = 'application/json'
        logger.debug("Response headers: %s", response.headers)
        return response

@app.route('/generate_pdf', methods=['GET'])
def generate_pdf():
    logger.debug(f"Received {request.method} request for /generate_pdf from {request.remote_addr}")
    try:
        report_file = 'static/interview_report.json'
        if not os.path.exists(report_file):
            logger.error("Interview report not found")
            response = make_response(jsonify({"status": "error", "error": "Report not found"}), 404)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Content-Type'] = 'application/json'
            return response

        with open(report_file, 'r', encoding='utf-8') as f:
            report = json.load(f)

        json_file = 'user.json'
        user_data = []
        if os.path.exists(json_file):
            with open(json_file, 'r', encoding='utf-8') as f:
                try:
                    user_data = json.load(f)
                    if not isinstance(user_data, list):
                        user_data = [user_data]
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON in user.json, using empty list")
                    user_data = []

        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        c.setFont("Helvetica", 12)
        y = 750
        c.drawString(100, y, "Interview Report")
        y -= 30
        c.drawString(100, y, f"Name: {user_data[-1]['name'] if user_data else 'Unknown'}")
        y -= 20
        c.drawString(100, y, f"Company: {user_data[-1]['company'] if user_data else 'Unknown'}")
        y -= 20
        c.drawString(100, y, f"Date: {pd.Timestamp.now().strftime('%Y-%m-%d')}")
        y -= 30
        c.drawString(100, y, "Scores:")
        y -= 20
        c.drawString(120, y, f"Communication: {report['communication']}/10")
        y -= 20
        c.drawString(120, y, f"Confidence: {report['confidence']}/10")
        y -= 20
        c.drawString(120, y, f"Domain Knowledge: {report['domain_knowledge']}/10")
        y -= 20
        c.drawString(120, y, f"Overall Score: {report['overall_score']}/10")
        y -= 30
        c.drawString(100, y, "Strengths:")
        for strength in report['strengths']:
            y -= 20
            c.drawString(120, y, f"- {strength}")
        y -= 30
        c.drawString(100, y, "Weaknesses:")
        for weakness in report['weaknesses']:
            y -= 20
            c.drawString(120, y, f"- {weakness}")
        y -= 30
        c.drawString(100, y, "Feedback:")
        y -= 20
        text = c.beginText(120, y)
        text.setFont("Helvetica", 12)
        for line in report['feedback'].split('\n'):
            text.textLine(line)
            y -= 15
        c.drawText(text)
        c.showPage()
        c.save()
        buffer.seek(0)

        response = make_response(buffer.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'attachment; filename=interview_report.pdf'
        response.headers['Access-Control-Allow-Origin'] = '*'
        logger.debug("Generated PDF successfully")
        return response
    except Exception as e:
        logger.error(f"Error generating PDF: {str(e)}")
        response = make_response(jsonify({"status": "error", "error": str(e)}), 500)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Content-Type'] = 'application/json'
        return response

@app.route('/')
def serve_index():
    logger.debug(f"Serving index.html from {request.remote_addr}")
    return send_from_directory('static', 'index.html')

@app.route('/interview.html')
def serve_interview():
    logger.debug(f"Serving interview.html from {request.remote_addr}")
    return send_from_directory('static', 'interview.html')

@app.route('/summary.html')
def serve_summary():
    logger.debug(f"Serving summary.html from {request.remote_addr}")
    return send_from_directory('static', 'summary.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('static', path)

def clear_user_data():
    with open("user.json", "w") as f:
        json.dump([], f)

def clear_answers_data():
    with open("answers.json", "w") as f:
        json.dump([], f)

clear_user_data()
clear_answers_data()

@app.route('/generate_summary', methods=['POST'])
def generate_summary():
    logger.debug(f"Received {request.method} request for /generate_summary from {request.remote_addr}")
    try:
        answers_file = 'answers.json'
        if not os.path.exists(answers_file):
            return jsonify({"status": "error", "error": "No answers found"}), 404

        with open(answers_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if not data or not isinstance(data, list):
            return jsonify({"status": "error", "error": "Answers are empty"}), 404

        last_answers = data[-1]["answers"]

        json_file = 'user.json'
        user_data = []
        if os.path.exists(json_file):
            with open(json_file, 'r', encoding='utf-8') as f:
                try:
                    user_data = json.load(f)
                    if not isinstance(user_data, list):
                        user_data = [user_data]
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON in user.json, using empty list")
                    user_data = []

        resume_text = user_data[-1].get("resume_text", "") if user_data else ""
        job_description = user_data[-1].get("job_description", "") if user_data else ""
        company_details = user_data[-1].get("company_details", "") if user_data else ""

        all_answers_text = "\n".join([f"Q{i+1}: {ans['question']}\nA{i+1}: {ans['answer']}" for i, ans in enumerate(last_answers)])

        summary_prompt = f"""
            You are an experienced interviewer evaluating a candidate's interview based on their answers.
            The candidate's resume is:
            {resume_text}
            The job description is:
            {job_description}
            The company is:
            {company_details}
            Interview transcript:
            {all_answers_text}
            Provide a JSON object with the following:
            - communication: Score out of 10 (integer, based on clarity, coherence, and articulation in answers)
            - confidence: Score out of 10 (integer, based on assertiveness and composure in answers)
            - domain_knowledge: Score out of 10 (integer, based on technical accuracy and relevance to job description)
            - overall_score: Average of the above scores (integer)
            - strengths: List of 3-5 specific strengths (strings, 1-2 sentences each, tied to answers, resume, or job requirements)
            - weaknesses: List of 3-5 specific areas to improve (strings, 1-2 sentences each, with actionable advice)
            - feedback: Detailed feedback (string, 3-5 sentences, summarizing performance and offering actionable advice)
            Ensure scores reflect the quality of answers relative to the resume and job description.
            Strengths and weaknesses must be specific, tied to the transcript, and useful for candidate improvement.
        """

        api_key = "AIzaSyDov9DCp1LBEIeIFDNc-KtWEnfp1GoBNqQ"
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(summary_prompt)
        response_text = response.text.strip()

        try:
            report = json.loads(response_text)
        except json.JSONDecodeError:
            logger.error("Invalid JSON from Gemini summary response")
            return jsonify({"status": "error", "error": "Failed to parse summary"}), 500

        with open("static/interview_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        return jsonify({"status": "success", "report": report}), 200
    except Exception as e:
        logger.error(f"Error generating summary: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500

#added 5000 port
if __name__ == '__main__':
    port = int(os.getenv('PORT', '5000'))
    debug_flag = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(debug=debug_flag, host='0.0.0.0', port=port)
