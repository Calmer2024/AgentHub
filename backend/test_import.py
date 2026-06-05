import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("Testing imports...")

try:
    from app.config import settings
    print(f"✅ config OK, deepseek key present: {bool(settings.deepseek_api_key)}")
except Exception as e:
    print(f"❌ config FAILED: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

try:
    from app.database import Base, engine
    print("✅ database OK")
except Exception as e:
    print(f"❌ database FAILED: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

try:
    from app.system_models import DeepSeekSystemAdapter
    print("✅ DeepSeek system adapter OK")
except Exception as e:
    print(f"❌ DeepSeek system adapter FAILED: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

try:
    from app.main import app
    print("✅ FastAPI app OK")
except Exception as e:
    print(f"❌ FastAPI app FAILED: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
