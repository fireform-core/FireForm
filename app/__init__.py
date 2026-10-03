"""FireForm backend application package."""

import os

# Force CPU before any service module imports torch / rfdetr. Prevents PyTorch
# from probing for NVIDIA drivers on Mac Silicon and inside Docker. Runs here so
# it is guaranteed to execute before `app.main` imports the service layer.
os.environ["CUDA_VISIBLE_DEVICES"] = ""
