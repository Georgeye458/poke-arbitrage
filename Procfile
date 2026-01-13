web: gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT
worker: celery -A app.tasks.celery_app worker --loglevel=info
beat: celery -A app.tasks.celery_app beat --loglevel=info
release: alembic upgrade head
