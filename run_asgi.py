import os

import uvicorn


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "djangoproject.settings")
    uvicorn.run(
        "djangoproject.asgi:application",
        host=os.getenv("UVICORN_HOST", "127.0.0.1"),
        port=int(os.getenv("UVICORN_PORT", "8000")),
        reload=os.getenv("UVICORN_RELOAD", "").strip().lower() in {"1", "true", "yes", "on"},
        proxy_headers=True,
        forwarded_allow_ips=os.getenv("UVICORN_FORWARDED_ALLOW_IPS", "127.0.0.1"),
    )


if __name__ == "__main__":
    main()
