import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeRaw from 'rehype-raw';

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [darkMode, setDarkMode] = useState(true);
  const messagesEndRef = useRef(null);
  const [isBotTyping, setIsBotTyping] = useState(false);
  const [botResponse, setBotResponse] = useState("");  // Original response
  const [displayedMessage, setDisplayedMessage] = useState("");
  const token = process.env.REACT_APP_ASHA_TOKEN;
  const backednUrl = process.env.REACT_APP_BACKEND_URL;
  const session_id = sessionStorage.getItem('session_id')
  sessionStorage.setItem('session_id', session_id);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const typeText = (fullText) => {
    let index = 0;
    setDisplayedMessage(fullText.charAt(0)); // Set the first character immediately
  
    const interval = setInterval(() => {
      setDisplayedMessage((prev) => prev + fullText.charAt(index));
      index++;
  
      if (index >= fullText.length) {
        clearInterval(interval);
      }
    }, 5); // Adjust typing speed here (ms per character)
    return () => clearInterval(interval);
  };

useEffect(scrollToBottom, [messages]);

  useEffect(() => {
    const handleResize = () => {
      scrollToBottom();
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);
  useEffect(() => {
    const greeting = {
      sender: 'bot',
      text: "👋 Hi! I’m Asha AI. Ask me about jobs, events, or mentorship opportunities!"
    };
    setMessages([greeting]);
    setBotResponse(greeting.text);
  }, []);

  const sendMessage = async () => {
    if (!input.trim()) return;

    const userMessage = { sender: 'user', text: input };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsBotTyping(true); // Show dots when bot is typing

    try {
      const myHeaders = new Headers();
      myHeaders.append("accept", "application/json");
      myHeaders.append("Authorization", `Bearer ${token}`);
      myHeaders.append("Content-Type", "application/json");
      
      const raw = JSON.stringify({
      "user_input": input,
      "session_id": session_id,
      "user_id": "admin"
      });
    
      const requestOptions = {
        method: "POST",
        headers: myHeaders,
        body: raw,
        redirect: "follow",
    };
  
    const res = await fetch(backednUrl, requestOptions).then(result => {return result.json()});

    const data = res;
    const botMessage = { sender: 'bot', text: data.response || 'Something went wrong. Please try again after some time.' };
    console.log("🤖 Bot response:", data.response);
    if (!data.response) {
      alert("No response from bot. Check your backend.");
    }
    setBotResponse(botMessage.text); // Store the original response
    setMessages(prev => [...prev, botMessage]);
    } catch (err) {
      console.error('Error:', err);
    } finally {
      setIsBotTyping(false); // 👈 Bot finishes "typing"
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') sendMessage();
  };

  useEffect(() => {
    if (botResponse) {
      typeText(botResponse);
    }
  }, [botResponse]);

  const themeStyles = darkMode ? darkTheme : lightTheme;

  return (
    <div style={{ ...styles.container, ...themeStyles.container }}>
      <div style={styles.headerBar}>
        <h1 style={themeStyles.header}>Asha AI Chat</h1>
        <button style={themeStyles.toggleButton} onClick={() => setDarkMode(!darkMode)}>
          {darkMode ? '☀️ Light Mode' : '🌙 Dark Mode'}
        </button>
      </div>

      <div style={{ ...styles.chatBox, ...themeStyles.chatBox }} className="chat-box">
        {messages.map((msg, idx) => (
          <div
            key={idx}
            style={{
              ...styles.message,
              alignSelf: msg.sender === 'user' ? 'flex-end' : 'flex-start',
              backgroundColor: msg.sender === 'user'
                ? themeStyles.userMessage
                : themeStyles.botMessage,
              color: themeStyles.messageText,
            }}
          >
            {msg.sender === "bot" && idx === messages.length - 1 ? (
              <ReactMarkdown
              rehypePlugins={[rehypeRaw]} // 👈 enable inline HTML
              components={{
                a: ({ node, ...props }) => (
                  <a {...props} target="_blank" rel="noopener noreferrer" style={{ color: 'cyan' }} />
                ),
              }}
              >
                {displayedMessage}
              </ReactMarkdown>
            ) : (
              <ReactMarkdown
              rehypePlugins={[rehypeRaw]}
              components={{
                a: ({ node, ...props }) => (
                  <a {...props} target="_blank" rel="noopener noreferrer" style={{ color: 'cyan' }} />
                ),
              }}
              >
                {msg.text}
              </ReactMarkdown>
            )}
          </div>
        ))}
        {isBotTyping && (
          <div className="typing-indicator">
            <span className="typing-dot" />
            <span className="typing-dot" />
            <span className="typing-dot" />
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <div className="input-area" style={styles.inputArea}>
        <input
          style={{ ...styles.input, ...themeStyles.input }}
          placeholder="Ask me about jobs, events, mentorship.."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyPress}
        />
        <button style={{ ...styles.button, ...themeStyles.button }} onClick={sendMessage}>
          Send
        </button>
      </div>
      <div style={{ textAlign: 'center', fontSize: '12px', color: '#999', marginTop: '10px' }}>
        AshaAI is experimental and might generate incorrect responses.
      </div>
    </div>
  );
}

const darkTheme = {
  container: {
    backgroundColor: '#0d0d0d',
    color: '#f1f1f1',
  },
  header: {
    color: '#f1f1f1',
  },
  chatBox: {
    backgroundColor: '#1a1a1a',
  },
  input: {
    backgroundColor: '#222',
    color: '#f1f1f1',
  },
  button: {
    background: 'linear-gradient(135deg, #1e90ff, #00bfff)',
    color: 'white',
  },
  toggleButton: {
    background: 'linear-gradient(135deg, #ffcc70, #ff8177)',
    color: '#111',
    border: 'none',
    padding: '8px 14px',
    borderRadius: '12px',
    cursor: 'pointer',
    fontWeight: '600',
    transition: 'all 0.2s ease',
  },
  userMessage: '#007bff',
  botMessage: '#333333',
  messageText: 'white',
  startMessage: '#333333',
};

const lightTheme = {
  container: {
    backgroundColor: '#f9f9f9',
    color: '#111',
  },
  header: {
    color: '#111',
  },
  chatBox: {
    backgroundColor: '#ffffff',
  },
  input: {
    backgroundColor: '#fff',
    color: '#111',
  },
  button: {
    background: 'linear-gradient(135deg, #4facfe, #00f2fe)',
    color: 'white',
  },
  toggleButton: {
    background: 'linear-gradient(135deg, #f6d365, #fda085)',
    color: '#111',
    border: 'none',
    padding: '8px 14px',
    borderRadius: '12px',
    cursor: 'pointer',
    fontWeight: '600',
    transition: 'all 0.2s ease',
  },
  userMessage: '#eeeeee',
  botMessage: '#ffffff',
  messageText: '#111',
};

const styles = {
  container: {
    height: '100dvh',
    padding: '10px',
    boxSizing: 'border-box',
    display: 'flex',
    flexDirection: 'column',
    fontFamily: 'Inter, sans-serif',
  },
  headerBar: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    flexWrap: 'wrap',
    marginBottom: '10px',
    paddingBottom: '8px',
    borderBottom: '1px solid rgba(255,255,255,0.1)',
  },
  chatBox: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    overflowY: 'auto',
    padding: '20px',
    borderRadius: '20px',
    marginBottom: '20px',
    backdropFilter: 'blur(4px)',
    boxShadow: 'inset 0 0 10px rgba(0,0,0,0.2)',
  },
  message: {
    padding: '10px 14px',
    margin: '6px 0',
    borderRadius: '14px',
    maxWidth: '90%',
    lineHeight: '1.5',
    fontSize: '15px',
    boxShadow: '0 2px 6px rgba(0,0,0,0.15)',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
  },
  inputArea: {
    position: 'relative',
    display: 'flex',
    gap: '8px',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.05)',
    padding: '8px 12px',
    borderRadius: '12px',
    boxShadow: '0 4px 20px rgba(0,0,0,0.2)',
  },
  input: {
    flex: 1,
    padding: '10px',
    fontSize: '14px',
    borderRadius: '10px',
    border: 'none',
    outline: 'none',
  },
  button: {
    padding: '10px 18px',
    fontSize: '14px',
    borderRadius: '10px',
    fontWeight: '600',
    border: 'none',
    cursor: 'pointer',
    transition: 'all 0.2s ease-in-out',
  },
};

export default App;