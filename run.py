import uvicorn
import os
import sys

if __name__ == "__main__":
    # Ensure current directory is in PYTHONPATH
    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
    from backend.app.config import HOST, PORT, DEBUG
    
    print("=" * 70)
    print("🚀 RazorBack.ai — Autonomous Chargeback Evidence Responder")
    print(f"📡 Serving Ops Dashboard at: http://{HOST}:{PORT}")
    print("🔒 Razorpay Webhook Endpoint: /api/webhooks/razorpay")
    print("=" * 70)
    
    uvicorn.run("backend.app.main:app", host=HOST, port=PORT, reload=DEBUG)
