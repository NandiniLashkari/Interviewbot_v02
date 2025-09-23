---
title: InterviewBot - AI-Powered Virtual Interview Assistant
emoji: 🤖
colorFrom: blue
colorTo: purple
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
license: mit
short_description: An AI-powered virtual interview assistant with 3D character interaction
---

# InterviewBot - AI-Powered Virtual Interview Assistant

InterviewBot is an innovative virtual interview platform that combines AI-powered question generation, 3D character interaction, and real-time speech recognition to provide a comprehensive mock interview experience.

##  Features

- **3D Virtual Interviewer**: Interactive 3D character with realistic animations and lip-sync
- **AI-Powered Questions**: Dynamic question generation based on resume and job description using Google Gemini
- **Speech Recognition**: Real-time voice interaction with the virtual interviewer
- **Resume Analysis**: Automatic text extraction from PDF and image resumes using OCR
- **Interview Recording**: Screen recording capability for interview review
- **Intelligent Feedback**: AI-generated interview summary and evaluation
- **Responsive Design**: Works on desktop and mobile devices

##  How to Use

1. **Upload Your Resume**: Submit your resume (PDF or image format) along with your personal details
2. **Enter Job Description**: Paste the job description you're preparing for
3. **Start the Interview**: The 3D virtual interviewer will greet you and begin asking questions
4. **Answer Questions**: Speak your answers naturally - the system uses speech recognition
5. **Get Feedback**: Receive AI-generated feedback and interview summary at the end

##  Technical Stack

- **Backend**: Flask (Python)
- **Frontend**: HTML5, CSS3, JavaScript
- **3D Graphics**: Three.js
- **AI Integration**: Google Gemini API
- **OCR**: Tesseract OCR
- **Speech**: Web Speech API + ElevenLabs TTS
- **File Processing**: pdf2image, Pillow

##  Requirements

- Modern web browser with microphone access
- JavaScript enabled
- Stable internet connection
- Microphone for voice interaction

## Setup for Local Development

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Install system dependencies:
   - Tesseract OCR
   - Poppler (for PDF processing)
4. Set up environment variables:
   ```bash
   export GEMINI_API_KEY="your_gemini_api_key"
   ```
5. Run the application:
   ```bash
   python app.py
   ```

##  Deployment on Hugging Face Spaces

This application is configured to run on Hugging Face Spaces. The main requirements are:

- `requirements.txt` with all Python dependencies
- `app.py` as the main application file
- Static files in the `static/` directory
- Environment variables for API keys

##  Project Structure

```
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── README.md             # This file
├── .gitignore           # Git ignore rules
├── static/              # Static web assets
│   ├── index.html       # User input form
│   ├── interview.html   # 3D interview interface
│   ├── rules.html       # Interview guidelines
│   ├── summary.html     # Results page
│   └── models/          # 3D character models
├── uploads/             # User uploaded files
└── user.json           # User data storage
```

##  API Keys Required

To use the full functionality, you'll need:

1. **Google Gemini API Key**: For AI question generation and responses
   - Get it from: https://makersuite.google.com/app/apikey
   - Set as environment variable: `GEMINI_API_KEY`

2. **ElevenLabs API Key** (optional): For enhanced text-to-speech
   - Get it from: https://elevenlabs.io/app/profile/api-keys
   - Update in `static/interview.html`

##  Features in Detail

### 3D Character Interaction
- Realistic 3D character with multiple animations
- Lip-sync during speech
- Eye blinking and natural movements
- Responsive to user interaction

### AI Question Generation
- Context-aware questions based on resume content
- Job-specific question customization
- Follow-up questions based on previous answers
- Fallback questions if AI generation fails

### Speech Processing
- Real-time speech recognition
- Text-to-speech with multiple voice options
- Natural conversation flow
- Error handling and recovery

### Resume Processing
- PDF to image conversion
- OCR text extraction
- Name detection and validation
- Support for multiple file formats

##  Important Notes

- The application requires microphone access for voice interaction
- Screen recording is optional but recommended for review
- All data is processed locally and not stored permanently
- The 3D models are loaded from CDN for better performance

##  Contributing

Contributions are welcome! Please feel free to submit issues, feature requests, or pull requests.

##  License

This project is licensed under the MIT License - see the LICENSE file for details.

##  Acknowledgments

- Three.js for 3D graphics
- Google Gemini for AI capabilities
- ElevenLabs for text-to-speech
- Tesseract OCR for text extraction
- Flask for the web framework

---

**Note**: This is a demo application for educational purposes. For production use, additional security measures and data handling practices should be implemented.
