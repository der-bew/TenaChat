from supabase import create_client, Client
from app.config import SUPABASE_KEY, SUPABASE_URL
import logging

logger = logging.getLogger(__name__)

def get_supabase_client() -> Client:
    """Initialize and return Supabase client with validation."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("Supabase URL and KEY must be configured")
    
    try:
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase client initialized successfully")
        return client
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
        raise

# Initialize the global client
supabase: Client = get_supabase_client()
