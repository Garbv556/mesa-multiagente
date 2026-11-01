"""
Ponto de entrada principal para a aplicação na nuvem.
"""

import os
import uvicorn
from src.dashboard.app import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
