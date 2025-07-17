import os
import logging
from dotenv import load_dotenv
# Import from langchain_community as recommended
from langchain_community.chat_models import ChatOpenAI
from langchain.agents import initialize_agent, Tool, AgentType
from langchain.memory import ConversationBufferMemory
from langchain.prompts import MessagesPlaceholder # Needed for conversational agent prompt
from services.GoogleCalendar import GoogleCalendarService # Import your Calendar service

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Initialize Google Calendar Service
# Note: This will be initialized once when the script is first imported.
# Ensure it handles potential initialization errors gracefully.
calendar_service = GoogleCalendarService()

# Define the tool for booking appointments
# The input to this tool will be a string from the LLM
def book_appointment_tool(info_string: str) -> str:
    """
    Books a real estate appointment using extracted information.
    Input should be a string containing appointment details (name, email, phone, address, date, time).
    The format of the string should be parsable by GoogleCalendarService.create_appointment_from_string.
    """
    logger.info(f"Attempting to book appointment with info: {info_string}")
    if calendar_service.service is None:
        logger.error("Google Calendar service is not initialized. Cannot book appointment.")
        return "Error: Calendar service not available."

    try:
        # Call the method in your GoogleCalendarService to handle parsing and booking
        calendar_link = calendar_service.create_appointment_from_string(info_string)
        if calendar_link:
            logger.info(f"Appointment booked successfully. Link: {calendar_link}")
            return f"Appointment booked successfully. Calendar link: {calendar_link}"
        else:
            logger.error("Appointment booking failed via GoogleCalendarService.")
            return "Appointment booking failed."
    except Exception as e:
        logger.error(f"Error calling Google Calendar tool: {e}")
        return f"An error occurred during appointment booking: {e}"


tools = [
    Tool(
        name="BookAppointment",
        func=book_appointment_tool,
        description="Books a real estate appointment. Input should be a string containing appointment details like name, email, phone, address, date (YYYY-MM-DD), and time (HH:MM). Example input: '{{\"name\": \"John Doe\", \"email\": \"john@example.com\", \"phone\": \"555-1234\", \"address\": \"123 Main St\", \"date\": \"2025-07-10\", \"time\": \"14:30\"}}'"
    )
]

# Define the system prompt for the agent
system_message = (
    "You are a friendly and professional real estate appointment assistant. "
    "Your job is to: "
    "- Greet the lead and introduce yourself. "
    "- Ask for their name and what kind of property they want to view. "
    "- Collect their email, phone number, and preferred appointment date (YYYY-MM-DD) and time (HH:MM). "
    "- Confirm the details back to them. "
    "- Once you have ALL required information (name, email, phone, address, date, time) AND the user confirms they want to book, use the BookAppointment tool. "
    "- The input to the BookAppointment tool MUST be a JSON string containing the collected details. Example: '{{\"name\": \"John Doe\", \"email\": \"john@example.com\", \"phone\": \"555-1234\", \"address\": \"123 Main St\", \"date\": \"2025-07-10\", \"time\": \"14:30\"}}' "
    "- After using the tool, inform the user if the booking was successful and politely end the call. "
    "- If the user declines booking, thank them and end the call politely. "
    "Always keep the conversation natural and helpful. Do NOT book the appointment until the user explicitly confirms."
)

# Initialize the LLM
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    logger.error("OPENAI_API_KEY not found in environment variables. LangChain agent will not work.")
    llm = None # Or raise an error
else:
    llm = ChatOpenAI(temperature=0, openai_api_key=openai_api_key, model="gpt-4o") # Using gpt-4o for better reasoning/tool use

# Initialize memory
memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

# Initialize the agent
if llm:
    agent_chain = initialize_agent(
        tools,
        llm,
        agent=AgentType.CHAT_CONVERSATIONAL_REACT_DESCRIPTION,
        memory=memory,
        verbose=True, # Set to True to see agent's thought process
        agent_kwargs={
            "system_message": system_message,
            "extra_prompt_messages": [MessagesPlaceholder(variable_name="chat_history")],
        }
    )
    logger.info("LangChain agent initialized.")
else:
    agent_chain = None
    logger.error("LangChain agent not initialized due to missing OpenAI API key.")


def run_agent(user_input: str) -> str:
    """
    Runs the LangChain agent with user input.
    Returns the agent's response.
    """
    if agent_chain is None:
        return "Sorry, the AI agent is not available."
    try:
        # The agent_chain.run method handles the conversation and tool calls
        response = agent_chain.run(input=user_input)
        return response
    except Exception as e:
        logger.error(f"Error running LangChain agent: {e}")
        return "Sorry, I encountered an error. Could you please try again?"
