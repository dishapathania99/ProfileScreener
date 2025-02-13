import os
import openai
import pandas as pd
import ast
from flask import Flask, render_template, request, redirect, url_for
from PyPDF2 import PdfReader
from werkzeug.utils import secure_filename
# from docx import Document
# import subprocess
import re

# Flask configuration
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploaded_files')  # Outside static folder
ALLOWED_EXTENSIONS = {"pdf"}  # Allow pdf extensions

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Define the allowed_file function
def allowed_file(filename):
    """Check if the file has an allowed extension (PDF)."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# def convert_doc_to_pdf(doc_path):
#     """Convert .doc or .docx to .pdf."""
#     pdf_path = doc_path.rsplit(".", 1)[0] + ".pdf"
#     if doc_path.endswith(".docx"):
#         doc = Document(doc_path)
#         doc.save(pdf_path)
#     elif doc_path.endswith(".doc"):
#         subprocess.run(["unoconv", "-f", "pdf", doc_path])
#     return pdf_path

# Function to extract text from PDFs
def extract_text_from_pdfs(folder_path):
    """Extract text from all PDF files in a folder."""
    data = []
    for filename in os.listdir(folder_path):
        if filename.endswith(".pdf"):
            filepath = os.path.join(folder_path, filename)
            try:
                reader = PdfReader(filepath)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\n"
                data.append({"Filename": f"<strong>{filename}</strong>", "Content": text.strip()})
            except Exception as e:
                data.append({"Filename": f"<strong>{filename}</strong>", "Content": f"Error: {str(e)}"})
    return data

# Function to delete all previously uploaded files
def delete_all_uploaded_files():
    """Delete all files in the uploaded files folder."""
    for filename in os.listdir(app.config["UPLOAD_FOLDER"]):
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        if os.path.isfile(file_path):
            os.remove(file_path)  # Delete file

# GPT response function
def get_gpt_response(resumetext):
    """Send text to OpenAI GPT-3.5 and get a formatted response."""
    try:
        # Construct the prompt with the actual resume content
        prompt = (
            f"You are a helpful assistant. Analyze the provided resume text:\n\n{resumetext}\n\n"
            "Your task is to check for the presence of the following skills/technologies in the resume: "
            "'Generative AI', 'AWS', 'Azure', 'NLP', 'Deep Learning', 'Database', 'Time Series', 'Machine Learning', 'Predictive Modelling.'. "
            "Additionally, extract the following information from the resume: "
            "- **Candidate Name** (the full name of the candidate, typically found near the top of the resume) "
            "- **Contact No.** (the candidate's phone number) "
            "- **Email ID** (the candidate's email address) "
            "Then, return a dictionary with only 4 keys: "
            "- **Candidate Name** (extracted from the resume) "
            "- **Contact No.** (extracted from the resume) "
            "- **Email ID** (extracted from the resume) "
            "- **TP1** (a value indicating if the candidate meets the skill requirements) "
            "For the value of **TP1**, put: "
            "- 'Yes' if the resume includes more than 3 or all of the following skills: "
            "  'Generative AI', 'AWS or Azure', 'NLP', 'Deep Learning', 'Time Series', 'Machine Learning', 'Predictive Modelling'. "
            "- 'No' if only 1-2 of the above skills are mentioned, or if none of these skills are present in the resume."
            "Return the dictionary in a valid Python format."
        )
        
        # Send the request to GPT
        response = openai.Completion.create(
            engine="gpt-3.5-turbo-instruct",
            prompt=prompt,
            max_tokens=1000,
            n=1,
        )
 
        # Get the raw text response from GPT
        raw_text = response["choices"][0].get("text", "").strip()
        
        # Log the full raw GPT response
        print("Full Raw GPT Response:", raw_text)  # Log the full response to check its format
        
        if raw_text:
            try:
                # Check if the response starts with a '{' and ends with a '}'
                if raw_text.startswith("{") and raw_text.endswith("}"):
                    # Try parsing the response as a dictionary
                    mydict = ast.literal_eval(raw_text)
                    
                    # Fallback to extract name if GPT doesn't provide it in the dictionary
                    if not mydict.get('Candidate Name'):
                        # Try using a regex pattern to extract the name from the text
                        name_match = re.search(r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)", resumetext)
                        if name_match:
                            mydict['Candidate Name'] = name_match.group(0)
                        else:
                            mydict['Candidate Name'] = "Unknown"
                    
                    # Optional: Add an overall rating if needed
                    mydict['Rating'] = calculate_overall_rating(mydict)
                    return mydict
                else:
                    # If the response is not in the expected dictionary format, handle it
                    print("GPT Response is not in expected dictionary format:", raw_text)
                    
                    # Return a custom message instead of just an error
                    return {"Error": "GPT response is not in the expected dictionary format. Raw response was: " + raw_text}
            except Exception as e:
                # If parsing fails, log the error and return a meaningful message
                print("Error parsing GPT response:", e)
                return {"Error": f"Error parsing GPT response: {str(e)}"}
        else:
            return {"Error": "No text returned from GPT response."}
 
    except Exception as e:
        return {"Error": f"Error processing GPT response: {str(e)}"}

# Function to calculate the overall rating based on proficiency levels
def calculate_overall_rating(skill_dict):
    """Calculate an overall rating based on proficiency levels of skills."""
    proficiency_map = {
        "Expert": 5,
        "Proficient": 4,
        "Intermediate": 3,
        "NA": 0  # "NA" should not contribute to the overall rating
    }
    total_score = 0
    count = 0
    
    # Iterate over skills and calculate the total score
    for skill, proficiency in skill_dict.items():
        if proficiency in proficiency_map:
            total_score += proficiency_map[proficiency]
            count += 1
    
    # Calculate average score and scale it to out of 5
    if count > 0:
        average_score = total_score / count
        return round(average_score, 1)  # Rounded to 1 decimal place
    else:
        return 0  # Return 0 if no valid proficiency ratings were found

@app.route("/", methods=["GET", "POST"])
def index():
    data = None
    analyzed_data = []
    uploaded_files = []
    
    if request.method == "POST":
        # Read the OpenAI API key from the form input
        api_key = request.form.get("api_key")
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key
            openai.api_key = api_key
        else:
            return "API Key is required", 400

        if "files" not in request.files:
            return redirect(request.url)

        files = request.files.getlist("files")
        if not files:
            print("No files uploaded.")
        
        # Delete previously uploaded files before saving new ones
        delete_all_uploaded_files()

        saved_files = []
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                file.save(file_path)  # Save the file in the uploaded_files folder                
                saved_files.append(file_path)
                uploaded_files.append(filename)  # Add the PDF filename if already a PDF

        # Extract text from PDFs (now includes converted DOCX files as well)
        extracted_data = extract_text_from_pdfs(app.config["UPLOAD_FOLDER"])

        # Analyze each extracted text using GPT
        for pdf in extracted_data:
            filename = pdf["Filename"]
            content = pdf["Content"]
            if content:
                gpt_result = get_gpt_response(content)
                print("GPT Result:", gpt_result)
                
                if isinstance(gpt_result, dict):  # Ensure it is a valid result
                    analyzed_data.append({
                        "Candidate Name": filename.replace("<strong>", "").replace("</strong>", ""), 
                        **gpt_result  # Add the skills and ratings as separate columns
                    })
                    print("Analyzed Data:", analyzed_data)
        # Convert analyzed data to a DataFrame for display
        data = pd.DataFrame(analyzed_data)
        print(data)

        # Drop the 'Rating' column if it exists
        if "Rating" in data.columns:
            data = data.drop(columns=["Rating"])

    return render_template(
        "index.html",
        tables=[data.to_html(classes="table table-bordered", index=False, escape=False)] if data is not None else None,
        uploaded_files=uploaded_files,  # Pass uploaded filenames to the template
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
