import os
import openai
from dotenv import load_dotenv

class TextGenerator:
    def __init__(self):
        load_dotenv()
        openai.api_key = os.getenv("OPENAI_API_KEY")
        self.conversation_history = []
    
    def generate_response(self, user_input):
        """Generates a response based on user input using OpenAI's language model"""
        try:
            # Add user input to conversation history
            self.conversation_history.append({"role": "user", "content": user_input})
            
            # Get response from OpenAI API
            response = openai.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": """
                     You are a helpful, friendly, and conversational AI assistant and act as a resentionist. 
                     Respond in a natural, engaging way as if you were talking to a client, 
                     make it simple, and specific. do not talk in markdown and bullets, do it like a
                     conversational, also if possible do not cross more then 3 short"""},
                    *self.conversation_history
                ]
            )
            
            # Extract assistant's reply
            assistant_reply = response.choices[0].message.content.strip()
            
            # Add assistant's reply to conversation history
            self.conversation_history.append({"role": "assistant", "content": assistant_reply})
            
            return assistant_reply
        except Exception as e:
            print(f"Error generating response: {e}")
            return "I'm sorry, I encountered an error while processing your request."
    
    def clear_conversation(self):
        """Clears the conversation history"""
        self.conversation_history = []