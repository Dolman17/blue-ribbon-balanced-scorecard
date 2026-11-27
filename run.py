from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=__import__("os").environ.get("BSC_DEV_MODE") == "1")
