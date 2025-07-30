# Asha AI Chatbot

Asha AI is an intelligent chatbot designed to assist users with information about **jobs, mentorships, and events** tailored for women in tech. It leverages FastAPI for the backend and React for the frontend, with animated UI and real-time responses.

## Features

- Conversational AI powered by custom logic
- Dynamic job search using HerKey APIs
- Mentorship & event listings with clickable details
- Typing animation and loading indicator
- Markdown support for links
- Mobile responsive with dark/light mode toggle
- Fuzzy matching and typo detection
- Bias detector for prompt moderation

## Tech Stack

- **Frontend**: React.js
- **Backend**: FastAPI (Python)
- **Styling**: CSS-in-JS (custom styles)
- **APIs Used**:
  - HerKey Jobs API
  - HerKey Mentorship & Events API

## Getting Started

### Prerequisites

- Node.js & npm
- Python 3.9+
- `pip` and `venv` or `virtualenv`

### Backend Setup

```bash
cd AshaAI
python -m venv venv
source venv/bin/activate   # or .\venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn main:app --reload
```

### Frontend Setup

```bash
cd asha-chatbot
npm install
npm start
```

### Environment Variables

Create a `.env` file in the `asha-chatbot/` folder and add:

```
REACT_APP_ASHA_TOKEN=your_jwt_token_here
REACT_APP_BACKEND_URL=
```

## Folder Structure

```
AshaAI/
│
├── main.py                  # FastAPI backend
├── job_title_dataset.py     # List of job keywords
├── requirements.txt         # Python dependencies
├── asha-chatbot/            # React frontend
│   ├── src/
│   │   ├── App.js
│   │   └── ...
│   ├── .env
│   ├── package.json
│   └── ...
```

## Contributing

Feel free to fork the repo and submit pull requests! Contributions are welcome.

## License

MIT License — feel free to use, share, and modify.