import os
import io
import re
import json
import docx
import PyPDF2
import pandas as pd
from io import BytesIO
import streamlit as st
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate


load_dotenv()

llm = ChatGroq(temperature=1,
             model_name=st.secrets["MODEL_NAME"],
             api_key=st.secrets["GROQ_API_KEY"],
             model_kwargs={"response_format": {"type": "json_object"}})

# Initialize Session State
if 'json_data' not in st.session_state:
    st.session_state.json_data = []
if 'markdown_data' not in st.session_state:
    st.session_state.markdown_data = []
if 'match_results' not in st.session_state:
    st.session_state.match_results = []
    
# Function to extract text from PDF
def extract_text_from_pdf(file):
    pdf_reader = PyPDF2.PdfReader(io.BytesIO(file.read()))
    text = ""
    for page_num in range(len(pdf_reader.pages)):
        page = pdf_reader.pages[page_num]
        text += page.extract_text().strip()
    return text

# Function to extract text from DOCX
def extract_text_from_doc(file):
    doc = docx.Document(io.BytesIO(file.read()))
    text = ""
    for paragraph in doc.paragraphs:
        text += paragraph.text.strip() + "\n"
    return text

# Function to extract required information from resume text
def extract_text_from_file(file):
    file_type = file.name.split(".")[-1]
    if file_type == "pdf":
        return extract_text_from_pdf(file)
    elif file_type == "docx":
        return extract_text_from_doc(file)
    
# function to extract JSON from the resume text    
def extract_json_from_text(resume_text):

    format_instruction = """
        {
        "name": "Candidate's full name",
        "email": "Candidate's email address",
        "phone_number": "Candidate's phone number",
        "location": {
            "address": "Candidate's full address",
            "city": "Candidate's city",
            "country": "Candidate's country"
        },
        "linkedin_profile": "URL to LinkedIn profile",
        "github_profile": "URL to GitHub profile (if applicable)",
        "portfolio_website": "URL to personal portfolio or website (if applicable)",
        "career_objective": "Candidate's career objective or summary",
        "total_experience": "Total years of work experience",
        "relevant_experience": "Years of relevant experience",
        "current_job_title": "Candidate's current job title",
        "current_company": "Candidate's current company",
        "previous_job_titles": [
            "List of previous job titles"
        ],
        "previous_companies": [
            "List of previous companies"
        ],
        "skills": {
            "technical_skills": [
            "List of technical skills"
            ],
            "soft_skills": [
            "List of soft skills"
            ]
        },
        "education": [
            {
            "degree": "Degree obtained",
            "institution": "Institution name",
            "year_of_passing": "Year of passing",
            "division": "Division/Grade/CGPA"
            }
        ],
        "certifications": "List of certifications (if any)",
        "projects": [
            {
            "project_name": "Name of the project",
            "description": "Brief description of the project",
            "technologies_used": "List of technologies/tools used",
            "role": "Role in the project"
            }
        ],
        "achievements": "List of major achievements (if any)",
        "publications": "List of publications (if applicable)",
        "languages": [
            "List of languages"
        ],
        }
    """

    prompt_template = """
        You are tasked with extracting data from resume and returning a JSON structre.
        {format_instruction}
        Resume Text:
        {resume_text}
    """

    prompt = PromptTemplate(
    template=prompt_template,
    input_variables=["format_instruction", "resume_text"],
    )
    
    llm_resume_parser = prompt | llm
    
    parsed_candidate_data = llm_resume_parser.invoke({"format_instruction": format_instruction, "resume_text":resume_text})
    
    return json.loads(parsed_candidate_data.content)

# function to match JD with the resume and return match score alongwith justifications
def match_JD_with_resume(JD_text, candidate_json):
    
    job_description = JD_text
    candidate = candidate_json
    
    llm = ChatGroq(temperature=1,
             model_name=os.getenv("MODEL_NAME"),
             api_key=os.getenv("GROQ_API_KEY"),
            )
    
    prompt_template = """
        You are tasked with matching the Job Description provided with the candidate's JSON data and returning a match score out of 100. After scoring, you must determine the Application Status based on this logic: if the score is less than or equal to 50, the status should be "Rejected"; if greater than 60, it should be "Shortlisted".

        Please return the results strictly in the following format without any additional explanations:
        Match Score: <score>
        Application Status: <status>

        Score Breakdown:
        1. <Reason_Title> - <One-line explanation>
        2. <Reason_Title> - <One-line explanation>
        3. <Reason_Title> - <One-line explanation>

        Job Description:
        {job_description}

        Candidate's JSON:
        {candidate}
    """
    
    prompt = PromptTemplate(
    template=prompt_template,
    input_variables=["job_description"],
    )
    
    llm_jd_match = prompt | llm
    
    resume_JD_match = llm_jd_match.invoke({"candidate":candidate, "job_description":job_description})
    
    return resume_JD_match.content

# Function to load JD
def load_jd(file):
    return extract_text_from_file(file=file)

# Function to load JSON files
def load_json_files(directory='Output/JSON'):
    json_list = []
    for filename in os.listdir(directory):
        if filename.endswith('.json'):
            filepath = os.path.join(directory, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                json_list.append(data)
    return json_list

# Function to save JSON data
def save_json(data, filename, directory='Output/JSON'):
    if not os.path.exists(directory):
        os.makedirs(directory)
    filepath = os.path.join(directory, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    st.session_state.json_data.append(filepath)
    
# Function to save Match Score data for individual candidates
def save_evaluation_to_markdown(data, filename, directory='Output/Evaluations'):
    if not os.path.exists(directory):
        os.makedirs(directory)
    filepath = os.path.join(directory, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(data)
    # Store the file path in session state for tracking
    if 'markdown_data' not in st.session_state:
        st.session_state.markdown_data = []
    st.session_state.markdown_data.append(filepath)
    
# Function to extract Match Score and Application Status from markdown files
def extract_evaluation_from_markdown(filepath):
    with open(filepath, 'r', encoding='utf-8') as file:
        content = file.read()

    # Use regex to extract Match Score and Application Status
    match_score = re.search(r"Match Score:\s*(\d+)", content)
    application_status = re.search(r"Application Status:\s*(\w+)", content)

    # Get values if found, else default to 'N/A'
    score = match_score.group(1) if match_score else None
    status = application_status.group(1) if application_status else None

    return {
        "File Name": os.path.basename(filepath),
        "Match Score": score,
        "Application Status": status
    }

# Function to process all markdown files and extract required information
def process_markdown_files(directory='Output/Evaluations'):
    data = []
    if os.path.exists(directory):
        for filename in os.listdir(directory):
            if filename.endswith('.md'):
                filepath = os.path.join(directory, filename)
                extracted_data = extract_evaluation_from_markdown(filepath)
                data.append(extracted_data)
    # print(data)
    return data

# Streamlit UI

# setting up the page header here.
hide_st_style = """
                <style>
                #MainMenu {visibility : hidden;}
                header {visibility : hidden;}
                </style>
                """

st.set_page_config(
    page_title="GenAI Resume-JD Parser",
    page_icon="📃"
)
# removing all the default streamlit configs here
st.markdown(hide_st_style, unsafe_allow_html=True)

st.title("Resume Parser & JD Evaluation 🪄")

# Sidebar for Job Description Upload
st.sidebar.header("Job Description 📃")
jd_file = st.sidebar.file_uploader("Upload Job Description (PDF/DOCX)", type=["pdf", "docx"], key = "jd_file")

if jd_file is not None:
    jd_text = load_jd(jd_file)
    st.sidebar.success("Job Description Processed Successfully!")
else:
    jd_text = ""
    st.sidebar.warning("Upload a Job Description to get started")
    
st.header("Upload Candidate Resumes 📂")
uploaded_files = st.file_uploader("Choose PDF or DOCX files", type=["pdf", "docx"], accept_multiple_files=True)

col_1, col_2, col_3, col_4 = st.columns(4)

with col_1:
    if st.button("Process Resumes with AI 🧠"):
        if not uploaded_files:
            st.error("Please upload at least one resume.")
        elif not jd_file:
            st.error("Please upload a Job Description in the sidebar.")
        else:
            with st.spinner('Processing resumes...'):
                progress_bar = st.progress(0)
                total_files = len(uploaded_files)
                for idx, file in enumerate(uploaded_files):
                    # Extract text based on file type
                    text = extract_text_from_file(file)
                    # st.write(text)
                    extracted_info = extract_json_from_text(text)
                    # Save extracted info as JSON
                    filename = os.path.splitext(file.name)[0] + "_data.json"
                    save_json(extracted_info, filename)
                    # Update progress bar
                    progress = (idx + 1) / total_files
                    progress_bar.progress(progress)
            st.success(f"{len(uploaded_files)} resumes processed & saved successfully.")
            st.balloons()
        
with col_4:
    if st.button("Flush Loaded Data 🗑️"):
        st.session_state.json_data = []
        st.session_state.markdown_data = []
        st.session_state.match_results = []
        if 'jd_file' in st.session_state:
            del st.session_state.jd_file
        st.success("All data has been cleared 👍")
        st.rerun()

with col_3:
    if st.button("Download Evaluated Data ⚡"):
        if not st.session_state.markdown_data:
            st.warning("Please Apply for Evaluation first ⚠️")
        else:
            # Process the markdown files and extract data
            evaluation_data = process_markdown_files()
            if evaluation_data:
                # Convert data to DataFrame
                df = pd.DataFrame(evaluation_data)
                with st.expander("Preview Dataframe"):
                    st.dataframe(df)
                # Create an Excel file in memory
                excel_buffer = BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='Evaluations')
                excel_buffer.seek(0)

                # Download button for the Excel file
                st.download_button(
                    label="Download Excel",
                    data=excel_buffer,
                    file_name="evaluation_data.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.warning("No Evaluated Files Found ⚠️")

with col_2:
    # Matching JD with Resumes and Generating Excel
    if st.button("Evaluate Resumes w.r.t. Job 💯"):
        if not jd_text:
            st.error("Please upload a Job Description in the sidebar.")
        elif not st.session_state.json_data:
            st.error("No processed JSON files found. Please process resumes first.")
        else:
            if not st.session_state.match_results:  # Only run if no match results are present
                with st.spinner('Matching resumes with Job Description...'):
                    total_files = len(st.session_state.json_data)
                    progress_bar = st.progress(0)
                    for idx, json_file in enumerate(st.session_state.json_data):
                        with open(json_file, 'r', encoding='utf-8') as f:
                            candidate_data = json.load(f)
                            match = match_JD_with_resume(jd_text, candidate_data)
                            st.session_state.match_results.append(match)
                        # Update progress bar
                        progress = (idx + 1) / total_files
                        progress_bar.progress(progress)
                    
                with st.spinner('Saving the Evaluated Resumes...'):
                    for idx, file in enumerate(uploaded_files):
                        filename_evaluated = os.path.splitext(file.name)[0] + "_evaluated.md"
                        save_evaluation_to_markdown(data=st.session_state.match_results[idx], filename=filename_evaluated)
                    st.success("All resumes have been evaluated successfully and saved.")
                    st.balloons()

    
# Display processed JSON files
if st.session_state.json_data:
    with st.expander("Processed JSON from Resume Files 🧠🪄", expanded=False):
        for json_file in st.session_state.json_data:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                st.json(data)
            

# Display the Processed Match Results.
if st.session_state.match_results:
    with st.expander("Preview Resume Match Results with Job Description 🔍🪄", expanded=False):
        st.write(st.session_state.match_results)
        
st.markdown(
    "<footer style='text-align: center; padding: 10px;'><strong>Made with ❤️ by Abhijit x Llama 3.1 🦙</strong></footer>", 
    unsafe_allow_html=True
)
