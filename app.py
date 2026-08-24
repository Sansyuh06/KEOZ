"""Hugging Face Spaces entrypoint for KEOZ."""

import uvicorn
from keoz.server.app import app

# Standalone execution for Hugging Face Spaces (Port 7860)
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
