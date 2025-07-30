from fastapi import FastAPI, HTTPException, Request, Depends
from job_title_dataset import keywords as job_title_keywords
from pydantic import BaseModel
from openai import OpenAI
import faiss
import requests
import redis
import logging
import time
from jose import jwt
from datetime import datetime, timedelta, timezone
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from langdetect import detect
from deep_translator import GoogleTranslator
import csv
import io
import os
from dotenv import load_dotenv
import re

# Load environment variables
load_dotenv()
auth_secret_key = os.getenv("Secret_Key")

# Initialize FastAPI app
app = FastAPI()

# Setup CORS for UI integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Placeholder for FAISS vector database
vector_dim = 512
db = faiss.IndexFlatL2(vector_dim)
data_store = []

# OpenAI API Key
client = OpenAI(base_url="https://models.inference.ai.azure.com",
    api_key=os.environ.get("Github_Token"))

# Check if OpenAI API key is set

# Redis for context memory storage
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# JWT Auth setup
SECRET_KEY = auth_secret_key
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")

# Define request models
class QueryRequest(BaseModel):
    user_input: str
    session_id: str
    user_id: str

class FeedbackRequest(BaseModel):
    session_id: str
    feedback: str

class AdminFeedbackRequest(BaseModel):
    session_id: str

class UserCredentials(BaseModel):
    username: str
    password: str

# JWT helpers
def create_token(data: dict):
    data["exp"] = datetime.now(timezone.utc) + timedelta(weeks=12)
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM )

def verify_token(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if form_data.username == "admin" and form_data.password == "password":
        token = create_token({"sub": form_data.username})
        return {"access_token": token, "token_type": "bearer"}
    raise HTTPException(status_code=401, detail="Incorrect credentials")

@app.post("/chat")
def chat_with_asha(request: QueryRequest, user: dict = Depends(verify_token)):
    user_input = request.user_input
    session_id = request.session_id
    user_id = request.user_id
    start_time = time.time()

    # Detect language and translate to English if needed
    lang = detect(user_input)
    translator = GoogleTranslator(source=lang, target="en")
    translated_input = translator.translate(user_input) if lang != 'en' else user_input
    is_biased, highlighted_text = detect_bias(translated_input)
    
    if is_biased:
        return {
            "response": f"This input contains potentially biased or discriminatory language:\n\n{highlighted_text}\n\nPlease rephrase it to keep the conversation respectful and inclusive.",
            "response_time": round(time.time() - start_time, 3),
            "language": lang
        }
    
    def extract_job_keywords(translated_input):
        common_keywords = job_title_keywords
        found = []
        user_words = translated_input.lower().split()
        for word in user_words:
            matches = difflib.get_close_matches(word, common_keywords, n=1, cutoff=0.85)
            if matches:
                found.append(matches[0])
        return list(set(found))

    job_api_trigger = False
    user_input_lower = translated_input.lower()

    # Use regex if original or typo-close variant matches
    search_match = re.search(r"(search\s+\w+\s+for)\s+(.+)", user_input_lower)
    if search_match:
        role_raw = search_match.group(2).strip()
        role = role_raw.replace(" ", "%20")
        job_api_trigger = True
    else:
        extracted = extract_job_keywords(translated_input)
        if extracted:
            role = "%20".join(extracted)
            job_api_trigger = True
        elif any(w in user_input_lower for w in ["job", "jobs", "jbs", "jbos", "jbos"]):
            role = False
            job_api_trigger = True

    data_response = ""
    if job_api_trigger:
        if role:
            herkey_url = f"https://api-prod.herkey.com/api/v1/herkey/jobs/es_candidate_jobs?page_no=1&page_size=5&keyword={role}&is_global_query=false"
        else:
            herkey_url = "https://api-prod.herkey.com/api/v1/herkey/jobs/es_candidate_jobs?type=boosted&more=featured_jobs&page_no=1&page_size=5"

        headers = {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'en-US,en;q=0.9,te;q=0.8',
        'authorization': 'Token eyJhbGciOiJSUzUxMiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl9rZXkiOiJhbm9uX2NkNTQ4ZmI3YmE4ZDNmZTdmMmI2ZTNlNzZhM2VjYmYxNjI5MWYzNzFiMWI4NTk3YzY2MDhjNzc5OTRkZDU3MDciLCJwYXRoIjoiYW5vbl91c2VyX3Rva2VuX2J1Y2tldC9hbm9uX2NkNTQ4ZmI3YmE4ZDNmZTdmMmI2ZTNlNzZhM2VjYmYxNjI5MWYzNzFiMWI4NTk3YzY2MDhjNzc5OTRkZDU3MDciLCJleHBpcnkiOjE3NDgxNzc4MzksInR5cGUiOiIyZiIsImlhdCI6MTc0NTU4NTgzOX0.pwm0uewOiMvrfzIg1is5cICH0yASEhkqvD-il7XgSPn3OhdReitmN_ZIUY-rh7r1jKydEnAcZ6i6YqWFXjFo_iN5HzzDqExgCnvYmH-w3wpdzh0VN02YLABknqwLblXPh9npHuRhJJtJEy4BFbMhLmKqRLYwXoLStvQlJKlzp3fRkzCybkVICaKqxUnJ5fSmuCeL27o80S7bw910ed0m9we88rwPCjgMWdFI8uCqnKjnrMcTEPAOp5R8ngfjEPmRoz5_ERPzHLPT4J2SEpCKThKdkcBh6vQA1Yd3aDOTTilgcqatHGbsGLELaxzoN5kMt2H_1CYBBX0091YMhAsmKA',
        'origin': 'https://www.herkey.com',
        'priority': 'u=1, i',
        'referer': 'https://www.herkey.com/',
        'sec-ch-ua': '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"macOS"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'
        }
        try:
            job_response = requests.get(herkey_url, headers=headers, timeout=10)
            if job_response.status_code == 200:
                job_json = job_response.json()
                jobs = job_json.get("body", [])
            else:
                jobs = []
                data_response += f"\nFailed to retrieve jobs: {job_response.status_code} - {job_response.text}\n"
            job_details = []

            for job in jobs:
                title = job.get("title", "N/A")
                company = job.get("company_name", "N/A")
                skills = ", ".join(job.get("skills", [])) if isinstance(job.get("skills"), list) else job.get("skills", "N/A")
                work_mode = ", ".join(job.get("work_mode", [])) if isinstance(job.get("work_mode"), list) else job.get("work_mode", "N/A")
                location = job.get("location_name", "N/A")
                min_exp = job.get("min_year", "N/A")
                max_exp = job.get("max_year", "N/A")
                link = job.get("redirect_url") or f"https://www.herkey.com/jobs/{title.replace(' ', '—').lower()}/{job.get('id')}"
                if job.get("redirect_url"):
                    if 'ad.doubleclick.net' in job.get("redirect_url"):
                        extracted_url = job.get('redirect_').split(';')[-1]
                        final_url = extracted_url[2:]
                        link = final_url
                    else:
                        link = job.get("redirect_url")

                job_md = f"""{title}
🏢 Company: {company}
📍 Location: {location}
💼 Work Mode: {work_mode}
🛠️ Skills: {skills}
🧠 Experience: {min_exp} - {max_exp} years
🔗 [Apply Here]({link})
"""
                job_details.append(job_md)

            if job_details:
                data_response += "\nHere are some job listings based on your interest:\n" + "\n---\n".join(job_details)
            else:
                return {
                    "response": f"Sorry, no listings were found for '{role.replace('%20', ' ')}'. You can check manually at https://www.herkey.com/jobs.",
                    "response_time": round(time.time() - start_time, 3),
                    "language": lang
                }

        except Exception as e:
            data_response += f"\nError retrieving job data: {str(e)}"

    session_words = translated_input.lower().split()
    mentor_match = any(difflib.get_close_matches(word, ["mentor", "mentorship"], n=1, cutoff=0.8) for word in session_words)
    if mentor_match:
        try:
            mentor_url = "https://api-prod.herkey.com/api/v1/herkey/herkeysearch/sessions/?page_number=1&is_global_query=true"
            
            headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'en-GB,en-IN;q=0.9,en-US;q=0.8,en;q=0.7',
            'authorization': 'Token eyJhbGciOiJSUzUxMiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl9rZXkiOiJhbm9uXzFkZmY4ODdlMjNjNWQwNWE5ZDRmYzM4MDczYmVmNDFiNzZiZTJkNWQyZmRmMzVjZjk1YjJlMDU3YWM0ZmFjZDMiLCJwYXRoIjoiYW5vbl91c2VyX3Rva2VuX2J1Y2tldC9hbm9uXzFkZmY4ODdlMjNjNWQwNWE5ZDRmYzM4MDczYmVmNDFiNzZiZTJkNWQyZmRmMzVjZjk1YjJlMDU3YWM0ZmFjZDMiLCJleHBpcnkiOjE3NDgyOTQzMTQsInR5cGUiOiIyZiIsImlhdCI6MTc0NTcwMjMxNH0.o__PxGiiRZJREwvhZSdKuCdA8W1OZ1mEUWb6OJ9A-5AqGiCpjXuQBKuNr4dmKI0oTH8NC7o6dz8VUiGnkuuo8HHf0Cv6ZHSIxuIMX8-JAf5AqHJRI4LcGa0DxGUQgdbrCqU8JalRlZtGSzRNTqrmRQ7Ukpk7ystMim_xABrLP2xMeSgIoBW1CbY1t6S7bTOsdkf7rdy0GodvS_ujagv0JAmmn5cAM4oRsMqmFGRny5W8FNoq39BifTFgFLJhp7KC8rTQbmaX04cHYB2PugpFxHylcLSaI4ZJz4rXJyCZcMkw9pKD1j72HRM00-FZeXf3J2eHjq1c4L7PzcvmpDHYyQ',
            'origin': 'https://www.herkey.com',
            'priority': 'u=1, i',
            'referer': 'https://www.herkey.com/',
            'sec-ch-ua': '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'
            }
            mentor_response = requests.get(mentor_url, headers=headers, timeout=10)
            if mentor_response.status_code == 200:
                mentor_json = mentor_response.json()
                sessions = mentor_json.get("body", [])
                mentor_list = []
                for session in sessions[:3]:  # show only 3 for now
                    post_id = session.get("post_id")
                    username = session.get("post_info", {}).get("user_short_profile", {}).get("username", "Unknown")
                    content = session.get("post_content", {})
                    topic = content.get("post_topic_text", "N/A")
                    date = content.get("discussion_date_time", "N/A")
                    duration = content.get("duration", "N/A")
                    link = f"https://www.herkey.com/sessions/{post_id}"
                    mentor_md = f"""**{topic}**
👤 Host: _{username}_
🗓️ Date & Time: {date}
⏱️ Duration: {duration}
🔗 [Join Session]({link})"""
                    mentor_list.append(mentor_md)

                if mentor_list:
                    data_response += "\nHere are some mentorship sessions:\n" + "\n---\n".join(mentor_list)
                else:
                    data_response += "\nNo mentorship sessions found at the moment."
            else:
                data_response += f"\nError fetching mentorships: {mentor_response.status_code}"
        except Exception as e:
            data_response += f"\nMentorship API error: {str(e)}"

    event_match = any(difflib.get_close_matches(word, ["event", "events", "workshop"], n=1, cutoff=0.8) for word in session_words)
    if event_match:
        try:
            events_url = "https://api-prod.herkey.com/api/v1/herkey/sessions/event-session?page=1&page_size=10&expiry=false&session_type=upcoming_featured"
            headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'en-GB,en-IN;q=0.9,en-US;q=0.8,en;q=0.7',
            'authorization': 'Token eyJhbGciOiJSUzUxMiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl9rZXkiOiJhbm9uXzQ0YjdkZTZhZGU1YjI0MDkyYzQ5MjdhM2E3NzhhYTIzYTQyNjBkZjk0ZjZjZTliNzkyYWMzYmE3NzRiYTUwZTciLCJwYXRoIjoiYW5vbl91c2VyX3Rva2VuX2J1Y2tldC9hbm9uXzQ0YjdkZTZhZGU1YjI0MDkyYzQ5MjdhM2E3NzhhYTIzYTQyNjBkZjk0ZjZjZTliNzkyYWMzYmE3NzRiYTUwZTciLCJleHBpcnkiOjE3NDgyOTU3NzYsInR5cGUiOiIyZiIsImlhdCI6MTc0NTcwMzc3Nn0.YBIy1gznRy_9UcsBks1aqCkMqQozk69CYURHDgkUeDA_JjRdZIzmS47PD1ZYP7xOwrdIQ1tAV9YXSHMHRq2u6QtFFMIj3Tm0xXunmWusYcCmhCJVXa9hFoejDCwKI-Jv03dOHNOgJp04wwdfa0O61v5C3AeHXFhETgIUrv_U8B3KQH2fnHOXveCj0zHYOsSCvnzVbqPtkjq-MVS6o4XKQ9jyBG6xKhce33Zk7p2Kwf80r_oXImZNfxVEqo3PYvnQTZP1HH7Sh_UwHaSx1klmpCST1oA-fTFAToCQ8pQsmjUQM3I6tOmXhAZxUHfmTn_X6y8qDFNzVoVw9JWQFr8c8g',
            'origin': 'https://www.herkey.com',
            'priority': 'u=1, i',
            'referer': 'https://www.herkey.com/',
            'sec-ch-ua': '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'
            }
            event_response = requests.get(events_url, headers=headers, timeout=10)
            if event_response.status_code == 200:
                event_json = event_response.json()
                events = event_json.get("body", [])
                event_list = []
                for session in events[:3]:  # show only 3 for now
                    post_id = session.get("post_id")
                    username = session.get("post_info", {}).get("user_short_profile", {}).get("username", "Unknown")
                    content = session.get("post_content", {})
                    topic = content.get("post_topic_text", "N/A")
                    date = content.get("discussion_date_time", "N/A")
                    duration = content.get("duration", "N/A")
                    link = f"https://www.herkey.com/sessions/{post_id}"
                    event_md = f"""**{topic}**
👤 Host: _{username}_
🗓️ Date & Time: {date}
⏱️ Duration: {duration}
🔗 [Join Session]({link})"""
                    event_list.append(event_md)

                if event_list:
                    data_response += "\nHere are some upcoming events:\n" + "\n---\n".join(event_list)
                else:
                    data_response += "\nNo upcoming events found at the moment."
            else:
                data_response += f"\nError fetching events: {event_response.status_code}"
        except Exception as e:
            data_response += f"\nEvents API error: {str(e)}"


    # Event or mentorship search by keyword
    session_search_match = re.search(r"(find|search)\s+(\w+)\s+for\s+(.+)", translated_input.lower())
    if session_search_match:
        query_type = session_search_match.group(2)
        matched_type = difflib.get_close_matches(query_type, ["mentorship", "mentorships", "events", "event"], n=1, cutoff=0.8)
        if matched_type:
            session_role = session_search_match.group(3).strip().replace(" ", "%20")
            try:
                keyword_url = f"https://api-prod.herkey.com/api/v1/herkey/herkeysearch/sessions/?page_number=1&is_global_query=true&title={session_role}"
                headers = {
                'accept': 'application/json, text/plain, */*',
                'accept-language': 'en-GB,en-IN;q=0.9,en-US;q=0.8,en;q=0.7',
                'authorization': 'Token eyJhbGciOiJSUzUxMiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl9rZXkiOiJhbm9uXzFkZmY4ODdlMjNjNWQwNWE5ZDRmYzM4MDczYmVmNDFiNzZiZTJkNWQyZmRmMzVjZjk1YjJlMDU3YWM0ZmFjZDMiLCJwYXRoIjoiYW5vbl91c2VyX3Rva2VuX2J1Y2tldC9hbm9uXzFkZmY4ODdlMjNjNWQwNWE5ZDRmYzM4MDczYmVmNDFiNzZiZTJkNWQyZmRmMzVjZjk1YjJlMDU3YWM0ZmFjZDMiLCJleHBpcnkiOjE3NDgyOTQzMTQsInR5cGUiOiIyZiIsImlhdCI6MTc0NTcwMjMxNH0.o__PxGiiRZJREwvhZSdKuCdA8W1OZ1mEUWb6OJ9A-5AqGiCpjXuQBKuNr4dmKI0oTH8NC7o6dz8VUiGnkuuo8HHf0Cv6ZHSIxuIMX8-JAf5AqHJRI4LcGa0DxGUQgdbrCqU8JalRlZtGSzRNTqrmRQ7Ukpk7ystMim_xABrLP2xMeSgIoBW1CbY1t6S7bTOsdkf7rdy0GodvS_ujagv0JAmmn5cAM4oRsMqmFGRny5W8FNoq39BifTFgFLJhp7KC8rTQbmaX04cHYB2PugpFxHylcLSaI4ZJz4rXJyCZcMkw9pKD1j72HRM00-FZeXf3J2eHjq1c4L7PzcvmpDHYyQ',
                'origin': 'https://www.herkey.com',
                'priority': 'u=1, i',
                'referer': 'https://www.herkey.com/',
                'sec-ch-ua': '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"macOS"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-site',
                'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'
                }
                keyword_response = requests.get(keyword_url, headers=headers, timeout=10)
                if keyword_response.status_code == 200:
                    keyword_json = keyword_response.json()
                    keyword_sessions = keyword_json.get("body", [])
                    session_list = []
                    for session in keyword_sessions[:3]:
                        post_id = session.get("post_id")
                        username = session.get("post_info", {}).get("user_short_profile", {}).get("username", "Unknown")
                        content = session.get("post_content", {})
                        topic = content.get("post_topic_text", "N/A")
                        date = content.get("discussion_date_time", "N/A")
                        duration = content.get("duration", "N/A")
                        link = f"https://www.herkey.com/sessions/{post_id}"
                        session_md = f"""**{topic}**
    👤 Host: _{username}_
    🗓️ Date & Time: {date}
    ⏱️ Duration: {duration}
    🔗 [Join Session]({link})"""
                        session_list.append(session_md)

                    if session_list:
                        data_response += "\nHere are some sessions based on your interest:\n" + "\n---\n".join(session_list)
                    else:
                        data_response += f"\nNo sessions found for '{session_role.replace('%20', ' ')}'."
                else:
                    data_response += f"\nError fetching session search results: {keyword_response.status_code}"
            except Exception as e:
                data_response += f"\nSession keyword API error: {str(e)}"

    # Context retrieval
    context = redis_client.lrange(session_id, 0, -1)
    redis_client.rpush(session_id, translated_input)
    redis_client.expire(session_id, 86400)

    # Store personalized user data
    redis_client.hset(f"user:{user_id}", "last_query", translated_input)

    # Real-time analytics logging
    redis_client.hincrby("analytics:user_count", user_id, 1)
    redis_client.hincrby("analytics:total_queries", "count", 1)

    try:
        prompt_messages = [
            {"role": "system", "content": "You're AshaAI, an assistant that returns real job listings from HerKey and helps women explore careers. If job data is provided, format it clearly and do not ignore it. Respond using the listings only when available. Keep responses helpful and actionable for women seeking tech roles."}
        ]
        if data_response:
            prompt_messages.append({"role": "system", "content": f"Here are the job listings or data you must use to answer the next question:\n{data_response}"})
        prompt_messages.append({"role": "user", "content": translated_input})
        ai_response = client.chat.completions.create(
            model="gpt-4o",
            messages=prompt_messages,
            temperature=0.7,
            max_tokens=2048,
            top_p=1,
        )
        response_text = ai_response.choices[0].message.content
    except Exception as e:
        logging.error(f"OpenAI API error: {str(e)}")
        response_text = "I'm having trouble processing your request right now. Please try again later."

    # Translate back to original language
    if lang != 'en':
        response_text = translator.translate(response_text, src='en', dest=lang)

    redis_client.rpush(f"response:{session_id}", response_text)
    response_time = round(time.time() - start_time, 3)

    return {"response": response_text, "response_time": response_time, "language": lang}

@app.post("/feedback")
def submit_feedback(request: FeedbackRequest):
    redis_client.rpush(f"feedback:{request.session_id}", request.feedback)
    return {"message": "Feedback submitted. Thank you!"}

@app.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(user: dict = Depends(verify_token)):
    all_sessions = redis_client.keys("response:*")
    session_data = ""
    for session in all_sessions:
        responses = redis_client.lrange(session, 0, -1)
        session_data += f"<h3>{session}</h3><p>{'<br>'.join(responses)}</p><hr>"

    analytics = redis_client.hgetall("analytics:total_queries")
    user_stats = redis_client.hgetall("analytics:user_count")

    feedback_sessions = redis_client.keys("feedback:*")
    feedback_data = ""
    for fsession in feedback_sessions:
        feedbacks = redis_client.lrange(fsession, 0, -1)
        feedback_data += f"<h4>{fsession}</h4><p>{'<br>'.join(feedbacks)}</p>"

    analytics_html = f"<h2>Analytics</h2><p>Total Queries: {analytics.get('count', 0)}</p><p>Active Users: {len(user_stats)}</p>"

    html_content = f"""
    <html>
    <head><title>Admin Dashboard</title></head>
    <body>
        <h1>User Sessions and Feedback</h1>
        {analytics_html}
        <h2>Session Responses</h2>
        {session_data if session_data else "<p>No session data available.</p>"}
        <h2>Feedback</h2>
        {feedback_data if feedback_data else "<p>No feedback submitted.</p>"}
        <a href='/admin/export' download>Export CSV</a>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/admin/export")
def export_data(user: dict = Depends(verify_token)):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Session ID", "Response"])
    
    all_sessions = redis_client.keys("response:*")
    for session in all_sessions:
        responses = redis_client.lrange(session, 0, -1)
        for res in responses:
            writer.writerow([session, res])

    output.seek(0)
    return HTMLResponse(content=output.read(), media_type="text/csv")

@app.get("/health")
def health_check():
    return {"status": "running"}



import difflib


def detect_bias(text):
    biased_keywords = [
        "only men", "women can't", "not for girls", "girls are bad at",
        "not suitable for women", "too hard for women", "females shouldn't",
        "men are better", "girls can't", "for boys only", "just for guys",
        "women are weak", "girls must not", "men only", "not for females",
        "no girls allowed"
    ]
    
    normalized_text = text.lower()
    found_biases = []

    for phrase in biased_keywords:
        if phrase in normalized_text:
            found_biases.append(phrase)
        elif difflib.SequenceMatcher(None, phrase, normalized_text).ratio() > 0.75:
            found_biases.append(phrase)

    if found_biases:
        # Highlight all biased phrases in the text
        highlighted_text = text
        for phrase in found_biases:
            pattern = re.compile(re.escape(phrase), re.IGNORECASE)
            highlighted_text = pattern.sub(f"<span style='color:red'>{phrase}</span>", highlighted_text)
        return True, highlighted_text

    return False, text

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)