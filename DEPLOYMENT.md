# Deployment Guide for Hugging Face Spaces

This guide will help you deploy your InterviewBot application to Hugging Face Spaces.

## Prerequisites

1. **Hugging Face Account**: Create an account at [huggingface.co](https://huggingface.co)
2. **Git**: Make sure you have Git installed on your system
3. **API Keys**: You'll need a Google Gemini API key

## Step 1: Prepare Your Repository

1. **Initialize Git Repository** (if not already done):
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   ```

2. **Create a Hugging Face Space**:
   - Go to [huggingface.co/new-space](https://huggingface.co/new-space)
   - Choose a name for your space (e.g., "interviewbot")
   - Select "Gradio" as the SDK
   - Choose "Public" or "Private" based on your preference
   - Click "Create Space"

## Step 2: Upload Your Code

### Option A: Using Git (Recommended)

1. **Add Hugging Face Remote**:
   ```bash
   git remote add origin https://huggingface.co/spaces/YOUR_USERNAME/YOUR_SPACE_NAME
   ```

2. **Push Your Code**:
   ```bash
   git push origin main
   ```

### Option B: Using Web Interface

1. Upload all files through the Hugging Face web interface
2. Make sure to include all files from your project

## Step 3: Configure Environment Variables

1. **Go to your Space Settings**:
   - Navigate to your space on Hugging Face
   - Click on "Settings" tab
   - Scroll down to "Repository secrets"

2. **Add Required Secrets**:
   - `GEMINI_API_KEY`: Your Google Gemini API key
   - `ELEVENLABS_API_KEY`: (Optional) Your ElevenLabs API key

## Step 4: Verify Deployment

1. **Check Build Logs**:
   - Go to the "Logs" tab in your space
   - Monitor the build process for any errors

2. **Test the Application**:
   - Once deployed, test all functionality
   - Upload a resume and try the interview process

## Step 5: Customize Your Space

1. **Update README.md**:
   - The README.md will be displayed on your space page
   - Customize it with your specific information

2. **Configure Space Settings**:
   - Update the space title and description
   - Add relevant tags
   - Set appropriate license

## Troubleshooting

### Common Issues

1. **Build Failures**:
   - Check the logs for specific error messages
   - Ensure all dependencies are in requirements.txt
   - Verify file paths are correct

2. **API Key Issues**:
   - Make sure environment variables are set correctly
   - Check that API keys are valid and have proper permissions

3. **Static Files Not Loading**:
   - Verify that static files are in the correct directory
   - Check file permissions and paths

4. **OCR Not Working**:
   - Tesseract might not be available in the Hugging Face environment
   - The app has fallback mechanisms for this

### Performance Optimization

1. **Reduce Bundle Size**:
   - Optimize 3D models
   - Use CDN for large assets
   - Minimize JavaScript and CSS

2. **Memory Management**:
   - Clear temporary files regularly
   - Implement proper error handling

## Security Considerations

1. **API Key Protection**:
   - Never commit API keys to the repository
   - Use environment variables for sensitive data

2. **Data Privacy**:
   - User data is not permanently stored
   - Implement proper data handling practices

## Monitoring and Maintenance

1. **Monitor Usage**:
   - Check space metrics regularly
   - Monitor for errors in logs

2. **Update Dependencies**:
   - Keep requirements.txt updated
   - Test updates in a development environment first

## Advanced Configuration

### Custom Domain (Optional)

1. **Configure Custom Domain**:
   - Follow Hugging Face documentation for custom domains
   - Update CORS settings if needed

### Scaling Considerations

1. **Resource Limits**:
   - Hugging Face Spaces have resource limits
   - Optimize for the available resources

2. **Caching**:
   - Implement caching for better performance
   - Use appropriate cache headers

## Support

If you encounter issues:

1. **Check Documentation**:
   - [Hugging Face Spaces Documentation](https://huggingface.co/docs/hub/spaces)
   - [Flask Documentation](https://flask.palletsprojects.com/)

2. **Community Support**:
   - Hugging Face Community Forums
   - GitHub Issues

3. **Debugging**:
   - Use the logs tab for debugging
   - Test locally before deploying

## Next Steps

After successful deployment:

1. **Share Your Space**:
   - Share the link with others
   - Add to your portfolio

2. **Gather Feedback**:
   - Collect user feedback
   - Iterate and improve

3. **Monitor Performance**:
   - Track usage metrics
   - Optimize based on data

---

**Note**: This deployment guide assumes you're using the free tier of Hugging Face Spaces. For production use, consider upgrading to paid tiers for better performance and resources.
