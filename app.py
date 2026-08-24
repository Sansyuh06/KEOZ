"""Hugging Face Spaces Gradio/FastAPI entrypoint for KEOZ."""

import gradio as gr
from keoz.server.app import app

# Mount Gradio Blocks with full embedded KEOZ Command Center
with gr.Blocks(title="KEOZ — Merchant Command Center", theme=gr.themes.Base()) as demo:
    gr.HTML("""
    <iframe src="/" style="width: 100%; height: 96vh; border: none; border-radius: 12px; background: #070a12;"></iframe>
    """)

# Mount gradio app
app = gr.mount_gradio_app(app, demo, path="/gradio")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
