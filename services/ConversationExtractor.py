import re
import json
import os
import datetime
from collections import defaultdict

class ConversationExtractor:
    """
    Extracts and stores important information from conversations.
    This class can identify key details like names, dates, phone numbers,
    and other structured information from conversation text.
    """
    
    def __init__(self, storage_file="conversation_data.json"):
        """
        Initialize the ConversationExtractor.
        
        Args:
            storage_file (str): Filepath to store extracted information
        """
        self.storage_file = storage_file
        self.current_session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.extracted_data = self._load_existing_data()
        
        # Initialize patterns for information extraction
        self.patterns = {
            "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            "phone": r'\b(\+\d{1,2}\s?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b',
            "date": r'\b(0?[1-9]|1[0-2])[\/\-](0?[1-9]|[12]\d|3[01])[\/\-](19|20)?\d{2}\b',
            "time": r'\b([01]?[0-9]|2[0-3]):([0-5][0-9])(:[0-5][0-9])?\s*(am|pm|AM|PM)?\b',
            "url": r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[/\w\.-]*\??[/\w\.-=&%]*',
            "name": r'(?:Mr\.|Mrs\.|Ms\.|Dr\.|Prof\.)\s[A-Z][a-z]+(?:\s[A-Z][a-z]+)*'
        }
        
        # Define keywords for important information
        self.important_keywords = [
            "appointment", "schedule", "meeting", "remember", "important", 
            "deadline", "contact", "follow up", "call back", "priority",
            "urgent", "critical", "key point", "action item"
        ]
    
    def _load_existing_data(self):
        """Load existing data from storage file if it exists"""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                return {"sessions": {}}
        return {"sessions": {}}
    
    def _save_data(self):
        """Save extracted data to storage file"""
        with open(self.storage_file, 'w') as f:
            json.dump(self.extracted_data, f, indent=2)
    
    def extract_information(self, user_text, assistant_text):
        """
        Extract important information from a conversation turn.
        
        Args:
            user_text (str): Text from the user
            assistant_text (str): Text from the assistant
            
        Returns:
            dict: Dictionary of extracted information
        """
        # Combine texts for analysis
        combined_text = f"User: {user_text}\nAssistant: {assistant_text}"
        
        # Initialize extracted info
        extracted_info = defaultdict(list)
        
        # Extract structured information using patterns
        for info_type, pattern in self.patterns.items():
            matches = re.findall(pattern, combined_text)
            if matches:
                extracted_info[info_type].extend(matches)
        
        # Look for sentences containing important keywords
        sentences = re.split(r'(?<=[.!?])\s+', combined_text)
        for sentence in sentences:
            if any(keyword in sentence.lower() for keyword in self.important_keywords):
                extracted_info["important_points"].append(sentence.strip())
        
        # Store information with timestamp
        timestamp = datetime.datetime.now().isoformat()
        
        if not self.current_session_id in self.extracted_data["sessions"]:
            self.extracted_data["sessions"][self.current_session_id] = []
        
        conversation_entry = {
            "timestamp": timestamp,
            "user_text": user_text,
            "assistant_text": assistant_text,
            "extracted_info": dict(extracted_info)
        }
        
        self.extracted_data["sessions"][self.current_session_id].append(conversation_entry)
        self._save_data()
        
        return dict(extracted_info)
    
    def get_session_summary(self, session_id=None):
        """
        Generate a summary of extracted information for a session.
        
        Args:
            session_id (str, optional): Session ID to summarize. Defaults to current session.
            
        Returns:
            dict: Summary of extracted information
        """
        session_id = session_id or self.current_session_id
        
        if session_id not in self.extracted_data["sessions"]:
            return {"error": "Session not found"}
        
        session_data = self.extracted_data["sessions"][session_id]
        
        # Aggregate all extracted information
        summary = defaultdict(list)
        for entry in session_data:
            for info_type, items in entry["extracted_info"].items():
                summary[info_type].extend(items)
        
        # Remove duplicates while preserving order
        for info_type in summary:
            seen = set()
            summary[info_type] = [x for x in summary[info_type] 
                                 if not (x in seen or seen.add(x))]
        
        return dict(summary)
    
    def search_conversations(self, query):
        """
        Search for conversations containing the query.
        
        Args:
            query (str): Search query
            
        Returns:
            list: List of matching conversation entries
        """
        results = []
        
        for session_id, entries in self.extracted_data["sessions"].items():
            for entry in entries:
                if (query.lower() in entry["user_text"].lower() or 
                    query.lower() in entry["assistant_text"].lower()):
                    results.append({
                        "session_id": session_id,
                        "timestamp": entry["timestamp"],
                        "conversation": f"User: {entry['user_text']}\nAssistant: {entry['assistant_text']}",
                        "extracted_info": entry["extracted_info"]
                    })
        
        return results
    
    def start_new_session(self):
        """Start a new conversation session with a unique ID"""
        self.current_session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.current_session_id