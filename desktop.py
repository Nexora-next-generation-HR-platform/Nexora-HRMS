import threading
import webview
from app import app  # imports your Flask app object

def start_flask():
    app.run(port=5000, debug=False, use_reloader=False)

if __name__ == '__main__':
    threading.Thread(target=start_flask, daemon=True).start()
    webview.create_window(
        'Nexora HRMS',
        'http://127.0.0.1:5000',
        width=1280,
        height=800,
        min_size=(1000, 700)
    )
    webview.start()
