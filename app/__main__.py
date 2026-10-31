import uvicorn

from .config import HOST, PORT

if __name__ == "__main__":
    print(f"Digital Architect running at http://{HOST}:{PORT}")
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False)
