import uvicorn
import logging
import os
from dotenv import load_dotenv

# Load environment variables at the entry point
load_dotenv()

# Set up basic logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Starting FastAPI server...")
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)