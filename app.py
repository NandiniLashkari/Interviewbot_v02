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

# Set Tesseract path
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if not os.path.exists(pytesseract.pytesseract.tesseract_cmd):
    logger.error("Tesseract executable not found")
    raise FileNotFoundError("Tesseract executable not found")

# Set Poppler path
os.environ['PATH'] += os.pathsep + r"C:\Program Files\Poppler\bin"

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

    if 'resume' not in request.files or not all(key in request.form for key in ['name', 'phone', 'email', 'jobDesc']):
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
    job_description = request.form['jobDesc'].strip()

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
            'job_description': job_description,
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
            'job_description': job_description,
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

@app.route('/generate_questions', methods=['POST'])
def generate_questions():
    logger.debug(f"Received {request.method} request for /generate_questions from {request.remote_addr}")
    logger.debug(f"Headers: {request.headers}")
    logger.debug(f"Body: {request.get_json()}")
    try:
        data = request.get_json()
        job_description = data.get("job_description", "")
        previous_answer = data.get("previous_answer", "")
        num_questions = data.get("num_questions", 5)  # Default to 5 if not provided
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
        if not resume_text:
            response = make_response(jsonify({"status": "error", "error": "No resume text found"}), 404)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Content-Type'] = 'application/json'
            logger.debug("Response headers: %s", response.headers)
            return response

        prompt = (
            f"Generate {num_questions} interview questions for a candidate whose resume is:\n"
            f"{resume_text}\n\n"
            f"And for a job with this description:\n"
            f"{job_description}\n\n"
        )
        if previous_answer:
            prompt += (
                f"The candidate's previous answer was:\n"
                f"{previous_answer}\n\n"
                f"Include at least one follow-up question based on this answer.\n"
            )
        prompt += "Provide the questions in plain text, numbered 1 to {num_questions}."

        api_key = "AIzaSyB3K47UGq3dVh_VZZvNpbNuqfiB8v-F-ys"
        if not api_key:
            logger.error("GEMINI_API_KEY not set")
            response = make_response(jsonify({"status": "error", "error": "API key not configured"}), 500)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Content-Type'] = 'application/json'
            logger.debug("Response headers: %s", response.headers)
            return response
        genai.configure(api_key=api_key)
        try:
            model = genai.GenerativeModel("gemini-1.5-flash")  # Corrected model name
        except Exception as e:
            logger.error(f"Failed to load model: {str(e)}")
            response = make_response(jsonify({"status": "error", "error": str(e)}), 500)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Content-Type'] = 'application/json'
            logger.debug("Response headers: %s", response.headers)
            return response
        response = model.generate_content(prompt)

        questions_text = response.text if hasattr(response, "text") else None
        logger.info(f"Gemini raw output: {questions_text}")

        if not questions_text:
            raise Exception("No valid response from Gemini")

        lines = questions_text.strip().split('\n')
        questions_list = []
        for line in lines:
            line = re.sub(r'^[\-\*\•]\s*', '', line)
            line = re.sub(r'^\d+[\.\)]\s*', '', line)
            if line.strip():
                questions_list.append(line.strip())

        logger.info(f"Parsed questions: {questions_list}")
        if not questions_list or len(questions_list) < 2:
            raise Exception("Gemini returned insufficient questions")

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
                "Can you tell me about a challenging project you worked on?",
                "What are your key strengths for this role?",
                "How do you handle tight deadlines?",
                "Why are you interested in this position?",
                "Describe a time you worked in a team."
            ].slice(0, num_questions),
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

        api_key = "AIzaSyB3K47UGq3dVh_VZZvNpbNuqfiB8v-F-ys"
        if not api_key:
            logger.error("GEMINI_API_KEY not set")
            response = make_response(jsonify({"status": "error", "error": "API key not configured"}), 500)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Content-Type'] = 'application/json'
            logger.debug("Response headers: %s", response.headers)
            return response
        genai.configure(api_key=api_key)
        try:
            model = genai.GenerativeModel("gemini-2.0-flash")
        except Exception as e:
            logger.warning(f"Failed to load gemini-2.0-flash: {str(e)}. Falling back to gemini-1.5-flash")
            model = genai.GenerativeModel("gemini-1.5-flash")
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
                "phone": data.get("phone")
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

@app.route('/')
def serve_index():
    logger.debug(f"Serving index.html from {request.remote_addr}")
    return send_from_directory('static', 'index.html')

@app.route('/interview.html')
def serve_interview():
    logger.debug(f"Serving interview.html from {request.remote_addr}")
    return send_from_directory('static', 'interview.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('static', path)

def clear_user_data():
    with open("user.json", "w") as f:
        json.dump([], f)

def clear_answers_data():
    with open("answers.json", "w") as f:
        json.dump([], f)

# Call them:
clear_user_data()
clear_answers_data()

@app.route('/generate_summary', methods=['POST'])
def generate_summary():
    try:
        answers_file = 'answers.json'
        if not os.path.exists(answers_file):
            return jsonify({"status": "error", "error": "No answers found"}), 404

        with open(answers_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if not data or not isinstance(data, list):
            return jsonify({"status": "error", "error": "Answers are empty"}), 404

        last_answers = data[-1]["answers"]

        # Very basic scoring rules
        communication = min(10, sum(len(a.split()) for a in last_answers) // 20)
        confidence = 8  # example
        domain_knowledge = 7  # example
        overall_score = round((communication + confidence + domain_knowledge) / 3, 1)

        strengths = [
            "Clear explanations",
            "Structured answers"
        ]
        weaknesses = [
            "Could improve technical depth",
            "Add more examples"
        ]
        feedback = "You communicated well but adding more technical details would improve your impact."

        report = {
            "communication": communication,
            "confidence": confidence,
            "domain_knowledge": domain_knowledge,
            "overall_score": overall_score,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "feedback": feedback
        }

        with open("static/interview_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        return jsonify({"status": "success"}), 200

    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500




if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)